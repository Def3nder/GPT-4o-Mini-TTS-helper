"""OpenAI implementation of the provider-independent TTS contract."""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Iterator, Mapping

from openai import OpenAI, OpenAIError

from markdown_tts.config import TTSProviderConfig
from markdown_tts.tts.base import SpeechRequest, SpeechSynthesisResult, SpeechUsage


LOGGER = logging.getLogger(__name__)


class MissingApiKeyError(ValueError):
    """Raised when the configured API-key environment variable is unavailable."""


class OutputFileExistsError(FileExistsError):
    """Raised before an existing audio file would be overwritten."""


class TTSGenerationError(RuntimeError):
    """Raised when audio generation fails with an actionable explanation."""


class OpenAITTSProvider:
    """Generate audio through OpenAI without exposing API concerns upstream."""

    def __init__(
        self,
        config: TTSProviderConfig,
        *,
        environment: Mapping[str, str] | None = None,
        client: Any | None = None,
    ) -> None:
        self._config = config
        active_environment = os.environ if environment is None else environment
        api_key = active_environment.get(config.api_key_environment_variable, "").strip()
        if not api_key:
            raise MissingApiKeyError(
                "OpenAI API-Key nicht gefunden. Erwartete Windows-Umgebungsvariable: "
                f"'{config.api_key_environment_variable}'. Bitte die Variable setzen und "
                "PowerShell bzw. die Anwendung anschließend neu starten."
            )
        self._client = client or OpenAI(
            api_key=api_key,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
        )

    def synthesize(
        self,
        request: SpeechRequest,
        output_path: str | Path,
        *,
        overwrite: bool = False,
    ) -> SpeechSynthesisResult:
        """Stream one request into an atomically published file with actual usage."""
        destination = Path(output_path)
        expected_suffix = f".{self._config.response_format.lower()}"
        if destination.suffix.lower() != expected_suffix:
            raise TTSGenerationError(
                f"Ausgabedatei muss zur Konfiguration passen und auf '{expected_suffix}' enden."
            )
        if destination.exists() and not overwrite:
            raise OutputFileExistsError(
                f"Ausgabedatei '{destination}' existiert bereits. "
                "Zum Ersetzen ausdrücklich '--overwrite' verwenden."
            )

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            file_descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.stem}-",
                suffix=f"{destination.suffix}.part",
                dir=destination.parent,
            )
            os.close(file_descriptor)
        except OSError as error:
            raise TTSGenerationError(
                f"Temporäre Audiodatei für '{destination}' konnte nicht angelegt werden. "
                "Bitte Zielpfad und Schreibrechte prüfen."
            ) from error

        temporary_path = Path(temporary_name)
        LOGGER.info(
            "Starte OpenAI-TTS: Modell=%s, Format=%s, Ziel=%s",
            self._config.model,
            self._config.response_format,
            destination,
        )
        usage: SpeechUsage | None = None
        try:
            with self._client.audio.speech.with_streaming_response.create(
                model=self._config.model,
                voice=request.voice,
                input=request.text,
                instructions=request.instructions,
                response_format=self._config.response_format,
                speed=request.speed,
                stream_format=self._config.stream_format,
                extra_headers=(
                    {"Accept": "text/event-stream"}
                    if self._config.stream_format == "sse"
                    else None
                ),
            ) as response:
                if self._config.stream_format == "sse":
                    usage = _stream_sse_audio(response, temporary_path)
                else:
                    response.stream_to_file(temporary_path)

            if destination.exists() and not overwrite:
                raise OutputFileExistsError(
                    f"Ausgabedatei '{destination}' wurde während der Erzeugung angelegt; "
                    "sie wurde nicht überschrieben."
                )
            temporary_path.replace(destination)
        except OutputFileExistsError:
            raise
        except TTSGenerationError:
            raise
        except OpenAIError as error:
            raise TTSGenerationError(
                _format_openai_error(error)
            ) from error
        except OSError as error:
            raise TTSGenerationError(
                f"Audiodatei '{destination}' konnte nicht gespeichert werden. "
                "Bitte Zielpfad und freien Speicher prüfen."
            ) from error
        finally:
            temporary_path.unlink(missing_ok=True)

        LOGGER.info(
            "OpenAI-TTS abgeschlossen: %s%s",
            destination,
            (
                f"; Input-Tokens={usage.input_tokens}, "
                f"Output-Tokens={usage.output_tokens}"
                if usage is not None
                else "; keine Usage-Daten im Audio-Streammodus"
            ),
        )
        return SpeechSynthesisResult(destination, usage)


def _stream_sse_audio(response: Any, destination: Path) -> SpeechUsage:
    """Decode documented speech SSE events into audio bytes and final usage."""
    usage: SpeechUsage | None = None
    audio_byte_count = 0
    try:
        with destination.open("wb") as target:
            for event in _iter_sse_events(response.iter_lines()):
                event_type = event.get("type")
                if event_type == "speech.audio.delta":
                    encoded_audio = event.get("audio")
                    if not isinstance(encoded_audio, str) or not encoded_audio:
                        raise TTSGenerationError(
                            "OpenAI-SSE-Audioereignis enthält keine Audiodaten."
                        )
                    try:
                        audio = base64.b64decode(encoded_audio, validate=True)
                    except (binascii.Error, ValueError) as error:
                        raise TTSGenerationError(
                            "OpenAI-SSE-Audioereignis enthält ungültige Base64-Daten."
                        ) from error
                    target.write(audio)
                    audio_byte_count += len(audio)
                elif event_type == "speech.audio.done":
                    usage = _parse_speech_usage(event.get("usage"))
                elif event_type == "error":
                    raise TTSGenerationError(
                        _format_sse_error(event)
                    )
    except OSError as error:
        raise TTSGenerationError(
            f"Gestreamte Audiodaten konnten nicht in '{destination}' geschrieben werden."
        ) from error

    if audio_byte_count <= 0:
        raise TTSGenerationError("OpenAI-Speech-Stream enthielt keine Audiodaten.")
    if usage is None:
        raise TTSGenerationError(
            "OpenAI-Speech-Stream endete ohne 'speech.audio.done' und Usage-Daten."
        )
    return usage


def _format_openai_error(error: OpenAIError) -> str:
    """Expose the SDK's server message without dumping response bodies or requests."""
    sdk_message = getattr(error, "message", None)
    detail = _safe_error_detail(
        sdk_message if isinstance(sdk_message, str) else str(error)
    )
    status_code = getattr(error, "status_code", None)
    status = f" (HTTP {status_code})" if isinstance(status_code, int) else ""
    if detail:
        return f"OpenAI konnte die Audiodatei nicht erzeugen{status}: {detail}"
    return (
        f"OpenAI konnte die Audiodatei nicht erzeugen{status}. Bitte API-Key, Guthaben, "
        "Modellzugriff und Netzwerkverbindung prüfen."
    )


def _format_sse_error(event: dict[str, Any]) -> str:
    """Extract only the documented human-readable detail from an SSE error event."""
    raw_error = event.get("error")
    raw_message = raw_error.get("message") if isinstance(raw_error, dict) else raw_error
    detail = _safe_error_detail(raw_message)
    if detail:
        return f"OpenAI meldete während des Speech-Streams einen Fehler: {detail}"
    return "OpenAI meldete während des Speech-Streams einen Fehler."


def _safe_error_detail(value: object) -> str:
    """Normalize and bound provider text without serializing arbitrary payload data."""
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:1000]


def _iter_sse_events(lines: Iterable[str]) -> Iterator[dict[str, Any]]:
    """Parse JSON data fields from a server-sent event line stream."""
    data_lines: list[str] = []
    for line in lines:
        if line:
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
            continue
        if data_lines:
            yield _decode_sse_data("\n".join(data_lines))
            data_lines = []
    if data_lines:
        yield _decode_sse_data("\n".join(data_lines))


def _decode_sse_data(data: str) -> dict[str, Any]:
    if data == "[DONE]":
        return {"type": "done"}
    try:
        event = json.loads(data)
    except json.JSONDecodeError as error:
        raise TTSGenerationError(
            "OpenAI-Speech-Stream enthielt ungültiges SSE-JSON."
        ) from error
    if not isinstance(event, dict):
        raise TTSGenerationError(
            "OpenAI-Speech-Stream enthielt ein unerwartetes SSE-Ereignis."
        )
    return event


def _parse_speech_usage(raw: Any) -> SpeechUsage:
    if not isinstance(raw, dict):
        raise TTSGenerationError(
            "OpenAI-Abschlussereignis enthält keine gültigen Usage-Daten."
        )
    try:
        usage = SpeechUsage(
            input_tokens=int(raw["input_tokens"]),
            output_tokens=int(raw["output_tokens"]),
            total_tokens=int(raw["total_tokens"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise TTSGenerationError(
            "OpenAI-Abschlussereignis enthält unvollständige Usage-Daten."
        ) from error
    if min(usage.input_tokens, usage.output_tokens, usage.total_tokens) < 0:
        raise TTSGenerationError("OpenAI-Usage-Daten enthalten negative Tokenwerte.")
    return usage
