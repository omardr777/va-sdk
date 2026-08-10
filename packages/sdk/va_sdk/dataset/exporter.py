from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any


def export_jsonl(
    conversations: list[dict[str, Any]],
    output_dir: str | Path,
    *,
    train_split: float = 0.8,
    seed: int = 42,
) -> tuple[Path, Path, int, int]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    random.seed(seed)
    shuffled = list(conversations)
    random.shuffle(shuffled)

    split_idx = int(len(shuffled) * train_split)
    train = shuffled[:split_idx]
    test = shuffled[split_idx:]

    train_path = output_dir / "train.jsonl"
    test_path = output_dir / "test.jsonl"

    _write_file(train_path, train)
    _write_file(test_path, test)

    return train_path, test_path, len(train), len(test)


def _write_file(path: Path, conversations: list[dict[str, Any]]) -> None:
    with open(path, "w") as f:
        for conv in conversations:
            f.write(json.dumps(conv, ensure_ascii=False) + "\n")
