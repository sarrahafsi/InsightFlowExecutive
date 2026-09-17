"""
Vérification d'existence d'une adresse email par sondage SMTP (RCPT TO),
sans envoyer de message. Utilisée à l'inscription pour rejeter les emails
manifestement inexistants.

Fiabilité : beaucoup de fournisseurs (Gmail notamment) répondent "accepté"
à toute adresse par sécurité (anti-harvesting), ou bloquent/greylistent les
connexions de sondage. On ne peut donc PAS traiter un résultat ambigu comme
un rejet — seul un rejet SMTP explicite (550/551/553/554) ou l'absence totale
de serveur mail pour le domaine sont traités comme invalides. Toute erreur
réseau/timeout est fail-open (email considéré valide) pour ne jamais bloquer
un utilisateur légitime à cause d'un problème réseau transitoire.
"""
import logging
import smtplib
import socket

import dns.resolver

logger = logging.getLogger(__name__)

SMTP_PROBE_TIMEOUT = 8
DEFINITIVE_REJECT_CODES = {550, 551, 553, 554}


def _resolve_mx_host(domain: str) -> str | None:
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=5)
        best = min(answers, key=lambda r: r.preference)
        return str(best.exchange).rstrip(".")
    except Exception:
        return None


def verify_email_exists(email: str) -> tuple[bool, str | None]:
    """
    Retourne (is_valid, reason_si_invalide).
    is_valid=False uniquement sur un rejet explicite (mailbox inexistante)
    ou un domaine sans serveur mail — jamais sur une simple erreur réseau.
    """
    if "@" not in email:
        return False, "Format d'email invalide."
    domain = email.rsplit("@", 1)[1].strip().lower()

    mx_host = _resolve_mx_host(domain)
    if not mx_host:
        return False, "Le domaine de cette adresse n'a pas de serveur mail valide."

    try:
        with smtplib.SMTP(timeout=SMTP_PROBE_TIMEOUT) as smtp:
            smtp.connect(mx_host, 25)
            smtp.helo("insightflow.ai")
            smtp.mail("verify@insightflow.ai")
            code, _msg = smtp.rcpt(email)
            if code in DEFINITIVE_REJECT_CODES:
                return False, "Cette adresse email n'existe pas."
            return True, None
    except (socket.timeout, ConnectionRefusedError, smtplib.SMTPException, OSError) as e:
        logger.info("[email-verify] Sondage SMTP inconclusif pour %s (%s) — email accepté par défaut.", email, e)
        return True, None
