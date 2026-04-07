"""
InsightFlow Executive — Synthetic Dataset Generator
=====================================================
Generates ~3000 realistic multi-source organizational messages
using Ollama (local LLM), labeled for sentiment + emotion + business.

Same schema as messages_raw PostgreSQL table.
Used for fine-tuning XLM-RoBERTa.

Usage:
    python ml/generate_dataset.py

Output:
    ml/dataset/insightflow_synthetic.csv
    ml/dataset/insightflow_synthetic.json
"""

import csv
import json
import os
import random
import uuid
from datetime import datetime, timedelta
from openai import OpenAI

# ── Config ────────────────────────────────────────────────────
OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_MODEL    = "llama3.2"
DATASET_DIR     = os.path.join(os.path.dirname(__file__), "dataset")
os.makedirs(DATASET_DIR, exist_ok=True)

client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")

# ── Labels ────────────────────────────────────────────────────
SENTIMENT_LABELS = ["POSITIVE", "NEGATIVE", "NEUTRAL"]
EMOTION_LABELS   = ["satisfaction", "frustration", "concern", "urgency", "neutral"]
BUSINESS_LABELS  = [
    "Progress", "Neutral Update", "Concern",
    "Risk", "Blocked", "Overload", "Conflict", "Urgent"
]
TOPICS = [
    "project update", "deadline", "budget", "technical issue",
    "client relations", "team management", "deployment", "planning"
]

# ── Source configs ────────────────────────────────────────────
SOURCES = {
    "gmail": {
        "item_type": "email",
        "authors": ["alice.martin@company.com", "bob.johnson@company.com",
                    "carol.smith@company.com", "david.lee@company.com",
                    "emma.wilson@company.com", "frank.brown@company.com"],
        "style": "formal professional email",
        "count": 700,
    },
    "slack": {
        "item_type": "message",
        "authors": ["alice.m", "bob.j", "carol.s", "david.l", "emma.w", "frank.b"],
        "style": "informal team chat message, short, direct, sometimes uses emoji",
        "count": 700,
    },
    "jira": {
        "item_type": "ticket",
        "authors": ["alice.martin", "bob.johnson", "carol.smith", "tech-lead"],
        "style": "technical project ticket or comment, concise, structured",
        "count": 600,
    },
    "teams": {
        "item_type": "message",
        "authors": ["Alice Martin", "Bob Johnson", "Carol Smith", "Manager"],
        "style": "professional team chat, medium formality",
        "count": 500,
    },
    "crm": {
        "item_type": "note",
        "authors": ["sales@company.com", "support@company.com", "account.manager@company.com"],
        "style": "CRM note about client interaction or deal status",
        "count": 500,
    },
}

# ── Scenario templates per business label ─────────────────────
SCENARIOS = {
    "Progress": [
        "Successfully completed a task or milestone",
        "Deployment went well, all systems green",
        "Client approved the proposal",
        "Sprint goals achieved ahead of schedule",
        "Feature released to production without issues",
    ],
    "Neutral Update": [
        "Weekly status update with no major issues",
        "Routine meeting notes or summary",
        "Administrative update or reminder",
        "FYI message about process change",
        "Standard progress report",
    ],
    "Concern": [
        "Slight delay noticed, might affect timeline",
        "Client seems less engaged than usual",
        "Some technical debt accumulating",
        "Minor budget overrun starting to appear",
        "Team capacity might be an issue next sprint",
    ],
    "Risk": [
        "Major technical bug discovered in production",
        "Key client threatening to cancel contract",
        "Critical dependency not delivered by vendor",
        "Budget significantly over target",
        "Project timeline severely impacted",
    ],
    "Blocked": [
        "Waiting for approval from stakeholder for 3 days",
        "Cannot proceed — dependency not ready",
        "Access credentials not provided, team idle",
        "Integration blocked waiting for API from partner",
        "Task on hold — no response from client",
    ],
    "Overload": [
        "Team working overtime for two weeks straight",
        "Developer handling 3 projects simultaneously",
        "Too many urgent requests, team overwhelmed",
        "Burnout signals — team members taking sick days",
        "Unrealistic deadlines causing team stress",
    ],
    "Conflict": [
        "Disagreement between teams on technical approach",
        "Product and engineering misaligned on priorities",
        "Client and team have conflicting expectations",
        "Internal argument about resource allocation",
        "Two managers giving contradictory instructions",
    ],
    "Urgent": [
        "Production is down, immediate action needed",
        "Client escalation requires CEO intervention",
        "Security vulnerability discovered, patch needed now",
        "Emergency board meeting called",
        "Critical deadline missed, exec attention required",
    ],
}

# Sentiment mapping logic
BUSINESS_TO_SENTIMENT = {
    "Progress":       ("POSITIVE", "satisfaction"),
    "Neutral Update": ("NEUTRAL",  "neutral"),
    "Concern":        ("NEUTRAL",  "concern"),
    "Risk":           ("NEGATIVE", "concern"),
    "Blocked":        ("NEGATIVE", "frustration"),
    "Overload":       ("NEGATIVE", "frustration"),
    "Conflict":       ("NEGATIVE", "frustration"),
    "Urgent":         ("NEGATIVE", "urgency"),
}


def random_timestamp() -> str:
    """Generate a realistic timestamp within the last 90 days."""
    base  = datetime.utcnow()
    delta = timedelta(days=random.randint(0, 90),
                      hours=random.randint(7, 20),
                      minutes=random.randint(0, 59))
    return (base - delta).isoformat()


def generate_message(source: str, style: str, business_label: str, scenario: str, lang: str = "en") -> dict | None:
    """Call Ollama to generate one realistic message."""
    sentiment, emotion = BUSINESS_TO_SENTIMENT[business_label]

    if lang == "fr":
        lang_instruction = "Write in French (professional business French). Use natural French expressions."
    elif lang == "both":
        lang_instruction = (
            "Write in French." if random.random() < 0.5
            else "Write in English."
        )
    else:
        lang_instruction = "Write in English."

    prompt = f"""Generate a realistic {style} for an executive intelligence platform.

Context:
- Source platform: {source}
- Business situation: {scenario}
- Tone: {sentiment.lower()} ({emotion})
- Business signal: {business_label}
- Language: {lang_instruction}

Requirements:
- Write ONLY the message content (no subject line prefix, no JSON)
- Match the style of {source} communications
- Length: {'1-3 sentences' if source in ['slack', 'teams'] else '2-5 sentences'}
- Be specific and realistic, use business vocabulary
- Do NOT mention the word "{business_label}" explicitly

Write the message now:"""

    try:
        response = client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=200,
        )
        content = response.choices[0].message.content.strip()
        # Clean up common LLM artifacts
        for prefix in ["Message:", "Content:", "Here's", "Sure,"]:
            if content.startswith(prefix):
                content = content[len(prefix):].strip()
        return content if len(content) > 20 else None
    except Exception as e:
        return None


def generate_title(source: str, business_label: str, topic: str) -> str:
    """Generate a realistic title/subject for the message."""
    titles = {
        "gmail":  [f"Re: {topic.title()} update", f"[Action Required] {topic.title()}",
                   f"Weekly {topic} summary", f"Important: {topic.title()} situation"],
        "slack":  [f"#{topic.replace(' ', '-')}", f"@channel {business_label}",
                   f"Quick update on {topic}", ""],
        "jira":   [f"[{business_label.upper()}] {topic.title()} issue",
                   f"Sprint: {topic} blocked", f"BUG: {topic} failure"],
        "teams":  [f"{topic.title()} Discussion", f"Update: {topic}",
                   f"Team sync — {topic}"],
        "crm":    [f"Client note: {topic}", f"Account update — {topic}",
                   f"Deal status: {topic}"],
    }
    return random.choice(titles.get(source, [f"{topic} update"]))


def build_record(source: str, config: dict, business_label: str, content: str, topic: str) -> dict:
    """Build a full record matching the messages_raw schema."""
    sentiment, emotion = BUSINESS_TO_SENTIMENT[business_label]
    # Add small noise to confidence scores
    sentiment_score = round(random.uniform(0.65, 0.97), 4)
    business_conf   = round(random.uniform(0.72, 0.96), 4)

    return {
        "id":                   f"synth-{uuid.uuid4().hex[:12]}",
        "source":               source,
        "author":               random.choice(config["authors"]),
        "author_email":         random.choice(config["authors"]) if "@" in config["authors"][0] else "",
        "timestamp":            random_timestamp(),
        "title":                generate_title(source, business_label, topic),
        "content":              content,
        "item_type":            config["item_type"],
        "tags":                 [topic, business_label.lower()],
        "thread_id":            f"thread-{uuid.uuid4().hex[:8]}",
        "url":                  "",
        # NLP labels (ground truth for fine-tuning)
        "sentiment_label":      sentiment,
        "sentiment_score":      sentiment_score,
        "emotion_label":        emotion,
        "emotion_score":        round(random.uniform(0.55, 0.92), 4),
        "topic":                topic,
        "business_label":       business_label,
        "business_confidence":  business_conf,
        "business_reason":      f"Scenario: {business_label} — {topic}",
    }


def run_generation(lang: str = "en"):
    lang_label = {"en": "English", "fr": "French", "both": "English + French"}[lang]
    out_suffix = f"_{lang}"
    csv_name   = f"insightflow_synthetic{out_suffix}.csv"
    json_name  = f"insightflow_synthetic{out_suffix}.json"

    print("=" * 65)
    print("  InsightFlow Executive — Synthetic Dataset Generator")
    print("=" * 65)
    print(f"  Model    : {OLLAMA_MODEL} via Ollama")
    print(f"  Language : {lang_label}")
    print(f"  Target   : ~3000 messages across 5 sources")
    print(f"  Output   : {csv_name}")
    print("=" * 65)

    all_records = []
    total_generated = 0
    total_failed    = 0

    for source, config in SOURCES.items():
        target = config["count"]
        print(f"\n[{source.upper()}] Generating {target} messages...")

        # Distribute evenly across business labels
        per_label = target // len(BUSINESS_LABELS)
        source_records = []

        for business_label in BUSINESS_LABELS:
            scenarios = SCENARIOS[business_label]
            count = 0

            while count < per_label:
                scenario = random.choice(scenarios)
                topic    = random.choice(TOPICS)
                content  = generate_message(source, config["style"], business_label, scenario, lang=lang)

                if content:
                    record = build_record(source, config, business_label, content, topic)
                    source_records.append(record)
                    count += 1
                    total_generated += 1
                else:
                    total_failed += 1

                # Progress indicator
                done = total_generated + total_failed
                if done % 50 == 0:
                    print(f"  Progress: {total_generated} generated | {total_failed} failed")

        all_records.extend(source_records)
        print(f"  [{source.upper()}] Done: {len(source_records)} messages")

    # ── Save CSV ──────────────────────────────────────────────
    csv_path = os.path.join(DATASET_DIR, csv_name)
    if all_records:
        fieldnames = list(all_records[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_records)
        print(f"\n  CSV saved : {csv_path}")

    # ── Save JSON ─────────────────────────────────────────────
    json_path = os.path.join(DATASET_DIR, json_name)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2, default=str)
    print(f"  JSON saved: {json_path}")

    # ── Merge si les deux fichiers existent ───────────────────
    en_path = os.path.join(DATASET_DIR, "insightflow_synthetic_en.csv")
    fr_path = os.path.join(DATASET_DIR, "insightflow_synthetic_fr.csv")
    if os.path.exists(en_path) and os.path.exists(fr_path):
        print(f"\n  Both EN + FR files found — merging into insightflow_synthetic_full.csv...")
        merged = []
        for p in [en_path, fr_path]:
            with open(p, encoding="utf-8") as f:
                merged.extend(list(csv.DictReader(f)))
        random.shuffle(merged)
        full_path = os.path.join(DATASET_DIR, "insightflow_synthetic_full.csv")
        with open(full_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(merged[0].keys()))
            writer.writeheader()
            writer.writerows(merged)
        print(f"  Full dataset: {full_path} ({len(merged)} messages)")

    # ── Stats ─────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  Total generated : {total_generated}")
    print(f"  Total failed    : {total_failed}")
    print(f"  Success rate    : {total_generated/(total_generated+total_failed)*100:.1f}%")

    from collections import Counter
    bl = Counter(r["business_label"] for r in all_records)
    sl = Counter(r["sentiment_label"] for r in all_records)
    sc = Counter(r["source"] for r in all_records)

    print(f"\n  Distribution par source :")
    for s, c in sc.most_common():
        print(f"    {s:<12} {c:>4} messages")

    print(f"\n  Distribution sentiment :")
    for s, c in sl.most_common():
        print(f"    {s:<12} {c:>4} ({c/len(all_records)*100:.1f}%)")

    print(f"\n  Distribution business labels :")
    for b, c in bl.most_common():
        print(f"    {b:<16} {c:>4} ({c/len(all_records)*100:.1f}%)")
    print(f"{'='*65}")


if __name__ == "__main__":
    import sys
    lang = "en"
    for arg in sys.argv[1:]:
        if arg in ("--lang", "-l") and sys.argv.index(arg) + 1 < len(sys.argv):
            lang = sys.argv[sys.argv.index(arg) + 1]
        elif arg in ("en", "fr", "both"):
            lang = arg
    run_generation(lang=lang)
