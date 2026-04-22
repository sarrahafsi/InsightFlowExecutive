"""
Analytics Engine — Organizational Intelligence System
=====================================================
Uses NLP metadata from fine-tuned models (sentiment, emotion)
and Ollama business classification.

Falls back to keyword heuristics for non-enriched items.
"""

from collections import Counter, defaultdict
from datetime import datetime, timedelta

from integrations.connectors.schemas import SourceType
from core.store import ItemStore
from data.analytics.sentiment import has_escalation, extract_keywords

# ─────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────

RISK_LABELS = {"Risk", "Blocked", "Urgent", "Conflict", "Overload"}

BUSINESS_LABEL_ORDER = [
    "Blocked", "Urgent", "Risk", "Conflict", "Overload",
    "Concern", "Progress", "Neutral Update",
]

EMOTION_ORDER = ["frustration", "urgency", "concern", "satisfaction", "neutral"]

BUSINESS_LABEL_META = {
    "Blocked":        {"color": "#ef4444", "icon": "🚫", "desc": "Travail bloqué"},
    "Urgent":         {"color": "#f97316", "icon": "🚨", "desc": "Attention immédiate"},
    "Risk":           {"color": "#f59e0b", "icon": "⚠️",  "desc": "Danger projet"},
    "Conflict":       {"color": "#8b5cf6", "icon": "⚔️",  "desc": "Friction équipe"},
    "Overload":       {"color": "#ec4899", "icon": "💥", "desc": "Surcharge"},
    "Concern":        {"color": "#eab308", "icon": "🔶", "desc": "À surveiller"},
    "Progress":       {"color": "#22c55e", "icon": "✅", "desc": "Avancement positif"},
    "Neutral Update": {"color": "#94a3b8", "icon": "ℹ️",  "desc": "Information neutre"},
}

EMOTION_META = {
    "frustration":  {"color": "#ef4444", "icon": "🔥"},
    "urgency":      {"color": "#f97316", "icon": "⚡"},
    "concern":      {"color": "#eab308", "icon": "⚠️"},
    "satisfaction": {"color": "#22c55e", "icon": "✅"},
    "neutral":      {"color": "#94a3b8", "icon": "○"},
}

SEVERITY = {"Blocked": 4, "Urgent": 3, "Risk": 2, "Conflict": 2, "Overload": 1}


# ─────────────────────────────────────────────────────────
# NLP Helpers
# ─────────────────────────────────────────────────────────

def _get_sentiment(item) -> str:
    """Use fine-tuned model result if available, fallback to keywords."""
    sl = (item.metadata or {}).get("sentiment_label")
    if sl:
        return sl.upper()
    text = f"{item.title} {item.content}".lower()
    neg = sum(1 for w in {"urgent","critical","blocked","failed","error","risk","issue","problem","delay","disappointed","frustrated"} if w in text)
    pos = sum(1 for w in {"success","completed","great","excellent","approved","done","delivered","progress","milestone"} if w in text)
    if neg > pos: return "NEGATIVE"
    if pos > neg: return "POSITIVE"
    return "NEUTRAL"


def _get_business_label(item) -> str:
    """Use Ollama result if available, fallback to heuristics."""
    bl = (item.metadata or {}).get("business_label")
    if bl:
        return bl
    text = f"{item.title} {item.content}".lower()
    if any(w in text for w in ["blocked", "blocker", "waiting for approval", "cannot proceed", "depends on"]):
        return "Blocked"
    if any(w in text for w in ["urgent", "asap", "immediately", "emergency", "action required"]):
        return "Urgent"
    if any(w in text for w in ["at risk", "critical failure", "major issue", "danger", "losing"]):
        return "Risk"
    if any(w in text for w in ["conflict", "disagree", "friction", "argument"]):
        return "Conflict"
    if any(w in text for w in ["overwhelmed", "overload", "too much work", "burnout"]):
        return "Overload"
    if any(w in text for w in ["concern", "worried", "issue", "problem", "failure"]):
        return "Concern"
    if any(w in text for w in ["completed", "done", "shipped", "success", "delivered", "achieved", "milestone"]):
        return "Progress"
    return "Neutral Update"


def _has_nlp(item) -> bool:
    return bool((item.metadata or {}).get("sentiment_label"))


# ─────────────────────────────────────────────────────────
# Organizational Intelligence Layer
# ─────────────────────────────────────────────────────────

def compute_intelligence(items: list, since_days: int = 30) -> dict:
    """
    Extract all organizational intelligence signals.
    This is the core of the Business Sentiment Intelligence system.
    """
    total = max(len(items), 1)
    now = datetime.utcnow()

    business_counts: Counter = Counter()
    emotion_counts: Counter = Counter()
    topic_counts: Counter = Counter()
    burnout_scores: list = []
    after_hours_count = 0
    weekend_count = 0
    nlp_enriched = 0

    for item in items:
        m = item.metadata or {}

        business_counts[_get_business_label(item)] += 1

        el = m.get("emotion_label")
        if el:
            emotion_counts[el] += 1

        t = m.get("topic")
        if t and t != "other":
            topic_counts[t] += 1

        bs = m.get("burnout_score")
        if bs is not None:
            burnout_scores.append(float(bs))
        if m.get("is_after_hours"):
            after_hours_count += 1
        if m.get("is_weekend"):
            weekend_count += 1
        if _has_nlp(item):
            nlp_enriched += 1

    # Risk signals
    risk_count = sum(business_counts.get(l, 0) for l in RISK_LABELS)

    # At-risk messages sorted by severity
    risk_items = [i for i in items if _get_business_label(i) in RISK_LABELS]
    risk_items.sort(
        key=lambda x: SEVERITY.get(_get_business_label(x), 0),
        reverse=True,
    )

    # Risk trend (day by day)
    timeline_days = min(since_days, 30)
    risk_trend_map: dict = {}
    for d in range(timeline_days):
        day = (now - timedelta(days=timeline_days - 1 - d)).strftime("%Y-%m-%d")
        risk_trend_map[day] = 0
    for item in items:
        if _get_business_label(item) in RISK_LABELS:
            day = item.timestamp.strftime("%Y-%m-%d")
            if day in risk_trend_map:
                risk_trend_map[day] += 1

    # Climate label
    risk_rate = risk_count / total
    frustration_rate = emotion_counts.get("frustration", 0) / total
    if risk_rate > 0.25 or frustration_rate > 0.30:
        climate = "critical"
        climate_label = "Critique"
        climate_color = "#ef4444"
    elif risk_rate > 0.10 or frustration_rate > 0.15:
        climate = "tense"
        climate_label = "Tendu"
        climate_color = "#f59e0b"
    elif risk_rate > 0.05:
        climate = "moderate"
        climate_label = "Modéré"
        climate_color = "#eab308"
    else:
        climate = "healthy"
        climate_label = "Sain"
        climate_color = "#22c55e"

    return {
        "business_labels": [
            {
                "label": lbl,
                "count": business_counts.get(lbl, 0),
                "pct": round(business_counts.get(lbl, 0) / total * 100),
                "color": BUSINESS_LABEL_META[lbl]["color"],
                "icon": BUSINESS_LABEL_META[lbl]["icon"],
                "desc": BUSINESS_LABEL_META[lbl]["desc"],
            }
            for lbl in BUSINESS_LABEL_ORDER
            if business_counts.get(lbl, 0) > 0
        ],
        "emotions": [
            {
                "label": lbl,
                "count": emotion_counts.get(lbl, 0),
                "pct": round(emotion_counts.get(lbl, 0) / total * 100),
                "color": EMOTION_META.get(lbl, {}).get("color", "#94a3b8"),
                "icon": EMOTION_META.get(lbl, {}).get("icon", "○"),
            }
            for lbl in EMOTION_ORDER
            if emotion_counts.get(lbl, 0) > 0
        ],
        "topics": [
            {"label": l, "count": c}
            for l, c in topic_counts.most_common(6)
        ],
        "risk_count": risk_count,
        "risk_rate": round(risk_count / total * 100),
        "risk_trend": [{"date": d, "count": c} for d, c in risk_trend_map.items()],
        "at_risk_items": [
            {
                "id": i.id,
                "title": (i.title or "")[:80],
                "author": i.author or "",
                "timestamp": i.timestamp.isoformat(),
                "source": i.source,
                "business_label": _get_business_label(i),
                "business_reason": (i.metadata or {}).get("business_reason", ""),
                "emotion_label": (i.metadata or {}).get("emotion_label", ""),
                "burnout_score": (i.metadata or {}).get("burnout_score"),
                "is_after_hours": (i.metadata or {}).get("is_after_hours", False),
                "is_weekend": (i.metadata or {}).get("is_weekend", False),
            }
            for i in risk_items[:8]
        ],
        "burnout": {
            "after_hours_count": after_hours_count,
            "after_hours_rate": round(after_hours_count / total * 100),
            "weekend_count": weekend_count,
            "weekend_rate": round(weekend_count / total * 100),
            "high_burnout_count": sum(1 for s in burnout_scores if s >= 0.5),
            "avg_burnout_score": round(sum(burnout_scores) / len(burnout_scores), 2) if burnout_scores else 0.0,
        },
        "climate": climate,
        "climate_label": climate_label,
        "climate_color": climate_color,
        "nlp_coverage": round(nlp_enriched / total * 100),
    }


# ─────────────────────────────────────────────────────────
# Overview
# ─────────────────────────────────────────────────────────

def compute_overview(store: ItemStore, since_days: int = 30) -> dict:
    now = datetime.utcnow()
    since = now - timedelta(days=since_days)
    items = store.all(since=since, limit=10_000)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    this_week = [i for i in items if i.timestamp >= week_ago]
    last_week = [i for i in items if two_weeks_ago <= i.timestamp < week_ago]
    total = max(len(items), 1)

    by_source: dict = defaultdict(int)
    by_type: dict = defaultdict(int)
    for item in items:
        by_source[item.source] += 1
        by_type[item.type] += 1

    # Sentiment from NLP model (with fallback)
    sentiment_counts: Counter = Counter()
    for i in items:
        sentiment_counts[_get_sentiment(i)] += 1

    sentiment = {
        "positive": round(sentiment_counts["POSITIVE"] / total * 100),
        "neutral":  round(sentiment_counts["NEUTRAL"]  / total * 100),
        "negative": round(sentiment_counts["NEGATIVE"] / total * 100),
    }

    # Activity timeline
    timeline_days = min(since_days, 30)
    timeline: dict = {}
    for d in range(timeline_days):
        day = (now - timedelta(days=timeline_days - 1 - d)).strftime("%Y-%m-%d")
        timeline[day] = 0
    for item in items:
        day = item.timestamp.strftime("%Y-%m-%d")
        if day in timeline:
            timeline[day] += 1
    activity_timeline = [{"date": d, "count": c} for d, c in timeline.items()]

    # Risk index based on business labels
    risk_items_count = sum(1 for i in items if _get_business_label(i) in RISK_LABELS)
    neg_rate = sentiment_counts["NEGATIVE"] / total
    risk_rate = risk_items_count / total
    risk_index = min(100, round((neg_rate * 0.3 + risk_rate * 0.7) * 100))

    # Velocity
    tw = len(this_week)
    lw = max(len(last_week), 1)
    delta_pct = round((tw - lw) / lw * 100, 1)

    # Escalation (legacy keyword-based)
    critical_alerts = sum(1 for i in items if has_escalation(f"{i.title} {i.content}"))

    # Intelligence layer
    intelligence = compute_intelligence(items, since_days)

    return {
        "total_items": len(items),
        "connected_sources": len(by_source),
        "total_sources": 5,
        "critical_alerts": critical_alerts,
        "sentiment": sentiment,
        "by_source": dict(by_source),
        "by_type": dict(by_type),
        "activity_timeline": activity_timeline,
        "risk_index": risk_index,
        "velocity": {
            "this_week": tw,
            "last_week": len(last_week),
            "delta_pct": delta_pct,
        },
        "since_days": since_days,
        "computed_at": now.isoformat(),
        "intelligence": intelligence,
    }


# ─────────────────────────────────────────────────────────
# Gmail Detail
# ─────────────────────────────────────────────────────────

def compute_gmail(store: ItemStore, since_days: int = 30) -> dict:
    now = datetime.utcnow()
    since = now - timedelta(days=since_days)
    items = store.all(source=SourceType.GMAIL, since=since, limit=10_000)
    week_ago   = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    h48_ago = now - timedelta(hours=48)

    this_week = [i for i in items if i.timestamp >= week_ago]
    last_week = [i for i in items if two_weeks_ago <= i.timestamp < week_ago]
    lw = max(len(last_week), 1)
    total = max(len(items), 1)

    volume_delta = round((len(this_week) - lw) / lw * 100, 1)

    label_counts: dict = defaultdict(int)
    for item in items:
        for tag in item.tags:
            if tag:
                label_counts[tag] += 1

    unread_count     = label_counts.get("UNREAD", 0)
    important_count  = label_counts.get("IMPORTANT", 0)
    starred_count    = label_counts.get("STARRED", 0)

    sender_counts: dict = defaultdict(int)
    sender_emails: dict = {}
    for item in items:
        sender_counts[item.author] += 1
        sender_emails[item.author] = item.metadata.get("from_email", "") if item.metadata else ""
    top_senders = sorted(
        [{"name": k, "email": sender_emails[k], "count": v} for k, v in sender_counts.items()],
        key=lambda x: -x["count"]
    )[:8]

    domain_counts: dict = defaultdict(int)
    for item in items:
        email = (item.metadata or {}).get("from_email", "")
        if "@" in email:
            domain = email.split("@")[1].lower()
            domain_counts[domain] += 1
    domain_distribution = sorted(
        [{"domain": k, "count": v} for k, v in domain_counts.items()],
        key=lambda x: -x["count"]
    )[:8]

    thread_map: dict = defaultdict(list)
    for item in items:
        tid = (item.metadata or {}).get("thread_id", item.id)
        thread_map[tid].append(item)

    thread_lengths = [len(v) for v in thread_map.values()]
    long_threads = [
        {"subject": sorted(v, key=lambda x: x.timestamp)[0].title, "message_count": len(v)}
        for v in thread_map.values() if len(v) > 3
    ]
    avg_thread = round(sum(thread_lengths) / max(len(thread_lengths), 1), 1)
    baf_threads = [v for v in thread_map.values() if len(v) > 2]
    baf_score = round(len(baf_threads) / max(len(thread_map), 1) * 10, 1)

    escalation_items = [i for i in items if has_escalation(f"{i.title} {i.content}")]
    no_reply_48h = [i for i in items if "IMPORTANT" in i.tags and i.timestamp < h48_ago]
    unanswered_critical = [i for i in escalation_items if i.timestamp < h48_ago]

    response_times = []
    for v in thread_map.values():
        if len(v) >= 2:
            sorted_v = sorted(v, key=lambda x: x.timestamp)
            delta = (sorted_v[1].timestamp - sorted_v[0].timestamp).total_seconds() / 3600
            if 0 < delta < 168:
                response_times.append(delta)
    avg_response_hours = round(sum(response_times) / len(response_times), 1) if response_times else None

    DAY_NAMES = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    by_day_map: dict = {}
    for d in range(7):
        day_dt = (now - timedelta(days=6 - d))
        by_day_map[day_dt.strftime("%Y-%m-%d")] = 0
    for item in this_week:
        key = item.timestamp.strftime("%Y-%m-%d")
        if key in by_day_map:
            by_day_map[key] += 1
    by_day = [
        {"day": DAY_NAMES[datetime.strptime(d, "%Y-%m-%d").weekday()], "date": d, "count": c}
        for d, c in by_day_map.items()
    ]

    by_hour_map: dict = defaultdict(int)
    for item in items:
        by_hour_map[item.timestamp.hour] += 1
    by_hour = [{"hour": h, "count": by_hour_map.get(h, 0)} for h in range(24)]

    HIDDEN_LABELS = {"INBOX", "UNREAD", "CATEGORY_PROMOTIONS", "CATEGORY_UPDATES",
                     "CATEGORY_SOCIAL", "CATEGORY_FORUMS"}
    label_dist = sorted(
        [{"label": k, "count": v} for k, v in label_counts.items() if k not in HIDDEN_LABELS],
        key=lambda x: -x["count"]
    )[:6]

    keyword_freq = extract_keywords([i.content for i in items], top_n=12)

    sentiment_counts: Counter = Counter()
    for i in items:
        sentiment_counts[_get_sentiment(i)] += 1
    sentiment = {
        "positive": round(sentiment_counts["POSITIVE"] / total * 100),
        "neutral":  round(sentiment_counts["NEUTRAL"]  / total * 100),
        "negative": round(sentiment_counts["NEGATIVE"] / total * 100),
    }

    intelligence = compute_intelligence(items, since_days)

    return {
        "volume": {
            "this_week":  len(this_week),
            "last_week":  len(last_week),
            "total":      len(items),
            "delta_pct":  volume_delta,
        },
        "unread":    {"count": unread_count,    "rate": round(unread_count    / total * 100)},
        "important": {"count": important_count, "rate": round(important_count / total * 100)},
        "starred_count":      starred_count,
        "unique_senders":     len(sender_counts),
        "avg_response_hours": avg_response_hours,
        "threads": {
            "total":                len(thread_map),
            "long_count":           len(long_threads),
            "long_threads":         long_threads[:5],
            "avg_length":           avg_thread,
            "back_and_forth_score": baf_score,
        },
        "escalation": {
            "count": len(escalation_items),
            "items": [{"title": i.title, "timestamp": i.timestamp.isoformat(), "author": i.author}
                      for i in escalation_items[:5]],
        },
        "no_reply_48h": {
            "count": len(no_reply_48h),
            "items": [{"title": i.title, "timestamp": i.timestamp.isoformat()} for i in no_reply_48h[:5]],
        },
        "unanswered_critical": {
            "count": len(unanswered_critical),
            "items": [{"title": i.title, "timestamp": i.timestamp.isoformat()} for i in unanswered_critical[:5]],
        },
        "by_day":              by_day,
        "by_hour":             by_hour,
        "top_senders":         top_senders,
        "label_distribution":  label_dist,
        "domain_distribution": domain_distribution,
        "keyword_frequency":   keyword_freq,
        "sentiment":           sentiment,
        "since_days":          since_days,
        "computed_at":         now.isoformat(),
        "intelligence":        intelligence,
    }


# ─────────────────────────────────────────────────────────
# Jira Detail
# ─────────────────────────────────────────────────────────

def compute_jira(store: ItemStore, since_days: int = 30) -> dict:
    now = datetime.utcnow()
    since = now - timedelta(days=since_days)
    items = store.all(source=SourceType.JIRA, since=since, limit=10_000)
    week_ago      = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    this_week = [i for i in items if i.timestamp >= week_ago]
    last_week  = [i for i in items if two_weeks_ago <= i.timestamp < week_ago]
    total = max(len(items), 1)
    lw    = max(len(last_week), 1)
    volume_delta = round((len(this_week) - lw) / lw * 100, 1)

    # ── Status breakdown ──────────────────────────────────
    status_counts: Counter = Counter()
    for i in items:
        st = (i.metadata or {}).get("status", "Unknown")
        status_counts[st] += 1

    done_items     = [i for i in items if (i.metadata or {}).get("status", "").lower() == "done"]
    open_items     = [i for i in items if (i.metadata or {}).get("status", "").lower() in ("to do", "open", "new")]
    inprog_items   = [i for i in items if (i.metadata or {}).get("status", "").lower() in ("in progress", "en cours")]
    blocked_items  = [i for i in items if (i.metadata or {}).get("priority", "").lower() in ("highest", "blocker")
                      or "block" in (i.title or "").lower()
                      or "bloqu" in (i.title or "").lower()]

    # ── Story Points ──────────────────────────────────────
    def sp(item): return (item.metadata or {}).get("story_points") or 0
    total_sp      = sum(sp(i) for i in items)
    done_sp       = sum(sp(i) for i in done_items)
    inprog_sp     = sum(sp(i) for i in inprog_items)
    remaining_sp  = total_sp - done_sp

    # ── Issue types ───────────────────────────────────────
    type_counts: Counter = Counter()
    for i in items:
        t = (i.metadata or {}).get("issue_type", "Task")
        type_counts[t] += 1

    bug_items    = [i for i in items if
                    (i.metadata or {}).get("issue_type", "").lower() == "bug"
                    or "bug" in (i.title or "").lower()
                    or "bug" in [(t or "").lower() for t in (i.tags or [])]]
    bug_rate     = round(len(bug_items) / total * 100)

    # ── Priority breakdown ────────────────────────────────
    priority_counts: Counter = Counter()
    for i in items:
        p = (i.metadata or {}).get("priority", "Medium")
        priority_counts[p] += 1

    # ── Cycle Time (Done items) ───────────────────────────
    cycle_times = []
    for i in done_items:
        ct = (i.metadata or {}).get("cycle_time_days")
        if ct and ct > 0:
            cycle_times.append(ct)
    avg_cycle_time = round(sum(cycle_times) / len(cycle_times), 1) if cycle_times else None

    # ── Velocity (Story Points done) ─────────────────────
    velocity = round(done_sp, 1)

    # ── Delivery Success Rate ─────────────────────────────
    delivery_rate = round(len(done_items) / total * 100)

    # ── Sprint Predictability (SP done / SP total) ───────
    sprint_predictability = round(done_sp / max(total_sp, 1) * 100)

    # ── Risk Score ────────────────────────────────────────
    high_priority = sum(1 for i in items if (i.metadata or {}).get("priority", "") in ("High", "Highest", "Critical"))
    old_open = sum(1 for i in open_items if (now - i.timestamp).days > 7)
    risk_score = min(100, round(
        (len(blocked_items) * 25 + high_priority * 10 + old_open * 15) / max(total, 1)
    ))

    # ── Risky issues ──────────────────────────────────────
    risky_issues = []
    for i in items:
        m = i.metadata or {}
        reasons = []
        if m.get("priority") in ("High", "Highest", "Critical"):
            reasons.append("Haute priorité")
        if m.get("status", "").lower() not in ("done",) and (now - i.timestamp).days > 7:
            reasons.append("Ouvert depuis +7j")
        if "block" in (i.title or "").lower() or "bloqu" in (i.title or "").lower():
            reasons.append("Bloqué")
        if reasons:
            risky_issues.append({
                "key":      m.get("key", i.id),
                "title":    i.title or "",
                "status":   m.get("status", ""),
                "priority": m.get("priority", ""),
                "type":     m.get("issue_type", "Task"),
                "reasons":  reasons,
                "url":      i.url or "",
                "sp":       m.get("story_points"),
            })

    # ── Top assignees ─────────────────────────────────────
    author_counts: Counter = Counter()
    for i in items:
        author_counts[i.author] += 1
    top_authors = sorted(
        [{"name": k, "count": v} for k, v in author_counts.items()],
        key=lambda x: -x["count"]
    )[:8]

    # ── Activity by day ───────────────────────────────────
    DAY_NAMES = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    by_day_map: dict = {}
    for d in range(7):
        day_dt = now - timedelta(days=6 - d)
        by_day_map[day_dt.strftime("%Y-%m-%d")] = 0
    for item in this_week:
        key = item.timestamp.strftime("%Y-%m-%d")
        if key in by_day_map:
            by_day_map[key] += 1
    by_day = [
        {"day": DAY_NAMES[datetime.strptime(d, "%Y-%m-%d").weekday()], "date": d, "count": c}
        for d, c in by_day_map.items()
    ]

    # ── Sentiment ─────────────────────────────────────────
    sentiment_counts: Counter = Counter()
    for i in items:
        sentiment_counts[_get_sentiment(i)] += 1
    sentiment = {
        "positive": round(sentiment_counts["POSITIVE"] / total * 100),
        "neutral":  round(sentiment_counts["NEUTRAL"]  / total * 100),
        "negative": round(sentiment_counts["NEGATIVE"] / total * 100),
    }

    # ── Keywords ──────────────────────────────────────────
    keyword_freq = extract_keywords([i.content for i in items], top_n=10)

    # ── Intelligence ──────────────────────────────────────
    intelligence = compute_intelligence(items, since_days)

    return {
        # Volume
        "volume": {
            "this_week": len(this_week),
            "last_week": len(last_week),
            "total":     len(items),
            "delta_pct": volume_delta,
        },
        # KPI Cards
        "kpis": {
            "total":                len(items),
            "done":                 len(done_items),
            "open":                 len(open_items),
            "in_progress":          len(inprog_items),
            "blocked":              len(blocked_items),
            "bugs":                 len(bug_items),
            "bug_rate":             bug_rate,
            "velocity_sp":          velocity,
            "total_sp":             total_sp,
            "done_sp":              done_sp,
            "remaining_sp":         remaining_sp,
            "avg_cycle_time_days":  avg_cycle_time,
            "delivery_rate":        delivery_rate,
            "sprint_predictability": sprint_predictability,
            "risk_score":           risk_score,
            "high_priority_count":  high_priority,
        },
        # Breakdowns
        "status_distribution": [
            {"status": k, "count": v,
             "color": {"Done": "#22c55e", "In Progress": "#3b82f6", "To Do": "#94a3b8"}.get(k, "#f59e0b")}
            for k, v in status_counts.most_common()
        ],
        "priority_distribution": [
            {"priority": k, "count": v,
             "color": {"Highest": "#ef4444", "High": "#f97316", "Medium": "#f59e0b", "Low": "#22c55e", "Lowest": "#94a3b8"}.get(k, "#94a3b8")}
            for k, v in priority_counts.most_common()
        ],
        "type_distribution": [
            {"type": k, "count": v,
             "color": {"Bug": "#ef4444", "Story": "#8b5cf6", "Task": "#3b82f6", "Epic": "#f59e0b", "Subtask": "#94a3b8"}.get(k, "#94a3b8")}
            for k, v in type_counts.most_common()
        ],
        # Risky issues
        "risky_issues":  risky_issues[:6],
        "critical_alerts": len(blocked_items) + len(bug_items),
        # Charts
        "by_day":            by_day,
        "top_authors":       top_authors,
        "keyword_frequency": keyword_freq,
        "sentiment":         sentiment,
        "since_days":        since_days,
        "computed_at":       now.isoformat(),
        "intelligence":      intelligence,
    }


# ─────────────────────────────────────────────────────────
# Generic (Slack, Jira)
# ─────────────────────────────────────────────────────────

def compute_generic(store: ItemStore, source_type: SourceType, since_days: int = 30) -> dict:
    now = datetime.utcnow()
    since = now - timedelta(days=since_days)
    items = store.all(source=source_type, since=since, limit=10_000)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    this_week = [i for i in items if i.timestamp >= week_ago]
    last_week  = [i for i in items if two_weeks_ago <= i.timestamp < week_ago]
    lw    = max(len(last_week), 1)
    total = max(len(items), 1)

    volume_delta = round((len(this_week) - lw) / lw * 100, 1)

    sentiment_counts: Counter = Counter()
    for i in items:
        sentiment_counts[_get_sentiment(i)] += 1
    sentiment = {
        "positive": round(sentiment_counts["POSITIVE"] / total * 100),
        "neutral":  round(sentiment_counts["NEUTRAL"]  / total * 100),
        "negative": round(sentiment_counts["NEGATIVE"] / total * 100),
    }

    critical_alerts = sum(1 for i in items if has_escalation(f"{i.title} {i.content}"))
    keyword_freq = extract_keywords([i.content for i in items], top_n=12)

    author_counts: dict = defaultdict(int)
    for item in items:
        author_counts[item.author] += 1
    top_authors = sorted(
        [{"name": k, "count": v} for k, v in author_counts.items()],
        key=lambda x: -x["count"]
    )[:8]

    DAY_NAMES = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    by_day_map: dict = {}
    for d in range(7):
        day_dt = now - timedelta(days=6 - d)
        by_day_map[day_dt.strftime("%Y-%m-%d")] = 0
    for item in this_week:
        key = item.timestamp.strftime("%Y-%m-%d")
        if key in by_day_map:
            by_day_map[key] += 1
    by_day = [
        {"day": DAY_NAMES[datetime.strptime(d, "%Y-%m-%d").weekday()], "date": d, "count": c}
        for d, c in by_day_map.items()
    ]

    intelligence = compute_intelligence(items, since_days)

    return {
        "volume": {
            "this_week": len(this_week),
            "last_week": len(last_week),
            "total":     len(items),
            "delta_pct": volume_delta,
        },
        "sentiment":         sentiment,
        "critical_alerts":   critical_alerts,
        "by_day":            by_day,
        "top_authors":       top_authors,
        "keyword_frequency": keyword_freq,
        "since_days":        since_days,
        "computed_at":       now.isoformat(),
        "intelligence":      intelligence,
    }
