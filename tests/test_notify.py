"""Quire's notification chime: one sound for the desktop and the phone."""
import wave
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from quire.presentation import notify  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ANDROID_CHIME = ROOT / "android" / "app" / "src" / "main" / "res" / "raw" / "chime.wav"


def test_desktop_and_phone_share_the_same_short_chime():
    assert notify.CHIME.read_bytes() == ANDROID_CHIME.read_bytes()
    with wave.open(str(notify.CHIME)) as chime:
        seconds = chime.getnframes() / chime.getframerate()
        # 16-bit PCM WAV: what winsound, pw-play/paplay, GNOME and Android all play.
        assert (chime.getnchannels(), chime.getsampwidth()) == (1, 2)
    assert 0.3 < seconds < 1.5


def test_a_server_that_plays_sounds_gets_the_chime():
    hints = notify.sound_hints(True, True, Path("/x/chime.wav"))
    assert "--hint=string:sound-file:/x/chime.wav" in hints


@pytest.mark.parametrize("sound, server_plays", [(False, True), (False, False), (True, False)])
def test_otherwise_the_server_stays_quiet(sound, server_plays):
    # Off: silence. No server sound: Quire plays the chime itself, so no second sound.
    assert notify.sound_hints(sound, server_plays) == ["--hint=boolean:suppress-sound:true"]

