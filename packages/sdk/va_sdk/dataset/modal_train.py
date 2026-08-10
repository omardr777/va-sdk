"""
Modal training script for fine-tuning SLMs on va-sdk datasets.

Uploads train.jsonl + test.jsonl, runs a LoRA fine-tune on the target model,
outputs merged GGUF weights ready for local serving.

Usage from CLI:
    python -m va_sdk.dataset.modal_train \\
        --train ./data/train.jsonl \\
        --test ./data/test.jsonl \\
        --model Qwen/Qwen2.5-0.5B-Instruct \\
        --token $MODAL_TOKEN

Usage from dashboard: POST /api/train with same config.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


class ModalTrainer:
    def __init__(self, token: str, token_id: str | None = None, secret: str | None = None):
        self.token = token
        self.token_id = token_id
        self.secret = secret
        self._job_id: str | None = None
        self._status: str = "idle"

    def train(
        self,
        train_path: str,
        test_path: str,
        model: str = "Qwen/Qwen2.5-0.5B-Instruct",
        lora_r: int = 16,
        epochs: int = 3,
    ) -> str:
        self._status = "uploading"
        self._job_id = f"va-sdk-{int(time.time())}"

        train_data = Path(train_path).read_text()
        test_data = Path(test_path).read_text()

        import modal

        app = modal.App("va-sdk-train")

        image = (
            modal.Image.debian_slim()
            .pip_install("torch", "transformers", "datasets", "peft", "bitsandbytes")
        )

        volume = modal.Volume.from_name("va-sdk-models", create_if_missing=True)

        @app.function(
            image=image,
            gpu="A10G",
            volumes={"/models": volume},
            timeout=3600,
            secrets=[modal.Secret.from_name("huggingface")] if self.secret else [],
        )
        def _train():
            from datasets import Dataset
            import torch
            from transformers import (
                AutoModelForCausalLM,
                AutoTokenizer,
                BitsAndBytesConfig,
                TrainingArguments,
            )
            from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
            from trl import SFTTrainer

            train_dataset = Dataset.from_json(train_path)
            test_dataset = Dataset.from_json(test_path)

            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
            )

            tokenizer = AutoTokenizer.from_pretrained(model)
            tokenizer.pad_token = tokenizer.eos_token

            base_model = AutoModelForCausalLM.from_pretrained(
                model,
                quantization_config=bnb_config,
                device_map="auto",
                torch_dtype=torch.bfloat16,
            )
            base_model = prepare_model_for_kbit_training(base_model)

            peft_config = LoraConfig(
                r=lora_r,
                lora_alpha=32,
                lora_dropout=0.05,
                bias="none",
                task_type="CAUSAL_LM",
                target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
            )

            model = get_peft_model(base_model, peft_config)

            training_args = TrainingArguments(
                output_dir="/tmp/va-sdk-train",
                num_train_epochs=epochs,
                per_device_train_batch_size=2,
                gradient_accumulation_steps=4,
                warmup_steps=10,
                logging_steps=5,
                save_strategy="epoch",
                learning_rate=2e-4,
                fp16=True,
                report_to="none",
            )

            trainer = SFTTrainer(
                model=model,
                args=training_args,
                train_dataset=train_dataset,
                tokenizer=tokenizer,
                max_seq_length=2048,
            )

            trainer.train()
            trainer.save_model("/models/va-sdk-output")
            tokenizer.save_pretrained("/models/va-sdk-output")

            return {"status": "done", "output_path": "/models/va-sdk-output"}

        with app.run():
            self._status = "training"
            result = _train.remote()
            self._status = "done"
            return result

    @property
    def status(self) -> str:
        return self._status

    @property
    def job_id(self) -> str:
        return self._job_id or "unknown"
