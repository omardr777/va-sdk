from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any


class DatasetStore:
    def __init__(self, file_path: str = "./data/seeds.jsonl"):
        self.file_path = Path(file_path)
        self._conversations: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if self.file_path.exists():
            with open(self.file_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        conv = json.loads(line)
                        if "id" not in conv:
                            conv["id"] = str(uuid.uuid4())[:8]
                        self._conversations.append(conv)
                    except json.JSONDecodeError:
                        pass

    def _save(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.file_path, "w") as f:
            for conv in self._conversations:
                f.write(json.dumps(conv, ensure_ascii=False) + "\n")

    def list(self, tool: str | None = None, source: str | None = None) -> list[dict[str, Any]]:
        result = self._conversations
        if tool:
            result = [c for c in result if c.get("tool") == tool or self._conv_has_tool(c, tool)]
        if source:
            result = [c for c in result if c.get("source") == source]
        return result

    @staticmethod
    def _conv_has_tool(conv: dict, tool_name: str) -> bool:
        for msg in conv.get("messages", []):
            for tc in msg.get("tool_calls", []):
                if tc.get("function", {}).get("name") == tool_name:
                    return True
        return False

    def add(self, conversation: dict[str, Any]) -> dict[str, Any]:
        conversation["id"] = str(uuid.uuid4())[:8]
        self._conversations.append(conversation)
        self._save()
        return conversation

    def get(self, conv_id: str) -> dict[str, Any] | None:
        for c in self._conversations:
            if c.get("id") == conv_id:
                return c
        return None

    def update(self, conv_id: str, conversation: dict[str, Any]) -> bool:
        for i, c in enumerate(self._conversations):
            if c.get("id") == conv_id:
                conversation["id"] = conv_id
                self._conversations[i] = conversation
                self._save()
                return True
        return False

    def delete(self, conv_id: str) -> bool:
        for i, c in enumerate(self._conversations):
            if c.get("id") == conv_id:
                self._conversations.pop(i)
                self._save()
                return True
        return False

    def export(self, output_dir: str, train_split: float = 0.8) -> dict[str, int]:
        from va_sdk.dataset.validator import validate_conversation
        from va_sdk.dataset.exporter import export_jsonl

        valid = []
        for c in self._conversations:
            errors = validate_conversation(c, [])
            if not errors:
                valid.append(c)

        train_path, test_path, n_train, n_test = export_jsonl(
            valid, output_dir, train_split=train_split,
        )
        return {
            "train_count": n_train,
            "test_count": n_test,
            "train_path": str(train_path),
            "test_path": str(test_path),
        }

    @property
    def count(self) -> int:
        return len(self._conversations)
