from __future__ import annotations

import difflib
import json
import re
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any

BOOK_NAME_ALIASES = {
    "psalm": "psalms",
    "psalms": "psalms",
    "song of songs": "song of solomon",
    "song of solomon": "song of solomon",
}


def _normalize_book_name(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()
    return BOOK_NAME_ALIASES.get(cleaned, cleaned)


def _parse_reference(reference: str) -> tuple[str, int, int, int] | None:
    """Parse a reference like 'Psalm 91:14-16' into book/chapter/verse bounds."""
    ref = str(reference).strip()
    if ":" not in ref:
        return None

    book_part, verse_part = ref.split(":", 1)
    book_part = book_part.strip()
    verse_part = verse_part.strip()
    if not book_part or not verse_part:
        return None

    chapter_bits = book_part.rsplit(" ", 1)
    if len(chapter_bits) != 2 or not chapter_bits[1].isdigit():
        return None

    book_name, chapter_str = chapter_bits
    try:
        chapter_num = int(chapter_str)
        if "-" in verse_part:
            start_str, end_str = verse_part.split("-", 1)
            start_v = int(start_str.strip())
            end_v = int(end_str.strip())
        else:
            start_v = end_v = int(verse_part.strip())
    except ValueError:
        return None

    if start_v < 1 or end_v < start_v:
        return None

    return book_name, chapter_num, start_v, end_v


@lru_cache(maxsize=8)
def _load_source_index(source_file: str) -> dict[tuple[str, int, int, int], str]:
    """Load a scripture source file into a normalized lookup index.

    Supports two formats:
    - Flat list of verse dicts with `reference` and `text`
    - Nested book/chapter JSON like `data/en_kjv.json`
    """
    raw = json.loads(Path(source_file).read_text(encoding="utf-8-sig"))
    index: dict[tuple[str, int, int, int], str] = {}

    if isinstance(raw, list) and raw and all(isinstance(entry, dict) and "reference" in entry for entry in raw):
        # Flat list: index by parsed reference so both single verses and ranges work.
        for entry in raw:
            text = _clean_source_verse(str(entry.get("text", "")))
            if not text:
                continue
            parsed = _parse_reference(str(entry.get("reference", "")))
            if parsed is None:
                continue
            book_name, chapter_num, start_v, end_v = parsed
            index[(_normalize_book_name(book_name), chapter_num, start_v, end_v)] = text
        return index

    if isinstance(raw, list):
        for book in raw:
            if not isinstance(book, dict):
                continue
            book_name = str(book.get("name") or "").strip()
            if not book_name:
                continue
            chapters = book.get("chapters", [])
            if not isinstance(chapters, list):
                continue
            norm_book = _normalize_book_name(book_name)
            for chapter_num, chapter in enumerate(chapters, start=1):
                if not isinstance(chapter, list):
                    continue
                for verse_num, verse_text in enumerate(chapter, start=1):
                    text = _clean_source_verse(str(verse_text))
                    if text:
                        index[(norm_book, chapter_num, verse_num, verse_num)] = text
        return index

    raise ValueError(f"Unsupported scripture source format: {source_file}")


@lru_cache(maxsize=4096)
def _fetch_dailybible_text(reference: str) -> str | None:
    """Fallback scripture lookup using the DailyBible API."""
    try:
        ref_param = reference.replace(" ", "+")
        url = f"https://dailybible.ca/api/{ref_param}?translation=kjv"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "BibleShorts/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError):
        return None
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    text = str(data.get("text", "")).strip()
    if text:
        return _clean_source_verse(text)

    verses = data.get("verses", [])
    if isinstance(verses, list):
        parts = [
            _clean_source_verse(str(item.get("text", "")))
            for item in verses
            if isinstance(item, dict) and str(item.get("text", "")).strip()
        ]
        parts = [part for part in parts if part]
        if parts:
            return " ".join(parts).strip()

    return None


def _resolve_source_file(path: Path, scripture_source: str | Path | None) -> Path | None:
    if scripture_source:
        candidate = Path(scripture_source).expanduser()
        if not candidate.is_absolute():
            candidate = (path.parent / candidate).resolve()
        else:
            candidate = candidate.resolve()
        if candidate.exists():
            return candidate

    fallback = path.with_name("en_kjv.json")
    if fallback.exists():
        return fallback.resolve()

    return None


def load_verses(path: str | Path, scripture_source: str | Path | None = None) -> list[dict]:
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("verses file must contain a non-empty JSON array")

    # Key-list format: reference + devotional metadata. Hydrate scripture text from source.
    if all(isinstance(entry, dict) and "reference" in entry for entry in raw) and any(
        isinstance(entry, dict) and ("theme" in entry or "devotional_score" in entry) for entry in raw
    ):
        source_path = _resolve_source_file(Path(path), scripture_source)
        if source_path is None:
            raise FileNotFoundError(
                "Could not locate a scripture source file. Configure paths.scripture_source_file or place en_kjv.json beside the verses file."
            )

        source_index = _load_source_index(str(source_path))
        if not source_index:
            raise ValueError(f"Scripture source file {source_path} did not contain usable verse text")

        hydrated: list[dict] = []
        for entry in raw:
            reference = str(entry["reference"]).strip()
            text = lookup_verse_text(source_path, reference)
            if text is None:
                raise ValueError(f"Could not resolve source text for {reference} from {source_path}")
            verse = {k: v for k, v in entry.items() if k != "text"}
            verse["reference"] = reference
            verse["text"] = text
            hydrated.append(verse)
        return hydrated

    # Flat scripture source format: return as-is, but clean text for downstream use.
    if all(isinstance(entry, dict) and "reference" in entry and "text" in entry for entry in raw):
        return [
            {
                **entry,
                "reference": str(entry["reference"]).strip(),
                "text": _clean_source_verse(str(entry.get("text", ""))),
            }
            for entry in raw
        ]

    verses: list[dict] = []
    for book in raw:
        if not isinstance(book, dict) or "name" not in book or "chapters" not in book:
            raise ValueError(f"invalid verse entry: {book!r}")
        book_name = str(book["name"])
        chapters = book["chapters"]
        if not isinstance(chapters, list):
            raise ValueError(f"invalid chapters entry for {book_name!r}")
        for chapter_index, chapter in enumerate(chapters, start=1):
            if not isinstance(chapter, list):
                raise ValueError(f"invalid chapter entry for {book_name} {chapter_index}")
            for verse_index, verse_text in enumerate(chapter, start=1):
                text = _clean_source_verse(str(verse_text))
                if not text:
                    continue
                verses.append(
                    {
                        "reference": f"{book_name} {chapter_index}:{verse_index}",
                        "text": text,
                        "book": book_name,
                        "chapter": str(chapter_index),
                        "verse": str(verse_index),
                    }
                )

    if not verses:
        raise ValueError("verses file did not contain any usable verses")
    return verses


def lookup_verse_text(source_file: str | Path, reference: str) -> str | None:
    """Return the exact source verse text for a reference like 'John 3:16'."""
    path = Path(source_file)
    parsed = _parse_reference(reference)
    if parsed is not None and path.exists():
        try:
            source_index = _load_source_index(str(path.resolve()))
        except (OSError, ValueError, json.JSONDecodeError):
            source_index = {}

        if source_index:
            book_name, chapter_num, start_v, end_v = parsed
            norm_book = _normalize_book_name(book_name)
            exact_key = (norm_book, chapter_num, start_v, end_v)
            if exact_key in source_index:
                return source_index[exact_key]

            if start_v != end_v:
                parts = [
                    source_index.get((norm_book, chapter_num, verse_num, verse_num))
                    for verse_num in range(start_v, end_v + 1)
                ]
                if all(parts):
                    return " ".join(parts).strip()

    # API fallback for direct lookups or when the local source is unavailable.
    return _fetch_dailybible_text(reference)


def _clean_source_verse(text: str) -> str:
    """Remove footnote-style annotations {word: explanation} but preserve variant readings {word}.

    The KJV JSON uses two brace patterns:
    - Variant readings: {he is}, {endureth} — these are alternate word choices, part of the verse text.
    - Footnotes: {the light from...: Heb. between...} — these are study notes, not verse text.
    """
    # Strip leading bracketed headings such as [A Psalm of David.]
    text = re.sub(r"^(?:\s*\[[^\]]+\]\s*)+", "", text)

    # Strip footnote annotations FIRST: {word: explanation} -> remove entirely
    text = re.sub(r"\s*\{[^}]*:\s*[^}]*\}\s*", " ", text)

    # Then: expand variant readings {word} -> word (remove braces, keep the text)
    text = re.sub(r"\{([^{}]+)\}", r"\1", text)

    return " ".join(text.split()).strip()


def validate_scripture(reference: str, generated_scripture: str, source_file: str | Path) -> str | None:
    """Compare the generated scripture against the actual KJV source.

    Strips KJV inline annotations (e.g. `{an...: or, a flat plate}`) from both
    before comparing, since these are study notes, not part of the verse text.

    Returns a fix instruction if the scripture doesn't match, or None if it passes.
    """
    source_text = lookup_verse_text(source_file, reference)
    if source_text is None:
        return f"Could not find source verse for {reference}. Verify the reference is valid."

    gen_clean = re.sub(r"\s*\{[^}]*\}", "", generated_scripture.strip())
    src_clean = re.sub(r"\s*\{[^}]*\}", "", source_text.strip())
    gen_clean = " ".join(gen_clean.split())
    src_clean = " ".join(src_clean.split())

    if gen_clean == src_clean:
        return None

    similarity = difflib.SequenceMatcher(None, gen_clean.lower(), src_clean.lower()).ratio()

    if similarity < 0.60:
        return f"Scripture text does not match the source KJV verse. The actual text is: {src_clean}"

    if similarity < 0.90:
        words_gen = set(gen_clean.lower().split())
        words_src = set(src_clean.lower().split())
        missing = words_src - words_gen
        extra = words_gen - words_src
        notes: list[str] = []
        if missing and len(missing) > 3:
            notes.append(f"Missing KJV content. Include the full source text: {src_clean}")
        elif extra:
            notes.append(f"Scripture contains extra/paraphrased words not in the source KJV. Use exactly: {src_clean}")
        if not notes:
            notes.append(f"Scripture is close but not exact. Use the exact source text: {src_clean}")
        return " ".join(notes)

    return None
