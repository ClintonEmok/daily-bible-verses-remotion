from pathlib import Path
import json
import re
import numpy as np
import soundfile as sf
from kokoro import KPipeline

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
SRC = ROOT / "src"
OUT = ROOT / "out"
PUBLIC.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

REFERENCE = "PSALM 23:4"
BLOCKS = [
    ("opening", "Some valleys feel dark because we cannot see ahead. But the Shepherd does not leave us."),
    ("intro", "Psalm 23:4 says:"),
    ("verse", "Yea, though I walk through the valley of the shadow of death,"),
    ("verse", "I will fear no evil:"),
    ("verse", "for thou art with me;"),
    ("verse", "thy rod and thy staff they comfort me."),
    ("reflection", "The valley may remain, but we do not walk through it alone. The Lord is with us."),
    ("prayer", "Lord, when the way feels dark, help me trust that You are near. Amen."),
    ("closing", "You do not walk alone today."),
]

pipeline = KPipeline(lang_code="a")
parts = []
for kind, text in BLOCKS:
    chunks = list(pipeline(text, voice="af_heart", speed=0.90))
    if not chunks:
        raise RuntimeError(f"Kokoro returned no audio for: {text}")
    parts.append(np.concatenate([np.asarray(chunk.audio, dtype=np.float32) for chunk in chunks]))

sample_rate = 24000
pause = np.zeros(int(sample_rate * 0.12), dtype=np.float32)
combined_parts = []
for i, part in enumerate(parts):
    combined_parts.append(part)
    if i < len(parts) - 1:
        combined_parts.append(pause)
combined = np.concatenate(combined_parts)

audio_name = "psalm_23_4_devotional_af_heart.wav"
audio_path = PUBLIC / audio_name
sf.write(audio_path, combined, sample_rate)

time = 0.0
cues = []
for i, ((kind, text), part) in enumerate(zip(BLOCKS, parts)):
    start = time
    end = start + len(part) / sample_rate
    cues.append({
        "index": i,
        "kind": kind,
        "text": text,
        "start": round(start, 4),
        "end": round(end, 4),
    })
    time = end + (0.12 if i < len(parts) - 1 else 0.0)

data = {
    "reference": REFERENCE,
    "audio": audio_name,
    "voice": "af_heart",
    "speed": 0.90,
    "duration": round(len(combined) / sample_rate, 4),
    "word_count": len(re.findall(r"\b[\w']+\b", " ".join(text for _, text in BLOCKS))),
    "mode": "devotional",
    "alignment": "Kokoro block boundaries; no WhisperX",
    "blocks": cues,
}
(SRC / "devotionalSampleData.ts").write_text(
    "export const DEVOTIONAL = " + json.dumps(data, indent=2) + " as const;\n",
    encoding="utf-8",
)

def srt_time(seconds):
    total_ms = round(seconds * 1000)
    hours, rem = divmod(total_ms, 3600000)
    minutes, rem = divmod(rem, 60000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

srt = []
for i, cue in enumerate(cues, 1):
    srt.extend([str(i), f"{srt_time(cue['start'])} --> {srt_time(cue['end'])}", cue["text"], ""])
(OUT / "sample_psalm_23_4_devotional.srt").write_text("\\n".join(srt), encoding="utf-8")
print(json.dumps(data, indent=2))
