# Daily Bible Verses Remotion

A clean Remotion + React production renderer for the Daily Bible Verses KJV YouTube channel.

## Formats

- `BibleShort`: verse-only KJV reading with phrase-level highlighting
- `DevotionalSample`: verse-specific opening, exact scripture, reflection, and prayer

Devotionals end on the prayer. There is no separate closing section.

Both formats use Kokoro `af_heart` at speed `0.90`. Audio and visual timing come from generated Kokoro phrase or block boundaries, so the displayed text is the exact text being spoken. WhisperX is not required for this renderer.

## Production workflow

`scripts/run_production.py` is the canonical production entry point:

```text
KJV pool → verse reservation → devotional JSON → Kokoro audio →
Remotion props → 1080×1920 MP4 → YouTube upload → API read-back → cleanup
```

Run a local render without uploading:

```bash
cd /Users/clintonemok/Personal/Mum/Youtube/daily-bible-verses-remotion
PYTHONPATH=src /Users/clintonemok/miniconda3/envs/bible-shorts/bin/python \
  scripts/run_production.py --slot test --script-json scripts/fixtures/psalm_23_4.json
```

Run production with an LLM-generated devotional and upload:

```bash
PYTHONPATH=src /Users/clintonemok/miniconda3/envs/bible-shorts/bin/python \
  scripts/run_production.py --slot 06:20 --upload
```

The production config is non-secret at `config/production.json`. API keys are loaded from the private Hermes environment. YouTube OAuth settings live outside the repository at:

```text
~/.hermes/profiles/bible-shorts/youtube_settings.json
```

## Background palette

Every production run receives the next palette in a persistent no-repeat cycle:

`emerald → navy → purple → teal → indigo → plum → forest → slate`

These are Remotion CSS gradients, not downloaded image assets. The selected palette is stored in the rebuild record, so a render can be reproduced exactly.

## Retention policy

Before upload, the working directory contains the MP4, WAV, SRT, and Remotion props JSON.

After YouTube returns a video ID, the runner reads the video back through the YouTube API. Only after that verification succeeds does it delete:

- Rendered MP4
- Generated WAV
- SRT file
- Temporary Remotion props JSON

It retains a compact JSON record under `data/records/` containing the exact KJV text, devotional script, palette, timing blocks, YouTube video ID, and deleted artifact paths. That record plus the source code and KJV pool is enough to rebuild the video if needed.

If upload or read-back verification fails, no artifacts are deleted.

## Requirements

- Node.js 18+
- FFmpeg with `ffprobe`
- Remotion 4
- Python environment with `kokoro==0.9.4`, `numpy<2`, `soundfile`, and `requests`

The current local Kokoro environment is:

```text
/Users/clintonemok/miniconda3/envs/bible-shorts/bin/python
```

Install JavaScript dependencies with:

```bash
npm install
```

Install the small Python runtime set in an appropriate environment with:

```bash
python -m pip install -r requirements.txt
```

## Samples and checks

```bash
npm run check
npm run sample:verse
npm run sample:devotional
npm run render:verse
npm run render:devotional
```

## Security and repository hygiene

The repository intentionally excludes OAuth credentials, API keys, environment files, production state, rebuild records, generated audio, subtitles, and rendered videos. Keep secrets in the private Hermes profile, not in Git.
