"""
InsightFlow RAG — Retriever
============================
Similarity search dans ChromaDB → retourne les top-K documents
les plus proches de la question du CEO.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from intelligence.rag.embedder import get_collection

logger = logging.getLogger(__name__)


@dataclass
class RetrievedDoc:
    id:              str
    text:            str
    score:           float          # distance cosine (0 = identique, 2 = opposé)
    source:          str
    author:          str
    author_email:    str
    timestamp:       str
    title:           str
    sentiment_label: str
    business_label:  str
    topic:           str
    url:             str


def retrieve(
    query: str,
    top_k: int = 5,
    source_filter: Optional[str] = None,
    since_date: Optional[str] = None,
) -> list[RetrievedDoc]:
    """
    Cherche les top_k messages les plus pertinents pour `query`.

    Args:
        query:         Question en langage naturel du CEO
        top_k:         Nombre de résultats à retourner
        source_filter: Filtrer par source (gmail / slack / jira) — optionnel
        since_date:    ISO date string pour filtrer les messages récents (ex: "2026-05-23")

    Returns:
        Liste de RetrievedDoc triés par pertinence (meilleur en premier)
    """
    if not query.strip():
        return []

    try:
        col = get_collection()
        if col.count() == 0:
            logger.warning("[RAG/Retriever] ChromaDB est vide — aucun document indexé.")
            return []

        kwargs: dict = {
            "query_texts": [query],
            "n_results":   min(top_k, col.count()),
            "include":     ["documents", "metadatas", "distances"],
        }

        # Build where filter (ChromaDB $and for multiple conditions)
        where_clauses = []
        if source_filter:
            where_clauses.append({"source": {"$eq": source_filter}})
        if since_date:
            where_clauses.append({"timestamp": {"$gte": since_date}})

        if len(where_clauses) == 1:
            kwargs["where"] = where_clauses[0]
        elif len(where_clauses) > 1:
            kwargs["where"] = {"$and": where_clauses}

        results = col.query(**kwargs)

        docs = []
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        ids       = results.get("ids",       [[]])[0]

        for doc_id, text, meta, dist in zip(ids, documents, metadatas, distances):
            docs.append(RetrievedDoc(
                id=doc_id,
                text=text,
                score=float(dist),
                source=meta.get("source", ""),
                author=meta.get("author", ""),
                author_email=meta.get("author_email", ""),
                timestamp=meta.get("timestamp", ""),
                title=meta.get("title", ""),
                sentiment_label=meta.get("sentiment_label", ""),
                business_label=meta.get("business_label", ""),
                topic=meta.get("topic", ""),
                url=meta.get("url", ""),
            ))

        logger.info("[RAG/Retriever] '%s' → %d résultats.", query[:60], len(docs))
        return docs

    except Exception as e:
        logger.error("[RAG/Retriever] Erreur lors de la recherche : %s", e)
        return []
