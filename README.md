# Daily Bible Verses Remotion

A clean Remotion + React renderer for the Daily Bible Verses KJV channel.

The project supports two formats:

- `BibleShort`: verse-only KJV reading with phrase-level highlighting
- `DevotionalSample`: verse-specific opening, scripture, reflection, and prayer

Both formats use Kokoro `af_heart` at speed `0.90`. Audio and visual timing come from the generated Kokoro phrase or block boundaries, so the displayed text is the exact text being spoken. WhisperX is not required for this renderer.

## Requirements

- Node.js 18+
- FFmpeg
- Python environment with Kokoro and SoundFile for regenerating audio
- Remotion 4

The existing local Kokoro environment is:

```text
/Users/clintonemok/miniconda3/envs/bible-shorts/bin/python
```

## Install

```bash
npm install
```

## Preview

```bash
npm run dev
```

## Render

```bash
npm run render:verse
npm run render:devotional
```

Rendered files are written to `out/`, which is intentionally ignored by Git.

## Regenerate samples

```bash
/Users/clintonemok/miniconda3/envs/bible-shorts/bin/python scripts/generate_verse_sample.py
/Users/clintonemok/miniconda3/envs/bible-shorts/bin/python scripts/generate_devotional_sample.py
```

The generators:

1. Define the exact spoken text
2. Generate Kokoro `af_heart` audio
3. Record phrase or block durations
4. Write the timing data used by Remotion
5. Generate matching SRT captions for the devotional sample

## Backgrounds

Place approved 9:16 background images in `public/backgrounds/`. The production renderer will select varied backgrounds deterministically and avoid repeats until the pool is exhausted. Backgrounds should remain dark enough for scripture readability.

## Devotional quality bar

Devotionals must be specific to the verse, natural when spoken, theologically careful, and concise. A future writer/reviewer stage should reject generic reflections, unsupported promises, invented context, inaccurate scripture paraphrases, and filler language.

## Security

YouTube OAuth credentials, SQLite state, rendered backlog files, and environment files do not belong in this repository.
