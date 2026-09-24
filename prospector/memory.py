"""Persistent memory: learned rules, user feedback labels, and learning-run
history. Everything lives under a `data/` directory as plain JSON/JSONL so it
is easy to inspect and diff.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Literal

from prospector.features import features
from prospector.osm import Lead
from prospector.rules import Rule

Label = Literal["good", "bad"]


class Memory:
    def __init__(self, data_dir: Path = Path("data")) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.rules_path = self.data_dir / "rules.json"
        self.labels_path = self.data_dir / "labels.jsonl"
        self.history_path = self.data_dir / "history.jsonl"

    # -- Rules --------------------------------------------------------

    def load_rules(self) -> list[Rule]:
        if not self.rules_path.exists():
            return []
        raw = json.loads(self.rules_path.read_text(encoding="utf-8"))
        return [Rule.from_dict(r) for r in raw]

    def save_rules(self, rules: list[Rule]) -> None:
        self.rules_path.write_text(
            json.dumps([r.to_dict() for r in rules], indent=2), encoding="utf-8"
        )

    # -- Labels ---------------------------------------------------------

    def add_label(self, lead: Lead, label: Label, run_id: str) -> None:
        """Append a labeled lead snapshot. Dedupe happens at read time in
        get_labels() (last label for a given lead id wins)."""
        record = {
            "lead_id": lead.id,
            "label": label,
            "run_id": run_id,
            "ts": time.time(),
            "lead": lead.to_dict(),
            "features": features(lead),
        }
        with self.labels_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def get_labels(self) -> list[dict]:
        """All labels, deduped by lead_id, last label wins."""
        if not self.labels_path.exists():
            return []
        by_id: dict[str, dict] = {}
        with self.labels_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                by_id[record["lead_id"]] = record
        return list(by_id.values())

    # -- History ----------------------------------------------------------

    def append_history(self, record: dict) -> None:
        record = dict(record)
        record.setdefault("ts", time.time())
        with self.history_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def get_history(self) -> list[dict]:
        if not self.history_path.exists():
            return []
        records = []
        with self.history_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records
