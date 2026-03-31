from __future__ import annotations

import argparse
import gc
import json
import math
import os
import re
import shutil
from pathlib import Path
from typing import Any

import orjson
import torch
import torch.distributed as dist
import torch.nn.functional as F
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training, set_peft_model_state_dict
from safetensors.torch import load_file as safe_load_file
from torch import nn
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.optim import AdamW
from torch.utils.data import DataLoader, Dataset, DistributedSampler
from tqdm.auto import tqdm
from transformers import AutoModelForImageTextToText, AutoProcessor, BitsAndBytesConfig, get_cosine_schedule_with_warmup

from vlm_rl.common import LABEL_TO_ID, SECONDARY_LABELS, build_classification_messages, load_pil_image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a discriminative Qwen3-VL classifier for six-scene classification")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--model-name", type=str, default="Qwen/Qwen3-VL-8B-Instruct")
    parser.add_argument("--max-train-samples", type=int, default=None)
    parser.add_argument("--max-eval-samples", type=int, default=None)
    parser.add_argument("--num-train-epochs", type=float, default=1.0)
    parser.add_argument("--max-steps", type=int, default=-1)
    parser.add_argument("--per-device-train-batch-size", type=int, default=1)
    parser.add_argument("--per-device-eval-batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--warmup-ratio", type=float, default=0.03)
    parser.add_argument("--logging-steps", type=int, default=10)
    parser.add_argument("--eval-steps", type=int, default=100)
    parser.add_argument("--save-steps", type=int, default=100)
    parser.add_argument("--save-total-limit", type=int, default=2)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--max-pixels", type=int, default=122880)
    parser.add_argument("--lora-r", type=int, default=8)
    parser.add_argument("--lora-alpha", type=int, default=16)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--tune-last-n-layers", type=int, default=8)
    parser.add_argument("--classifier-dropout", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=20260327)
    parser.add_argument("--resume-from-checkpoint", type=Path, default=None)
    parser.add_argument("--init-artifact-root", type=Path, default=None)
    parser.add_argument("--prompt-style", type=str, choices=["short", "standard"], default="short")
    parser.add_argument("--bf16", action="store_true")
    return parser.parse_args()


class JsonlDataset(Dataset):
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict[str, Any]:
        return self.rows[index]


class QwenVlClassificationCollator:
    def __init__(self, processor: Any, *, prompt_style: str) -> None:
        self.processor = processor
        self.messages = build_classification_messages(prompt_style)

    def __call__(self, features: list[dict[str, Any]]) -> dict[str, torch.Tensor]:
        images = [load_pil_image(item["image_path"]) for item in features]
        texts: list[str] = []
        for _ in features:
            texts.append(self.processor.apply_chat_template(self.messages, tokenize=False, add_generation_prompt=False))
        batch = self.processor(
            text=texts,
            images=images,
            padding=True,
            return_tensors="pt",
        )
        batch["labels"] = torch.tensor([LABEL_TO_ID[str(item["secondary_category"])] for item in features], dtype=torch.long)
        return batch


class Qwen3VLSceneClassifier(nn.Module):
    def __init__(self, args: argparse.Namespace, *, local_rank: int) -> None:
        super().__init__()
        compute_dtype = torch.bfloat16 if args.bf16 else torch.float16
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=compute_dtype,
        )
        backbone = AutoModelForImageTextToText.from_pretrained(
            args.model_name,
            trust_remote_code=True,
            torch_dtype=compute_dtype,
            quantization_config=bnb_config,
            device_map={"": local_rank},
            attn_implementation="sdpa",
        )
        backbone.config.use_cache = False
        backbone.gradient_checkpointing_enable()
        backbone = prepare_model_for_kbit_training(backbone)
        lora_config = LoraConfig(
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=args.lora_dropout,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        )
        self.backbone = get_peft_model(backbone, lora_config)
        freeze_early_lora_layers(
            self.backbone,
            total_layers=self.backbone.config.text_config.num_hidden_layers,
            keep_last_n=args.tune_last_n_layers,
        )
        hidden_size = int(self.backbone.config.text_config.hidden_size)
        self.dropout = nn.Dropout(args.classifier_dropout)
        final_device = self.backbone.get_base_model().lm_head.weight.device
        self.classifier = nn.Linear(hidden_size, len(SECONDARY_LABELS)).to(final_device)

    def forward(
        self,
        input_ids: torch.LongTensor,
        attention_mask: torch.Tensor,
        pixel_values: torch.Tensor | None = None,
        image_grid_thw: torch.LongTensor | None = None,
        labels: torch.LongTensor | None = None,
        **kwargs: Any,
    ) -> dict[str, torch.Tensor]:
        base_model = self.backbone.get_base_model()
        input_device = base_model.get_input_embeddings().weight.device
        input_ids = input_ids.to(input_device)
        attention_mask = attention_mask.to(input_device)
        if pixel_values is not None:
            pixel_values = pixel_values.to(input_device)
        if image_grid_thw is not None:
            image_grid_thw = image_grid_thw.to(input_device)
        outputs = base_model.model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            pixel_values=pixel_values,
            image_grid_thw=image_grid_thw,
            **kwargs,
        )
        hidden_states = outputs[0]
        batch_indices = torch.arange(hidden_states.size(0), device=hidden_states.device)
        last_token_indices = attention_mask.long().sum(dim=1).sub(1).clamp_min(0)
        pooled = hidden_states[batch_indices, last_token_indices]
        pooled = self.dropout(pooled.float())
        logits = self.classifier(pooled)
        loss = None
        if labels is not None:
            loss = F.cross_entropy(logits, labels.to(logits.device))
        return {"loss": loss, "logits": logits}

    def save_artifacts(self, output_dir: Path, processor: Any) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        self.backbone.save_pretrained(str(output_dir / "adapter"))
        processor.save_pretrained(str(output_dir / "adapter"))
        torch.save({"classifier": self.classifier.state_dict(), "labels": SECONDARY_LABELS}, output_dir / "classifier_head.pt")

    def load_artifacts(self, checkpoint_dir: Path) -> None:
        adapter_dir = checkpoint_dir / "adapter"
        if adapter_dir.exists():
            adapter_safetensors = adapter_dir / "adapter_model.safetensors"
            adapter_bin = adapter_dir / "adapter_model.bin"
            if adapter_safetensors.exists():
                peft_state = safe_load_file(str(adapter_safetensors))
            elif adapter_bin.exists():
                peft_state = torch.load(adapter_bin, map_location="cpu")
            else:
                peft_state = None
            if peft_state is not None:
                set_peft_model_state_dict(self.backbone, peft_state, adapter_name="default")
        classifier_path = checkpoint_dir / "classifier_head.pt"
        if classifier_path.exists():
            payload = torch.load(classifier_path, map_location="cpu")
            self.classifier.load_state_dict(payload["classifier"])


def freeze_early_lora_layers(model: nn.Module, *, total_layers: int, keep_last_n: int) -> None:
    min_trainable_layer = max(0, total_layers - keep_last_n)
    layer_pattern = re.compile(r"language_model\.layers\.(\d+)\.")
    for name, parameter in model.named_parameters():
        if "lora_" not in name:
            continue
        match = layer_pattern.search(name)
        if match and int(match.group(1)) < min_trainable_layer:
            parameter.requires_grad = False


def main() -> None:
    args = parse_args()
    local_rank, rank, world_size, distributed = setup_distributed()
    is_main = rank == 0
    set_seed(args.seed + rank)

    output_root = args.output_root.resolve()
    if is_main:
        output_root.mkdir(parents=True, exist_ok=True)
        save_json(output_root / "run_config.json", vars(args))
    barrier(distributed)

    train_rows = load_jsonl(args.data_root.resolve() / "train.jsonl")
    eval_rows = load_jsonl(args.data_root.resolve() / "dev.jsonl")
    if args.max_train_samples is not None:
        train_rows = train_rows[: args.max_train_samples]
    if args.max_eval_samples is not None:
        eval_rows = eval_rows[: args.max_eval_samples]

    processor = AutoProcessor.from_pretrained(args.model_name, trust_remote_code=True, max_pixels=args.max_pixels)
    collator = QwenVlClassificationCollator(processor, prompt_style=args.prompt_style)
    train_dataset = JsonlDataset(train_rows)
    eval_dataset = JsonlDataset(eval_rows)
    train_sampler = DistributedSampler(train_dataset, num_replicas=world_size, rank=rank, shuffle=True) if distributed else None
    train_loader = DataLoader(
        train_dataset,
        batch_size=args.per_device_train_batch_size,
        shuffle=train_sampler is None,
        sampler=train_sampler,
        num_workers=0,
        collate_fn=collator,
    )
    eval_loader = None
    if is_main:
        eval_loader = DataLoader(
            eval_dataset,
            batch_size=args.per_device_eval_batch_size,
            shuffle=False,
            num_workers=0,
            collate_fn=collator,
        )

    model = Qwen3VLSceneClassifier(args, local_rank=local_rank)
    if args.init_artifact_root is not None:
        model.load_artifacts(args.init_artifact_root.resolve())
    trainable_parameters = [parameter for parameter in model.parameters() if parameter.requires_grad]
    optimizer = AdamW(trainable_parameters, lr=args.learning_rate, weight_decay=args.weight_decay)

    steps_per_epoch = math.ceil(len(train_loader) / max(1, args.gradient_accumulation_steps))
    planned_steps = max(1, math.ceil(args.num_train_epochs * steps_per_epoch))
    total_steps = args.max_steps if args.max_steps > 0 else planned_steps
    warmup_steps = max(1, int(total_steps * args.warmup_ratio))
    scheduler = get_cosine_schedule_with_warmup(optimizer, num_warmup_steps=warmup_steps, num_training_steps=total_steps)

    best_accuracy = -1.0
    global_step = 0
    oom_skipped_train_batches = 0
    resume_checkpoint = resolve_resume_checkpoint(args.resume_from_checkpoint, output_root / "checkpoints")
    if resume_checkpoint is not None:
        model.load_artifacts(resume_checkpoint)
        optimizer_state_path = resume_checkpoint / "optimizer.pt"
        if optimizer_state_path.exists():
            optimizer.load_state_dict(torch.load(optimizer_state_path, map_location="cpu"))
        scheduler_state_path = resume_checkpoint / "scheduler.pt"
        if scheduler_state_path.exists():
            scheduler.load_state_dict(torch.load(scheduler_state_path, map_location="cpu"))
        trainer_state_path = resume_checkpoint / "trainer_state.json"
        if trainer_state_path.exists():
            trainer_state = json.loads(trainer_state_path.read_text(encoding="utf-8"))
            global_step = int(trainer_state.get("global_step", 0))
            best_accuracy = float(trainer_state.get("best_accuracy", -1.0))
            oom_skipped_train_batches = int(trainer_state.get("oom_skipped_train_batches", 0))

    if distributed:
        model = DDP(model, device_ids=[local_rank], output_device=local_rank, find_unused_parameters=False)
        model._set_static_graph()

    progress = tqdm(total=total_steps, initial=global_step, dynamic_ncols=True, disable=not is_main)
    optimizer.zero_grad(set_to_none=True)
    train_log_path = output_root / "train_log.jsonl"
    start_epoch = global_step // steps_per_epoch
    resume_steps_in_epoch = global_step % steps_per_epoch

    for epoch_index in range(start_epoch, math.ceil(args.num_train_epochs)):
        if global_step >= total_steps:
            break
        if train_sampler is not None:
            train_sampler.set_epoch(epoch_index)
        model.train()
        skip_micro_batches = resume_steps_in_epoch * args.gradient_accumulation_steps if epoch_index == start_epoch else 0
        for step_index, batch in enumerate(train_loader, start=1):
            if skip_micro_batches and step_index <= skip_micro_batches:
                continue
            if global_step >= total_steps:
                break

            outputs = None
            forward_oom = 0
            try:
                outputs = model(**batch)
            except torch.OutOfMemoryError:
                forward_oom = 1
            if sync_flag(forward_oom, local_rank, distributed):
                oom_skipped_train_batches += 1
                if outputs is not None:
                    del outputs
                optimizer.zero_grad(set_to_none=True)
                gc.collect()
                torch.cuda.empty_cache()
                if is_main:
                    append_jsonl(
                        train_log_path,
                        {"event": "skip_oom_forward", "batch_index": step_index, "global_step": global_step, "split": "train"},
                    )
                continue

            loss = outputs["loss"] / max(1, args.gradient_accumulation_steps)
            backward_oom = 0
            try:
                loss.backward()
            except torch.OutOfMemoryError:
                backward_oom = 1
            if sync_flag(backward_oom, local_rank, distributed):
                oom_skipped_train_batches += 1
                optimizer.zero_grad(set_to_none=True)
                del outputs
                del loss
                gc.collect()
                torch.cuda.empty_cache()
                if is_main:
                    append_jsonl(
                        train_log_path,
                        {"event": "skip_oom_backward", "batch_index": step_index, "global_step": global_step, "split": "train"},
                    )
                continue

            should_step = step_index % args.gradient_accumulation_steps == 0 or step_index == len(train_loader)
            if not should_step:
                continue

            optimizer.step()
            scheduler.step()
            optimizer.zero_grad(set_to_none=True)
            global_step += 1
            reduced_loss = reduce_mean(loss.detach() * args.gradient_accumulation_steps, local_rank, distributed)
            if is_main:
                progress.update(1)
                log_row = {
                    "global_step": global_step,
                    "epoch": epoch_index + 1,
                    "loss": round(reduced_loss, 6),
                    "learning_rate": scheduler.get_last_lr()[0],
                }
                append_jsonl(train_log_path, log_row)
                if global_step % args.logging_steps == 0:
                    print(json.dumps(log_row, ensure_ascii=False))

            if global_step % args.eval_steps == 0 or global_step == total_steps:
                barrier(distributed)
                if is_main and eval_loader is not None:
                    metrics = evaluate_model(unwrap_model(model), eval_loader)
                    metrics["global_step"] = global_step
                    metrics["epoch"] = epoch_index + 1
                    metrics["oom_skipped_train_batches"] = oom_skipped_train_batches
                    save_json(output_root / "latest_eval_metrics.json", metrics)
                    append_jsonl(output_root / "eval_log.jsonl", metrics)
                    print(json.dumps(metrics, ensure_ascii=False))
                    if float(metrics["accuracy"]) > best_accuracy:
                        best_accuracy = float(metrics["accuracy"])
                        unwrap_model(model).save_artifacts(output_root / "best", processor)
                        save_json(output_root / "best_metrics.json", metrics)
                barrier(distributed)

            if global_step % args.save_steps == 0 or global_step == total_steps:
                barrier(distributed)
                if is_main:
                    checkpoint_dir = output_root / "checkpoints" / f"step_{global_step}"
                    unwrap_model(model).save_artifacts(checkpoint_dir, processor)
                    torch.save(optimizer.state_dict(), checkpoint_dir / "optimizer.pt")
                    torch.save(scheduler.state_dict(), checkpoint_dir / "scheduler.pt")
                    save_json(
                        checkpoint_dir / "trainer_state.json",
                        {
                            "global_step": global_step,
                            "epoch": epoch_index + 1,
                            "best_accuracy": best_accuracy,
                            "oom_skipped_train_batches": oom_skipped_train_batches,
                        },
                    )
                    prune_old_checkpoints(output_root / "checkpoints", keep_last=args.save_total_limit)
                barrier(distributed)

        resume_steps_in_epoch = 0

    if is_main:
        progress.close()
    barrier(distributed)
    if is_main and eval_loader is not None:
        final_metrics = evaluate_model(unwrap_model(model), eval_loader)
        final_metrics["global_step"] = global_step
        final_metrics["oom_skipped_train_batches"] = oom_skipped_train_batches
        save_json(output_root / "final_eval_metrics.json", final_metrics)
        unwrap_model(model).save_artifacts(output_root / "final", processor)
        print(json.dumps(final_metrics, ensure_ascii=False, indent=2))
    barrier(distributed)
    cleanup_distributed(distributed)


@torch.no_grad()
def evaluate_model(model: Qwen3VLSceneClassifier, dataloader: DataLoader) -> dict[str, Any]:
    model.eval()
    total = 0
    correct = 0
    loss_sum = 0.0
    oom_skipped_eval_batches = 0
    per_label_total = {label: 0 for label in SECONDARY_LABELS}
    per_label_correct = {label: 0 for label in SECONDARY_LABELS}
    for batch in dataloader:
        try:
            outputs = model(**batch)
        except torch.OutOfMemoryError:
            oom_skipped_eval_batches += 1
            gc.collect()
            torch.cuda.empty_cache()
            continue
        logits = outputs["logits"]
        labels = batch["labels"].to(logits.device)
        loss = F.cross_entropy(logits, labels)
        predictions = logits.argmax(dim=-1)
        total += int(labels.numel())
        correct += int((predictions == labels).sum().item())
        loss_sum += float(loss.detach().cpu()) * int(labels.numel())
        for label_id, prediction in zip(labels.tolist(), predictions.tolist()):
            label_name = SECONDARY_LABELS[int(label_id)]
            per_label_total[label_name] += 1
            if int(prediction) == int(label_id):
                per_label_correct[label_name] += 1
    model.train()
    per_label_recall = {
        label: round(per_label_correct[label] / per_label_total[label], 6) if per_label_total[label] else 0.0
        for label in SECONDARY_LABELS
    }
    macro_recall = sum(per_label_recall.values()) / len(SECONDARY_LABELS)
    return {
        "eval_loss": round(loss_sum / max(1, total), 6),
        "accuracy": round(correct / max(1, total), 6),
        "macro_recall": round(macro_recall, 6),
        "per_label_recall": per_label_recall,
        "eval_samples": total,
        "oom_skipped_eval_batches": oom_skipped_eval_batches,
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [orjson.loads(line) for line in path.read_bytes().splitlines() if line.strip()]


def prune_old_checkpoints(checkpoints_root: Path, *, keep_last: int) -> None:
    if keep_last <= 0 or not checkpoints_root.exists():
        return
    checkpoint_dirs = sorted([path for path in checkpoints_root.iterdir() if path.is_dir()], key=lambda item: item.name)
    for path in checkpoint_dirs[:-keep_last]:
        shutil.rmtree(path, ignore_errors=True)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("ab") as handle:
        handle.write(orjson.dumps(payload))
        handle.write(b"\n")


def save_json(path: Path, payload: dict[str, Any]) -> None:
    serializable = {key: (str(value) if isinstance(value, Path) else value) for key, value in payload.items()}
    path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_resume_checkpoint(explicit_checkpoint: Path | None, checkpoints_root: Path) -> Path | None:
    if explicit_checkpoint is not None:
        checkpoint = explicit_checkpoint.resolve()
        return checkpoint if checkpoint.exists() else None
    if not checkpoints_root.exists():
        return None
    candidates = [path for path in checkpoints_root.iterdir() if path.is_dir() and path.name.startswith("step_")]
    if not candidates:
        return None
    return max(candidates, key=lambda item: int(item.name.split("_")[-1]))


def unwrap_model(model: nn.Module) -> Qwen3VLSceneClassifier:
    return model.module if isinstance(model, DDP) else model


def setup_distributed() -> tuple[int, int, int, bool]:
    world_size = int(os.environ.get("WORLD_SIZE", "1"))
    rank = int(os.environ.get("RANK", "0"))
    local_rank = int(os.environ.get("LOCAL_RANK", "0"))
    distributed = world_size > 1
    if torch.cuda.is_available():
        torch.cuda.set_device(local_rank)
    if distributed and not dist.is_initialized():
        dist.init_process_group(backend="nccl", init_method="env://", device_id=torch.device(f"cuda:{local_rank}"))
    return local_rank, rank, world_size, distributed


def cleanup_distributed(distributed: bool) -> None:
    if distributed and dist.is_initialized():
        dist.destroy_process_group()


def barrier(distributed: bool) -> None:
    if distributed and dist.is_initialized():
        dist.barrier()


def sync_flag(flag: int, local_rank: int, distributed: bool) -> bool:
    if not distributed:
        return bool(flag)
    device = torch.device(f"cuda:{local_rank}")
    tensor = torch.tensor([flag], device=device, dtype=torch.int32)
    dist.all_reduce(tensor, op=dist.ReduceOp.MAX)
    return bool(int(tensor.item()))


def reduce_mean(value: torch.Tensor, local_rank: int, distributed: bool) -> float:
    if not distributed:
        return float(value.detach().cpu())
    tensor = value.detach().to(torch.device(f"cuda:{local_rank}"), dtype=torch.float32)
    dist.all_reduce(tensor, op=dist.ReduceOp.SUM)
    tensor /= dist.get_world_size()
    return float(tensor.cpu())


def set_seed(seed: int) -> None:
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


if __name__ == "__main__":
    main()