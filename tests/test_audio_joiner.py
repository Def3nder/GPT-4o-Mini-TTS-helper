from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from markdown_tts.audio import (
    AudioCompatibilityError,
    AudioJoinError,
    AudioOutputExistsError,
    FFmpegAudioJoiner,
)
from markdown_tts.config import AudioJoinerConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _FakeAudioCommands:
    def __init__(self, properties: dict[str, tuple[str, int, int, float]]) -> None:
        self.properties = properties
        self.calls: list[list[str]] = []
        self.concat_manifest = ""

    def __call__(self, command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        executable = Path(command[0]).stem.casefold()
        if "ffprobe" in executable:
            path = Path(command[-1])
            codec, sample_rate, channels, duration = self.properties[path.name]
            payload = {
                "streams": [
                    {
                        "codec_name": codec,
                        "sample_rate": str(sample_rate),
                        "channels": channels,
                    }
                ],
                "format": {"duration": str(duration)},
            }
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(payload),
                stderr="",
            )

        manifest = Path(command[command.index("-i") + 1])
        self.concat_manifest = manifest.read_text(encoding="utf-8")
        Path(command[-1]).write_bytes(b"ID3-joined")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")


def _resolve_fake_executable(name: str) -> str:
    return f"C:/fake/{name}.exe"


class FFmpegAudioJoinerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = AudioJoinerConfig.from_file(
            PROJECT_ROOT / "config" / "audio_joiner.json"
        )

    def test_joins_compatible_streams_without_reencoding(self) -> None:
        commands = _FakeAudioCommands(
            {
                "part-001.mp3": ("mp3", 24000, 1, 10.0),
                "part-002.mp3": ("mp3", 24000, 1, 5.5),
                "joined.mp3": ("mp3", 24000, 1, 15.5),
            }
        )
        joiner = FFmpegAudioJoiner(
            self.config,
            runner=commands,
            executable_resolver=_resolve_fake_executable,
        )

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            root = Path(directory)
            first = root / "part-001.mp3"
            second = root / "part-002.mp3"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            output = root / "final.mp3"

            result = joiner.join((first, second), output)

            self.assertEqual(result, output)
            self.assertEqual(output.read_bytes(), b"ID3-joined")
            ffmpeg_call = next(
                call for call in commands.calls if "ffmpeg" in Path(call[0]).stem.casefold()
            )
            self.assertEqual(ffmpeg_call[ffmpeg_call.index("-c") + 1], "copy")
            self.assertIn("ffconcat version 1.0", commands.concat_manifest)
            self.assertLess(
                commands.concat_manifest.index("part-001.mp3"),
                commands.concat_manifest.index("part-002.mp3"),
            )

    def test_refuses_existing_output_before_running_tools(self) -> None:
        commands = _FakeAudioCommands({})
        joiner = FFmpegAudioJoiner(
            self.config,
            runner=commands,
            executable_resolver=_resolve_fake_executable,
        )

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            root = Path(directory)
            first = root / "part-001.mp3"
            second = root / "part-002.mp3"
            output = root / "final.mp3"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            output.write_bytes(b"existing")

            with self.assertRaises(AudioOutputExistsError):
                joiner.join((first, second), output)

            self.assertEqual(commands.calls, [])
            self.assertEqual(output.read_bytes(), b"existing")

    def test_rejects_incompatible_stream_parameters(self) -> None:
        commands = _FakeAudioCommands(
            {
                "part-001.mp3": ("mp3", 24000, 1, 10.0),
                "part-002.mp3": ("mp3", 44100, 2, 5.0),
            }
        )
        joiner = FFmpegAudioJoiner(
            self.config,
            runner=commands,
            executable_resolver=_resolve_fake_executable,
        )

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            root = Path(directory)
            first = root / "part-001.mp3"
            second = root / "part-002.mp3"
            first.write_bytes(b"first")
            second.write_bytes(b"second")

            with self.assertRaises(AudioCompatibilityError):
                joiner.join((first, second), root / "final.mp3")

            self.assertFalse(any("ffmpeg" in Path(call[0]).stem for call in commands.calls))

    def test_does_not_publish_output_when_duration_validation_fails(self) -> None:
        commands = _FakeAudioCommands(
            {
                "part-001.mp3": ("mp3", 24000, 1, 10.0),
                "part-002.mp3": ("mp3", 24000, 1, 5.0),
                "joined.mp3": ("mp3", 24000, 1, 8.0),
            }
        )
        joiner = FFmpegAudioJoiner(
            replace(self.config, duration_tolerance_seconds=0.5),
            runner=commands,
            executable_resolver=_resolve_fake_executable,
        )

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            root = Path(directory)
            first = root / "part-001.mp3"
            second = root / "part-002.mp3"
            output = root / "final.mp3"
            first.write_bytes(b"first")
            second.write_bytes(b"second")

            with self.assertRaisesRegex(AudioJoinError, "Dauer"):
                joiner.join((first, second), output)

            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
