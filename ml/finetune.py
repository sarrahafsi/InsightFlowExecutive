"""
InsightFlow Executive — Fine-tuning Script
==========================================
Fine-tunes HuggingFace models on the InsightFlow synthetic dataset.
Designed to run on Google Colab (free GPU) or locally.

Tasks:
    sentiment  — 3 classes : POSITIVE / NEUTRAL / NEGATIVE
    emotion    — 5 classes : frustration / concern / urgency / neutral / satisfaction

Usage:
    # Sentiment — XLM-RoBERTa (FR+EN) ← recommended
    python ml/finetune.py --task sentiment --model xlm --lang full

    # Sentiment — RoBERTa (English specialist)
    python ml/finetune.py --task sentiment --model roberta --lang en

    # Emotion — j-hartmann distilRoBERTa
    python ml/finetune.py --task emotion --lang full

Google Colab setup:
    !pip install transformers datasets torch scikit-learn accelerate evaluate
    !python ml/finetune.py --task sentiment --model xlm --lang full
    !python ml/finetune.py --task emotion --lang full

Outputs saved to ml/models/:
    insightflow-sentiment-xlm-v1/
    insightflow-sentiment-roberta-v1/
    insightflow-emotion-v1/
"""

import argparse
import os
import random
import numpy as np
import csv
from datetime import datetime

# ── Config ────────────────────────────────────────────────────
# ── Sentiment models ──────────────────────────────────────────
SENTIMENT_MODELS = {
    "roberta": "cardiffnlp/twitter-roberta-base-sentiment-latest",
    "xlm":     "cardiffnlp/twitter-xlm-roberta-base-sentiment",
}

SENTIMENT_LABEL2ID = {"NEGATIVE": 0, "NEUTRAL": 1, "POSITIVE": 2}
SENTIMENT_ID2LABEL = {0: "NEGATIVE", 1: "NEUTRAL", 2: "POSITIVE"}

# ── Emotion model ──────────────────────────────────────────────
EMOTION_MODEL = "j-hartmann/emotion-english-distilroberta-base"

EMOTION_LABEL2ID = {
    "frustration":  0,
    "concern":      1,
    "urgency":      2,
    "neutral":      3,
    "satisfaction": 4,
}
EMOTION_ID2LABEL = {v: k for k, v in EMOTION_LABEL2ID.items()}

# Keep for backward compat
MODELS   = SENTIMENT_MODELS
LABEL2ID = SENTIMENT_LABEL2ID
ID2LABEL = SENTIMENT_ID2LABEL

DATASET_DIR = os.path.join(os.path.dirname(__file__), "dataset")
MODELS_DIR  = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODELS_DIR, exist_ok=True)

SEED = 42
random.seed(SEED)
np.random.seed(SEED)


# ── Dataset loading ───────────────────────────────────────────

def load_csv_dataset(lang: str = "full", task: str = "sentiment") -> tuple[list[str], list[int]]:
    """
    Charge le dataset depuis les fichiers nettoyés (preprocess.py) si disponibles,
    sinon fallback sur le dataset brut.
    """
    label_col = "sentiment_label" if task == "sentiment" else "emotion_label"
    label2id  = SENTIMENT_LABEL2ID if task == "sentiment" else EMOTION_LABEL2ID

    # Priorité : fichiers nettoyés (produits par preprocess.py)
    clean_train = os.path.join(DATASET_DIR, f"clean_{task}_train.csv")
    clean_val   = os.path.join(DATASET_DIR, f"clean_{task}_val.csv")
    if os.path.exists(clean_train):
        print(f"[Data] Fichiers nettoyés détectés → lecture de clean_{task}_*.csv")
        texts, labels = [], []
        for fpath in [clean_train, clean_val]:
            with open(fpath, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    content = (row.get("content_clean") or row.get("content", "")).strip()
                    label   = row.get(label_col, "").strip()
                    if content and label in label2id:
                        texts.append(content[:512])
                        labels.append(label2id[label])
        print(f"[Data] {len(texts)} samples chargés (train+val nettoyés)")
        return texts, labels

    # Fallback : fichier brut
    file_map = {
        "en":   "insightflow_synthetic_en.csv",
        "fr":   "insightflow_synthetic_fr.csv",
        "full": "insightflow_synthetic_full.csv",
    }
    filename = file_map.get(lang, "insightflow_synthetic_en.csv")
    path = os.path.join(DATASET_DIR, filename)

    if not os.path.exists(path):
        for fallback in ["insightflow_synthetic_en.csv", "insightflow_synthetic.csv"]:
            fp = os.path.join(DATASET_DIR, fallback)
            if os.path.exists(fp):
                path = fp
                print(f"[Data] Fallback to {fallback}")
                break

    label_col  = "sentiment_label" if task == "sentiment" else "emotion_label"
    label2id   = SENTIMENT_LABEL2ID if task == "sentiment" else EMOTION_LABEL2ID

    print(f"[Data] Loading {path} (task={task})...")
    texts, labels = [], []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            content = row.get("content", "").strip()
            label   = row.get(label_col, "").strip()
            if content and label in label2id:
                texts.append(content[:512])
                labels.append(label2id[label])

    print(f"[Data] {len(texts)} samples loaded.")
    id2label = SENTIMENT_ID2LABEL if task == "sentiment" else EMOTION_ID2LABEL
    from collections import Counter
    dist = Counter(labels)
    for lid, count in sorted(dist.items()):
        print(f"       {id2label[lid]:<14} {count:>4} ({count/len(labels)*100:.1f}%)")

    return texts, labels


def split_dataset(texts, labels, test_size=0.2):
    """80% train / 20% test split, stratified."""
    from sklearn.model_selection import train_test_split
    return train_test_split(
        texts, labels,
        test_size=test_size,
        random_state=SEED,
        stratify=labels,
    )


# ── Fine-tuning ───────────────────────────────────────────────

def finetune(model_key: str, lang: str, task: str = "sentiment"):
    import torch
    from transformers import (
        AutoTokenizer, AutoModelForSequenceClassification,
        TrainingArguments, Trainer, DataCollatorWithPadding,
        EarlyStoppingCallback,
    )
    from datasets import Dataset
    import evaluate

    model_name  = SENTIMENT_MODELS[model_key]
    output_name = f"insightflow-sentiment-{model_key}-v1"
    output_dir  = os.path.join(MODELS_DIR, output_name)
    n_labels    = 3
    label2id    = SENTIMENT_LABEL2ID
    id2label    = SENTIMENT_ID2LABEL

    print(f"\n{'='*65}")
    print(f"  Fine-tuning: {model_name}")
    print(f"  Language   : {lang}")
    print(f"  Output     : {output_dir}")
    print(f"{'='*65}\n")

    # ── Load data ─────────────────────────────────────────────
    texts, labels = load_csv_dataset(lang, task=task)
    X_train, X_test, y_train, y_test = split_dataset(texts, labels)
    print(f"[Split] Train: {len(X_train)} | Test: {len(X_test)}")

    # ── Tokenizer ─────────────────────────────────────────────
    print(f"\n[Model] Loading tokenizer: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    def tokenize(batch):
        return tokenizer(batch["text"], truncation=True, max_length=128, padding=False)

    train_ds = Dataset.from_dict({"text": X_train, "label": y_train}).map(tokenize, batched=True)
    test_ds  = Dataset.from_dict({"text": X_test,  "label": y_test }).map(tokenize, batched=True)
    train_ds = train_ds.remove_columns(["text"])
    test_ds  = test_ds.remove_columns(["text"])

    # ── Model ─────────────────────────────────────────────────
    print(f"[Model] Loading model: {model_name}")
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=n_labels,
        id2label=id2label,
        label2id=label2id,
        ignore_mismatched_sizes=True,
    )

    # ── Class weights (handle imbalance) ──────────────────────
    from collections import Counter
    counts    = Counter(y_train)
    total     = len(y_train)
    weights   = [total / (n_labels * counts[i]) for i in range(n_labels)]
    class_w   = torch.tensor(weights, dtype=torch.float)
    print(f"[Class weights] {[round(w, 3) for w in weights]}")

    # ── Metrics ───────────────────────────────────────────────
    metric_acc = evaluate.load("accuracy")
    metric_f1  = evaluate.load("f1")

    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=-1)
        acc = metric_acc.compute(predictions=preds, references=labels)["accuracy"]
        f1  = metric_f1.compute(predictions=preds, references=labels, average="macro")["f1"]
        return {"accuracy": round(acc, 4), "f1_macro": round(f1, 4)}

    # ── Custom Trainer with class weights ─────────────────────
    class WeightedTrainer(Trainer):
        def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
            labels  = inputs.pop("labels")
            outputs = model(**inputs)
            logits  = outputs.logits
            loss_fn = torch.nn.CrossEntropyLoss(
                weight=class_w.to(logits.device)
            )
            loss = loss_fn(logits, labels)
            return (loss, outputs) if return_outputs else loss

    # ── Training arguments ────────────────────────────────────
    use_gpu = torch.cuda.is_available()
    print(f"[Device] {'GPU ✓' if use_gpu else 'CPU (slower)'}")

    args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=5,
        per_device_train_batch_size=16 if use_gpu else 8,
        per_device_eval_batch_size=32  if use_gpu else 16,
        learning_rate=2e-5,
        weight_decay=0.01,
        warmup_ratio=0.1,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1_macro",
        greater_is_better=True,
        logging_steps=50,
        fp16=use_gpu,
        seed=SEED,
        report_to="none",
    )

    # ── Train ─────────────────────────────────────────────────
    trainer = WeightedTrainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=test_ds,
        tokenizer=tokenizer,
        data_collator=DataCollatorWithPadding(tokenizer),
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )

    print(f"\n[Training] Starting fine-tuning...")
    trainer.train()

    # ── Final evaluation ──────────────────────────────────────
    print(f"\n[Evaluation] Final evaluation on test set...")
    results = trainer.evaluate()
    print(f"  Accuracy : {results['eval_accuracy']*100:.2f}%")
    print(f"  F1-macro : {results['eval_f1_macro']*100:.2f}%")

    # ── Save model ────────────────────────────────────────────
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)

    # Save results summary
    summary = {
        "model_base":    model_name,
        "model_name":    output_name,
        "language":      lang,
        "dataset_size":  len(texts),
        "train_size":    len(X_train),
        "test_size":     len(X_test),
        "eval_accuracy": results["eval_accuracy"],
        "eval_f1_macro": results["eval_f1_macro"],
        "trained_at":    datetime.utcnow().isoformat(),
    }
    import json
    with open(os.path.join(output_dir, "training_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n[Done] Model saved to: {output_dir}")
    print(f"{'='*65}")
    return results


# ── Emotion fine-tuning ───────────────────────────────────────

def finetune_emotion(lang: str = "full"):
    """Fine-tune j-hartmann distilRoBERTa on our 5 business emotion classes."""
    import torch
    from transformers import (
        AutoTokenizer, AutoModelForSequenceClassification,
        TrainingArguments, Trainer, DataCollatorWithPadding,
        EarlyStoppingCallback,
    )
    from datasets import Dataset
    import evaluate

    output_name = "insightflow-emotion-v1"
    output_dir  = os.path.join(MODELS_DIR, output_name)

    print(f"\n{'='*65}")
    print(f"  Fine-tuning: {EMOTION_MODEL}")
    print(f"  Task       : emotion (5 classes)")
    print(f"  Language   : {lang}")
    print(f"  Output     : {output_dir}")
    print(f"{'='*65}\n")

    texts, labels = load_csv_dataset(lang, task="emotion")
    if not texts:
        print("[Error] No emotion data found. Check emotion_label column.")
        return

    X_train, X_test, y_train, y_test = split_dataset(texts, labels)
    print(f"[Split] Train: {len(X_train)} | Test: {len(X_test)}")

    tokenizer = AutoTokenizer.from_pretrained(EMOTION_MODEL)

    def tokenize(batch):
        return tokenizer(batch["text"], truncation=True, max_length=128, padding=False)

    train_ds = Dataset.from_dict({"text": X_train, "label": y_train}).map(tokenize, batched=True)
    test_ds  = Dataset.from_dict({"text": X_test,  "label": y_test }).map(tokenize, batched=True)
    train_ds = train_ds.remove_columns(["text"])
    test_ds  = test_ds.remove_columns(["text"])

    model = AutoModelForSequenceClassification.from_pretrained(
        EMOTION_MODEL,
        num_labels=5,
        id2label=EMOTION_ID2LABEL,
        label2id=EMOTION_LABEL2ID,
        ignore_mismatched_sizes=True,
    )

    from collections import Counter
    counts  = Counter(y_train)
    total   = len(y_train)
    weights = [total / (5 * counts[i]) for i in range(5)]
    class_w = torch.tensor(weights, dtype=torch.float)
    print(f"[Class weights] {[round(w, 3) for w in weights]}")

    metric_acc = evaluate.load("accuracy")
    metric_f1  = evaluate.load("f1")

    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=-1)
        acc = metric_acc.compute(predictions=preds, references=labels)["accuracy"]
        f1  = metric_f1.compute(predictions=preds, references=labels, average="macro")["f1"]
        return {"accuracy": round(acc, 4), "f1_macro": round(f1, 4)}

    class WeightedTrainer(Trainer):
        def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
            labels  = inputs.pop("labels")
            outputs = model(**inputs)
            logits  = outputs.logits
            loss_fn = torch.nn.CrossEntropyLoss(weight=class_w.to(logits.device))
            loss = loss_fn(logits, labels)
            return (loss, outputs) if return_outputs else loss

    use_gpu = torch.cuda.is_available()
    print(f"[Device] {'GPU ✓' if use_gpu else 'CPU (slower)'}")

    args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=5,
        per_device_train_batch_size=16 if use_gpu else 8,
        per_device_eval_batch_size=32  if use_gpu else 16,
        learning_rate=2e-5,
        weight_decay=0.01,
        warmup_ratio=0.1,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1_macro",
        greater_is_better=True,
        logging_steps=50,
        fp16=use_gpu,
        seed=SEED,
        report_to="none",
    )

    trainer = WeightedTrainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=test_ds,
        tokenizer=tokenizer,
        data_collator=DataCollatorWithPadding(tokenizer),
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )

    print(f"\n[Training] Starting emotion fine-tuning...")
    trainer.train()

    results = trainer.evaluate()
    print(f"\n  Accuracy : {results['eval_accuracy']*100:.2f}%")
    print(f"  F1-macro : {results['eval_f1_macro']*100:.2f}%")

    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)

    import json
    summary = {
        "model_base":    EMOTION_MODEL,
        "model_name":    output_name,
        "task":          "emotion",
        "language":      lang,
        "dataset_size":  len(texts),
        "train_size":    len(X_train),
        "test_size":     len(X_test),
        "eval_accuracy": results["eval_accuracy"],
        "eval_f1_macro": results["eval_f1_macro"],
        "trained_at":    datetime.utcnow().isoformat(),
    }
    with open(os.path.join(output_dir, "training_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n[Done] Emotion model saved to: {output_dir}")
    print(f"{'='*65}")
    return results


# ── Main ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="InsightFlow Fine-tuning")
    parser.add_argument("--task",  choices=["sentiment", "emotion", "both"], default="sentiment",
                        help="Task: sentiment | emotion | both (default: sentiment)")
    parser.add_argument("--model", choices=["roberta", "xlm", "both"], default="xlm",
                        help="Sentiment model (default: xlm) — ignored for emotion task")
    parser.add_argument("--lang",  choices=["en", "fr", "full"], default="full",
                        help="Dataset language (default: full = EN+FR)")
    args = parser.parse_args()

    print(f"\n{'='*65}")
    print(f"  InsightFlow Executive — Fine-tuning Pipeline")
    print(f"  Task   : {args.task} | Model : {args.model} | Lang : {args.lang}")
    print(f"{'='*65}")

    if args.task == "emotion":
        finetune_emotion(args.lang)

    elif args.task == "both":
        if args.model == "both":
            finetune("roberta", args.lang)
            finetune("xlm",     args.lang)
        else:
            finetune(args.model, args.lang)
        finetune_emotion(args.lang)

    else:  # sentiment
        if args.model == "both":
            finetune("roberta", args.lang)
            finetune("xlm",     args.lang)
        else:
            finetune(args.model, args.lang)


if __name__ == "__main__":
    main()
