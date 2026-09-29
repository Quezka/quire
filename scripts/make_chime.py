"""Render Quire's notification chime: two soft bell notes rising a fifth (C6, then G6).

Writes the same WAV for the desktop (quire/assets) and Android (res/raw), so both apps
sound alike. Run it again only to change the sound: `python scripts/make_chime.py`.
"""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = [ROOT / "quire" / "assets" / "chime.wav",
           ROOT / "android" / "app" / "src" / "main" / "res" / "raw" / "chime.wav"]
RATE = 44100
LENGTH = 0.85  # seconds
# (start in seconds, frequency in Hz, loudness)
NOTES = [(0.0, 1046.50, 0.9), (0.13, 1567.98, 1.0)]
# Bell-like partials: (multiple of the note, loudness, how fast it fades in seconds)
PARTIALS = [(1.0, 1.0, 0.32), (2.0, 0.28, 0.16), (3.01, 0.10, 0.09), (4.2, 0.04, 0.05)]
ATTACK = 0.004
PEAK = 0.5  # of full scale, so it isn't startling


def sample(t: float) -> float:
    value = 0.0
    for start, freq, loud in NOTES:
        s = t - start
        if s < 0:
            continue
        envelope = min(s / ATTACK, 1.0)
        for multiple, weight, fade in PARTIALS:
            value += loud * weight * envelope * math.exp(-s / fade) * math.sin(
                2 * math.pi * freq * multiple * s)
    return value


def render() -> bytes:
    count = int(RATE * LENGTH)
    raw = [sample(i / RATE) for i in range(count)]
    tail = int(RATE * 0.05)  # fade the last 50 ms to silence, so it ends without a click
    for i in range(tail):
        raw[count - tail + i] *= 1 - i / tail
    scale = PEAK / max(abs(v) for v in raw)
    return b"".join(struct.pack("<h", round(v * scale * 32767)) for v in raw)


def main() -> None:
    frames = render()
    for path in TARGETS:
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(RATE)
            out.writeframes(frames)
        print(path.relative_to(ROOT), path.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
