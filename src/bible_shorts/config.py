from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Settings:
    data: dict[str, Any]
    base_dir: Path

    @property
    def llm(self) -> dict[str, Any]:
        return self.data["llm"]

    @property
    def tts(self) -> dict[str, Any]:
        return self.data["tts"]

    @property
    def video(self) -> dict[str, Any]:
        return self.data["video"]

    @property
    def content(self) -> dict[str, Any]:
        return self.data["content"]

    @property
    def paths(self) -> dict[str, Any]:
        return self.data["paths"]

    def resolve(self, relative: str) -> Path:
        return (self.base_dir / relative).resolve()

    def save(self, path: Path | None = None) -> None:
        """Write current data back to the settings JSON file."""
        target = path or (self.base_dir / "config" / "settings.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_settings(path: str | Path | None = None) -> Settings:
    base_dir = Path(__file__).resolve().parents[2]
    _load_dotenv(base_dir / ".env")
    settings_path = Path(path) if path else base_dir / "config" / "settings.json"
    if not settings_path.exists():
        settings_path = base_dir / "config" / "settings.example.json"
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    return Settings(data=data, base_dir=base_dir)
