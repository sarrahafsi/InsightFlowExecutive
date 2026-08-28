"""
Générateur de dataset de fine-tuning v2 — InsightFlow Executive PFE
=====================================================================
V2 sur la base du retour croisé (Claude + ChatGPT) sur la v1 :

1. Rendu HTML/CSS + navigateur headless (Playwright), pas matplotlib —
   ressemble à de vraies UI (Jira, Slack, terminal, dashboard), pas à des
   graphiques de rapport. Texte rendu exactement comme écrit (pas de risque
   de "Revenuue" halluciné comme avec une IA générative d'image).

2. Captions INTERPRÉTATIVES (sens métier), pas structurelles. V1 :
   "a jira ticket card showing key SCRUM-798, status In Progress" (décrit le
   widget). V2 : "A critical payment API task is blocked because the
   database is unavailable, delaying the production deployment" (décrit la
   situation métier — c'est ce que le modèle doit apprendre à extraire).

3. Distribution de sentiment contrôlée (~35% négatif / 35% neutre / 30%
   positif) dans TOUTES les catégories, y compris "error" — sinon le modèle
   apprend un raccourci du type "dashboard = problème". Toutes les images
   négatives n'ont plus leur place ; on inclut aussi des cas résolus/sains.

4. Métadonnées structurées par image (domain, scenario, severity, status,
   visible_text, business_context, key_entities) en plus de la caption —
   réutilisable pour évaluer l'étape de fusion JSON (OCR+Vision→LLM) du
   pipeline, pas seulement pour le fine-tuning BLIP.

5. 2-3 captions paraphrasées par image (pas une formule figée).

Toujours 100% synthétique et déterministe : chaque valeur affichée dans le
HTML est directement réutilisée pour construire la caption → vérité terrain
garantie exacte, aucune génération de caption a posteriori.

Usage :
    python finetune_dataset_generator.py --total 1500
    python finetune_dataset_generator.py --total 40   (test rapide)
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

from playwright.sync_api import sync_playwright

OUTPUT_DIR = Path(__file__).parent / "finetune_dataset"
IMAGES_DIR = OUTPUT_DIR / "images"
MANIFEST_JSONL = OUTPUT_DIR / "manifest.jsonl"
MANIFEST_CSV = OUTPUT_DIR / "manifest.csv"

SEED = 42

CATEGORY_WEIGHTS = {
    "error": 2.0,
    "ticket": 2.0,
    "chat": 2.0,
    "dashboard": 1.5,
    "chart": 1.0,
    "document": 1.0,
    "workflow": 1.0,
    "table": 0.5,
    "email": 0.5,
}
CATEGORY_SUBTYPES = {
    "error": ["dialog", "trace", "banner", "crash", "deploy_trace"],
    "ticket": ["card", "list", "comments"],
    "chat": ["conversation"],
    "dashboard": ["dashboard"],
    "chart": ["bar", "pie", "line"],
    "document": ["report"],
    "workflow": ["pipeline"],
    "table": ["table"],
    "email": ["email"],
}
SPLIT_RATIOS = {"train": 0.70, "val": 0.15, "test": 0.15}
SENTIMENT_WEIGHTS = {"negative": 0.35, "neutral": 0.35, "positive": 0.30}

FONT = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
MONO = "'Consolas', 'Courier New', monospace"

# ── Pools de contenu ──────────────────────────────────────────────────────
PEOPLE = [
    "Sarah Hafsi", "Karim Haddad", "John Doe", "Lina Amri", "Youssef Ben Ali",
    "Emma Chen", "Marco Rossi", "Fatima Zahra", "David Kim", "Nadia Belkacem",
    "Omar Trabelsi", "Julia Novak", "Ahmed Saidi", "Chloe Dubois", "Ravi Patel",
]
DOMAIN_SUBJECTS = [
    ("IT", "payment API"), ("IT", "authentication service"), ("IT", "mobile application"),
    ("IT", "database migration"), ("IT", "infrastructure upgrade"),
    ("Sales", "sales pipeline"), ("Sales", "quarterly sales target"), ("Sales", "client contract renewal"),
    ("Marketing", "marketing campaign"), ("Marketing", "lead generation program"),
    ("Finance", "budget approval"), ("Finance", "expense reporting process"),
    ("Operations", "delivery logistics"), ("Operations", "inventory management"),
    ("Customer Service", "support ticket queue"), ("Customer Service", "customer onboarding"),
    ("Project Management", "product roadmap"), ("Project Management", "sprint delivery"),
    ("HR", "recruitment pipeline"), ("HR", "employee onboarding"),
]
TOOLS = [("jira", "#0052CC"), ("clickup", "#7B68EE")]
PRIORITIES = ["Low", "Medium", "High", "Critical", "Urgent"]
STATUS_BY_SENTIMENT = {
    "negative": ["BLOCKED", "AT RISK", "OVERDUE", "CANCELLED"],
    "neutral": ["IN PROGRESS", "ON HOLD"],
    "positive": ["DONE", "COMPLETED"],
}
STATUS_COLOR = {
    "BLOCKED": "#C0392B", "AT RISK": "#E67E22", "OVERDUE": "#D35400", "CANCELLED": "#7F8C8D",
    "IN PROGRESS": "#2980B9", "ON HOLD": "#95A5A6",
    "DONE": "#27AE60", "COMPLETED": "#27AE60",
}
BLOCK_REASONS = [
    "the {subject} database is unavailable",
    "a critical dependency has not been delivered",
    "the responsible team is waiting on external approval",
    "a security review has not been completed",
    "the required infrastructure is still being provisioned",
    "an upstream vendor missed their delivery date",
]
CONSEQUENCES = [
    "the production deployment", "the client delivery", "the next sprint milestone",
    "the quarterly launch", "the go-live date",
]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

SERVICES = ["Payment API", "Authentication Service", "Database Cluster", "Mobile Application",
            "Checkout Service", "Search Index", "Notification Service", "Billing System"]
INCIDENT_CAUSES = [
    "a database connection timeout", "an expired SSL certificate",
    "a memory leak in the worker process", "an unhandled exception in the payment gateway",
    "a network partition between regions", "a failed dependency upgrade",
]

CHANNELS = ["general", "engineering", "product", "incidents", "sales", "eng-alerts"]
COLORS6 = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B2", "#937860"]


def weighted_sentiment(rng: random.Random) -> str:
    return rng.choices(list(SENTIMENT_WEIGHTS), weights=list(SENTIMENT_WEIGHTS.values()))[0]


def rand_key(rng: random.Random, tool: str) -> str:
    return f"SCRUM-{rng.randint(100, 999)}" if tool == "jira" else f"CU-{rng.randint(1000, 9999):x}"


def page_html(width: int, height: int, body: str, css: str, bg: str = "#ffffff", color: str = "#1a1a1a") -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ width: {width}px; height: {height}px; background: {bg}; font-family: {FONT}; color: {color}; overflow: hidden; }}
{css}
</style></head><body>{body}</body></html>"""


CSS_CARD = """
.card { margin: 16px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.12); overflow: hidden; background: #fff; border: 1px solid #e0e0e0; }
.topbar { padding: 10px 16px; color: #fff; font-weight: 700; font-size: 13px; letter-spacing: 0.3px; }
.body { padding: 18px; }
.title { font-size: 18px; font-weight: 700; color: #172B4D; margin-bottom: 14px; }
.row { display: flex; align-items: center; gap: 14px; margin-bottom: 12px; }
.pill { padding: 5px 14px; border-radius: 14px; color: #fff; font-size: 12px; font-weight: 700; }
.priority { font-size: 13px; color: #555; }
.progress-label { font-size: 12px; color: #555; margin-bottom: 6px; }
.progress-track { height: 8px; border-radius: 4px; background: #EBECF0; margin-bottom: 12px; }
.progress-fill { height: 8px; border-radius: 4px; background: #4C9AFF; }
.meta { font-size: 13px; color: #666; margin-bottom: 10px; }
.assignee { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #333; }
.avatar { width: 26px; height: 26px; border-radius: 50%; background: #8993A4; display: inline-block; }
.reason { margin-top: 14px; padding: 10px 12px; border-radius: 6px; background: #FDEDED; color: #7B241C; font-size: 12.5px; border-left: 3px solid #C0392B; }
"""


def build_ticket_card(rng: random.Random):
    domain, subject = rng.choice(DOMAIN_SUBJECTS)
    tool, tool_color = rng.choice(TOOLS)
    key = rand_key(rng, tool)
    sentiment = weighted_sentiment(rng)
    status = rng.choice(STATUS_BY_SENTIMENT[sentiment])
    priority = rng.choice(PRIORITIES)
    progress = {"positive": rng.randint(85, 100), "neutral": rng.randint(20, 70),
                "negative": rng.randint(5, 55)}[sentiment]
    assignee = rng.choice(PEOPLE)
    due = f"{rng.choice(MONTHS)} {rng.randint(1, 28)}"
    action = rng.choice(["migration", "integration", "rollout", "update", "fix", "review"])
    title = f"{subject.capitalize()} {action}"
    status_word = status.lower()

    reason_html = ""
    reason_text = None
    if sentiment == "negative":
        reason = rng.choice(BLOCK_REASONS).format(subject=subject)
        consequence = rng.choice(CONSEQUENCES)
        reason_text = f"{reason[0].upper() + reason[1:]}, impacting {consequence}."
        reason_html = f'<div class="reason">{reason_text}</div>'
        captions = [
            f"A {priority.lower()} priority {subject} task is {status_word} because {reason}, delaying {consequence}.",
            f"The {subject} task ({key}) is {status_word} — {reason} is preventing progress on {consequence}.",
            f"{reason[0].upper() + reason[1:]}, leaving the {subject} task {status_word} and putting {consequence} at risk.",
        ]
        business_context = f"The {domain} team needs to resolve the blocker on {subject} to avoid delaying {consequence}."
    elif sentiment == "positive":
        captions = [
            f"The {subject} task has been completed successfully, meeting its {due} deadline.",
            f"{title} ({key}) is now {status_word}, closing out the {subject} initiative on schedule.",
            f"Work on {subject} finished on time, with the task marked {status_word}.",
        ]
        business_context = f"The {domain} team delivered the {subject} task on schedule."
    else:
        captions = [
            f"The {subject} task is progressing at {progress}% completion, on track for its {due} deadline.",
            f"{title} ({key}) remains {status_word}, currently {progress}% complete.",
            f"Work on {subject} is ongoing, {progress}% done, with a target date of {due}.",
        ]
        business_context = f"The {domain} team is actively working on {subject}, tracking toward the {due} deadline."

    body = f"""
    <div class="card">
      <div class="topbar" style="background:{tool_color}">{tool.upper()}&nbsp;&nbsp;{key}</div>
      <div class="body">
        <div class="title">{title}</div>
        <div class="row">
          <span class="pill" style="background:{STATUS_COLOR[status]}">{status}</span>
          <span class="priority">Priority: {priority}</span>
        </div>
        <div class="progress-label">Progress: {progress}%</div>
        <div class="progress-track"><div class="progress-fill" style="width:{progress}%"></div></div>
        <div class="meta">Due date: {due}</div>
        <div class="assignee"><span class="avatar"></span> Assignee: {assignee}</div>
        {reason_html}
      </div>
    </div>"""
    html = page_html(640, 340, body, CSS_CARD)
    visible_text = [f"{tool.upper()}  {key}", title, status, f"Priority: {priority}",
                     f"Progress: {progress}%", f"Due date: {due}", f"Assignee: {assignee}"]
    if reason_text:
        visible_text.append(reason_text)
    meta = dict(domain=domain, scenario=f"{subject}_{status_word}".replace(" ", "_"),
                severity=("high" if sentiment == "negative" else None), status=status_word,
                sentiment=sentiment, visible_text=visible_text, business_context=business_context,
                key_entities=[key, status, priority, f"{progress}%", due])
    return html, captions, meta


CSS_TABLE = """
.wrap { margin: 18px; }
.h1 { font-size: 16px; font-weight: 700; color: #172B4D; margin-bottom: 12px; }
table { width: 100%; border-collapse: collapse; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
th { background: #2C3E50; color: #fff; padding: 9px 12px; font-size: 12.5px; text-align: left; }
td { padding: 9px 12px; font-size: 12.5px; border-bottom: 1px solid #EEE; }
tr:nth-child(even) td { background: #F8F9FA; }
.status { padding: 3px 10px; border-radius: 10px; color: #fff; font-size: 11px; font-weight: 700; }
"""


def build_ticket_list(rng: random.Random):
    tool, _ = rng.choice(TOOLS)
    rows = []
    row_meta = []
    for _ in range(4):
        _, subject = rng.choice(DOMAIN_SUBJECTS)
        sentiment = weighted_sentiment(rng)
        status = rng.choice(STATUS_BY_SENTIMENT[sentiment])
        title = f"{rng.choice(['Fix', 'Update', 'Add', 'Investigate'])} {subject}"
        key = rand_key(rng, tool)
        priority = rng.choice(PRIORITIES)
        rows.append(f"<tr><td>{key}</td><td>{title}</td>"
                     f'<td><span class="status" style="background:{STATUS_COLOR[status]}">{status}</span></td>'
                     f"<td>{priority}</td></tr>")
        row_meta.append((key, title, status, priority, sentiment))
    body = f"""<div class="wrap"><div class="h1">Ticket Board — {tool.capitalize()}</div>
    <table><tr><th>Key</th><th>Title</th><th>Status</th><th>Priority</th></tr>{''.join(rows)}</table></div>"""
    html = page_html(760, 300, body, CSS_TABLE)
    n_blocked = sum(1 for _, _, s, p, sent in row_meta if sent == "negative")
    n_done = sum(1 for _, _, s, p, sent in row_meta if sent == "positive")
    if n_blocked >= 2:
        captions = [f"The ticket board shows {n_blocked} tickets blocked or at risk, requiring attention.",
                    f"Several tickets ({n_blocked} of {len(row_meta)}) are blocked or delayed on this board."]
        business_context = "Multiple tickets need escalation to stay on schedule."
        sentiment = "negative"
    elif n_done >= 2:
        captions = [f"The ticket board shows steady progress, with {n_done} tickets completed.",
                    f"Most tickets on this board are progressing well, {n_done} already done."]
        business_context = "The team is on track across most active tickets."
        sentiment = "positive"
    else:
        captions = ["The ticket board shows a mix of tickets at various stages of progress.",
                    "The team has a balanced set of tickets in progress across the board."]
        business_context = "Ticket progress is mixed but no major blockers stand out."
        sentiment = "neutral"
    meta = dict(domain="Project Management", scenario="ticket_board_overview", severity=None,
                status="mixed", sentiment=sentiment,
                visible_text=[cell for k, t, s, p, _ in row_meta for cell in (k, t, s, p)],
                business_context=business_context, key_entities=[k for k, _, _, _, _ in row_meta])
    return html, captions, meta


CSS_COMMENTS = """
.wrap { margin: 18px; border-radius: 8px; border: 1px solid #E0E0E0; padding: 16px; }
.h1 { font-size: 15px; font-weight: 700; color: #172B4D; margin-bottom: 14px; }
.comment { display: flex; gap: 10px; margin-bottom: 14px; }
.avatar { width: 26px; height: 26px; border-radius: 50%; background: #8993A4; flex-shrink: 0; }
.author { font-weight: 700; font-size: 12.5px; color: #222; }
.text { font-size: 12.5px; color: #555; margin-top: 2px; }
"""


def build_ticket_comments(rng: random.Random):
    tool, _ = rng.choice(TOOLS)
    key = rand_key(rng, tool)
    domain, subject = rng.choice(DOMAIN_SUBJECTS)
    title = f"{rng.choice(['Add', 'Fix', 'Update'])} {subject}"
    people = rng.sample(PEOPLE, 2)
    sentiment = weighted_sentiment(rng)
    if sentiment == "negative":
        exchange = [(people[0], f"Blocked on {subject} — waiting for the {rng.choice(['infra', 'security', 'legal'])} team."),
                    (people[1], "This is delaying the whole milestone, can we escalate?"),
                    (people[0], "Escalated, waiting for a response.")]
        caption = f"The comment thread on {key} shows the {subject} task is blocked and has been escalated."
    elif sentiment == "positive":
        exchange = [(people[0], "Implementation done, PR is up for review."),
                    (people[1], "Reviewed and approved, nice work!"),
                    (people[0], "Merged and deployed.")]
        caption = f"The comment thread on {key} shows the {subject} task was completed and merged successfully."
    else:
        exchange = [(people[0], "Started implementation, PR incoming today."),
                    (people[1], "Please add unit tests before merging."),
                    (people[0], "Will do, tests coming tomorrow.")]
        caption = f"The comment thread on {key} shows ongoing discussion about implementing and testing {subject}."
    rows = "".join(
        f'<div class="comment"><span class="avatar"></span><div><div class="author">{a}</div>'
        f'<div class="text">{t}</div></div></div>' for a, t in exchange)
    body = f'<div class="wrap"><div class="h1">{key} — {title}</div>{rows}</div>'
    html = page_html(640, 340, body, CSS_COMMENTS)
    meta = dict(domain=domain, scenario=f"{subject}_comment_thread".replace(" ", "_"), severity=None,
                status=sentiment, sentiment=sentiment,
                visible_text=[f"{key} — {title}"] + [text for pair in exchange for text in pair],
                business_context=caption, key_entities=[key, subject])
    return html, [caption, caption.replace("shows", "reveals")], meta


CSS_DIALOG = """
.dialog { margin: 20px; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 16px rgba(0,0,0,0.2); border: 1px solid #ccc; background: #F0F0F0; }
.titlebar { padding: 10px 14px; color: #fff; font-weight: 700; font-size: 13px; }
.content { display: flex; padding: 20px; gap: 16px; align-items: center; }
.icon { font-size: 34px; }
.msg { font-size: 13px; color: #222; line-height: 1.4; }
.btnrow { padding: 0 20px 18px; display: flex; justify-content: flex-end; }
.btn { padding: 7px 20px; border-radius: 4px; background: #E0E0E0; border: 1px solid #999; font-size: 12.5px; }
"""

DIALOG_MESSAGES = {
    "negative": [
        "The application has encountered an unexpected error and needs to close.",
        "A required service failed to respond within the expected time.",
        "The connection to the server was lost unexpectedly.",
    ],
    "positive": [
        "The operation completed successfully with no errors.",
        "All changes have been saved and synced successfully.",
        "The system update completed without any issues.",
    ],
    "neutral": [
        "A new update is available and will be installed on next restart.",
        "The scheduled maintenance window will begin in 10 minutes.",
    ],
}


def build_error_dialog(rng: random.Random):
    sentiment = weighted_sentiment(rng)
    message = rng.choice(DIALOG_MESSAGES[sentiment])
    if sentiment == "negative":
        titlebar_color, icon, title = "#C0392B", "⚠", "Application Error"
    elif sentiment == "positive":
        titlebar_color, icon, title = "#27AE60", "✓", "Success"
    else:
        titlebar_color, icon, title = "#2980B9", "ℹ", "Notice"
    body = f"""<div class="dialog">
      <div class="titlebar" style="background:{titlebar_color}">{title}</div>
      <div class="content"><span class="icon" style="color:{titlebar_color}">{icon}</span>
        <span class="msg">{message}</span></div>
      <div class="btnrow"><span class="btn">OK</span></div>
    </div>"""
    html = page_html(520, 260, body, CSS_DIALOG)
    verb = {"negative": "A critical application error occurred", "positive": "The operation completed successfully",
            "neutral": "A system notification informs the user"}[sentiment]
    captions = [f"{verb}: {message.lower()[0] + message[1:] if False else message}",
                f"{title}: {message}"]
    meta = dict(domain="IT", scenario="app_dialog", severity=("high" if sentiment == "negative" else None),
                status=sentiment, sentiment=sentiment, visible_text=[title, message],
                business_context=captions[0], key_entities=[title])
    return html, captions, meta


CSS_TERMINAL = """
.term { margin: 16px; border-radius: 8px; overflow: hidden; background: #1E1E1E; box-shadow: 0 2px 10px rgba(0,0,0,0.3); }
.termbar { padding: 8px 12px; background: #2D2D2D; display: flex; gap: 6px; }
.dot { width: 11px; height: 11px; border-radius: 50%; }
.termbody { padding: 14px 16px; font-family: 'Consolas','Courier New',monospace; font-size: 12.5px; line-height: 1.6; }
.ok { color: #6BCB77; } .err { color: #FF6B6B; } .dim { color: #D4D4D4; }
"""


def build_terminal(rng: random.Random, deploy: bool):
    sentiment = weighted_sentiment(rng)
    domain, subject = rng.choice(DOMAIN_SUBJECTS)
    version = f"v{rng.randint(1, 4)}.{rng.randint(0, 9)}.{rng.randint(0, 9)}"
    if deploy:
        if sentiment == "positive":
            lines = [(f"$ deploy production --release {version}", "dim"),
                     ("Deployment successful", "ok"),
                     ("Status: HEALTHY — 0 critical alerts", "ok")]
            caption = f"The production deployment of {version} completed successfully with zero critical alerts."
        elif sentiment == "negative":
            reason = rng.choice(INCIDENT_CAUSES)
            lines = [(f"$ deploy production --release {version}", "dim"),
                     ("Deployment failed", "err"),
                     (reason.capitalize(), "err"),
                     ("CRITICAL: rollback triggered automatically", "err")]
            caption = f"The production deployment of {version} failed due to {reason}, triggering an automatic rollback."
        else:
            lines = [(f"$ deploy production --release {version}", "dim"),
                     ("Deployment completed with warnings", "dim"),
                     ("2 non-critical checks skipped", "dim")]
            caption = f"The production deployment of {version} completed with minor warnings but no critical issues."
    else:
        if sentiment == "positive":
            lines = [(f"$ pytest {subject.split()[0]}_worker.py", "dim"),
                     ("32 passed in 4.2s", "ok"), ("Build succeeded", "ok")]
            caption = f"The automated test suite for the {subject} module passed successfully with no failures."
        else:
            error_type = rng.choice(["ConnectionTimeoutError", "ValueError", "KeyError", "RuntimeError"])
            host = f"db-{rng.choice(['prod', 'staging'])}-{rng.randint(1, 3):02d}"
            lines = [(f"$ python {subject.split()[0]}_worker.py", "dim"),
                     ("Traceback (most recent call last):", "err"),
                     (f"  File \"{subject.split()[0]}_worker.py\", line {rng.randint(10, 200)}, in run", "dim"),
                     (f"{error_type}: could not connect to database (host={host})", "err")]
            caption = f"A background job for {subject} crashed with a {error_type} while connecting to {host}."
            sentiment = "negative"
    dots = "".join(f'<span class="dot" style="background:{c}"></span>'
                    for c in ("#FF5F56", "#FFBD2E", "#27C93F"))
    rows = "".join(f'<div class="{cls}">{t}</div>' for t, cls in lines)
    body = f'<div class="term"><div class="termbar">{dots}</div><div class="termbody">{rows}</div></div>'
    html = page_html(720, 210, body, CSS_TERMINAL)
    meta = dict(domain=domain, scenario=("deployment" if deploy else "background_job"),
                severity=("high" if sentiment == "negative" else None), status=sentiment, sentiment=sentiment,
                visible_text=[t for t, _ in lines], business_context=caption, key_entities=[version if deploy else subject])
    return html, [caption, caption.replace("The", "This", 1)], meta


CSS_BANNER = """
.banner { margin: 20px; padding: 20px 24px; border-radius: 8px; border-left: 5px solid; }
.code { font-size: 22px; font-weight: 800; }
.title { font-size: 14px; font-weight: 700; margin: 6px 0; }
.msg { font-size: 12.5px; }
"""


def build_banner(rng: random.Random):
    sentiment = weighted_sentiment(rng)
    service = rng.choice(SERVICES)
    if sentiment == "negative":
        code = rng.choice(["503", "502", "504"])
        color = "#C0392B"; bg = "#FDEDED"
        title = "Service Unavailable"
        message = f"{service} is temporarily unable to handle requests. Please try again later."
        caption = f"A {code} service unavailable error is affecting {service}."
    elif sentiment == "positive":
        code = "OK"
        color = "#27AE60"; bg = "#EAFAF1"
        title = "All Systems Operational"
        message = f"{service} is running normally with no reported issues."
        caption = f"{service} is fully operational with no reported issues."
    else:
        code = "WARN"
        color = "#E67E22"; bg = "#FEF5E7"
        title = "Degraded Performance"
        message = f"{service} is experiencing elevated response times but remains operational."
        caption = f"{service} is experiencing degraded performance but is still operational."
    body = f"""<div class="banner" style="border-color:{color};background:{bg}">
      <div class="code" style="color:{color}">{code}</div>
      <div class="title" style="color:{color}">{title}</div>
      <div class="msg">{message}</div></div>"""
    html = page_html(640, 220, body, CSS_BANNER)
    meta = dict(domain="IT", scenario="service_status", severity=("high" if sentiment == "negative" else None),
                status=sentiment, sentiment=sentiment, visible_text=[code, title, message],
                business_context=caption, key_entities=[service, code])
    return html, [caption, f"{title}: {message}"], meta


def build_crash(rng: random.Random):
    service = rng.choice(SERVICES)
    code = rng.choice(["ERR_4471", "ERR_2201", "ERR_9080"])
    n_users = rng.randint(50, 5000)
    duration = rng.randint(5, 90)
    cause = rng.choice(INCIDENT_CAUSES)
    color = "#C0392B"; bg = "#FDEDED"
    title = "Crash Report"
    message = f"{service} crashed unexpectedly (code {code}) — {n_users:,} users affected for {duration} min."
    body = f"""<div class="banner" style="border-color:{color};background:{bg}">
      <div class="code" style="color:{color}">{code}</div>
      <div class="title" style="color:{color}">{title}</div>
      <div class="msg">{message}</div></div>"""
    html = page_html(640, 220, body, CSS_BANNER)
    caption = f"A critical incident affects {service} (code {code}) caused by {cause}, impacting {n_users:,} users for {duration} minutes."
    meta = dict(domain="IT", scenario="production_incident", severity="high", status="negative",
                sentiment="negative", visible_text=[code, title, message],
                business_context=caption, key_entities=[service, code, f"{n_users} users"])
    return html, [caption, f"A production incident on {service} lasted {duration} minutes and affected {n_users:,} users."], meta


CSS_CHAT = """
.chatwrap { margin: 16px; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.12); border: 1px solid #ddd; }
.chathead { padding: 10px 16px; color: #fff; font-weight: 700; font-size: 13px; }
.msgs { padding: 14px 16px; }
.msg { display: flex; gap: 10px; margin-bottom: 14px; }
.avatar { width: 24px; height: 24px; border-radius: 50%; flex-shrink: 0; }
.author { font-weight: 700; font-size: 12.5px; }
.time { font-size: 10.5px; color: #999; margin-left: 6px; }
.text { font-size: 12.5px; margin-top: 2px; }
.footer { padding: 8px 16px; font-size: 11.5px; color: #777; font-style: italic; }
"""

CHAT_TOPICS = ["production deployment", "client onboarding", "marketing campaign", "sprint delivery",
               "budget approval", "database migration"]


def build_chat(rng: random.Random):
    platform = rng.choice(["slack", "teams"])
    people = rng.sample(PEOPLE, 2)
    sentiment = weighted_sentiment(rng)
    topic = rng.choice(CHAT_TOPICS)
    footer = None
    if sentiment == "negative":
        issue = rng.choice(["database connectivity issues", "an unexpected approval delay", "a critical bug"])
        delay = rng.randint(1, 5)
        messages = [(people[0], f"The {topic} failed again.", "09:44"),
                    (people[1], f"Looks like {issue}.", "09:46"),
                    (people[0], f"Can we still deliver on time?", "09:47"),
                    (people[1], f"Probably not, we need at least {delay} more days.", "09:48")]
        caption = f"The team reports a {topic} failure caused by {issue}, expecting a delay of at least {delay} days."
    elif sentiment == "positive":
        metric = rng.choice(["signups", "revenue", "conversion rate"])
        pct = rng.randint(8, 30)
        messages = [(people[0], f"{topic.capitalize()} is live!", "16:40"),
                    (people[1], f"Amazing — {metric} already up {pct}%!", "16:41")]
        caption = f"The team celebrates the successful {topic}, which already increased {metric} by {pct}%."
        footer = "3 reactions"
    else:
        new_time = rng.choice(["3pm", "10am tomorrow", "Friday morning"])
        messages = [(people[0], f"{topic.capitalize()} moved to {new_time}, everyone ok?", "10:02"),
                    (people[1], "Works for me, updating the calendar.", "10:04")]
        caption = f"The team confirms rescheduling the {topic} to {new_time}."
    header_color = "#4A154B" if platform == "slack" else "#464775"
    channel = rng.choice(CHANNELS)
    header_text = f"# {channel}" if platform == "slack" else "Teams — Direct Message"
    rows = "".join(
        f'<div class="msg"><span class="avatar" style="background:{header_color}"></span>'
        f'<div><span class="author">{a}</span><span class="time">{t}</span>'
        f'<div class="text">{txt}</div></div></div>' for a, txt, t in messages)
    footer_html = f'<div class="footer">{footer}</div>' if footer else ""
    body = f"""<div class="chatwrap"><div class="chathead" style="background:{header_color}">{header_text}</div>
    <div class="msgs">{rows}</div>{footer_html}</div>"""
    html = page_html(640, 340, body, CSS_CHAT)
    visible_text = [header_text] + [text for a, text, _ in messages]
    if footer:
        visible_text.append(footer)
    meta = dict(domain="Project Management", scenario=f"chat_{topic}".replace(" ", "_"),
                severity=("medium" if sentiment == "negative" else None), status=sentiment, sentiment=sentiment,
                visible_text=visible_text, business_context=caption,
                key_entities=[topic])
    return html, [caption, caption.replace("The team", "Team members", 1)], meta


CSS_CHART = """
.chartwrap { margin: 18px; }
.h1 { font-size: 15px; font-weight: 700; color: #172B4D; margin-bottom: 12px; }
"""


def build_bar_chart(rng: random.Random):
    domain, subject = rng.choice(DOMAIN_SUBJECTS)
    labels = rng.sample(["Eng", "Sales", "Marketing", "Ops", "Support", "Finance"], k=5)
    values = [rng.randint(20, 200) for _ in labels]
    max_v = max(values)
    bar_w = 90
    bars = ""
    for i, (lb, v) in enumerate(zip(labels, values)):
        h = int(v / max_v * 200)
        color = COLORS6[i % len(COLORS6)]
        x = 20 + i * (bar_w + 20)
        bars += (f'<rect x="{x}" y="{240 - h}" width="{bar_w}" height="{h}" fill="{color}"/>'
                 f'<text x="{x + bar_w/2}" y="{255}" font-size="11" text-anchor="middle">{lb}</text>'
                 f'<text x="{x + bar_w/2}" y="{235 - h}" font-size="11" text-anchor="middle">{v}</text>')
    best_i, worst_i = values.index(max_v), values.index(min(values))
    title = f"{subject.capitalize()} by Team"
    body = f"""<div class="chartwrap"><div class="h1">{title}</div>
    <svg width="600" height="270">{bars}</svg></div>"""
    html = page_html(640, 320, body, CSS_CHART)
    caption = (f"A bar chart comparing {subject} across teams — {labels[best_i]} leads with {max_v}, "
               f"while {labels[worst_i]} trails at {values[worst_i]}.")
    meta = dict(domain=domain, scenario=f"bar_{subject}".replace(" ", "_"), severity=None, status="comparison",
                sentiment="neutral",
                visible_text=[title] + [str(x) for pair in zip(labels, values) for x in pair],
                business_context=caption, key_entities=[labels[best_i], labels[worst_i]])
    return html, [caption, f"{labels[best_i]} performs best on {subject} ({max_v}), {labels[worst_i]} the lowest ({values[worst_i]})."], meta


def build_pie_chart(rng: random.Random):
    domain, subject = rng.choice(DOMAIN_SUBJECTS)
    labels = rng.sample(["Enterprise", "SMB", "Startup", "Government", "Partner"], k=4)
    raw = [rng.randint(10, 100) for _ in labels]
    total = sum(raw)
    sizes = [round(v / total * 100) for v in raw]
    cx, cy, r = 130, 130, 110
    import math
    start = 0.0
    slices = ""
    for i, (lb, pct) in enumerate(zip(labels, sizes)):
        angle = pct / 100 * 360
        x1 = cx + r * math.cos(math.radians(start - 90))
        y1 = cy + r * math.sin(math.radians(start - 90))
        x2 = cx + r * math.cos(math.radians(start + angle - 90))
        y2 = cy + r * math.sin(math.radians(start + angle - 90))
        large = 1 if angle > 180 else 0
        color = COLORS6[i % len(COLORS6)]
        slices += f'<path d="M{cx},{cy} L{x1:.1f},{y1:.1f} A{r},{r} 0 {large} 1 {x2:.1f},{y2:.1f} Z" fill="{color}"/>'
        start += angle
    legend = "".join(f'<div style="display:flex;align-items:center;gap:6px;font-size:11.5px;margin-bottom:4px;">'
                      f'<span style="width:10px;height:10px;background:{COLORS6[i % len(COLORS6)]};display:inline-block;border-radius:2px;"></span>'
                      f'{lb} ({pct}%)</div>' for i, (lb, pct) in enumerate(zip(labels, sizes)))
    top_i = sizes.index(max(sizes))
    title = f"{subject.capitalize()} Distribution"
    body = f"""<div class="chartwrap"><div class="h1">{title}</div>
    <div style="display:flex;gap:20px;align-items:center;">
      <svg width="260" height="260">{slices}</svg><div>{legend}</div></div></div>"""
    html = page_html(520, 320, body, CSS_CHART)
    caption = f"A pie chart showing {subject} distribution — {labels[top_i]} accounts for the largest share at {sizes[top_i]}%."
    meta = dict(domain=domain, scenario=f"pie_{subject}".replace(" ", "_"), severity=None, status="distribution",
                sentiment="neutral", visible_text=[title] + [f"{lb} ({pct}%)" for lb, pct in zip(labels, sizes)],
                business_context=caption, key_entities=[labels[top_i]])
    return html, [caption, f"{labels[top_i]} is the dominant segment for {subject}, at {sizes[top_i]}% of the total."], meta


def build_line_chart(rng: random.Random):
    domain, subject = rng.choice(DOMAIN_SUBJECTS)
    metric = rng.choice(["Revenue (K EUR)", "Customer Satisfaction (%)", "Server Incidents", "Active Users"])
    n = rng.choice([6, 8])
    trend = rng.choice(["up", "down", "spike"])
    base = rng.randint(50, 150)
    values = []
    for i in range(n):
        if trend == "up":
            values.append(base + i * rng.randint(4, 12))
        elif trend == "down":
            values.append(max(5, base - i * rng.randint(4, 12)))
        else:
            values.append(base + rng.randint(-5, 5))
    if trend == "spike":
        values[-1] = int(values[-2] * rng.uniform(2.5, 4))
    max_v, min_v = max(values), min(values)
    span = max(1, max_v - min_v)
    pts = []
    for i, v in enumerate(values):
        x = 20 + i * (560 / (n - 1))
        y = 220 - (v - min_v) / span * 180
        pts.append((x, y))
    polyline = " ".join(f"{x:.0f},{y:.0f}" for x, y in pts)
    dots = "".join(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="4" fill="#2196F3"/>' for x, y in pts)
    labels_svg = "".join(
        f'<text x="{x:.0f}" y="{y - 10:.0f}" font-size="11" text-anchor="middle">{v}</text>'
        for (x, y), v in zip(pts, values) if v in (values[0], values[-1], max_v, min_v))
    title = f"{metric} Trend"
    body = f"""<div class="chartwrap"><div class="h1">{title}</div>
    <svg width="600" height="240"><polyline points="{polyline}" fill="none" stroke="#2196F3" stroke-width="2.5"/>{dots}{labels_svg}</svg></div>"""
    html = page_html(640, 300, body, CSS_CHART)
    if trend == "up":
        caption = f"A line chart showing {metric.lower()} trending upward, from {values[0]} to {values[-1]}."
        sentiment = "positive"
    elif trend == "down":
        caption = f"A line chart showing {metric.lower()} trending downward, from {values[0]} to {values[-1]}."
        sentiment = "negative"
    else:
        caption = f"A line chart showing {metric.lower()} with an unusual spike to {values[-1]} in the last period."
        sentiment = "negative"
    labeled_values = sorted({values[0], values[-1], max_v, min_v})
    meta = dict(domain=domain, scenario=f"line_{trend}", severity=None, status=trend, sentiment=sentiment,
                visible_text=[title] + [str(v) for v in labeled_values], business_context=caption,
                key_entities=[str(values[0]), str(values[-1])])
    return html, [caption, caption.replace("A line chart showing", "The trend for")], meta


DASHBOARD_KPIS = {
    "Sales": ["Revenue", "Orders", "Customers"],
    "Marketing": ["Leads", "Conversion Rate", "Campaign Spend"],
    "Customer Service": ["Tickets Resolved", "CSAT Score", "Avg Response Time"],
    "Finance": ["Revenue", "Operating Costs", "Profit Margin"],
    "Operations": ["Delivery Time", "Inventory Level", "Order Accuracy"],
}
CSS_DASH = """
.dashwrap { margin: 18px; }
.h1 { font-size: 15px; font-weight: 700; color: #172B4D; margin-bottom: 14px; }
.kpis { display: flex; gap: 14px; margin-bottom: 12px; }
.kpi { flex: 1; padding: 14px; border-radius: 8px; background: #F8F9FA; border: 1px solid #eee; }
.kpiname { font-size: 11px; color: #777; }
.kpival { font-size: 20px; font-weight: 800; color: #172B4D; margin: 4px 0; }
.delta { font-size: 12px; font-weight: 700; }
.up { color: #27AE60; } .down { color: #C0392B; }
.status-line { padding: 10px 12px; border-radius: 6px; font-size: 12.5px; font-weight: 600; }
"""


def build_dashboard(rng: random.Random):
    domain = rng.choice(list(DASHBOARD_KPIS))
    kpi_names = DASHBOARD_KPIS[domain]
    deltas = []
    kpi_texts = []
    kpi_html = ""
    for name in kpi_names:
        pct = rng.randint(2, 25)
        direction = rng.choice(["up", "down"])
        deltas.append(direction)
        value = f"{rng.randint(10, 500)}{'K' if 'Revenue' in name or 'Spend' in name else ''}"
        arrow = "↑" if direction == "up" else "↓"
        cls = "up" if direction == "up" else "down"
        kpi_html += (f'<div class="kpi"><div class="kpiname">{name}</div><div class="kpival">{value}</div>'
                     f'<div class="delta {cls}">{arrow} {pct}%</div></div>')
        kpi_texts += [name, value, f"{arrow} {pct}%"]
    n_up = deltas.count("up")
    if n_up == len(kpi_names):
        status_color, status_bg, status_text, sentiment = "#27AE60", "#EAFAF1", "All KPIs trending positively", "positive"
    elif n_up == 0:
        status_color, status_bg, status_text, sentiment = "#C0392B", "#FDEDED", "Performance below target on all KPIs", "negative"
    else:
        status_color, status_bg, status_text, sentiment = "#E67E22", "#FEF5E7", "Mixed performance across KPIs", "neutral"
    title = f"{domain} Executive Dashboard"
    body = f"""<div class="dashwrap"><div class="h1">{title}</div><div class="kpis">{kpi_html}</div>
    <div class="status-line" style="background:{status_bg};color:{status_color}">{status_text}</div></div>"""
    html = page_html(720, 260, body, CSS_DASH)
    kpi_summary = ", ".join(f"{n} {d}" for n, d in zip(kpi_names, deltas))
    caption = f"The {domain.lower()} dashboard shows {status_text.lower()} — {kpi_summary}."
    meta = dict(domain=domain, scenario="kpi_dashboard", severity=("high" if sentiment == "negative" else None),
                status=sentiment, sentiment=sentiment, visible_text=[title] + kpi_texts + [status_text],
                business_context=caption, key_entities=kpi_names)
    return html, [caption, f"{domain} KPIs: {kpi_summary}. {status_text}."], meta


def build_table(rng: random.Random):
    projects = rng.sample(["Alpha", "Beta", "Gamma", "Delta", "Orion"], k=4)
    rows_meta = []
    rows_html = ""
    for p in projects:
        sentiment = weighted_sentiment(rng)
        status = rng.choice(STATUS_BY_SENTIMENT[sentiment])
        delay = rng.randint(1, 10) if sentiment == "negative" else 0
        rows_meta.append((p, status, delay, sentiment))
        rows_html += (f"<tr><td>{p}</td>"
                       f'<td><span class="status" style="background:{STATUS_COLOR[status]}">{status}</span></td>'
                       f"<td>{delay if delay else '-'} days</td></tr>")
    body = f"""<div class="wrap"><div class="h1">Project Status Overview</div>
    <table><tr><th>Project</th><th>Status</th><th>Delay</th></tr>{rows_html}</table></div>"""
    html = page_html(640, 280, body, CSS_TABLE)
    worst = max(rows_meta, key=lambda r: r[2])
    best = next((r for r in rows_meta if r[3] == "positive"), None)
    if worst[2] > 0 and best:
        caption = f"Project {worst[0]} is {worst[1].lower()} with a {worst[2]}-day delay, while project {best[0]} remains {best[1].lower()}."
        sentiment = "neutral"
    elif worst[2] > 0:
        caption = f"Project {worst[0]} is the most delayed, {worst[1].lower()} by {worst[2]} days."
        sentiment = "negative"
    else:
        caption = "All tracked projects are progressing without significant delays."
        sentiment = "positive"
    meta = dict(domain="Project Management", scenario="project_status_table", severity=None, status="mixed",
                sentiment=sentiment,
                visible_text=[cell for p, s, d, _ in rows_meta for cell in (p, s, f"{d if d else '-'} days")],
                business_context=caption, key_entities=[worst[0]])
    return html, [caption, caption.replace("Project", "The project", 1)], meta


CSS_EMAIL = """
.mail { margin: 16px; border-radius: 8px; overflow: hidden; border: 1px solid #ddd; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
.mailhead { padding: 14px 18px; background: #F5F5F5; }
.field { font-size: 11.5px; color: #666; }
.subject { font-size: 14px; font-weight: 700; margin: 4px 0; }
.mailbody { padding: 16px 18px; font-size: 12.5px; line-height: 1.7; color: #333; }
"""


def build_email(rng: random.Random):
    sender = rng.choice(PEOPLE)
    domain, subject_topic = rng.choice(DOMAIN_SUBJECTS)
    sentiment = weighted_sentiment(rng)
    if sentiment == "negative":
        pct = rng.randint(5, 30)
        subject = f"URGENT — {subject_topic.capitalize()} Issue"
        body_lines = [f"The {subject_topic} is down {pct}% versus target.", "Immediate action is required."]
        caption = f"An urgent email reports a {pct}% shortfall in {subject_topic}, requesting immediate action."
        bg, subj_color = "#FFF8E1", "#C62828"
    elif sentiment == "positive":
        pct = rng.randint(5, 30)
        subject = f"{subject_topic.capitalize()} — Results Update"
        body_lines = [f"{subject_topic.capitalize()} exceeded target by {pct}%.", "Great work from the whole team."]
        caption = f"An email reports that {subject_topic} exceeded target by {pct}%, highlighting a strong result."
        bg, subj_color = "white", "#222"
    else:
        subject = f"{subject_topic.capitalize()} — Weekly Update"
        body_lines = [f"Here is the weekly update on {subject_topic}.", "No major changes to report."]
        caption = f"A routine email provides a weekly status update on {subject_topic}."
        bg, subj_color = "white", "#222"
    body = f"""<div class="mail">
      <div class="mailhead" style="background:{bg}"><div class="field">From: {sender.lower().replace(' ', '.')}@company.com</div>
        <div class="subject" style="color:{subj_color}">{subject}</div>
        <div class="field">To: sarah.hafsi@company.com</div></div>
      <div class="mailbody">{'<br>'.join(body_lines)}</div></div>"""
    html = page_html(640, 210, body, CSS_EMAIL)
    meta = dict(domain=domain, scenario=f"email_{subject_topic}".replace(" ", "_"),
                severity=("medium" if sentiment == "negative" else None), status=sentiment, sentiment=sentiment,
                visible_text=[subject] + body_lines, business_context=caption, key_entities=[subject_topic])
    return html, [caption, caption.replace("An email", "A message", 1)], meta


CSS_DOCUMENT = """
.docwrap { margin: 18px; }
.dochead { padding: 16px 20px; border-radius: 8px 8px 0 0; background: #2C3E50; color: #fff; }
.dochead .h1 { font-size: 15px; font-weight: 700; letter-spacing: 0.4px; text-transform: uppercase; }
.docbody { padding: 18px 20px; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 8px 8px; }
.section { margin-bottom: 14px; }
.seclabel { font-size: 11px; font-weight: 700; color: #888; text-transform: uppercase; letter-spacing: 0.4px; margin-bottom: 3px; }
.secvalue { font-size: 13px; color: #222; }
"""

REPORT_TITLES = ["Monthly Operations Report", "Weekly Sales Summary", "Quarterly Finance Review",
                  "Customer Satisfaction Report", "Incident Postmortem", "HR Staffing Update"]


def build_document(rng: random.Random):
    domain, subject = rng.choice(DOMAIN_SUBJECTS)
    report_title = rng.choice(REPORT_TITLES)
    sentiment = weighted_sentiment(rng)
    pct = rng.randint(8, 35)
    if sentiment == "negative":
        summary = f"{subject.capitalize()} complaints increased by {pct}% during the last period."
        cause = rng.choice(["delayed deliveries in the northern region", "a staffing shortage in support",
                             "an unresolved technical defect", "a pricing change that confused customers"])
        finding = f"Main cause: {cause}."
        recommendation = rng.choice(["increase temporary capacity", "escalate to senior management",
                                      "launch a corrective action plan"])
        caption = f"The {report_title.lower()} shows a {pct}% increase in {subject} complaints, caused by {cause}, and recommends {recommendation}."
    elif sentiment == "positive":
        summary = f"{subject.capitalize()} performance improved by {pct}% during the last period."
        cause = rng.choice(["a successful process improvement initiative", "the new automation rollout",
                             "improved team coordination"])
        finding = f"Main driver: {cause}."
        recommendation = rng.choice(["continue the current approach", "scale the initiative to other teams",
                                      "document the process as best practice"])
        caption = f"The {report_title.lower()} shows a {pct}% improvement in {subject}, driven by {cause}, and recommends to {recommendation}."
    else:
        summary = f"{subject.capitalize()} remained stable during the last period, with no major change."
        finding = "No significant issues were identified."
        recommendation = "continue monitoring as usual"
        caption = f"The {report_title.lower()} shows a stable, routine update on {subject} with no major issues to report."
    body = f"""<div class="docwrap"><div class="dochead"><div class="h1">{report_title}</div></div>
    <div class="docbody">
      <div class="section"><div class="seclabel">Summary</div><div class="secvalue">{summary}</div></div>
      <div class="section"><div class="seclabel">Key finding</div><div class="secvalue">{finding}</div></div>
      <div class="section"><div class="seclabel">Recommended action</div><div class="secvalue">Recommendation: {recommendation}.</div></div>
    </div></div>"""
    html = page_html(640, 300, body, CSS_DOCUMENT)
    meta = dict(domain=domain, scenario=f"report_{subject}".replace(" ", "_"),
                severity=("medium" if sentiment == "negative" else None), status=sentiment, sentiment=sentiment,
                visible_text=[report_title, summary, finding, f"Recommendation: {recommendation}."],
                business_context=caption, key_entities=[subject, f"{pct}%"])
    return html, [caption, caption.replace("The", "This", 1)], meta


CSS_WORKFLOW = """
.wfwrap { margin: 20px; }
.wfhead { font-size: 15px; font-weight: 700; color: #172B4D; margin-bottom: 20px; }
.steps { display: flex; align-items: center; }
.step { flex: 1; padding: 14px; border-radius: 8px; border: 1.5px solid; text-align: center; }
.stepname { font-size: 13px; font-weight: 700; color: #222; margin-bottom: 4px; }
.stepstatus { font-size: 11px; font-weight: 700; letter-spacing: 0.3px; }
.connector { width: 24px; height: 2px; background: #ccc; flex-shrink: 0; }
.summary { margin-top: 18px; padding: 12px 14px; border-radius: 6px; background: #F0F1F5; font-size: 12.5px; font-weight: 600; color: #333; }
"""

WORKFLOW_PIPELINES = {
    "order fulfillment": ["Order", "Payment", "Validation", "Shipment"],
    "deployment pipeline": ["Build", "Test", "Deploy", "Verify"],
    "recruitment pipeline": ["Application", "Interview", "Offer", "Onboarding"],
    "support ticket flow": ["Received", "Triage", "Resolution", "Closed"],
}
STEP_STYLE = {
    "DONE": ("#EAFAF1", "#27AE60"),
    "FAILED": ("#FDEDED", "#C0392B"),
    "BLOCKED": ("#FDEDED", "#C0392B"),
    "WAITING": ("#FEF5E7", "#B9770E"),
    "IN PROGRESS": ("#EBF3FC", "#2980B9"),
}


def build_workflow(rng: random.Random):
    pipeline_name, steps = rng.choice(list(WORKFLOW_PIPELINES.items()))
    sentiment = weighted_sentiment(rng)
    statuses = []
    if sentiment == "negative":
        fail_idx = rng.randint(1, len(steps) - 2)
        for i in range(len(steps)):
            if i < fail_idx:
                statuses.append("DONE")
            elif i == fail_idx:
                statuses.append(rng.choice(["FAILED", "BLOCKED"]))
            else:
                statuses.append("WAITING")
        failed_step = steps[fail_idx]
        reason = rng.choice(["payment processing failed", "a validation error occurred",
                              "the required approval was not received", "an external service timed out"])
        caption = f"The {pipeline_name} workflow is blocked at {failed_step.lower()} because {reason}."
    elif sentiment == "positive":
        statuses = ["DONE"] * len(steps)
        caption = f"The {pipeline_name} workflow completed successfully, with all steps done."
    else:
        cut = rng.randint(1, len(steps) - 1)
        statuses = ["DONE"] * cut + ["IN PROGRESS"] + ["WAITING"] * (len(steps) - cut - 1)
        current_step = steps[cut]
        caption = f"The {pipeline_name} workflow is progressing, currently at the {current_step.lower()} stage."
    step_html = ""
    for i, (name, status) in enumerate(zip(steps, statuses)):
        bg, color = STEP_STYLE[status]
        step_html += f'<div class="step" style="background:{bg};border-color:{color}">' \
                      f'<div class="stepname">{name}</div><div class="stepstatus" style="color:{color}">{status}</div></div>'
        if i < len(steps) - 1:
            step_html += '<div class="connector"></div>'
    body = f"""<div class="wfwrap"><div class="wfhead">{pipeline_name.capitalize()} — Workflow Status</div>
    <div class="steps">{step_html}</div><div class="summary">{caption}</div></div>"""
    html = page_html(680, 260, body, CSS_WORKFLOW)
    header_text = f"{pipeline_name.capitalize()} — Workflow Status"
    visible_text = [header_text] + [x for n, s in zip(steps, statuses) for x in (n, s)] + [caption]
    meta = dict(domain="Operations", scenario=f"workflow_{pipeline_name}".replace(" ", "_"),
                severity=("high" if sentiment == "negative" else None), status=sentiment, sentiment=sentiment,
                visible_text=visible_text, business_context=caption,
                key_entities=steps)
    return html, [caption, caption.replace("The", "This", 1)], meta


GENERATORS = {
    ("ticket", "card"): build_ticket_card,
    ("ticket", "list"): build_ticket_list,
    ("ticket", "comments"): build_ticket_comments,
    ("error", "dialog"): build_error_dialog,
    ("error", "trace"): lambda rng: build_terminal(rng, deploy=False),
    ("error", "deploy_trace"): lambda rng: build_terminal(rng, deploy=True),
    ("error", "banner"): build_banner,
    ("error", "crash"): build_crash,
    ("chat", "conversation"): build_chat,
    ("chart", "bar"): build_bar_chart,
    ("chart", "pie"): build_pie_chart,
    ("chart", "line"): build_line_chart,
    ("dashboard", "dashboard"): build_dashboard,
    ("table", "table"): build_table,
    ("email", "email"): build_email,
    ("document", "report"): build_document,
    ("workflow", "pipeline"): build_workflow,
}


def assign_splits(n: int, rng: random.Random) -> list[str]:
    n_train = round(n * SPLIT_RATIOS["train"])
    n_val = round(n * SPLIT_RATIOS["val"])
    splits = ["train"] * n_train + ["val"] * n_val + ["test"] * (n - n_train - n_val)
    rng.shuffle(splits)
    return splits


def main(total: int):
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    weight_sum = sum(CATEGORY_WEIGHTS.values())
    manifest = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        for category, subtypes in CATEGORY_SUBTYPES.items():
            cat_weight = CATEGORY_WEIGHTS[category]
            category_total = max(len(subtypes), round(total * cat_weight / weight_sum))
            per_subtype = max(1, round(category_total / len(subtypes)))
            for subtype in subtypes:
                splits = assign_splits(per_subtype, rng)
                for i in range(per_subtype):
                    fname = f"{category}_{subtype}_{i:04d}.png"
                    fpath = IMAGES_DIR / fname
                    gen_fn = GENERATORS[(category, subtype)]
                    html, captions, meta = gen_fn(rng)
                    # width/height baked into html via page_html; extract from the style block
                    w = int(html.split("width: ")[1].split("px")[0])
                    h = int(html.split("height: ")[1].split("px")[0])
                    page.set_viewport_size({"width": w, "height": h})
                    page.set_content(html, wait_until="load")
                    page.screenshot(path=str(fpath))
                    row = {"file": f"images/{fname}", "category": category, "subtype": subtype,
                           "split": splits[i], "caption": captions[0], "captions": captions}
                    row.update(meta)
                    manifest.append(row)

        browser.close()

    with open(MANIFEST_JSONL, "w", encoding="utf-8") as f:
        for row in manifest:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    csv_fields = ["file", "category", "subtype", "domain", "sentiment", "severity", "status",
                  "scenario", "caption", "business_context", "split"]
    with open(MANIFEST_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(manifest)

    for split_name in ("train", "val", "test"):
        rows = [r for r in manifest if r["split"] == split_name]
        with open(OUTPUT_DIR / f"{split_name}.csv", "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    def counts_of(key):
        c = {}
        for row in manifest:
            v = row[key]
            c[v] = c.get(v, 0) + 1
        return c

    report = {
        "dataset_name": "InsightFlow Business Vision Dataset",
        "total_images": len(manifest),
        "generation_method": "programmatic HTML/CSS rendered via headless Chromium (Playwright), deterministic (seed=%d)" % SEED,
        "category_subtype": {c: [st for st in CATEGORY_SUBTYPES[c]] for c in CATEGORY_SUBTYPES},
        "counts_by_category": counts_of("category"),
        "counts_by_domain": counts_of("domain"),
        "counts_by_sentiment": counts_of("sentiment"),
        "counts_by_split": counts_of("split"),
        "captions_per_image": 2,
        "notes": [
            "100% synthetic, code-generated business screenshots — no AI image generation used.",
            "visible_text is a literal concatenation of the exact strings drawn on the page (OCR ground truth).",
            "No real company data or credentials are included.",
            "Sentiment is weighted ~35% negative / 35% neutral / 30% positive across categories to avoid a "
            "'business screenshot = problem' bias.",
            "The original 45-image Phase 0 benchmark set (benchmark_images/) is NOT included here and should "
            "be kept as an independent final test set.",
        ],
    }
    with open(OUTPUT_DIR / "dataset_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    readme = f"""# InsightFlow Business Vision Dataset

{len(manifest)} images synthétiques métier, générées par code (HTML/CSS rendu via Chromium headless,
Playwright) — déterministe, seed={SEED}. Aucune génération d'image par IA.

## Contenu
- `images/` — les fichiers PNG
- `manifest.jsonl` / `manifest.csv` — toutes les images avec métadonnées complètes
- `train.csv` / `val.csv` / `test.csv` — le même manifest, pré-découpé par split
- `dataset_report.json` — statistiques (catégories, domaines, sentiment, splits)

## Catégories
{chr(10).join(f"- **{c}** ({', '.join(CATEGORY_SUBTYPES[c])})" for c in CATEGORY_SUBTYPES)}

## Champs du manifest
`file, category, subtype, domain, sentiment, severity, status, scenario, caption, captions
(2 paraphrases), business_context, visible_text (= OCR ground truth littéral), key_entities, split`

## Notes
- Sentiment pondéré ~35% négatif / 35% neutre / 30% positif dans toutes les catégories.
- `visible_text` est une concaténation littérale des chaînes réellement dessinées dans la page —
  pas une reformulation — utilisable comme vérité terrain OCR exacte.
- Les 45 images du benchmark Phase 0 (`benchmark_images/`) sont volontairement exclues de ce
  dataset et doivent rester un test set final indépendant.
"""
    with open(OUTPUT_DIR / "README.md", "w", encoding="utf-8") as f:
        f.write(readme)

    print(f"[OK] {len(manifest)} images generees dans {IMAGES_DIR}")
    print(f"[OK] manifest : {MANIFEST_JSONL} / {MANIFEST_CSV}")
    print(f"[OK] splits : train.csv / val.csv / test.csv")
    print(f"[OK] rapport : dataset_report.json / README.md")
    for key in ("split", "category", "sentiment"):
        print(f"Repartition {key} :", counts_of(key))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--total", type=int, default=1500)
    args = parser.parse_args()
    main(args.total)
