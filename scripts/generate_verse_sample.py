from pathlib import Path
import json
import numpy as np
import soundfile as sf
from kokoro import KPipeline

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
SRC = ROOT / "src"
PUBLIC.mkdir(parents=True, exist_ok=True)

REFERENCE = "ISAIAH 41:10"
PHRASES = [
    "Fear thou not; for I am with thee:",
    "be not dismayed; for I am thy God:",
    "I will strengthen thee;",
    "yea, I will help thee;",
    "yea, I will uphold thee with the right hand of my righteousness.",
]

pipeline = KPipeline(lang_code="a")
parts = []
for phrase in PHRASES:
    chunks = list(pipeline(phrase, voice="af_heart", speed=0.90))
    if not chunks:
        raise RuntimeError(f"Kokoro returned no audio for: {phrase}")
    audio = np.concatenate([np.asarray(chunk.audio, dtype=np.float32) for chunk in chunks])
    parts.append(audio)

sample_rate = 24000
pause = np.zeros(int(sample_rate * 0.10), dtype=np.float32)
combined = np.concatenate([part if i == len(parts) - 1 else np.concatenate([part, pause]) for i, part in enumerate(parts)])
audio_path = PUBLIC / "isaiah_41_10_af_heart_verse_only.wav"
sf.write(audio_path, combined, sample_rate)

time = 0.0
cues = []
for i, (phrase, part) in enumerate(zip(PHRASES, parts)):
    start = time
    end = start + len(part) / sample_rate
    cues.append({"index": i, "text": phrase, "start": round(start, 4), "end": round(end, 4)})
    time = end + (0.10 if i < len(parts) - 1 else 0.0)

data = {
    "reference": REFERENCE,
    "phrases": cues,
    "audio": audio_path.name,
    "duration": round(len(combined) / sample_rate, 4),
    "voice": "af_heart",
    "mode": "verse-only",
    "alignment": "Kokoro phrase chunk boundaries; no WhisperX",
}
(SRC / "sampleData.ts").write_text(
    "export const SAMPLE = " + json.dumps(data, indent=2) + " as const;\n",
    encoding="utf-8",
)
print(json.dumps(data, indent=2))
