"""
Fine-tuning BLIP-base + LoRA — InsightFlow Executive PFE
===========================================================
Conçu pour tourner sur Google Colab (GPU T4 gratuit). Protocole issu de la
discussion PFE : LoRA uniquement sur le text_decoder (query/value des
couches d'attention), vision encoder totalement gelé, LR faible, peu
d'epochs, early stopping sur la validation loss — pour limiter à la fois
l'overfitting (peu de données par rapport à un modèle from-scratch) et le
catastrophic forgetting (le modèle ne doit pas perdre sa capacité de
captioning générale hors du domaine InsightFlow).

Vérifié empiriquement (sans télécharger les poids, juste la config) que
"query"/"value" comme target_modules LoRA ne matchent QUE dans
text_decoder.bert.encoder.layer.*.(attention|crossattention).self —
le vision encoder utilise un layer "qkv" fusionné, donc aucun risque de
LoRA-adapter accidentellement l'encodeur visuel avec ce réglage.

Colab quickstart
-----------------
!pip install -q transformers peft accelerate pillow pandas
# dézipper/monter le dataset (finetune_dataset/) dans le répertoire courant
!python finetune_blip_lora.py --data_dir finetune_dataset --output_dir blip_insightflow_lora

Usage local (test rapide, CPU, sous-échantillon) :
    python finetune_blip_lora.py --data_dir finetune_dataset --output_dir /tmp/out \
        --max_train 8 --max_val 4 --epochs 1 --batch_size 2
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import torch
from torch.utils.data import Dataset, DataLoader
from PIL import Image
from transformers import BlipProcessor, BlipForConditionalGeneration
from peft import LoraConfig, get_peft_model, PeftModel


class CaptionDataset(Dataset):
    """Lit manifest.jsonl filtré par split. Choisit une des paraphrases de
    caption au hasard à chaque accès (léger anti-mémorisation littérale)."""

    def __init__(self, manifest_path: Path, images_root: Path, split: str, limit: int | None = None):
        self.images_root = images_root
        self.rows = []
        with open(manifest_path, encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                if row["split"] == split:
                    self.rows.append(row)
        if limit:
            self.rows = self.rows[:limit]

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, idx):
        row = self.rows[idx]
        image = Image.open(self.images_root / row["file"]).convert("RGB")
        captions = row.get("captions") or [row["caption"]]
        caption = random.choice(captions)
        return image, caption


def make_collate_fn(processor):
    def collate(batch):
        images, captions = zip(*batch)
        enc = processor(images=list(images), text=list(captions), return_tensors="pt", padding=True)
        return enc
    return collate


def build_model(lora_r: int, lora_alpha: int, lora_dropout: float, resume_from: str | None = None):
    processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
    model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")

    for p in model.parameters():
        p.requires_grad = False

    if resume_from:
        print(f"[INFO] reprise depuis le checkpoint LoRA existant : {resume_from}")
        model = PeftModel.from_pretrained(model, resume_from, is_trainable=True)
    else:
        lora_config = LoraConfig(
            r=lora_r,
            lora_alpha=lora_alpha,
            lora_dropout=lora_dropout,
            target_modules=["query", "value"],  # ne matche que text_decoder.*.attention.self.{query,value}
            bias="none",
        )
        model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    return processor, model


def run_epoch(model, loader, device, optimizer=None):
    training = optimizer is not None
    model.train(training)
    total_loss, n_batches = 0.0, 0
    for batch in loader:
        batch = {k: v.to(device) for k, v in batch.items()}
        with torch.set_grad_enabled(training):
            outputs = model(input_ids=batch["input_ids"], pixel_values=batch["pixel_values"],
                             attention_mask=batch.get("attention_mask"), labels=batch["input_ids"])
            loss = outputs.loss
            if training:
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
        total_loss += loss.item()
        n_batches += 1
    return total_loss / max(1, n_batches)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", type=str, default="finetune_dataset")
    parser.add_argument("--output_dir", type=str, default="blip_insightflow_lora")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch_size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=3e-5)
    parser.add_argument("--lora_r", type=int, default=8)
    parser.add_argument("--lora_alpha", type=int, default=16)
    parser.add_argument("--lora_dropout", type=float, default=0.05)
    parser.add_argument("--patience", type=int, default=2, help="early stopping patience (epochs without val improvement)")
    parser.add_argument("--resume_from", type=str, default=None,
                         help="chemin vers un checkpoint LoRA existant (ex: blip_insightflow_lora/best) pour continuer l'entrainement au lieu de repartir de zero")
    parser.add_argument("--max_train", type=int, default=None, help="debug: cap train set size")
    parser.add_argument("--max_val", type=int, default=None, help="debug: cap val set size")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    torch.manual_seed(args.seed)

    data_dir = Path(args.data_dir)
    manifest_path = data_dir / "manifest.jsonl"
    images_root = data_dir
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[INFO] device = {device}")

    processor, model = build_model(args.lora_r, args.lora_alpha, args.lora_dropout, args.resume_from)
    model.to(device)

    train_ds = CaptionDataset(manifest_path, images_root, "train", limit=args.max_train)
    val_ds = CaptionDataset(manifest_path, images_root, "val", limit=args.max_val)
    print(f"[INFO] train={len(train_ds)} val={len(val_ds)}")

    collate = make_collate_fn(processor)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, collate_fn=collate)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, collate_fn=collate)

    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=args.lr)

    best_val_loss = float("inf")
    patience_counter = 0
    history = []
    start_epoch = 1

    history_path = output_dir / "training_history.json"
    if args.resume_from and history_path.exists():
        with open(history_path, encoding="utf-8") as f:
            history = json.load(f)
        if history:
            best_val_loss = min(h["val_loss"] for h in history)
            start_epoch = history[-1]["epoch"] + 1
            print(f"[INFO] historique repris : {len(history)} epochs precedents, "
                  f"meilleur val_loss={best_val_loss:.4f}, reprise a l'epoch {start_epoch}")

    for epoch in range(start_epoch, start_epoch + args.epochs):
        train_loss = run_epoch(model, train_loader, device, optimizer)
        val_loss = run_epoch(model, val_loader, device, optimizer=None)
        history.append({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss})
        print(f"[EPOCH {epoch}] train_loss={train_loss:.4f}  val_loss={val_loss:.4f}")

        model.save_pretrained(output_dir / f"epoch_{epoch}")
        print(f"[INFO] checkpoint de l'epoch {epoch} sauvegarde dans {output_dir / f'epoch_{epoch}'} "
              f"(garde pour pouvoir comparer plusieurs epochs sur Phase 0, le val_loss seul ne suffit pas)")

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            patience_counter = 0
            model.save_pretrained(output_dir / "best")
            print(f"[INFO] nouveau meilleur checkpoint (val_loss={val_loss:.4f}) sauvegarde dans {output_dir / 'best'}")
        else:
            patience_counter += 1
            print(f"[INFO] pas d'amelioration ({patience_counter}/{args.patience})")
            if patience_counter >= args.patience:
                print("[INFO] early stopping.")
                break

    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)
    print(f"[OK] termine. Meilleur val_loss={best_val_loss:.4f}. Checkpoint LoRA dans {output_dir / 'best'}")


if __name__ == "__main__":
    main()
