"""
InsightFlow Executive — Fine-tuning Script
==========================================
Fine-tunes a HuggingFace sentiment model on the InsightFlow synthetic dataset.
Designed to run on Google Colab (free GPU) or locally.

Usage:
    # RoBERTa (English specialist)
    python ml/finetune.py --model roberta --lang en

    # XLM-RoBERTa (Multilingual FR+EN) ← recommended for production
    python ml/finetune.py --model xlm --lang full

    # Both models sequentially
    python ml/finetune.py --model both --lang full

Google Colab setup:
    !pip install transformers datasets torch scikit-learn accelerate evaluate
    !python ml/finetune.py --model xlm --lang full

Outputs saved to ml/models/:
    insightflow-roberta-v1/
    insightflow-xlm-roberta-v1/
"""

import argparse
import os
import random
import numpy as np
import csv
from datetime import datetime

# ── Config ────────────────────────────────────────────────────
MODELS = {
    "roberta": "cardiffnlp/twitter-roberta-base-sentiment-latest",
    "xlm":     "cardiffnlp/twitter-xlm-roberta-base-sentiment",
}

LABEL2ID = {"NEGATIVE": 0, "NEUTRAL": 1, "POSITIVE": 2}
ID2LABEL = {0: "NEGATIVE", 1: "NEUTRAL", 2: "POSITIVE"}

DATASET_DIR = os.path.join(os.path.dirname(__file__), "dataset")
MODELS_DIR  = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODELS_DIR, exist_ok=True)

SEED = 42
random.seed(SEED)
np.random.seed(SEED)


# ── Dataset loading ───────────────────────────────────────────

def load_csv_dataset(lang: str = "full") -> tuple[list[str], list[int]]:
    """Load synthetic dataset from CSV. Returns texts + integer labels."""
    file_map = {
        "en":   "insightflow_synthetic_en.csv",
        "fr":   "insightflow_synthetic_fr.csv",
        "full": "insightflow_synthetic_full.csv",
    }
    filename = file_map.get(lang, "insightflow_synthetic_en.csv")
    path = os.path.join(DATASET_DIR, filename)

    # Fallback si full n'existe pas encore
    if not os.path.exists(path):
        for fallback in ["insightflow_synthetic_en.csv", "insightflow_synthetic.csv"]:
            fp = os.path.join(DATASET_DIR, fallback)
            if os.path.exists(fp):
                path = fp
                print(f"[Data] Fallback to {fallback}")
                break

    print(f"[Data] Loading {path}...")
    texts, labels = [], []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            content = row.get("content", "").strip()
            label   = row.get("sentiment_label", "").strip()
            if content and label in LABEL2ID:
                texts.append(content[:512])
                labels.append(LABEL2ID[label])

    print(f"[Data] {len(texts)} samples loaded.")
    from collections import Counter
    dist = Counter(labels)
    for lid, count in sorted(dist.items()):
        print(f"       {ID2LABEL[lid]:<12} {count:>4} ({count/len(labels)*100:.1f}%)")

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

def finetune(model_key: str, lang: str):
    import torch
    from transformers import (
        AutoTokenizer, AutoModelForSequenceClassification,
        TrainingArguments, Trainer, DataCollatorWithPadding,
        EarlyStoppingCallback,
    )
    from datasets import Dataset
    import evaluate

    model_name  = MODELS[model_key]
    output_name = f"insightflow-{model_key}-v1"
    output_dir  = os.path.join(MODELS_DIR, output_name)

    print(f"\n{'='*65}")
    print(f"  Fine-tuning: {model_name}")
    print(f"  Language   : {lang}")
    print(f"  Output     : {output_dir}")
    print(f"{'='*65}\n")

    # ── Load data ─────────────────────────────────────────────
    texts, labels = load_csv_dataset(lang)
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
        num_labels=3,
        id2label=ID2LABEL,
        label2id=LABEL2ID,
        ignore_mismatched_sizes=True,
    )

    # ── Class weights (handle imbalance) ──────────────────────
    from collections import Counter
    counts    = Counter(y_train)
    total     = len(y_train)
    weights   = [total / (3 * counts[i]) for i in range(3)]
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


# ── Main ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="InsightFlow Fine-tuning")
    parser.add_argument("--model", choices=["roberta", "xlm", "both"], default="xlm",
                        help="Model to fine-tune (default: xlm)")
    parser.add_argument("--lang",  choices=["en", "fr", "full"],       default="full",
                        help="Dataset language (default: full = EN+FR)")
    args = parser.parse_args()

    print(f"\n{'='*65}")
    print(f"  InsightFlow Executive — Fine-tuning Pipeline")
    print(f"  Model  : {args.model} | Language : {args.lang}")
    print(f"{'='*65}")

    results = {}
    if args.model == "both":
        results["roberta"] = finetune("roberta", args.lang)
        results["xlm"]     = finetune("xlm",     args.lang)

        # Comparison table
        print(f"\n{'='*65}")
        print(f"  Fine-tuning Results Comparison")
        print(f"{'='*65}")
        for name, r in results.items():
            print(f"  {MODELS[name]}")
            print(f"    Accuracy : {r['eval_accuracy']*100:.2f}%")
            print(f"    F1-macro : {r['eval_f1_macro']*100:.2f}%\n")
    else:
        finetune(args.model, args.lang)


if __name__ == "__main__":
    main()
