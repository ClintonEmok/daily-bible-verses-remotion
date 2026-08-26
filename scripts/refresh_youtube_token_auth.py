#!/usr/bin/env python3
"""Renew YouTube OAuth tokens without storing credentials in this repo.

Usage:
  python scripts/refresh_youtube_token_auth.py --url
  python scripts/refresh_youtube_token_auth.py
  python scripts/refresh_youtube_token_auth.py '<redirect-code-or-url>'
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bible_shorts.config import Settings  # noqa: E402
from bible_shorts.youtube import (  # noqa: E402
    YouTubeConfig,
    build_auth_url,
    exchange_code_for_tokens,
    get_channel,
    get_upload_playlist_id,
)

SETTINGS_PATH = Path(os.path.expanduser("~/.hermes/profiles/bible-shorts/youtube_settings.json"))


def load_document() -> tuple[dict, Settings, YouTubeConfig]:
    document = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    settings = Settings(data={"youtube": document["youtube"]}, base_dir=ROOT)
    return document, settings, YouTubeConfig.from_settings(settings)


def extract_code(value: str) -> str:
    value = value.strip()
    if value.startswith("http://") or value.startswith("https://"):
        return parse_qs(urlparse(value).query).get("code", [""])[0]
    return value


def main() -> int:
    document, settings, cfg = load_document()
    if "--url" in sys.argv:
        print(build_auth_url(cfg.client_id))
        return 0

    raw = next((arg for arg in sys.argv[1:] if not arg.startswith("--")), "")
    if not raw:
        raw = input("Paste the authorization code or redirect URL: ")
    code = extract_code(raw)
    if not code:
        raise SystemExit("No authorization code found.")

    token_data = exchange_code_for_tokens(cfg.client_id, cfg.client_secret, code)
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        raise SystemExit("Google did not return a refresh token. Re-run consent with prompt=consent.")

    cfg.refresh_token = refresh_token
    cfg.access_token = token_data["access_token"]
    cfg.token_expiry = time.time() + int(token_data.get("expires_in", 3600)) - 60
    channel = get_channel(cfg)
    title = channel.get("items", [{}])[0].get("snippet", {}).get("title", "unknown")
    cfg.upload_playlist = get_upload_playlist_id(cfg)
    cfg.save_to_settings(settings)
    document["youtube"] = settings.data["youtube"]
    SETTINGS_PATH.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
    SETTINGS_PATH.chmod(0o600)
    print(f"YouTube OAuth renewed for channel: {title}")
    print("Credentials saved in the private Hermes profile.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
