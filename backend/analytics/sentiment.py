"""Keyword-based sentiment & escalation scoring."""

NEGATIVE = {
    "urgent", "asap", "critical", "emergency", "immediately",
    "failed", "failure", "error", "blocked", "blocker",
    "risk", "issue", "problem", "concern", "warning",
    "delay", "overdue", "deadline missed", "escalate", "escalation",
    "unacceptable", "disappointed", "frustrated", "difficult",
    "loss", "decline", "drop", "decrease", "negative",
    "wrong", "incorrect", "mistake", "bug", "crash", "down",
    "breach", "violation", "complaint", "refund", "churn",
    "resign", "layoff", "cut", "reject", "rejected",
}

POSITIVE = {
    "success", "successful", "great", "excellent", "amazing",
    "approved", "completed", "done", "achieved", "accomplished",
    "happy", "good", "positive", "improvement", "improved",
    "growth", "increase", "profit", "win", "winning",
    "congratulations", "well done", "fantastic", "perfect",
    "opportunity", "progress", "milestone", "launch", "delivered",
    "signed", "closed", "promoted", "hired", "onboard",
    "partnership", "deal", "revenue", "record", "ahead",
}

ESCALATION = {
    "urgent", "asap", "escalate", "escalation", "critical",
    "emergency", "immediately", "action required", "follow up",
    "overdue", "unacceptable", "please help", "deadline",
    "last chance", "final notice", "no response", "still waiting",
    "not resolved", "weeks ago", "days ago", "ignored",
}


def score_text(text: str) -> str:
    """Returns 'positive', 'negative', or 'neutral'."""
    lower = text.lower()
    neg = sum(1 for w in NEGATIVE if w in lower)
    pos = sum(1 for w in POSITIVE if w in lower)
    if neg > pos:
        return "negative"
    if pos > neg:
        return "positive"
    return "neutral"


def has_escalation(text: str) -> bool:
    lower = text.lower()
    return any(w in lower for w in ESCALATION)


def extract_keywords(texts: list[str], top_n: int = 10) -> list[dict]:
    """Return top N meaningful words by frequency."""
    STOPWORDS = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
        "for", "of", "with", "is", "it", "this", "that", "be", "are",
        "was", "were", "have", "has", "had", "do", "does", "did",
        "will", "would", "could", "should", "may", "might", "can",
        "not", "no", "from", "by", "as", "we", "you", "i", "my",
        "your", "our", "their", "its", "re", "hi", "hello", "thanks",
        "thank", "please", "let", "know", "get", "just", "also",
        "been", "about", "up", "out", "if", "so", "all", "more",
    }
    import re
    from collections import Counter
    words = []
    for text in texts:
        tokens = re.findall(r"\b[a-zA-Z]{4,}\b", text.lower())
        words.extend(t for t in tokens if t not in STOPWORDS)
    counts = Counter(words).most_common(top_n)
    return [{"word": w, "count": c} for w, c in counts]
