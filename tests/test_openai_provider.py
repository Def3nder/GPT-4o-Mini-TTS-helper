from __future__ import annotations

import base64
from collections.abc import Iterator
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from openai import OpenAIError

from markdown_tts.config import TTSProviderConfig
from markdown_tts.tts.base import SpeechRequest
from markdown_tts.tts.openai_provider import (
    MissingApiKeyError,
    OpenAITTSProvider,
    OutputFileExistsError,
    TTSGenerationError,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _FakeStreamingResponse:
    def __enter__(self) -> _FakeStreamingResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def iter_lines(self) -> Iterator[str]:
        events = (
            {
                "type": "speech.audio.delta",
                "audio": base64.b64encode(b"ID3-fake-audio").decode("ascii"),
            },
            {
                "type": "speech.audio.done",
                "usage": {
                    "input_tokens": 14,
                    "output_tokens": 120,
                    "total_tokens": 134,
                },
            },
        )
        for event in events:
            yield f"event: {event['type']}"
            yield f"data: {json.dumps(event)}"
            yield ""


class _FakeCreate:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> _FakeStreamingResponse:
        self.calls.append(kwargs)
        return _FakeStreamingResponse()


class OpenAITTSProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = TTSProviderConfig.from_file(
            PROJECT_ROOT / "config" / "tts_provider.json"
        )
        self.create = _FakeCreate()
        self.client = SimpleNamespace(
            audio=SimpleNamespace(
                speech=SimpleNamespace(
                    with_streaming_response=SimpleNamespace(create=self.create)
                )
            )
        )

    def test_streams_to_atomic_output_with_configured_model(self) -> None:
        provider = OpenAITTSProvider(
            self.config,
            environment={self.config.api_key_environment_variable: "test-secret"},
            client=self.client,
        )
        request = SpeechRequest(
            text="Kurzer Test.",
            voice="cedar",
            instructions="Sprich klar.",
        )

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            output = Path(directory) / "speech.mp3"
            result = provider.synthesize(request, output)

            self.assertEqual(result.output_path, output)
            self.assertEqual(output.read_bytes(), b"ID3-fake-audio")
            self.assertIsNotNone(result.usage)
            assert result.usage is not None
            self.assertEqual(result.usage.input_tokens, 14)
            self.assertEqual(result.usage.output_tokens, 120)
            self.assertEqual(result.usage.total_tokens, 134)
            self.assertEqual(len(self.create.calls), 1)
            call = self.create.calls[0]
            self.assertEqual(call["model"], self.config.model)
            self.assertEqual(call["voice"], "cedar")
            self.assertEqual(call["speed"], 1.0)
            self.assertEqual(call["response_format"], "mp3")
            self.assertEqual(call["stream_format"], "sse")
            self.assertEqual(call["extra_headers"], {"Accept": "text/event-stream"})

    def test_does_not_publish_sse_audio_without_done_usage(self) -> None:
        class _IncompleteResponse(_FakeStreamingResponse):
            def iter_lines(self) -> Iterator[str]:
                event = {
                    "type": "speech.audio.delta",
                    "audio": base64.b64encode(b"partial").decode("ascii"),
                }
                yield f"data: {json.dumps(event)}"
                yield ""

        client = SimpleNamespace(
            audio=SimpleNamespace(
                speech=SimpleNamespace(
                    with_streaming_response=SimpleNamespace(
                        create=lambda **kwargs: _IncompleteResponse()
                    )
                )
            )
        )
        provider = OpenAITTSProvider(
            self.config,
            environment={self.config.api_key_environment_variable: "test-secret"},
            client=client,
        )

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            output = Path(directory) / "speech.mp3"
            with self.assertRaisesRegex(TTSGenerationError, "Usage-Daten"):
                provider.synthesize(SpeechRequest("Test", "cedar", ""), output)
            self.assertFalse(output.exists())

    def test_refuses_to_overwrite_existing_output_by_default(self) -> None:
        provider = OpenAITTSProvider(
            self.config,
            environment={self.config.api_key_environment_variable: "test-secret"},
            client=self.client,
        )
        request = SpeechRequest("Test", "cedar", "")

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            output = Path(directory) / "speech.mp3"
            output.write_bytes(b"existing")

            with self.assertRaises(OutputFileExistsError):
                provider.synthesize(request, output)

            self.assertEqual(output.read_bytes(), b"existing")
            self.assertEqual(self.create.calls, [])

    def test_requires_configured_environment_variable(self) -> None:
        with self.assertRaisesRegex(MissingApiKeyError, "GPT-4o-Mini-TTS-Key"):
            OpenAITTSProvider(self.config, environment={}, client=self.client)

    def test_preserves_specific_openai_error_message(self) -> None:
        def fail_with_specific_error(**kwargs: object) -> None:
            raise OpenAIError("Input exceeds the model's maximum context length")

        client = SimpleNamespace(
            audio=SimpleNamespace(
                speech=SimpleNamespace(
                    with_streaming_response=SimpleNamespace(
                        create=fail_with_specific_error
                    )
                )
            )
        )
        provider = OpenAITTSProvider(
            self.config,
            environment={self.config.api_key_environment_variable: "test-secret"},
            client=client,
        )

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            output = Path(directory) / "speech.mp3"
            with self.assertRaisesRegex(
                TTSGenerationError,
                "maximum context length",
            ):
                provider.synthesize(SpeechRequest("Test", "cedar", ""), output)

            self.assertFalse(output.exists())

    def test_preserves_specific_sse_error_message(self) -> None:
        class _ErrorResponse(_FakeStreamingResponse):
            def iter_lines(self) -> Iterator[str]:
                event = {
                    "type": "error",
                    "error": {
                        "type": "invalid_request_error",
                        "message": "Input text is too long",
                    },
                }
                yield f"data: {json.dumps(event)}"
                yield ""

        client = SimpleNamespace(
            audio=SimpleNamespace(
                speech=SimpleNamespace(
                    with_streaming_response=SimpleNamespace(
                        create=lambda **kwargs: _ErrorResponse()
                    )
                )
            )
        )
        provider = OpenAITTSProvider(
            self.config,
            environment={self.config.api_key_environment_variable: "test-secret"},
            client=client,
        )

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            output = Path(directory) / "speech.mp3"
            with self.assertRaisesRegex(TTSGenerationError, "Input text is too long"):
                provider.synthesize(SpeechRequest("Test", "cedar", ""), output)

            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
