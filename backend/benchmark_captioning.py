"""
Benchmark image captioning — InsightFlow Executive PFE
Modèles  : ViT-GPT2, BLIP-base, GIT-base
Images   : 30 images synthétiques business (6 catégories × 5 types)
Métriques: BLEU, ROUGE-L, METEOR, CLIP Score, load_sec, inference_sec

Dépendances supplémentaires (à installer une fois) :
    pip install nltk rouge-score
"""

import time
import csv
import math
from pathlib import Path
from collections import defaultdict

import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from PIL import Image

# ── Métriques NLP ────────────────────────────────────────────────────────────
import nltk
from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
from nltk.translate.meteor_score import meteor_score
from rouge_score import rouge_scorer as rouge_lib

# ── Modèles HuggingFace ──────────────────────────────────────────────────────
from transformers import (
    BlipProcessor, BlipForConditionalGeneration,
    AutoProcessor, AutoModelForCausalLM,
    VisionEncoderDecoderModel, ViTImageProcessor, AutoTokenizer,
    CLIPProcessor, CLIPModel,
)

# Téléchargement données NLTK (silencieux après le 1er lancement)
for pkg in ("punkt", "wordnet", "omw-1.4", "punkt_tab"):
    nltk.download(pkg, quiet=True)

# ── Config ───────────────────────────────────────────────────────────────────
IMAGES_DIR   = Path(__file__).parent / "benchmark_images"
RESULTS_FILE = Path(__file__).parent / "benchmark_results.csv"
DEVICE       = "cuda" if torch.cuda.is_available() else "cpu"

MODELS = {
    "ViT-GPT2": {"model_id": "nlpconnect/vit-gpt2-image-captioning", "approx_size_mb": 500},
    "BLIP-base": {"model_id": "Salesforce/blip-image-captioning-base", "approx_size_mb": 900},
    "GIT-base":  {"model_id": "microsoft/git-base",                    "approx_size_mb": 700},
}

# ── Captions de référence (ground truth pour BLEU/ROUGE/METEOR) ──────────────
REFERENCES = {
    # Bar charts
    "bar_revenue":    "a bar chart showing monthly revenue in thousands of euros over five months",
    "bar_headcount":  "a bar chart showing the number of employees per department in a company",
    "bar_sales":      "a bar chart comparing product sales figures across different product lines",
    "bar_costs":      "a bar chart displaying operational cost breakdown by category",
    "bar_growth":     "a bar chart showing year over year revenue growth percentage by region",
    "bar_comparison": "a grouped bar chart comparing first and second quarter performance metrics",
    # Pie charts
    "pie_budget":   "a pie chart showing budget allocation across five company departments",
    "pie_clients":  "a pie chart showing client distribution across different business segments",
    "pie_markets":  "a pie chart showing market share distribution by geographic region",
    "pie_expenses": "a pie chart displaying company expense breakdown across operational categories",
    "pie_teams":    "a pie chart showing team composition by role and function",
    "pie_products": "a pie chart showing revenue contribution by product line",
    # Line charts
    "line_satisfaction": "a line chart showing weekly customer satisfaction scores compared to a target line",
    "line_revenue":      "a line chart showing monthly revenue trend over twelve months",
    "line_traffic":      "a line chart showing daily website traffic over thirty days",
    "line_performance":  "a line chart showing team performance score evolution over several months",
    "line_forecast":     "a line chart comparing sales forecast versus actual sales over the year",
    "line_trend":        "a line chart showing an upward market growth trend over time",
    # Data tables
    "table_projects":   "a table showing project status report with project names status budget and progress percentage",
    "table_kpis":       "a table displaying key performance indicators with current values and targets",
    "table_teams":      "a table showing team performance metrics including scores and rankings",
    "table_budget":     "a table comparing planned budget versus actual spending by department",
    "table_risks":      "a table showing a risk register with risk levels probability and mitigation actions",
    "table_milestones": "a table listing project milestones with planned dates and completion status",
    # Email screenshots
    "email_formal":   "a screenshot of a formal business email with sender subject line and message body",
    "email_urgent":   "a screenshot of an urgent email requesting immediate action on a critical business matter",
    "email_report":   "a screenshot of a weekly performance report email with summary and key metrics",
    "email_meeting":  "a screenshot of a meeting invitation email with agenda date and list of participants",
    "email_alert":    "a screenshot of a performance alert email notifying about a significant drop in key metrics",
    "email_summary":  "a screenshot of an executive summary email with highlights decisions and next steps",
    # Technical error screenshots (added — target category from the multimodal spec, missing from the original set)
    "error_dialog":   "a screenshot of a windows application error dialog box with a warning icon and an error message",
    "error_trace":    "a screenshot of a terminal showing a python stack trace after a program crashed",
    "error_503":      "a screenshot of a browser error page showing a service unavailable message",
    "error_crash":    "a screenshot of a crash report showing an application error code and a send report button",
    "error_deploy":   "a screenshot of a deployment failure notification showing a critical error banner",
    # Ticket screenshots (Jira/ClickUp)
    "ticket_jira":     "a screenshot of a jira ticket card showing the ticket key title status and assignee",
    "ticket_clickup":  "a screenshot of a clickup task card showing the task title status and priority",
    "ticket_list":     "a screenshot of a list of tickets showing their status in a table",
    "ticket_comments":  "a screenshot of a ticket detail view with a title and a thread of comments",
    "ticket_blocked":   "a screenshot of an urgent blocked ticket showing a red blocked status flag",
    # Conversation screenshots (Slack/Teams)
    "chat_slack":      "a screenshot of a slack conversation thread with multiple messages from different users",
    "chat_teams":      "a screenshot of a microsoft teams conversation between two people",
    "chat_reactions":  "a screenshot of a chat message with emoji reactions from several users",
    "chat_file":       "a screenshot of a chat conversation where a user shared a file attachment",
    "chat_mention":    "a screenshot of a chat message where a user is mentioned by another user",
}


# ── Génération des 30 images de test ─────────────────────────────────────────
def generate_test_images() -> dict:
    IMAGES_DIR.mkdir(exist_ok=True)
    images = {}

    COLORS6 = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B2", "#937860"]

    # ── BAR CHARTS ─────────────────────────────────────────────────────────
    def bar(name, title, xlabel, ylabel, labels, values, color=None):
        fig, ax = plt.subplots(figsize=(7, 4))
        c = color or COLORS6[:len(labels)]
        bars = ax.bar(labels, values, color=c)
        ax.set_title(title, fontsize=13, fontweight="bold")
        ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
        for b, v in zip(bars, values):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + max(values) * 0.01,
                    str(v), ha="center", fontsize=9)
        ax.grid(axis="y", alpha=0.3)
        path = IMAGES_DIR / f"{name}.png"
        fig.savefig(path, dpi=100, bbox_inches="tight"); plt.close(fig)
        images[name] = path

    bar("bar_revenue",   "Monthly Revenue (K€)",          "Month",      "Revenue (K€)",
        ["Jan","Feb","Mar","Apr","May"], [120, 145, 98, 167, 134])
    bar("bar_headcount", "Headcount by Department",        "Department", "Employees",
        ["Eng","Sales","HR","Ops","IT"], [85, 42, 18, 33, 27])
    bar("bar_sales",     "Product Sales Comparison",       "Product",    "Units Sold",
        ["Alpha","Beta","Gamma","Delta"], [320, 215, 410, 178])
    bar("bar_costs",     "Operational Costs (K€)",         "Category",   "Cost (K€)",
        ["Infra","Labor","Marketing","Legal","Misc"], [80, 210, 55, 30, 22])
    bar("bar_growth",    "YoY Revenue Growth (%)",         "Region",     "Growth (%)",
        ["North","South","East","West","Central"], [12, 8, 21, 5, 15])

    # Grouped bar (Q1 vs Q2)
    fig, ax = plt.subplots(figsize=(8, 4))
    cats = ["Sales", "Support", "R&D", "Ops"]
    q1 = [88, 74, 92, 68]; q2 = [95, 81, 87, 79]
    x = np.arange(len(cats)); w = 0.35
    ax.bar(x - w/2, q1, w, label="Q1", color="#4C72B0")
    ax.bar(x + w/2, q2, w, label="Q2", color="#DD8452")
    ax.set_xticks(x); ax.set_xticklabels(cats)
    ax.set_title("Q1 vs Q2 Performance by Team", fontsize=13, fontweight="bold")
    ax.set_ylabel("Score"); ax.legend(); ax.grid(axis="y", alpha=0.3)
    path = IMAGES_DIR / "bar_comparison.png"
    fig.savefig(path, dpi=100, bbox_inches="tight"); plt.close(fig)
    images["bar_comparison"] = path

    # ── PIE CHARTS ─────────────────────────────────────────────────────────
    def pie(name, title, labels, sizes, colors=None):
        fig, ax = plt.subplots(figsize=(5, 5))
        c = colors or COLORS6[:len(labels)]
        ax.pie(sizes, labels=labels, colors=c, autopct="%1.1f%%", startangle=90)
        ax.set_title(title, fontsize=13, fontweight="bold")
        path = IMAGES_DIR / f"{name}.png"
        fig.savefig(path, dpi=100, bbox_inches="tight"); plt.close(fig)
        images[name] = path

    pie("pie_budget",   "Budget Allocation 2025",
        ["Marketing","R&D","Operations","HR","IT"], [30,25,20,15,10])
    pie("pie_clients",  "Client Segments",
        ["Enterprise","SMB","Startup","Gov"], [45, 30, 15, 10])
    pie("pie_markets",  "Market Share by Region",
        ["Europe","Americas","Asia","Africa","Other"], [38, 27, 22, 8, 5])
    pie("pie_expenses", "Expense Breakdown",
        ["Personnel","Tech","Travel","Office","Legal"], [55, 20, 10, 10, 5])
    pie("pie_teams",    "Team Composition by Role",
        ["Developers","Designers","PMs","QA","DevOps"], [40, 20, 15, 15, 10])
    pie("pie_products", "Revenue by Product Line",
        ["SaaS","Consulting","Licenses","Support"], [50, 25, 15, 10])

    # ── LINE CHARTS ────────────────────────────────────────────────────────
    def line_single(name, title, xlabel, ylabel, x, y, target=None, label="Actual"):
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.plot(x, y, marker="o", label=label, color="#2196F3", linewidth=2)
        if target:
            ax.axhline(target, linestyle="--", color="#F44336", label="Target", linewidth=1.5)
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
        ax.legend(); ax.grid(True, alpha=0.3)
        path = IMAGES_DIR / f"{name}.png"
        fig.savefig(path, dpi=100, bbox_inches="tight"); plt.close(fig)
        images[name] = path

    weeks = list(range(1, 13))
    line_single("line_satisfaction", "Customer Satisfaction Score (Weekly)",
                "Week", "Score",
                weeks, [80,85,78,92,88,95,102,98,110,108,115,120], target=90)
    line_single("line_revenue", "Monthly Revenue Trend (K€)",
                "Month", "Revenue (K€)",
                weeks, [100,110,105,120,115,130,125,140,135,150,145,160])
    line_single("line_traffic", "Daily Website Traffic",
                "Day", "Visits",
                list(range(1,31)),
                [1200,1350,1100,1400,1600,1500,1300,1700,1800,1650,
                 1900,2000,1850,2100,2200,2050,2300,2150,2400,2350,
                 2500,2450,2600,2550,2700,2650,2800,2750,2900,3000])
    line_single("line_performance", "Team Performance Score (Monthly)",
                "Month", "Score",
                list(range(1,10)), [70,73,75,72,78,80,82,85,88], target=80)

    # Forecast vs Actual
    fig, ax = plt.subplots(figsize=(7, 4))
    months = list(range(1, 13))
    actual   = [95,102,98,110,108,115,112,120,118,125,122,130]
    forecast = [100,105,105,108,110,112,115,118,120,122,125,128]
    ax.plot(months, actual,   marker="o", label="Actual",   color="#2196F3", linewidth=2)
    ax.plot(months, forecast, marker="s", label="Forecast", color="#FF9800", linewidth=2, linestyle="--")
    ax.fill_between(months, actual, forecast, alpha=0.1, color="#9C27B0")
    ax.set_title("Sales Forecast vs Actual", fontsize=12, fontweight="bold")
    ax.set_xlabel("Month"); ax.set_ylabel("Sales (K€)"); ax.legend(); ax.grid(True, alpha=0.3)
    path = IMAGES_DIR / "line_forecast.png"
    fig.savefig(path, dpi=100, bbox_inches="tight"); plt.close(fig)
    images["line_forecast"] = path

    line_single("line_trend", "Market Growth Trend",
                "Quarter", "Index",
                list(range(1, 9)), [100,108,115,125,132,142,150,162])

    # ── DATA TABLES ────────────────────────────────────────────────────────
    def data_table(name, title, headers, rows, header_color="#2C3E50"):
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.axis("off")
        tbl = ax.table(cellText=rows, colLabels=headers, loc="center", cellLoc="center")
        tbl.auto_set_font_size(False); tbl.set_fontsize(10); tbl.scale(1.3, 1.8)
        for (r, c), cell in tbl.get_celld().items():
            if r == 0:
                cell.set_facecolor(header_color)
                cell.set_text_props(color="white", fontweight="bold")
            elif r % 2 == 0:
                cell.set_facecolor("#F8F9FA")
        ax.set_title(title, fontsize=12, fontweight="bold", pad=20)
        path = IMAGES_DIR / f"{name}.png"
        fig.savefig(path, dpi=100, bbox_inches="tight"); plt.close(fig)
        images[name] = path

    data_table("table_projects", "Project Status Report",
        ["Project","Status","Budget","Progress"],
        [["Alpha","On Track","50K€","75%"],["Beta","Delayed","30K€","40%"],
         ["Gamma","Completed","20K€","100%"],["Delta","At Risk","80K€","55%"]])

    data_table("table_kpis", "Key Performance Indicators",
        ["KPI","Target","Actual","Status"],
        [["Revenue","1.2M€","1.35M€","✓"],["NPS",">50","62","✓"],
         ["Churn","<5%","3.2%","✓"],["Uptime","99.9%","99.7%","⚠"]])

    data_table("table_teams", "Team Performance Q2",
        ["Team","Score","Rank","Trend"],
        [["Engineering","92","1","↑"],["Product","85","2","→"],
         ["Sales","78","3","↑"],["Support","71","4","↓"]])

    data_table("table_budget", "Budget vs Actual by Department",
        ["Department","Budget (K€)","Actual (K€)","Variance"],
        [["Engineering","200","185","-7.5%"],["Marketing","80","92","+15%"],
         ["Operations","120","118","-1.7%"],["HR","50","48","-4%"]])

    data_table("table_risks", "Risk Register",
        ["Risk","Level","Probability","Mitigation"],
        [["Data breach","High","15%","Encryption"],["Key staff loss","Medium","25%","Retention plan"],
         ["Vendor delay","Low","30%","Multi-vendor"],["Regulation change","Medium","20%","Legal review"]])

    data_table("table_milestones", "Project Milestones",
        ["Milestone","Planned","Actual","Status"],
        [["MVP Launch","Jan 15","Jan 18","Delayed"],["Beta Release","Mar 01","Mar 01","On Time"],
         ["GA Launch","Jun 01","—","Pending"],["v2.0 Planning","Aug 01","—","Pending"]])

    # ── EMAIL SCREENSHOTS ──────────────────────────────────────────────────
    def email_img(name, sender, subject, body_lines, urgent=False):
        fig, ax = plt.subplots(figsize=(8, 5.5))
        ax.set_xlim(0, 10); ax.set_ylim(0, 8); ax.axis("off")
        bg = "#FFF8E1" if urgent else "white"
        ax.add_patch(mpatches.FancyBboxPatch((0.2, 0.2), 9.6, 7.6,
            boxstyle="round,pad=0.1", facecolor=bg, edgecolor="#CCCCCC", linewidth=1))
        header_color = "#FFECB3" if urgent else "#F5F5F5"
        ax.add_patch(mpatches.FancyBboxPatch((0.2, 6.5), 9.6, 1.3,
            boxstyle="square", facecolor=header_color, edgecolor="#DDDDDD", linewidth=0.5))
        ax.text(0.5, 7.4, f"From: {sender}", fontsize=9, color="#555555")
        subj_color = "#C62828" if urgent else "#222222"
        ax.text(0.5, 7.0, f"Subject: {subject}", fontsize=10, fontweight="bold", color=subj_color)
        ax.text(0.5, 6.55, "To: sarah.hafsi@company.com", fontsize=9, color="#777777")
        y = 6.1
        for line in body_lines:
            ax.text(0.5, y, line, fontsize=9.5, color="#333333")
            y -= 0.45
        path = IMAGES_DIR / f"{name}.png"
        fig.savefig(path, dpi=100, bbox_inches="tight"); plt.close(fig)
        images[name] = path

    email_img("email_formal", "john.doe@company.com",
        "Q2 Financial Results — For Review",
        ["Dear Sarah,",
         "Please find attached the Q2 financial report.",
         "Revenue exceeded target by 12% — EBITDA margin: 18%.",
         "Key actions required before board meeting on July 5th.",
         "Best regards, John Doe — CFO"])

    email_img("email_urgent", "cto@company.com",
        "⚠ URGENT — Production Outage Detected",
        ["Sarah,",
         "Production is DOWN since 14:32. 3,200 users affected.",
         "Root cause: DB connection pool exhausted.",
         "ETA to fix: 45 min. War room started.",
         "Action needed: Approve emergency rollback NOW.",
         "— DevOps Team"],
        urgent=True)

    email_img("email_report", "analytics@company.com",
        "Weekly Performance Report — Week 24",
        ["Hi Sarah,",
         "Weekly highlights:",
         "• Revenue: 312K€ (+8% vs last week)",
         "• Active users: 14,200 (+3%)",
         "• Support tickets resolved: 98% SLA met",
         "Full dashboard: app.insightflow.io/dashboard"])

    email_img("email_meeting", "pa@company.com",
        "Executive Committee Meeting — Thursday 10:00",
        ["Dear Sarah,",
         "This is a reminder for the ExCom meeting.",
         "Date: Thursday June 19, 2025 at 10:00 AM",
         "Agenda: Q2 review, Budget reforecast, Hiring plan",
         "Participants: CEO, CFO, CTO, CMO",
         "Location: Boardroom B — Floor 3"])

    email_img("email_alert", "monitoring@insightflow.io",
        "⚠ Alert — NPS Score Dropped Below Threshold",
        ["Automated alert from InsightFlow,",
         "NPS score dropped to 38 (threshold: 50).",
         "Affected segment: Enterprise customers",
         "Period: Last 7 days",
         "Recommended action: Review recent support tickets.",
         "— InsightFlow Monitoring"])

    email_img("email_summary", "board@company.com",
        "Executive Summary — June 2025",
        ["Sarah,",
         "June 2025 executive summary:",
         "✓ Revenue: 1.35M€ (target: 1.2M€)",
         "✓ NPS: 62 — 3 new enterprise contracts signed",
         "⚠ Churn slightly elevated in SMB segment",
         "Next steps: Growth review July 2nd"])

    # ── TECHNICAL ERROR SCREENSHOTS ──────────────────────────────────────────
    def error_dialog_box(name, title, message, icon="⚠"):
        """Windows-style message box."""
        fig, ax = plt.subplots(figsize=(6, 3.2))
        ax.set_xlim(0, 10); ax.set_ylim(0, 5.3); ax.axis("off")
        ax.add_patch(mpatches.FancyBboxPatch((0.2, 0.2), 9.6, 5.0,
            boxstyle="square", facecolor="#F0F0F0", edgecolor="#888888", linewidth=1.2))
        ax.add_patch(mpatches.Rectangle((0.2, 4.6), 9.6, 0.6, facecolor="#C0392B", edgecolor="none"))
        ax.text(0.4, 4.9, title, fontsize=10, color="white", fontweight="bold", va="center")
        ax.text(1.0, 3.3, icon, fontsize=34, color="#C0392B")
        ax.text(2.2, 3.3, message, fontsize=9.5, color="#222222", va="center", wrap=True)
        ax.add_patch(mpatches.FancyBboxPatch((7.6, 0.6), 1.8, 0.7,
            boxstyle="round,pad=0.05", facecolor="#E0E0E0", edgecolor="#999999"))
        ax.text(8.5, 0.95, "OK", fontsize=9, ha="center", va="center")
        path = IMAGES_DIR / f"{name}.png"
        fig.savefig(path, dpi=100, bbox_inches="tight"); plt.close(fig)
        images[name] = path

    def terminal_trace(name, lines):
        """Dark terminal window with a stack trace."""
        fig, ax = plt.subplots(figsize=(8, 4.2))
        ax.set_xlim(0, 10); ax.set_ylim(0, 6); ax.axis("off")
        ax.add_patch(mpatches.FancyBboxPatch((0.1, 0.1), 9.8, 5.8,
            boxstyle="round,pad=0.05", facecolor="#1E1E1E", edgecolor="#333333"))
        for i, c in enumerate(("#FF5F56", "#FFBD2E", "#27C93F")):
            ax.add_patch(mpatches.Circle((0.4 + i * 0.3, 5.6), 0.08, facecolor=c, edgecolor="none"))
        y = 5.1
        for line in lines:
            color = "#FF6B6B" if line.lower().startswith(("traceback", "error", "exception")) else "#D4D4D4"
            ax.text(0.4, y, line, fontsize=8.5, color=color, family="monospace", va="center")
            y -= 0.42
        path = IMAGES_DIR / f"{name}.png"
        fig.savefig(path, dpi=100, bbox_inches="tight"); plt.close(fig)
        images[name] = path

    def error_banner(name, code, title, message):
        """Browser-style / notification error banner."""
        fig, ax = plt.subplots(figsize=(8, 3))
        ax.set_xlim(0, 10); ax.set_ylim(0, 4); ax.axis("off")
        ax.add_patch(mpatches.FancyBboxPatch((0.2, 0.2), 9.6, 3.6,
            boxstyle="round,pad=0.08", facecolor="#FDEDED", edgecolor="#C0392B", linewidth=1.2))
        ax.text(0.5, 3.1, code, fontsize=22, fontweight="bold", color="#C0392B")
        ax.text(0.5, 2.3, title, fontsize=12, fontweight="bold", color="#7B241C")
        ax.text(0.5, 1.5, message, fontsize=9.5, color="#333333")
        path = IMAGES_DIR / f"{name}.png"
        fig.savefig(path, dpi=100, bbox_inches="tight"); plt.close(fig)
        images[name] = path

    error_dialog_box("error_dialog", "Application Error",
        "The application has encountered an unexpected\nerror and needs to close.")

    terminal_trace("error_trace", [
        "$ python sync_worker.py",
        "Traceback (most recent call last):",
        '  File "sync_worker.py", line 42, in run',
        "    conn = db.connect(timeout=5)",
        "ConnectionTimeoutError: could not connect to database",
        "  after 5.0s (host=db-prod-01, port=5432)",
    ])

    error_banner("error_503", "503", "Service Unavailable",
        "The server is temporarily unable to handle the request. Please try again later.")

    error_banner("error_crash", "ERR_4471", "Application Crash Report",
        "Deployment worker crashed unexpectedly — send report to continue.")

    terminal_trace("error_deploy", [
        "$ deploy production --release v2.4.1",
        "Deployment failed",
        "Database connection timeout",
        "CRITICAL: rollback triggered automatically",
        "Contact on-call engineer immediately.",
    ])

    # ── TICKET SCREENSHOTS (Jira / ClickUp) ──────────────────────────────────
    def ticket_card(name, tool, key, title, status, assignee, priority,
                     status_color="#0052CC", extra_line=None):
        fig, ax = plt.subplots(figsize=(7.5, 3.2))
        ax.set_xlim(0, 10); ax.set_ylim(0, 4.2); ax.axis("off")
        ax.add_patch(mpatches.FancyBboxPatch((0.2, 0.2), 9.6, 3.8,
            boxstyle="round,pad=0.08", facecolor="white", edgecolor="#CCCCCC", linewidth=1))
        tool_color = "#0052CC" if tool == "jira" else "#7B68EE"
        ax.add_patch(mpatches.Rectangle((0.2, 3.6), 9.6, 0.4, facecolor=tool_color, edgecolor="none"))
        ax.text(0.4, 3.8, f"{tool.upper()}  {key}", fontsize=9, color="white",
                fontweight="bold", va="center")
        ax.text(0.4, 3.1, title, fontsize=11, fontweight="bold", color="#172B4D")
        ax.add_patch(mpatches.FancyBboxPatch((0.4, 2.3), 1.8, 0.5,
            boxstyle="round,pad=0.05", facecolor=status_color, edgecolor="none"))
        ax.text(1.3, 2.55, status, fontsize=8.5, color="white", ha="center", va="center", fontweight="bold")
        ax.text(2.6, 2.55, f"Priority: {priority}", fontsize=9, color="#555555", va="center")
        ax.add_patch(mpatches.Circle((0.65, 1.4), 0.28, facecolor="#8993A4", edgecolor="none"))
        ax.text(1.1, 1.4, f"Assignee: {assignee}", fontsize=9, color="#333333", va="center")
        if extra_line:
            ax.text(0.4, 0.7, extra_line, fontsize=8.5, color="#666666")
        path = IMAGES_DIR / f"{name}.png"
        fig.savefig(path, dpi=100, bbox_inches="tight"); plt.close(fig)
        images[name] = path

    ticket_card("ticket_jira", "jira", "SCRUM-231",
        "API rate limiting fails under load", "In Progress", "K. Haddad", "High",
        status_color="#0052CC")

    ticket_card("ticket_clickup", "clickup", "CU-88f2",
        "Update onboarding flow copy", "To Do", "S. Hafsi", "Normal",
        status_color="#7B68EE")

    def ticket_list_view(name, rows):
        fig, ax = plt.subplots(figsize=(8, 3.5))
        ax.axis("off")
        tbl = ax.table(cellText=rows, colLabels=["Key", "Title", "Status", "Priority"],
                        loc="center", cellLoc="center")
        tbl.auto_set_font_size(False); tbl.set_fontsize(9); tbl.scale(1.2, 1.7)
        for (r, c), cell in tbl.get_celld().items():
            if r == 0:
                cell.set_facecolor("#0052CC"); cell.set_text_props(color="white", fontweight="bold")
        path = IMAGES_DIR / f"{name}.png"
        fig.savefig(path, dpi=100, bbox_inches="tight"); plt.close(fig)
        images[name] = path

    ticket_list_view("ticket_list", [
        ["SCRUM-201", "Fix login redirect bug", "Done", "Low"],
        ["SCRUM-217", "Add export to CSV", "In Review", "Normal"],
        ["SCRUM-231", "API rate limiting fails", "In Progress", "High"],
        ["SCRUM-244", "Client onboarding delay", "Blocked", "Urgent"],
    ])

    def ticket_comments_view(name, key, title, comments):
        fig, ax = plt.subplots(figsize=(7.5, 4.2))
        ax.set_xlim(0, 10); ax.set_ylim(0, 6); ax.axis("off")
        ax.add_patch(mpatches.FancyBboxPatch((0.2, 0.2), 9.6, 5.6,
            boxstyle="round,pad=0.08", facecolor="white", edgecolor="#CCCCCC"))
        ax.text(0.4, 5.4, f"{key} — {title}", fontsize=10.5, fontweight="bold", color="#172B4D")
        y = 4.6
        for author, text in comments:
            ax.add_patch(mpatches.Circle((0.6, y), 0.22, facecolor="#8993A4", edgecolor="none"))
            ax.text(1.0, y + 0.15, author, fontsize=8.5, fontweight="bold", color="#333333")
            ax.text(1.0, y - 0.2, text, fontsize=8.5, color="#555555")
            y -= 1.0
        path = IMAGES_DIR / f"{name}.png"
        fig.savefig(path, dpi=100, bbox_inches="tight"); plt.close(fig)
        images[name] = path

    ticket_comments_view("ticket_comments", "SCRUM-217", "Add export to CSV", [
        ("K. Haddad", "Started implementation, PR incoming today."),
        ("S. Hafsi", "Please add unit tests before merging."),
        ("K. Haddad", "Tests added, ready for review."),
    ])

    ticket_card("ticket_blocked", "jira", "SCRUM-244",
        "Client onboarding delay — waiting on legal", "Blocked", "S. Hafsi", "Urgent",
        status_color="#C0392B", extra_line="⚑ Blocked 3 days — escalated to CEO")

    # ── CONVERSATION SCREENSHOTS (Slack / Teams) ─────────────────────────────
    def chat_mockup(name, platform, messages, extra_footer=None):
        fig, ax = plt.subplots(figsize=(7.5, 4.5))
        ax.set_xlim(0, 10); ax.set_ylim(0, 6.5); ax.axis("off")
        bg = "#F8F8F8" if platform == "slack" else "#EEF0FF"
        ax.add_patch(mpatches.FancyBboxPatch((0.2, 0.2), 9.6, 6.1,
            boxstyle="round,pad=0.08", facecolor=bg, edgecolor="#CCCCCC"))
        header_color = "#4A154B" if platform == "slack" else "#464775"
        ax.add_patch(mpatches.Rectangle((0.2, 5.8), 9.6, 0.5, facecolor=header_color, edgecolor="none"))
        ax.text(0.4, 6.05, f"# {platform}-channel" if platform == "slack" else "Teams — Direct Message",
                fontsize=9.5, color="white", fontweight="bold", va="center")
        y = 5.3
        for author, text, time_ in messages:
            ax.add_patch(mpatches.Circle((0.6, y), 0.22, facecolor=header_color, edgecolor="none"))
            ax.text(1.0, y + 0.12, f"{author}  ", fontsize=8.5, fontweight="bold", color="#222222")
            ax.text(1.0 + len(author) * 0.11 + 0.3, y + 0.12, time_, fontsize=7.5, color="#999999")
            ax.text(1.0, y - 0.22, text, fontsize=8.5, color="#333333")
            y -= 1.05
        if extra_footer:
            ax.text(0.4, 0.5, extra_footer, fontsize=8.5, color="#666666", style="italic")
        path = IMAGES_DIR / f"{name}.png"
        fig.savefig(path, dpi=100, bbox_inches="tight"); plt.close(fig)
        images[name] = path

    chat_mockup("chat_slack", "slack", [
        ("Karim Haddad", "Sprint review moved to 3pm, everyone ok?", "10:02"),
        ("Sarah Hafsi", "Works for me, updating the calendar invite.", "10:04"),
        ("Karim Haddad", "Thanks! Also pushed the fix for the API bug.", "10:06"),
    ])

    chat_mockup("chat_teams", "teams", [
        ("Karim Haddad", "Client asked to move the kickoff up a week.", "09:15"),
        ("Sarah Hafsi", "Let's confirm with the tech team before Friday.", "09:20"),
    ])

    chat_mockup("chat_reactions", "slack", [
        ("Sarah Hafsi", "Q2 numbers are in — we beat target by 12%! 🎉", "16:40"),
        ("Karim Haddad", "👍 👍 🎉 🔥  (4 reactions)", "16:41"),
    ])

    chat_mockup("chat_file", "teams", [
        ("Karim Haddad", "Sharing the updated budget spreadsheet.", "11:02"),
        ("Sarah Hafsi", "📎 budget_Q3_final.xlsx", "11:02"),
    ], extra_footer="1 file attached")

    chat_mockup("chat_mention", "slack", [
        ("Karim Haddad", "@Sarah Hafsi can you approve the deploy?", "14:10"),
        ("Sarah Hafsi", "Approved, go ahead.", "14:12"),
    ])

    print(f"[✓] {len(images)} images générées dans : {IMAGES_DIR}")
    return images


# ── Calcul des métriques NLP + CLIP ──────────────────────────────────────────
_rouge = rouge_lib.RougeScorer(["rougeL"], use_stemmer=True)
_smooth = SmoothingFunction().method1


def compute_nlp_metrics(hypothesis: str, reference: str) -> dict:
    hyp_tokens = nltk.word_tokenize(hypothesis.lower())
    ref_tokens  = nltk.word_tokenize(reference.lower())

    bleu  = round(sentence_bleu([ref_tokens], hyp_tokens, smoothing_function=_smooth), 4)
    rouge = round(_rouge.score(reference, hypothesis)["rougeL"].fmeasure, 4)
    try:
        meteor = round(meteor_score([ref_tokens], hyp_tokens), 4)
    except Exception:
        meteor = 0.0

    return {"bleu": bleu, "rouge_l": rouge, "meteor": meteor}


def load_clip():
    print("  Chargement CLIP (openai/clip-vit-base-patch32)...", end=" ", flush=True)
    t0 = time.time()
    processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(DEVICE)
    model.eval()
    print(f"{round(time.time()-t0, 2)}s")
    return processor, model


def compute_clip_score(clip_processor, clip_model, image_path: Path, caption: str) -> float:
    image = Image.open(image_path).convert("RGB")
    inputs = clip_processor(text=[caption], images=image, return_tensors="pt", padding=True).to(DEVICE)
    with torch.no_grad():
        img_feat  = clip_model.get_image_features(pixel_values=inputs["pixel_values"])
        txt_feat  = clip_model.get_text_features(
            input_ids=inputs["input_ids"], attention_mask=inputs["attention_mask"])
        img_feat  = img_feat / img_feat.norm(dim=-1, keepdim=True)
        txt_feat  = txt_feat / txt_feat.norm(dim=-1, keepdim=True)
        score     = max((img_feat * txt_feat).sum().item() * 100, 0)
    return round(score, 2)


# ── Loaders ──────────────────────────────────────────────────────────────────
def load_vit_gpt2():
    tok = AutoTokenizer.from_pretrained("nlpconnect/vit-gpt2-image-captioning")
    fe  = ViTImageProcessor.from_pretrained("nlpconnect/vit-gpt2-image-captioning")
    mdl = VisionEncoderDecoderModel.from_pretrained("nlpconnect/vit-gpt2-image-captioning").to(DEVICE)
    return {"model": mdl, "tokenizer": tok, "feature_extractor": fe}

def load_blip_base():
    proc = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
    mdl  = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base").to(DEVICE)
    return {"model": mdl, "processor": proc}

def load_git_base():
    proc = AutoProcessor.from_pretrained("microsoft/git-base")
    mdl  = AutoModelForCausalLM.from_pretrained("microsoft/git-base").to(DEVICE)
    return {"model": mdl, "processor": proc}


# ── Inférences ───────────────────────────────────────────────────────────────
def infer_vit_gpt2(loaded, image_path: Path) -> str:
    image = Image.open(image_path).convert("RGB")
    pv = loaded["feature_extractor"](images=[image], return_tensors="pt").pixel_values.to(DEVICE)
    ids = loaded["model"].generate(pv, max_length=30, num_beams=4)
    return loaded["tokenizer"].decode(ids[0], skip_special_tokens=True).strip()

def infer_blip_base(loaded, image_path: Path) -> str:
    image = Image.open(image_path).convert("RGB")
    inp = loaded["processor"](image, return_tensors="pt").to(DEVICE)
    out = loaded["model"].generate(**inp, max_new_tokens=50)
    return loaded["processor"].decode(out[0], skip_special_tokens=True).strip()

def infer_git_base(loaded, image_path: Path) -> str:
    image = Image.open(image_path).convert("RGB")
    pv  = loaded["processor"](images=image, return_tensors="pt").pixel_values.to(DEVICE)
    ids = loaded["model"].generate(pixel_values=pv, max_length=50)
    return loaded["processor"].batch_decode(ids, skip_special_tokens=True)[0].strip()


LOADERS   = {"ViT-GPT2": load_vit_gpt2, "BLIP-base": load_blip_base, "GIT-base": load_git_base}
INFERRERS = {"ViT-GPT2": infer_vit_gpt2, "BLIP-base": infer_blip_base, "GIT-base": infer_git_base}


# ── Benchmark principal ───────────────────────────────────────────────────────
def run_benchmark(images: dict, clip_processor, clip_model) -> list:
    results = []
    n = len(images)

    for model_name, meta in MODELS.items():
        print(f"\n{'='*65}")
        print(f"  {model_name}  (~{meta['approx_size_mb']} MB)  [{DEVICE.upper()}]")
        print(f"{'='*65}")

        print("  Chargement...", end=" ", flush=True)
        try:
            t0 = time.time()
            loaded = LOADERS[model_name]()
            load_sec = round(time.time() - t0, 2)
            print(f"{load_sec}s")
        except Exception as e:
            print(f"ERREUR : {e}")
            for img_name in images:
                results.append(_err(model_name, img_name, meta, str(e)))
            continue

        for idx, (img_name, img_path) in enumerate(images.items(), 1):
            print(f"  [{idx:02d}/{n}] {img_name:<25}", end=" ", flush=True)
            try:
                t0 = time.time()
                caption = INFERRERS[model_name](loaded, img_path)
                inf_sec = round(time.time() - t0, 2)

                ref = REFERENCES.get(img_name, "")
                nlp = compute_nlp_metrics(caption, ref) if ref else {"bleu": 0, "rouge_l": 0, "meteor": 0}
                clip_s = compute_clip_score(clip_processor, clip_model, img_path, caption)

                print(f"inf={inf_sec}s  BLEU={nlp['bleu']:.3f}  ROUGE-L={nlp['rouge_l']:.3f}"
                      f"  METEOR={nlp['meteor']:.3f}  CLIP={clip_s:.1f}")

                results.append({
                    "model": model_name, "image": img_name, "caption": caption,
                    "reference": ref,
                    "load_sec": load_sec, "inference_sec": inf_sec,
                    "total_first_image_sec": round(load_sec + inf_sec, 2) if idx == 1 else "",
                    "bleu": nlp["bleu"], "rouge_l": nlp["rouge_l"], "meteor": nlp["meteor"],
                    "clip_score": clip_s,
                    "approx_size_mb": meta["approx_size_mb"], "device": DEVICE, "error": "",
                })
            except Exception as e:
                print(f"ERREUR : {e}")
                results.append(_err(model_name, img_name, meta, str(e), load_sec))

        del loaded

    return results


def _err(model_name, img_name, meta, error, load_sec=-1):
    return {
        "model": model_name, "image": img_name, "caption": "", "reference": "",
        "load_sec": load_sec, "inference_sec": -1, "total_first_image_sec": "",
        "bleu": -1, "rouge_l": -1, "meteor": -1, "clip_score": -1,
        "approx_size_mb": meta["approx_size_mb"], "device": DEVICE, "error": error,
    }


# ── Sauvegarde CSV ────────────────────────────────────────────────────────────
def save_results(results: list):
    fields = [
        "model", "image", "caption", "reference",
        "load_sec", "inference_sec", "total_first_image_sec",
        "bleu", "rouge_l", "meteor", "clip_score",
        "approx_size_mb", "device", "error",
    ]
    with open(RESULTS_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(results)
    print(f"\n[✓] CSV sauvegardé : {RESULTS_FILE}")


# ── Résumé final ──────────────────────────────────────────────────────────────
def print_summary(results: list):
    metrics = defaultdict(lambda: defaultdict(list))
    for r in results:
        if r["inference_sec"] > 0:
            m = r["model"]
            metrics[m]["inf"].append(r["inference_sec"])
            metrics[m]["load"].append(r["load_sec"])
            if r["bleu"]       >= 0: metrics[m]["bleu"].append(r["bleu"])
            if r["rouge_l"]    >= 0: metrics[m]["rouge_l"].append(r["rouge_l"])
            if r["meteor"]     >= 0: metrics[m]["meteor"].append(r["meteor"])
            if r["clip_score"] >= 0: metrics[m]["clip"].append(r["clip_score"])

    def avg(lst): return round(sum(lst) / len(lst), 3) if lst else -1

    print(f"\n{'='*80}")
    print(f"  {'Modèle':<12} {'Load':>7} {'Inf moy':>8} {'BLEU':>7} {'ROUGE-L':>8} {'METEOR':>8} {'CLIP':>7} {'MB':>6}")
    print(f"{'='*80}")
    for model in MODELS:
        m = metrics[model]
        print(f"  {model:<12}"
              f"  {m['load'][0] if m['load'] else -1:>6}s"
              f"  {avg(m['inf']):>7}s"
              f"  {avg(m['bleu']):>7.3f}"
              f"  {avg(m['rouge_l']):>8.3f}"
              f"  {avg(m['meteor']):>8.3f}"
              f"  {avg(m['clip']):>7.1f}"
              f"  {MODELS[model]['approx_size_mb']:>5}MB")
    print(f"{'='*80}")
    print("""
  Légende :
  • Load      = chargement modèle en mémoire (1 fois au démarrage)
  • Inf moy   = temps moyen d'inférence par image
  • BLEU      = précision n-grams vs référence  (0→1, plus = mieux)
  • ROUGE-L   = rappel séquence la plus longue  (0→1, plus = mieux)
  • METEOR    = alignement sémantique           (0→1, plus = mieux)
  • CLIP      = alignement image↔texte          (0→100, plus = mieux)
    """)
    print(f"[i] Résultats complets → {RESULTS_FILE}")
    print("[i] Ouvre le CSV dans Excel pour les tableaux du rapport PFE.")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Device : {DEVICE.upper()}")

    print("\nÉtape 1/4 — Génération des 30 images de test...")
    images = generate_test_images()

    print("\nÉtape 2/4 — Chargement du modèle CLIP (métriques)...")
    clip_proc, clip_mdl = load_clip()

    print("\nÉtape 3/4 — Benchmark (téléchargement modèles au 1er lancement ~5-15 min)...")
    results = run_benchmark(images, clip_proc, clip_mdl)

    print("\nÉtape 4/4 — Sauvegarde...")
    save_results(results)
    print_summary(results)
