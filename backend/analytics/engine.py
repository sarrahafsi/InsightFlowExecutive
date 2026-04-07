"""Core analytics computation — works on the in-memory ItemStore."""

from collections import defaultdict
from datetime import datetime, timedelta

from connectors.schemas import SourceType
from store import ItemStore
from analytics.sentiment import score_text, has_escalation, extract_keywords


# ──────────────────────────────────────────────
# Overview
# ──────────────────────────────────────────────

def compute_overview(store: ItemStore, since_days: int = 30) -> dict:
    now = datetime.utcnow()
    since = now - timedelta(days=since_days)
    items = store.all(since=since, limit=10_000)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    this_week = [i for i in items if i.timestamp >= week_ago]
    last_week = [i for i in items if two_weeks_ago <= i.timestamp < week_ago]

    # Counts
    by_source: dict[str, int] = defaultdict(int)
    by_type: dict[str, int] = defaultdict(int)
    for item in items:
        by_source[item.source] += 1
        by_type[item.type] += 1

    # Sentiment
    sentiments = [score_text(f"{i.title} {i.content}") for i in items]
    total = max(len(sentiments), 1)
    sentiment = {
        "positive": round(sentiments.count("positive") / total * 100),
        "neutral":  round(sentiments.count("neutral")  / total * 100),
        "negative": round(sentiments.count("negative") / total * 100),
    }

    # Activity timeline (spans since_days, capped at 30 for readability)
    timeline_days = min(since_days, 30)
    timeline: dict[str, int] = {}
    for d in range(timeline_days):
        day = (now - timedelta(days=timeline_days - 1 - d)).strftime("%Y-%m-%d")
        timeline[day] = 0
    for item in items:
        day = item.timestamp.strftime("%Y-%m-%d")
        if day in timeline:
            timeline[day] += 1
    activity_timeline = [{"date": d, "count": c} for d, c in timeline.items()]

    # Alerts
    critical_alerts = sum(1 for i in items if has_escalation(f"{i.title} {i.content}"))

    # Velocity
    tw = len(this_week)
    lw = max(len(last_week), 1)
    delta_pct = round((tw - lw) / lw * 100, 1)

    # Risk index (0-100): weighted avg of negative sentiment + escalation rate
    neg_rate = sentiments.count("negative") / total
    esc_rate = critical_alerts / total
    risk_index = min(100, round((neg_rate * 0.5 + esc_rate * 0.5) * 100))

    # Connected sources
    connected = len({i.source for i in items if i.source != "slack" or True})

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
    }


# ──────────────────────────────────────────────
# Gmail Detail
# ──────────────────────────────────────────────

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

    # Volume
    volume_delta = round((len(this_week) - lw) / lw * 100, 1)

    # Labels
    label_counts: dict[str, int] = defaultdict(int)
    for item in items:
        for tag in item.tags:
            if tag not in ("", None):
                label_counts[tag] += 1

    unread_count     = label_counts.get("UNREAD", 0)
    important_count  = label_counts.get("IMPORTANT", 0)
    starred_count    = label_counts.get("STARRED", 0)
    total = max(len(items), 1)

    # Senders
    sender_counts: dict[str, int] = defaultdict(int)
    sender_emails: dict[str, str] = {}
    for item in items:
        sender_counts[item.author] += 1
        sender_emails[item.author] = item.metadata.get("from_email", "")
    top_senders = sorted(
        [{"name": k, "email": sender_emails[k], "count": v}
         for k, v in sender_counts.items()],
        key=lambda x: -x["count"]
    )[:8]

    # Domain distribution
    domain_counts: dict[str, int] = defaultdict(int)
    for item in items:
        email = item.metadata.get("from_email", "")
        if "@" in email:
            domain = email.split("@")[1].lower()
            domain_counts[domain] += 1
    domain_distribution = sorted(
        [{"domain": k, "count": v} for k, v in domain_counts.items()],
        key=lambda x: -x["count"]
    )[:8]

    # Thread analysis
    thread_map: dict[str, list] = defaultdict(list)
    for item in items:
        tid = item.metadata.get("thread_id", item.id)
        thread_map[tid].append(item)

    thread_lengths = [len(v) for v in thread_map.values()]
    long_threads = [
        {"subject": sorted(v, key=lambda x: x.timestamp)[0].title,
         "message_count": len(v)}
        for v in thread_map.values() if len(v) > 3
    ]
    avg_thread = round(sum(thread_lengths) / max(len(thread_lengths), 1), 1)

    # Back-and-forth intensity: threads with >2 messages / total threads
    baf_threads = [v for v in thread_map.values() if len(v) > 2]
    baf_score = round(len(baf_threads) / max(len(thread_map), 1) * 10, 1)

    # Escalation emails
    escalation_items = [
        i for i in items
        if has_escalation(f"{i.title} {i.content}")
    ]

    # No reply within 48h (proxy: IMPORTANT emails older than 48h)
    no_reply_48h = [
        i for i in items
        if "IMPORTANT" in i.tags and i.timestamp < h48_ago
    ]

    # Unanswered critical: escalation + no reply
    unanswered_critical = [
        i for i in escalation_items if i.timestamp < h48_ago
    ]

    # Avg response time: for threads with >1 message, delta between first and second
    response_times = []
    for v in thread_map.values():
        if len(v) >= 2:
            sorted_v = sorted(v, key=lambda x: x.timestamp)
            delta = (sorted_v[1].timestamp - sorted_v[0].timestamp).total_seconds() / 3600
            if 0 < delta < 168:  # ignore >1 week deltas
                response_times.append(delta)
    avg_response_hours = round(sum(response_times) / len(response_times), 1) if response_times else None

    # Emails by day (last 7 days)
    DAY_NAMES = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    by_day_map: dict[str, int] = {}
    for d in range(7):
        day_dt = (now - timedelta(days=6 - d))
        by_day_map[day_dt.strftime("%Y-%m-%d")] = 0
    for item in this_week:
        key = item.timestamp.strftime("%Y-%m-%d")
        if key in by_day_map:
            by_day_map[key] += 1
    by_day = [
        {"day": DAY_NAMES[datetime.strptime(d, "%Y-%m-%d").weekday()],
         "date": d, "count": c}
        for d, c in by_day_map.items()
    ]

    # Emails by hour
    by_hour_map: dict[int, int] = defaultdict(int)
    for item in items:
        by_hour_map[item.timestamp.hour] += 1
    by_hour = [{"hour": h, "count": by_hour_map.get(h, 0)} for h in range(24)]

    # Label distribution (clean labels)
    HIDDEN_LABELS = {"INBOX", "UNREAD", "CATEGORY_PROMOTIONS",
                     "CATEGORY_UPDATES", "CATEGORY_SOCIAL", "CATEGORY_FORUMS"}
    label_dist = sorted(
        [{"label": k, "count": v} for k, v in label_counts.items()
         if k not in HIDDEN_LABELS],
        key=lambda x: -x["count"]
    )[:6]

    # Keyword frequency
    keyword_freq = extract_keywords([i.content for i in items], top_n=12)

    # Sentiment
    sentiments = [score_text(f"{i.title} {i.content}") for i in items]
    sentiment = {
        "positive": round(sentiments.count("positive") / total * 100),
        "neutral":  round(sentiments.count("neutral")  / total * 100),
        "negative": round(sentiments.count("negative") / total * 100),
    }

    return {
        "volume": {
            "this_week":    len(this_week),
            "last_week":    len(last_week),
            "total":        len(items),
            "delta_pct":    volume_delta,
        },
        "unread": {
            "count": unread_count,
            "rate":  round(unread_count / total * 100),
        },
        "important": {
            "count": important_count,
            "rate":  round(important_count / total * 100),
        },
        "starred_count":      starred_count,
        "unique_senders":     len(sender_counts),
        "avg_response_hours": avg_response_hours,
        "threads": {
            "total":             len(thread_map),
            "long_count":        len(long_threads),
            "long_threads":      long_threads[:5],
            "avg_length":        avg_thread,
            "back_and_forth_score": baf_score,
        },
        "escalation": {
            "count": len(escalation_items),
            "items": [{"title": i.title, "timestamp": i.timestamp.isoformat(),
                       "author": i.author} for i in escalation_items[:5]],
        },
        "no_reply_48h": {
            "count": len(no_reply_48h),
            "items": [{"title": i.title, "timestamp": i.timestamp.isoformat()}
                      for i in no_reply_48h[:5]],
        },
        "unanswered_critical": {
            "count": len(unanswered_critical),
            "items": [{"title": i.title, "timestamp": i.timestamp.isoformat()}
                      for i in unanswered_critical[:5]],
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
    }


# ──────────────────────────────────────────────
# Generic (Slack, Jira, etc.)
# ──────────────────────────────────────────────

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

    sentiments = [score_text(f"{i.title} {i.content}") for i in items]
    sentiment = {
        "positive": round(sentiments.count("positive") / total * 100),
        "neutral":  round(sentiments.count("neutral")  / total * 100),
        "negative": round(sentiments.count("negative") / total * 100),
    }

    critical_alerts = sum(1 for i in items if has_escalation(f"{i.title} {i.content}"))
    keyword_freq = extract_keywords([i.content for i in items], top_n=12)

    author_counts: dict[str, int] = defaultdict(int)
    for item in items:
        author_counts[item.author] += 1
    top_authors = sorted(
        [{"name": k, "count": v} for k, v in author_counts.items()],
        key=lambda x: -x["count"]
    )[:8]

    DAY_NAMES = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    by_day_map: dict[str, int] = {}
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

    return {
        "volume": {
            "this_week": len(this_week),
            "last_week": len(last_week),
            "total":     len(items),
            "delta_pct": volume_delta,
        },
        "sentiment":       sentiment,
        "critical_alerts": critical_alerts,
        "by_day":          by_day,
        "top_authors":     top_authors,
        "keyword_frequency": keyword_freq,
        "since_days":      since_days,
        "computed_at":     now.isoformat(),
    }
