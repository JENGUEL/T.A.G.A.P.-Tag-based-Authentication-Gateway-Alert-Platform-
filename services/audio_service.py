"""
T.A.G.A.P. - Audio Service

Cross-platform audio feedback for the kiosk.
Plays WAV files without blocking the UI thread.
"""
import logging
import os
import subprocess
import sys
from pathlib import Path
from config import PROJECT_ROOT

logger = logging.getLogger(__name__)

SOUNDS_DIR = PROJECT_ROOT / "assets" / "sounds"

class AudioService:
    @staticmethod
    def _play_file(filename: str):
        file_path = SOUNDS_DIR / filename
        if not file_path.exists():
            logger.warning("Audio file missing: %s", file_path)
            return

        try:
            if sys.platform == "win32":
                import winsound
                winsound.PlaySound(str(file_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            elif sys.platform == "darwin":  # macOS
                subprocess.Popen(["afplay", str(file_path)])
            else:  # Linux (Raspberry Pi)
                subprocess.Popen(["aplay", "-q", str(file_path)])
        except Exception as e:
            logger.error("Failed to play audio %s: %s", filename, e)

    @classmethod
    def beep(cls):
        """Standard success/scan beep."""
        cls._play_file("beep.wav")

    @classmethod
    def error(cls):
        """Error/Alert beep."""
        cls._play_file("error.wav")