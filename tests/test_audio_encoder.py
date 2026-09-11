from __future__ import annotations

import json
from pathlib import Path
import struct
import subprocess
from tempfile import TemporaryDirectory
import unittest
import wave

from markdown_tts.audio import FFmpegAudioEncoder
from markdown_tts.config import AudioEncoderConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_one_second_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(1000)
        target.writeframes(struct.pack("<h", 1000) * 1000)


class _EncoderCommands:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        if "ffprobe" in Path(command[0]).stem.casefold():
            payload = {
                "streams": [{"codec_name": "mp3"}],
                "format": {"duration": "1.000"},
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
        Path(command[-1]).write_bytes(b"ID3-encoded")
        return subprocess.CompletedProcess(command, 0, "", "")


class FFmpegAudioEncoderTests(unittest.TestCase):
    def test_encodes_wav_once_and_validates_final_codec_and_duration(self) -> None:
        config = AudioEncoderConfig.from_file(
            PROJECT_ROOT / "config" / "audio_encoder.json"
        )
        commands = _EncoderCommands()
        encoder = FFmpegAudioEncoder(
            config,
            runner=commands,
            executable_resolver=lambda name: f"C:/fake/{name}.exe",
        )

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            root = Path(directory)
            source = root / "source.wav"
            output = root / "final.mp3"
            _write_one_second_wav(source)

            result = encoder.encode(source, output)

            self.assertEqual(result.read_bytes(), b"ID3-encoded")
            ffmpeg_call = next(
                call
                for call in commands.calls
                if "ffmpeg" in Path(call[0]).stem.casefold()
            )
            self.assertIn("libmp3lame", ffmpeg_call)
            self.assertEqual(ffmpeg_call[ffmpeg_call.index("-q:a") + 1], "5")
            self.assertNotIn("-b:a", ffmpeg_call)


if __name__ == "__main__":
    unittest.main()
