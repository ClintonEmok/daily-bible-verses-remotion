#!/usr/bin/env python3
"""Produce one devotional Bible Short with Remotion and optional YouTube upload.

The runner keeps the rebuildable record under data/records/ and treats rendered
MP4/WAV/SRT/props files as disposable artifacts. They are deleted only after a
successful YouTube upload has been read back from the API.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import requests
import soundfile as sf
from kokoro import KPipeline

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from bible_shorts.verse_store import load_verses  # noqa: E402

PALETTE_ORDER = ["emerald", "navy", "purple", "teal", "indigo", "plum", "forest", "slate"]
DEFAULT_CONFIG = ROOT / "config" / "production.json"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    for env_file in config.get("env_files", []):
        load_dotenv(Path(env_file).expanduser())
    load_dotenv(ROOT / ".env")
    return config


def atomic_json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"used": {}, "palette_cursor": 0, "jobs": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def choose_verse(verses: list[dict[str, Any]], state: dict[str, Any], forced: str | None, seed: str) -> dict[str, Any]:
    if forced:
        for verse in verses:
            if verse["reference"].lower() == forced.lower():
                return verse
        raise ValueError(f"Verse not found in the KJV pool: {forced}")

    today = date.today()
    cooldown = today - timedelta(days=90)
    used = state.setdefault("used", {})
    eligible = [
        verse for verse in verses
        if not used.get(verse["reference"]) or used[verse["reference"]] < cooldown.isoformat()
    ]
    pool = eligible or verses
    rng = random.Random(seed)
    weights = [max(1, int(verse.get("devotional_score", 5))) for verse in pool]
    chosen = rng.choices(pool, weights=weights, k=1)[0]

    # Same-day guard: never allow a second upload on one day to repeat a verse
    # already taken earlier that day. Re-draw deterministically from what remains.
    last_used = used.get(chosen["reference"])
    if last_used == today.isoformat():
        taken_today = {ref for ref, day in used.items() if day == today.isoformat()}
        remaining = [verse for verse in pool if verse["reference"] not in taken_today]
        if remaining:
            weights = [max(1, int(verse.get("devotional_score", 5))) for verse in remaining]
            chosen = rng.choices(remaining, weights=weights, k=1)[0]
            # Belt and braces: keep re-drawing within the same seed until fresh.
            attempts = 0
            while chosen["reference"] in taken_today and attempts < 100:
                attempts += 1
                chosen = random.Random(f"{seed}:{attempts}").choices(
                    [v for v in pool if v["reference"] not in taken_today] or pool,
                    k=1,
                )[0]
        if chosen["reference"] in taken_today:
            raise RuntimeError("Could not draw a unique verse for this slot")
    return chosen


def choose_palette(state: dict[str, Any]) -> str:
    cursor = int(state.get("palette_cursor", 0))
    palette = PALETTE_ORDER[cursor % len(PALETTE_ORDER)]
    state["palette_cursor"] = cursor + 1
    state.setdefault("palette_history", []).append(palette)
    state["palette_history"] = state["palette_history"][-len(PALETTE_ORDER):]
    return palette


def format_reference(reference: str) -> str:
    if ":" not in reference:
        return reference
    book, verses = reference.split(":", 1)
    bits = book.rsplit(" ", 1)
    if len(bits) != 2:
        return reference
    if "-" in verses:
        first, last = verses.split("-", 1)
        return f"{bits[0]} chapter {bits[1]} verses {first} through {last}"
    return f"{bits[0]} chapter {bits[1]} verse {verses}"


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w']+\b", text))


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = "\n".join(line for line in text.splitlines() if not line.strip().startswith("```"))
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("LLM did not return a JSON object")
    value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("LLM JSON was not an object")
    return value


def llm_prompt(verse: dict[str, Any], tone: str, translation: str) -> str:
    return f"""Write a natural, verse-specific Christian devotional for a vertical YouTube Short.

Return ONLY valid JSON. Do not use markdown fences. Do not use em dashes.

Required JSON keys:
title, hook, description, hashtags, opening_reflection, scripture_intro, scripture, reflection, prayer, caption

Rules:
- Tone: {tone}.
- Translation: {translation}.
- Keep the spoken narration around 30-45 seconds and under 110 words where possible.
- opening_reflection: one concrete sentence about a real human situation, maximum 14 words.
- scripture_intro: say "Today's scripture comes from {format_reference(verse['reference'])}."
- scripture: reproduce the exact KJV text supplied below, with no reference prefix and no paraphrase.
- reflection: one or two natural sentences tied specifically to the verse's words, maximum 24 words.
- prayer: one concise, verse-specific prayer, maximum 20 words, ending naturally with Amen.
- Do not write a closing section. The prayer is the final spoken section.
- description: 2-4 useful sentences with context and application.
- hashtags: 8-12 strings, including book, chapter, theme, #BibleShorts, and #DailyVerse.
- caption: a short readable caption, usually the reference.

Reference: {verse['reference']}
Exact KJV text: {verse['text']}
""".strip()


def call_llm(config: dict[str, Any], verse: dict[str, Any]) -> dict[str, Any]:
    llm = config["llm"]
    key = os.getenv("OPENCODE_GO_API_KEY") or os.getenv("OPENCODE_API_KEY") or os.getenv("MINIMAX_API_KEY")
    if not key:
        raise RuntimeError("No LLM API key found in the configured Hermes environment files")
    prompt = llm_prompt(verse, config["content"]["tone"], config["content"]["translation"])
    api_style = str(llm.get("api_style", "openai")).lower()
    if api_style == "openai":
        url = llm["base_url"].rstrip("/") + "/chat/completions"
        payload = {
            "model": llm["model"],
            "messages": [
                {"role": "system", "content": "You write short-form Christian devotional content."},
                {"role": "user", "content": prompt},
            ],
            "temperature": llm.get("temperature", 0.4),
            "max_tokens": llm.get("max_tokens", 2400),
        }
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
    else:
        url = llm["base_url"]
        payload = {
            "model": llm["model"],
            "system": "You write short-form Christian devotional content.",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": llm.get("temperature", 0.4),
            "max_tokens": llm.get("max_tokens", 2400),
        }
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}", "anthropic-version": "2023-06-01"}
    response = requests.post(url, json=payload, headers=headers, timeout=180)
    response.raise_for_status()
    body = response.json()
    pieces: list[str] = []
    if isinstance(body.get("choices"), list) and body["choices"]:
        message = body["choices"][0].get("message", {})
        if isinstance(message.get("content"), str):
            pieces.append(message["content"])
    if isinstance(body.get("content"), list):
        pieces.extend(str(block.get("text", "")) for block in body["content"] if isinstance(block, dict) and block.get("type") == "text")
    if not pieces and isinstance(body.get("output"), list):
        for block in body["output"]:
            if isinstance(block, dict) and block.get("type") == "message":
                content = block.get("content", [])
                if isinstance(content, list):
                    pieces.extend(str(item.get("text", "")) for item in content if isinstance(item, dict) and item.get("type") == "text")
    if not pieces:
        raise RuntimeError(f"LLM returned no text content. Response keys: {sorted(body)}")
    return extract_json("\n".join(pieces))


def normalize_script(raw: dict[str, Any], verse: dict[str, Any], max_words: int) -> dict[str, Any]:
    reference = verse["reference"]
    scripture = verse["text"]
    script = {
        "title": str(raw.get("title") or f"Hope from {reference}").strip(),
        "hook": str(raw.get("hook") or "A word for today").strip(),
        "description": str(raw.get("description") or f"A devotional reflection on {reference}.").strip(),
        "hashtags": [str(x).strip() for x in raw.get("hashtags", []) if str(x).strip()][:12],
        "opening_reflection": str(raw.get("opening_reflection") or "God meets us in the places we cannot solve alone.").strip(),
        "scripture_intro": f"Today's scripture comes from {format_reference(reference)}.",
        "scripture": scripture,
        "reflection": str(raw.get("reflection") or "This verse gives us a faithful way to meet today.").strip(),
        "prayer": str(raw.get("prayer") or "Lord, help me live this truth today. Amen.").strip(),
        "caption": str(raw.get("caption") or reference).strip(),
    }
    if "#BibleShorts" not in script["hashtags"]:
        script["hashtags"].append("#BibleShorts")
    if "#DailyVerse" not in script["hashtags"]:
        script["hashtags"].append("#DailyVerse")
    narration_parts = [
        script["opening_reflection"],
        script["scripture_intro"],
        script["scripture"],
        script["reflection"],
        script["prayer"],
    ]
    script["narration"] = "\n\n".join(narration_parts)
    script["word_count"] = word_count(script["narration"])
    if script["scripture"] != scripture:
        raise ValueError("KJV fidelity check failed")
    if script["word_count"] > max_words:
        raise ValueError(f"Narration is {script['word_count']} words; maximum is {max_words}")
    if not script["prayer"].lower().rstrip().endswith("amen."):
        script["prayer"] = script["prayer"].rstrip(" .") + ". Amen."
        script["narration"] = "\n\n".join([script[k] for k in ["opening_reflection", "scripture_intro", "scripture", "reflection", "prayer"]])
        script["word_count"] = word_count(script["narration"])
    return script


def split_text(text: str, max_words: int = 16) -> list[str]:
    sentences = [part.strip() for part in re.split(r"(?<=[.!?:;])\s+", text.strip()) if part.strip()]
    chunks: list[str] = []
    for sentence in sentences:
        words = sentence.split()
        while len(words) > max_words:
            cut = max_words
            chunks.append(" ".join(words[:cut]))
            words = words[cut:]
        if words:
            chunks.append(" ".join(words))
    return chunks or [text.strip()]


def generate_audio(config: dict[str, Any], script: dict[str, Any], audio_path: Path) -> tuple[list[dict[str, Any]], float]:
    tts = config["tts"]
    pipeline = KPipeline(lang_code="a")
    source_blocks = [
        ("opening", script["opening_reflection"]),
        ("intro", script["scripture_intro"]),
        *[("verse", chunk) for chunk in split_text(script["scripture"])],
        ("reflection", script["reflection"]),
        ("prayer", script["prayer"]),
    ]
    sample_rate = int(tts.get("sample_rate", 24000))
    pause_seconds = float(tts.get("pause_seconds", 0.12))
    pause = np.zeros(int(sample_rate * pause_seconds), dtype=np.float32)
    parts: list[np.ndarray] = []
    blocks: list[dict[str, Any]] = []
    cursor = 0.0
    for index, (kind, text) in enumerate(source_blocks):
        chunks = list(pipeline(text, voice=tts["voice"], speed=float(tts["speed"])))
        if not chunks:
            raise RuntimeError(f"Kokoro returned no audio for {text!r}")
        audio = np.concatenate([np.asarray(chunk.audio, dtype=np.float32) for chunk in chunks])
        parts.append(audio)
        start = cursor
        end = start + len(audio) / sample_rate
        blocks.append({"index": index, "kind": kind, "text": text, "start": round(start, 4), "end": round(end, 4)})
        cursor = end
        if index < len(source_blocks) - 1:
            parts.append(pause)
            cursor += pause_seconds
    combined = np.concatenate(parts)
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(audio_path, combined, sample_rate)
    return blocks, len(combined) / sample_rate


def srt_timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds_i, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds_i:02d},{millis:03d}"


def write_srt(blocks: list[dict[str, Any]], path: Path) -> None:
    lines: list[str] = []
    for index, block in enumerate(blocks, start=1):
        lines.extend([str(index), f"{srt_timestamp(block['start'])} --> {srt_timestamp(block['end'])}", block["text"], ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def generate_reading_audio(config: dict[str, Any], verse: dict[str, Any], audio_path: Path) -> tuple[list[dict[str, Any]], float]:
    """Narrate a verse-only reading. Phrases split on KJV clause punctuation."""
    tts = config["tts"]
    pipeline = KPipeline(lang_code="a")
    phrases = split_text(verse["text"])
    sample_rate = int(tts.get("sample_rate", 24000))
    pause_seconds = float(tts.get("pause_seconds", 0.10))
    pause = np.zeros(int(sample_rate * pause_seconds), dtype=np.float32)
    parts: list[np.ndarray] = []
    phrases_out: list[dict[str, Any]] = []
    cursor = 0.0
    for index, phrase in enumerate(phrases):
        chunks = list(pipeline(phrase, voice=tts["voice"], speed=float(tts["speed"])))
        if not chunks:
            raise RuntimeError(f"Kokoro returned no audio for {phrase!r}")
        audio = np.concatenate([np.asarray(chunk.audio, dtype=np.float32) for chunk in chunks])
        parts.append(audio)
        start = cursor
        end = start + len(audio) / sample_rate
        phrases_out.append({"index": index, "text": phrase, "start": round(start, 4), "end": round(end, 4)})
        cursor = end
        if index < len(phrases) - 1:
            parts.append(pause)
            cursor += pause_seconds
    combined = np.concatenate(parts)
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(audio_path, combined, sample_rate)
    return phrases_out, len(combined) / sample_rate


def render(config: dict[str, Any], data: dict[str, Any], props_path: Path, output_path: Path, composition: str = "DevotionalSample") -> None:
    if composition == "DevotionalSample":
        props_payload = {"devotionalData": data}
    else:
        props_payload = {"verseData": data}
    props_path.write_text(json.dumps(props_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    command = ["npx", "remotion", "render", "src/index.ts", composition, str(output_path), f"--props={props_path}"]
    try:
        result = subprocess.run(command, cwd=ROOT, check=True, timeout=900, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        tail = (exc.stdout or "")[-4000:] + (exc.stderr or "")[-4000:]
        raise RuntimeError(f"Remotion render failed: {tail}") from exc



def ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def load_youtube_settings(path: Path) -> tuple[dict[str, Any], Any]:
    from bible_shorts.config import Settings
    document = json.loads(path.read_text(encoding="utf-8"))
    yt = document.get("youtube", document)
    settings = Settings(data={"youtube": yt}, base_dir=ROOT)
    return document, settings


def upload_and_confirm(meta_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    from bible_shorts.youtube import YouTubeConfig, api_get, upload_from_meta
    settings_path = Path(config["youtube_settings_path"]).expanduser()
    document, settings = load_youtube_settings(settings_path)
    cfg = YouTubeConfig.from_settings(settings)
    if not cfg.is_complete():
        raise RuntimeError("YouTube OAuth settings are incomplete")
    result = upload_from_meta(meta_path, cfg, privacy=config["video"]["privacy"])
    items = api_get("videos", {"part": "id,status,snippet", "id": result.video_id}, cfg).get("items", [])
    if not any(item.get("id") == result.video_id for item in items):
        raise RuntimeError(f"YouTube upload returned {result.video_id}, but read-back verification found no matching video")
    cfg.save_to_settings(settings)
    document["youtube"] = settings.data["youtube"]
    settings_path.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
    settings_path.chmod(0o600)
    return {"video_id": result.video_id, "watch_url": result.watch_url, "title": result.title}


def cleanup_artifacts(paths: list[Path]) -> list[str]:
    removed: list[str] = []
    for path in paths:
        if path.exists():
            path.unlink()
            removed.append(str(path))
    return removed


def upload_existing_record(record_path: Path, config: dict[str, Any], privacy: str | None) -> int:
    meta = json.loads(record_path.read_text(encoding="utf-8"))
    if privacy:
        config["video"]["privacy"] = privacy
    upload_info = upload_and_confirm(record_path, config)
    artifacts = cleanup_artifacts([Path(meta["mp4_path"]), Path(meta["audio_path"]), Path(meta["srt_path"]), Path(meta["props_path"])])
    meta.update({
        "stage": "uploaded",
        "youtube": upload_info,
        "upload_verified_at": datetime.now(timezone.utc).isoformat(),
        "deleted_artifacts": artifacts,
        "artifact_retention": "MP4, WAV, SRT, and Remotion props deleted after YouTube read-back; JSON record retained for rebuild.",
    })
    atomic_json_write(record_path, meta)
    state_path = ROOT / config["paths"]["state_file"]
    state = load_state(state_path)
    state.setdefault("jobs", {})[meta["run_id"]] = {
        "reference": meta["verse"]["reference"],
        "palette": meta["palette"],
        "stage": "uploaded",
        "record": str(record_path),
        "video_id": upload_info["video_id"],
        "deleted_artifacts": artifacts,
    }
    atomic_json_write(state_path, state)
    print(json.dumps({"run_id": meta["run_id"], "reference": meta["verse"]["reference"], "palette": meta["palette"], "youtube": upload_info, "deleted": artifacts, "record": str(record_path)}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--verse", help="Force a KJV pool reference")
    parser.add_argument("--slot", default="manual", help="Stable slot label, e.g. 06:20")
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--privacy", choices=["public", "unlisted", "private"])
    parser.add_argument("--upload-record", type=Path, help="Upload an existing retained record and then delete its generated artifacts")
    parser.add_argument("--script-json", type=Path, help="Use a prepared script JSON instead of calling the LLM")
    parser.add_argument("--format", choices=["devotional", "reading"], default="devotional", help="reading = verse-only Bible Short; devotional = full narration")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.upload_record:
        return upload_existing_record(args.upload_record.expanduser().resolve(), config, args.privacy)
    paths = config["paths"]
    state_path = ROOT / paths["state_file"]
    state = load_state(state_path)
    previous_cursor = int(state.get("palette_cursor", 0))
    previous_history = list(state.get("palette_history", []))
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    verses = load_verses(ROOT / paths["verses_file"], ROOT / paths["scripture_source_file"])
    verse = choose_verse(verses, state, args.verse, f"{date.today().isoformat()}:{args.slot}")
    previous_used = state.setdefault("used", {}).get(verse["reference"])
    palette = choose_palette(state)
    reference_slug = re.sub(r"[^a-z0-9]+", "_", verse["reference"].lower()).strip("_")
    run_id = f"{run_stamp}_{reference_slug}"
    record_path = ROOT / paths["records_dir"] / f"{run_id}.json"
    generated_dir = ROOT / paths["generated_dir"]
    out_dir = ROOT / paths["out_dir"]
    audio_path = generated_dir / f"{run_id}.wav"
    srt_path = out_dir / f"{run_id}.srt"
    props_path = out_dir / f"{run_id}.props.json"
    mp4_path = out_dir / f"{run_id}.mp4"
    uploaded_confirmed = False

    state.setdefault("used", {})[verse["reference"]] = date.today().isoformat()
    state.setdefault("jobs", {})[run_id] = {"reference": verse["reference"], "palette": palette, "stage": "reserved"}
    atomic_json_write(state_path, state)

    try:
        if args.format == "reading":
            blocks, duration = generate_reading_audio(config, verse, audio_path)
            data = {
                "reference": verse["reference"].upper(),
                "verseText": verse["text"],
                "phrases": blocks,
                "audio": f"generated/{audio_path.name}",
                "voice": config["tts"]["voice"],
                "speed": config["tts"]["speed"],
                "duration": round(duration, 4),
                "mode": "verse-only",
                "alignment": "Kokoro phrase chunk boundaries; no WhisperX",
                "palette": palette,
            }
            script = {
                "title": f"{verse['reference']} - Daily Bible Reading",
                "description": f"A quiet reading of {verse['reference']} from the King James Version.",
                "caption": f"{verse['reference']} (KJV)",
                "hashtags": ["Bible", "KJV", "DailyVerse", "#BibleShorts", "#DailyVerse"],
                "narration": verse["text"],
                "word_count": word_count(verse["text"]),
            }
        else:
            raw_script = json.loads(args.script_json.read_text(encoding="utf-8")) if args.script_json else call_llm(config, verse)
            script = normalize_script(raw_script, verse, int(config["content"]["max_narration_words"]))
            blocks, duration = generate_audio(config, script, audio_path)
            data = {
                "reference": verse["reference"].upper(),
                "audio": f"generated/{audio_path.name}",
                "voice": config["tts"]["voice"],
                "speed": config["tts"]["speed"],
                "duration": round(duration, 4),
                "word_count": script["word_count"],
                "mode": "devotional",
                "alignment": "Kokoro block boundaries; no WhisperX",
                "palette": palette,
                "blocks": blocks,
            }
        write_srt(blocks, srt_path)
        composition = "BibleShort" if args.format == "reading" else "DevotionalSample"
        render(config, data, props_path, mp4_path, composition=composition)
        rendered_duration = ffprobe_duration(mp4_path)
        expected = duration + float(config["video"].get("tail_seconds", 1.2))
        if abs(rendered_duration - expected) > 1.0:
            raise RuntimeError(f"Rendered duration {rendered_duration:.3f}s differs from expected {expected:.3f}s")

        meta = {
            "run_id": run_id,
            "stage": "rendered",
            "format": args.format,
            "verse": {"reference": verse["reference"], "text": verse["text"], "theme": verse.get("theme")},
            "script": script,
            "palette": palette,
            "duration_seconds": rendered_duration,
            "audio_path": str(audio_path),
            "srt_path": str(srt_path),
            "mp4_path": str(mp4_path),
            "props_path": str(props_path),
            "record_path": str(record_path),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        atomic_json_write(record_path, meta)
        state["jobs"][run_id] = {"reference": verse["reference"], "palette": palette, "stage": "rendered", "record": str(record_path)}
        atomic_json_write(state_path, state)

        if args.upload:
            if args.privacy:
                config["video"]["privacy"] = args.privacy
            upload_info = upload_and_confirm(record_path, config)
            uploaded_confirmed = True
            meta.update({"stage": "uploaded", "youtube": upload_info, "upload_verified_at": datetime.now(timezone.utc).isoformat()})
            artifacts = cleanup_artifacts([mp4_path, audio_path, srt_path, props_path])
            meta["deleted_artifacts"] = artifacts
            meta["artifact_retention"] = "MP4, WAV, SRT, and Remotion props deleted after YouTube read-back; JSON record retained for rebuild."
            atomic_json_write(record_path, meta)
            state["jobs"][run_id] = {"reference": verse["reference"], "palette": palette, "stage": "uploaded", "record": str(record_path), "video_id": upload_info["video_id"], "deleted_artifacts": artifacts}
            atomic_json_write(state_path, state)
            print(json.dumps({"run_id": run_id, "reference": verse["reference"], "palette": palette, "youtube": upload_info, "deleted": artifacts, "record": str(record_path)}, indent=2))
        else:
            print(json.dumps({"run_id": run_id, "reference": verse["reference"], "palette": palette, "stage": "rendered", "duration": rendered_duration, "mp4": str(mp4_path), "record": str(record_path)}, indent=2))
        return 0
    except Exception as exc:
        if not uploaded_confirmed:
            if previous_used is None:
                state.setdefault("used", {}).pop(verse["reference"], None)
            else:
                state.setdefault("used", {})[verse["reference"]] = previous_used
            state["palette_cursor"] = previous_cursor
            state["palette_history"] = previous_history
        state.setdefault("jobs", {})[run_id] = {
            "reference": verse["reference"],
            "palette": palette,
            "stage": "failed",
            "error": str(exc),
            "record": str(record_path) if record_path.exists() else None,
        }
        atomic_json_write(state_path, state)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
