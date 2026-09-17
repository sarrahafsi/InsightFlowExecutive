"""
Envoi d'email de vérification via SMTP standard.
Générique — fonctionne avec Gmail SMTP (mot de passe d'application), SendGrid,
Mailgun ou tout autre relais SMTP configuré dans .env (SMTP_*).
"""
import html
import logging
import secrets
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

from core.config import settings

logger = logging.getLogger(__name__)

VERIFICATION_TOKEN_TTL_HOURS = 24


def generate_verification_token() -> tuple[str, datetime]:
    """Retourne (token, expires_at)."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=VERIFICATION_TOKEN_TTL_HOURS)
    return token, expires_at


def _verification_email_html(full_name: str, link: str) -> str:
    name = html.escape(full_name or "")
    safe_link = html.escape(link, quote=True)
    return f"""\
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f5f3ee;font-family:Georgia,'Times New Roman',serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f5f3ee;padding:40px 16px;">
    <tr><td align="center">
      <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px;width:100%;background:#ffffff;border-radius:20px;overflow:hidden;box-shadow:0 12px 40px rgba(13,19,33,0.12);">

        <tr><td style="height:4px;background:linear-gradient(90deg,#1d2d44,#3e5c76,#748cab);line-height:4px;font-size:4px;">&nbsp;</td></tr>

        <tr><td style="padding:40px 40px 8px;text-align:center;">
          <div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;letter-spacing:3px;text-transform:uppercase;color:#748cab;font-weight:600;">
            InsightFlow
          </div>
          <div style="font-family:Georgia,'Times New Roman',serif;font-size:22px;color:#0d1321;margin-top:2px;">
            Executive
          </div>
        </td></tr>

        <tr><td style="padding:8px 40px 0;text-align:center;">
          <div style="width:56px;height:56px;border-radius:50%;background:#1d2d44;margin:16px auto 20px;line-height:56px;font-size:22px;">
            &#9993;
          </div>
          <h1 style="font-family:Georgia,'Times New Roman',serif;font-size:20px;color:#0d1321;margin:0 0 14px;font-weight:normal;">
            Vérifiez votre adresse email
          </h1>
          <p style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.7;color:#4b5563;margin:0 0 28px;">
            Bonjour {name},<br/><br/>
            Confirmez votre adresse email pour activer votre compte InsightFlow Executive et créer votre organisation.
          </p>
        </td></tr>

        <tr><td style="padding:0 40px;text-align:center;">
          <a href="{safe_link}" style="display:inline-block;background:#1d2d44;color:#f0ebd8;text-decoration:none;font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:700;padding:14px 36px;border-radius:12px;">
            Vérifier mon email
          </a>
        </td></tr>

        <tr><td style="padding:24px 40px 8px;text-align:center;">
          <p style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#94a3b8;line-height:1.6;word-break:break-all;margin:0;">
            Si le bouton ne fonctionne pas, copiez ce lien :<br/>
            <a href="{safe_link}" style="color:#3e5c76;">{safe_link}</a>
          </p>
        </td></tr>

        <tr><td style="padding:20px 40px 32px;text-align:center;">
          <p style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#94a3b8;margin:0;">
            Ce lien expire dans {VERIFICATION_TOKEN_TTL_HOURS}h. Si vous n'êtes pas à l'origine de cette demande, ignorez cet email.
          </p>
        </td></tr>

      </table>
      <p style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#94a3b8;margin-top:20px;">
        InsightFlow Executive
      </p>
    </td></tr>
  </table>
</body>
</html>"""


def send_verification_email(to_email: str, full_name: str, token: str) -> None:
    """
    Envoie le lien de vérification. N'échoue jamais bruyamment — si le SMTP
    n'est pas configuré ou indisponible, on logue un warning pour ne pas
    bloquer l'inscription ; l'utilisateur pourra renvoyer le lien plus tard.
    """
    link = f"{settings.frontend_url}/verify-email?token={token}"

    if not settings.smtp_host or not settings.smtp_user:
        logger.warning(
            "[email] SMTP non configuré — lien de vérification pour %s : %s",
            to_email, link,
        )
        return

    msg = EmailMessage()
    msg["Subject"] = "Vérifiez votre adresse email — InsightFlow Executive"
    msg["From"] = settings.smtp_from_email or settings.smtp_user
    msg["To"] = to_email
    msg.set_content(
        f"Bonjour {full_name},\n\n"
        f"Confirmez votre adresse email pour activer votre compte InsightFlow Executive :\n\n"
        f"{link}\n\n"
        f"Ce lien expire dans {VERIFICATION_TOKEN_TTL_HOURS}h.\n\n"
        f"Si vous n'êtes pas à l'origine de cette demande, ignorez cet email."
    )
    msg.add_alternative(_verification_email_html(full_name, link), subtype="html")

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            if settings.smtp_use_tls:
                server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        logger.info("[email] Email de vérification envoyé à %s", to_email)
    except Exception as e:
        logger.warning("[email] Échec envoi email à %s : %s — lien : %s", to_email, e, link)
