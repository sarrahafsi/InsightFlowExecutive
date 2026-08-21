"""
Seed script — insère 13 jours normaux + 1 jour spike Gmail pour tester l'anomaly detector.
Run depuis le dossier backend/ : python seed_gmail_anomaly.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timedelta
from core.database import SessionLocal
from core.models import MessageRaw, Organisation

db = SessionLocal()

# Utilise l'org_id passé en argument ou cherche par nom d'utilisateur
TARGET_EMAIL = "sarrahafsi@gmail.com"
from core.models import User
user = db.query(User).filter(User.email == TARGET_EMAIL).first()
if user and user.org_id:
    org_id = user.org_id
    print(f"Org de l'utilisateur {TARGET_EMAIL} : {org_id}")
else:
    org = db.query(Organisation).first()
    if not org:
        print("Aucune organisation trouvée en base.")
        db.close()
        sys.exit(1)
    org_id = org.id
    print(f"Org fallback : {org.name} ({org_id})")

# Supprime tous les seeds précédents (toutes orgs) pour éviter les doublons de PK
deleted = db.query(MessageRaw).filter(
    MessageRaw.author.in_(["alice@company.com", "bob@company.com"]),
).delete(synchronize_session=False)
if deleted:
    print(f"  → {deleted} anciens seeds supprimés")

# 13 jours normaux : 5 emails/jour, heure de bureau, faible burnout
for day_offset in range(1, 14):
    ts = datetime.utcnow() - timedelta(days=day_offset)
    for i in range(5):
        db.add(MessageRaw(
            id=f"seed-normal-gmail-{day_offset}-{i}",
            source="gmail",
            org_id=org_id,
            timestamp=ts.replace(hour=10, minute=i * 5, second=0, microsecond=0),
            author="alice@company.com",
            title=f"Rapport journalier #{i}",
            business_label="General",
            burnout_score=0.1,
            hour_sent=10,
            is_after_hours=False,
        ))

# Aujourd'hui : spike — 20 emails, nuit, burnout élevé, label Urgent
today = datetime.utcnow()
for i in range(20):
    db.add(MessageRaw(
        id=f"seed-spike-gmail-{i}",
        source="gmail",
        org_id=org_id,
        timestamp=today.replace(hour=23, minute=i, second=0, microsecond=0),
        author="bob@company.com",
        title=f"URGENT action requise #{i}",
        business_label="Urgent",
        burnout_score=0.8,
        hour_sent=23,
        is_after_hours=True,
    ))

db.commit()
db.close()
print("Seed OK — 65 messages Gmail insérés (13j × 5 normaux + 20 spike aujourd'hui)")
print("Lance maintenant : POST /api/anomaly/run")
