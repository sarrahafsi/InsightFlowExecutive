"""
InsightFlow RAG — Embedder & ChromaDB Index
============================================
- Modèle : sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (multilingue FR/EN, 100% local)
- Vector store : ChromaDB persistant sur disque (backend/chroma_db/)
- Singleton : un seul client ChromaDB partagé dans le processus

API publique :
    get_collection()            → ChromaDB collection (lazy init)
    index_item(item)            → indexer un DataItem
    index_items(items)          → indexer une liste
    index_from_db(db)           → (ré)indexer tous les messages depuis PostgreSQL
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Chemins ────────────────────────────────────────────────────
BACKEND_DIR  = Path(__file__).parent.parent
CHROMA_DIR   = BACKEND_DIR / "chroma_db"
CHROMA_DIR.mkdir(exist_ok=True)

COLLECTION_NAME = "insightflow_messages"
# Multilingue (FR/EN) — all-MiniLM-L6-v2 echouait totalement (P@1=0.00) sur les
# requetes dont la langue differe de celle du document source (ex: question EN
# sur un email FR), un cas reel vu le melange de sources InsightFlow (Gmail
# souvent FR, Jira/Slack souvent EN). Voir backend/BENCHMARK_RESULTS_EMBEDDINGS.md.
EMBED_MODEL     = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# ── Singletons (lazy init) ──────────────────────────────────────
_chroma_client: Optional[object]     = None
_collection:    Optional[object]     = None
_embed_fn:      Optional[object]     = None


def _get_embed_fn():
    """Charge le modèle d'embedding une seule fois."""
    global _embed_fn
    if _embed_fn is None:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        _embed_fn = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
        logger.info("[RAG/Embedder] Modèle d'embedding chargé : %s", EMBED_MODEL) #chargement de modele
    return _embed_fn


def get_collection():
    """Retourne la collection ChromaDB (crée le client si besoin)."""
    global _chroma_client, _collection
    if _collection is None:
        import chromadb
        _chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _collection = _chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=_get_embed_fn(), 
            metadata={"hnsw:space": "cosine"},  #on compare par cosinus pour les embeddings
        )
        logger.info(
            "[RAG/Embedder] Collection '%s' prête — %d documents indexés.",
            COLLECTION_NAME, _collection.count(),
        )
    return _collection


# ── Helpers ────────────────────────────────────────────────────

def _build_document(item) -> tuple[str, dict, str]:
    """
    Construit (document_text, metadata, id) pour ChromaDB.
    On concatène titre + contenu pour un meilleur embedding.
    """
    title   = (item.title   or "").strip()
    content = (item.content or "").strip()
    text    = f"{title}\n\n{content}"[:2000]   # ChromaDB limite la taille

    # item peut etre un DataItem (timestamp: datetime) ou un EnrichedItem —
    # ce dernier stocke timestamp en str (cf. intelligence/nlp/base.py), ce
    # qui faisait planter .isoformat()/.timestamp() ci-dessous des qu'un item
    # enrichi en temps reel (load_items(run_nlp=True)) etait indexe (incident
    # "'str' object has no attribute 'isoformat'").
    ts = item.timestamp
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            ts = None

    meta = item.metadata or {}
    metadata = {
        "source":           str(item.source or ""),
        "author":           str(item.author or ""),
        "author_email":     str(meta.get("from_email") or ""),
        "timestamp":        str(ts.isoformat() if ts else ""),
        # ChromaDB >=1.0 exige un nombre pour $gte/$gt/$lt — un filtre sur le
        # "timestamp" (string ISO) plantait silencieusement et retournait 0
        # résultat (incident 03/09/2026). Champ numérique dédié pour le filtre.
        "timestamp_epoch":  ts.timestamp() if ts else 0.0,
        "title":            title[:200],
        "sentiment_label":  str(meta.get("sentiment_label") or ""),
        "emotion_label":    str(meta.get("emotion_label") or ""),
        "business_label":   str(meta.get("business_label") or ""),
        "topic":            str(meta.get("topic") or ""),
        "url":              str(item.url or ""),
        "org_id":           str(meta.get("org_id") or ""),
    }
    return text, metadata, str(item.id)


# ── API publique ───────────────────────────────────────────────

def index_item(item) -> bool:
    """Indexe ou met à jour un DataItem dans ChromaDB. Retourne True si succès."""
    try:
        text, metadata, doc_id = _build_document(item)
        if not text.strip():
            return False
        col = get_collection()
        col.upsert(documents=[text], metadatas=[metadata], ids=[doc_id])
        return True
    except Exception as e:
        logger.warning("[RAG/Embedder] index_item failed for %s: %s", getattr(item, "id", "?"), e)
        return False


def index_items(items: list) -> int:
    """Indexe une liste de DataItems. Retourne le nombre d'items indexés."""
    if not items:
        return 0

    texts, metadatas, ids = [], [], []
    for item in items:
        try:
            text, metadata, doc_id = _build_document(item)
            if text.strip():
                texts.append(text)
                metadatas.append(metadata)
                ids.append(doc_id)
        except Exception as e:
            logger.warning("[RAG/Embedder] Build failed for %s: %s", getattr(item, "id", "?"), e)

    if not texts:
        return 0

    try:
        col = get_collection()
        # Upsert par batch de 100 pour éviter les timeouts
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            col.upsert(
                documents=texts[i:i+batch_size],
                metadatas=metadatas[i:i+batch_size],
                ids=ids[i:i+batch_size],
            )
        logger.info("[RAG/Embedder] %d items indexés dans ChromaDB.", len(texts))
        return len(texts)
    except Exception as e:
        logger.error("[RAG/Embedder] Batch upsert failed: %s", e)
        return 0


def index_from_db(db, limit: int = 2000, org_id: str | None = None) -> int:
    """
    (Ré)indexe les messages depuis PostgreSQL.
    org_id=None réindexe TOUTES les organisations (usage admin/tâche planifiée) ;
    sinon réindexe uniquement les messages de l'org donnée (usage POST /api/ask/reindex).
    """
    from integrations.connectors.schemas import DataItem
    from core.models import MessageRaw

    query = db.query(MessageRaw)
    if org_id is not None:
        query = query.filter(MessageRaw.org_id == org_id)
    rows = query.order_by(MessageRaw.timestamp.desc()).limit(limit).all()

    if not rows:
        logger.info("[RAG/Embedder] Aucun message à indexer.")
        return 0

    items = []
    for r in rows:
        try:
            items.append(DataItem(
                id=r.id,
                source=r.source,
                type=r.item_type or "email",
                title=r.title or "",
                content=r.content or "",
                author=r.author or "",
                timestamp=r.timestamp,
                url=r.url,
                metadata={
                    "from_email":      r.author_email or "",
                    "sentiment_label": r.sentiment_label or "",
                    "emotion_label":   r.emotion_label  or "",
                    "topic":           r.topic          or "",
                    "business_label":  r.business_label or "",
                    "org_id":          r.org_id or "",
                },
            ))
        except Exception:
            pass

    return index_items(items)
