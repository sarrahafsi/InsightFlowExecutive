import base64
import re
from datetime import datetime, timezone
from typing import Any

from .base import BaseConnector
from .registry import ConnectorRegistry
from .schemas import DataItem, ItemType, SourceType

MOCK_EMAILS = [
    {
        "id": "msg_001",
        "subject": "Board Meeting — Agenda for April 7th",
        "from": "board@company.com",
        "from_name": "Board Secretary",
        "body": "Please find attached the agenda for the upcoming board meeting. Key items: Q1 financials, headcount review, product roadmap.",
        "date": "2026-03-31T09:00:00Z",
        "labels": ["INBOX", "IMPORTANT"],
        "thread_id": "thread_001",
    },
    {
        "id": "msg_002",
        "subject": "RE: Partnership with Acme Corp — urgent decision needed",
        "from": "cto@company.com",
        "from_name": "CTO",
        "body": "We need a decision by EOD Friday otherwise Acme will go with a competitor. My recommendation is to accept their terms.",
        "date": "2026-04-01T14:23:00Z",
        "labels": ["INBOX", "IMPORTANT", "STARRED"],
        "thread_id": "thread_002",
    },
    {
        "id": "msg_003",
        "subject": "Customer churn report — March 2026",
        "from": "analytics@company.com",
        "from_name": "Analytics Team",
        "body": "Churn rate increased to 4.2% in March, up from 2.8% in February. Main driver appears to be pricing concerns among SMB segment.",
        "date": "2026-04-01T08:00:00Z",
        "labels": ["INBOX"],
        "thread_id": "thread_003",
    },
]


@ConnectorRegistry.register(SourceType.GMAIL)
class GmailConnector(BaseConnector):
    """
    Fetches emails from Gmail via Google API.

    Config keys:
        use_mock (bool) : use mock data (default False — uses real API)

    Authentication is handled separately via /auth/gmail OAuth2 flow.
    Token is loaded from token.json (managed by api/routes/auth.py).
    """

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._service = None

    async def authenticate(self) -> None:
        if self.config.get("use_mock", False):
            self._authenticated = True
            return

        from application.routes.auth import get_gmail_credentials
        creds = get_gmail_credentials()
        if not creds or not creds.valid:
            raise RuntimeError(
                "Gmail not authenticated. Visit http://localhost:8000/auth/gmail to authorize."
            )

        from googleapiclient.discovery import build
        self._service = build("gmail", "v1", credentials=creds)
        self._authenticated = True

    async def fetch_raw(self, since: datetime) -> list[dict[str, Any]]:
        if self.config.get("use_mock", False):
            return [
                e for e in MOCK_EMAILS
                if datetime.fromisoformat(e["date"].replace("Z", "+00:00")).replace(tzinfo=None) >= since
            ]

        # Query: all inbox messages after `since`
        since_date = since.strftime("%Y/%m/%d")
        query = f"in:inbox -category:promotions -label:spam -label:junk after:{since_date}"

        response = self._service.users().messages().list(
            userId="me", q=query, maxResults=200
        ).execute()

        messages = response.get("messages", [])
        raw_items = []

        for msg_ref in messages:
            msg = self._service.users().messages().get(
                userId="me",
                id=msg_ref["id"],
                format="full",
            ).execute()
            raw_items.append(msg)

        # Filter out automated emails (newsletters, digests, notifications)
        NO_REPLY_PATTERNS = (
            "no-reply", "noreply", "do-not-reply", "donotreply",
            "notifications@", "mailer-daemon", "bounce@",
        )
        def _is_automated(msg: dict) -> bool:
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            # 1. no-reply sender
            from_raw = headers.get("From", "").lower()
            if any(p in from_raw for p in NO_REPLY_PATTERNS):
                return True
            # 2. List-Unsubscribe header → newsletter / digest / marketing
            if headers.get("List-Unsubscribe") or headers.get("List-ID"):
                return True
            return False

        return [m for m in raw_items if not _is_automated(m)]

    def normalize(self, raw: dict[str, Any]) -> DataItem:
        if self.config.get("use_mock", False):
            return self._normalize_mock(raw)
        return self._normalize_real(raw)

    # ------------------------------------------------------------------

    def _normalize_mock(self, raw: dict[str, Any]) -> DataItem:
        return DataItem(
            id=f"gmail_{raw['id']}",
            source=SourceType.GMAIL,
            type=ItemType.EMAIL,
            title=raw.get("subject", "(no subject)"),
            content=raw.get("body", ""),
            author=raw.get("from_name", raw.get("from", "unknown")),
            timestamp=datetime.fromisoformat(raw["date"].replace("Z", "+00:00")).replace(tzinfo=None),
            tags=raw.get("labels", []),
            metadata={"thread_id": raw.get("thread_id"), "from_email": raw.get("from")},
            raw=raw,
        )

    def _normalize_real(self, raw: dict[str, Any]) -> DataItem:
        headers = {h["name"]: h["value"] for h in raw.get("payload", {}).get("headers", [])}

        subject = headers.get("Subject", "(no subject)")
        from_raw = headers.get("From", "unknown")
        from_name, from_email = self._parse_from(from_raw)
        date_str = headers.get("Date", "")
        timestamp = self._parse_date(date_str)
        body = self._strip_html(self._extract_body(raw.get("payload", {})))
        labels = raw.get("labelIds", [])

        return DataItem(
            id=f"gmail_{raw['id']}",
            source=SourceType.GMAIL,
            type=ItemType.EMAIL,
            title=subject,
            content=body,
            author=from_name,
            timestamp=timestamp,
            tags=labels,
            metadata={
                "thread_id": raw.get("threadId"),
                "from_email": from_email,
                "snippet": raw.get("snippet", ""),
            },
            raw={k: v for k, v in raw.items() if k != "payload"},  # skip large payload in raw
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def send_email(self, to: str, subject: str, body: str, thread_id: str | None = None) -> str:
        """
        Envoie un email via Gmail API.
        Retourne le message_id Gmail de l'email envoyé.
        """
        import email.mime.text
        import email.mime.multipart

        msg = email.mime.multipart.MIMEMultipart()
        msg["To"]      = to
        msg["Subject"] = subject
        msg.attach(email.mime.text.MIMEText(body, "plain", "utf-8"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        payload: dict = {"raw": raw}
        if thread_id:
            payload["threadId"] = thread_id

        sent = self._service.users().messages().send(
            userId="me", body=payload
        ).execute()
        return sent.get("id", "")

    @staticmethod
    def _parse_from(from_str: str) -> tuple[str, str]:
        """Parse 'Name <email@example.com>' into (name, email)."""
        match = re.match(r"^(.*?)\s*<(.+?)>$", from_str.strip())
        if match:
            name = match.group(1).strip().strip('"')
            email = match.group(2).strip()
            return name or email, email
        return from_str, from_str

    @staticmethod
    def _parse_date(date_str: str) -> datetime:
        """Parse RFC 2822 email date header into a naive UTC datetime."""
        from email.utils import parsedate_to_datetime
        try:
            dt = parsedate_to_datetime(date_str)
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            return datetime.utcnow()

    @staticmethod
    def _strip_html(text: str) -> str:
        """Remove HTML tags, URLs, separators and collapse whitespace."""
        # 1. Supprimer les balises HTML
        text = re.sub(r'<[^>]+>', ' ', text)
        # 2. Supprimer les URLs (http/https)
        text = re.sub(r'https?://\S+', '', text)
        # 3. Supprimer les lignes de séparateurs (-----, ====)
        text = re.sub(r'[-=*]{4,}', '', text)
        # 4. Supprimer les tokens/paramètres encodés (longues chaînes sans espaces)
        text = re.sub(r'\S{80,}', '', text)
        # 5. Collapse whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    @staticmethod
    def _extract_body(payload: dict[str, Any]) -> str:
        """Recursively extract plain text body from a Gmail message payload."""
        mime_type = payload.get("mimeType", "")

        if mime_type == "text/plain":
            data = payload.get("body", {}).get("data", "")
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")

        if mime_type.startswith("multipart/"):
            for part in payload.get("parts", []):
                text = GmailConnector._extract_body(part)
                if text:
                    return text

        return payload.get("snippet", "")
