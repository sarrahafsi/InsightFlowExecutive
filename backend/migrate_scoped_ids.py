"""
Migration one-shot — renomme les anciens ids messages_raw (`{source}_{raw_id}`)
vers le nouveau format org-scopé (`{source}_{raw_id}_{org_id}`) introduit par
BaseConnector.scoped_id().

Sans ce script, les messages déjà synchronisés avant le fix scoped_id sont
resynchronisés sous un nouvel id → load_items() les traite comme "nouveaux"
→ doublons dans messages_raw (et dans l'index RAG ChromaDB).

Run depuis le dossier backend/ :
    python migrate_scoped_ids.py           # applique la migration
    python migrate_scoped_ids.py --dry-run # affiche ce qui serait fait, sans écrire
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import argparse
from core.database import SessionLocal
from core.models import MessageRaw, ActionItem, HumanCorrection

parser = argparse.ArgumentParser()
parser.add_argument("--dry-run", action="store_true", help="N'écrit rien, affiche juste le plan")
args = parser.parse_args()

db = SessionLocal()

rows = db.query(MessageRaw).filter(MessageRaw.org_id.isnot(None)).all()

to_migrate = [r for r in rows if not r.id.endswith(f"_{r.org_id}")]
old_ids = [r.id for r in to_migrate]  # capturé avant migration/commit (les objets sont ensuite supprimés)

print(f"{len(rows)} messages avec org_id, {len(to_migrate)} à migrer vers le format scoped_id.")

renamed = 0
merged_duplicates = 0

for row in to_migrate:
    old_id = row.id

    # Certains ids portent déjà un ancien suffixe court (org_id[:8]) posé par une
    # génération encore antérieure du code (avant le format actuel sans suffixe) —
    # on l'enlève d'abord pour ne pas empiler les suffixes.
    base_id = old_id
    short_suffix = f"_{row.org_id[:8]}"
    if base_id.endswith(short_suffix):
        base_id = base_id[: -len(short_suffix)]

    new_id = f"{base_id}_{row.org_id}"

    if new_id == old_id:
        continue

    existing_new = db.query(MessageRaw).filter(MessageRaw.id == new_id).first()

    if args.dry_run:
        action = "FUSIONNER (doublon déjà créé par un resync)" if existing_new else "RENOMMER"
        print(f"  [{action}] {old_id} -> {new_id}")
        continue

    if existing_new:
        # Le resync a déjà recréé la ligne sous le nouvel id (doublon présent) :
        # on garde la ligne neuve (déjà ré-enrichie NLP) et on supprime l'ancienne,
        # après avoir répointé les FKs qui référencent encore l'ancien id.
        db.query(ActionItem).filter(ActionItem.message_id == old_id).update(
            {"message_id": new_id}, synchronize_session=False
        )
        db.query(HumanCorrection).filter(HumanCorrection.message_id == old_id).update(
            {"message_id": new_id}, synchronize_session=False
        )
        db.delete(row)
        merged_duplicates += 1
    else:
        # Pas encore resynchronisé : simple renommage de la PK.
        # On ne peut pas juste faire row.id = new_id (les FK enfants pointent
        # encore sur old_id) donc on copie la ligne sous le nouvel id d'abord.
        new_row = MessageRaw(**{
            col.name: getattr(row, col.name)
            for col in MessageRaw.__table__.columns
            if col.name != "id"
        })
        new_row.id = new_id
        db.add(new_row)
        db.flush()

        db.query(ActionItem).filter(ActionItem.message_id == old_id).update(
            {"message_id": new_id}, synchronize_session=False
        )
        db.query(HumanCorrection).filter(HumanCorrection.message_id == old_id).update(
            {"message_id": new_id}, synchronize_session=False
        )
        db.delete(row)
        renamed += 1

    db.flush()

if args.dry_run:
    db.rollback()
    print("Dry-run — rien n'a été écrit.")
else:
    db.commit()
    print(f"OK — {renamed} messages renommés, {merged_duplicates} doublons fusionnés.")

    # Nettoyage best-effort de l'index RAG ChromaDB : les anciens ids ne
    # doivent plus servir de clé (les nouveaux seront réindexés au prochain sync).
    try:
        from intelligence.rag.embedder import get_collection
        col = get_collection()
        if old_ids:
            col.delete(ids=old_ids)
            print(f"ChromaDB — {len(old_ids)} anciens ids nettoyés de l'index.")
    except Exception as e:
        print(f"ChromaDB — nettoyage ignoré ({e}).")

db.close()
