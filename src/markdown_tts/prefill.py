"""Provider-independent prefill request decoration and calibration metadata."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from markdown_tts.config import PrefillConfig, SpeechProfile, TTSProviderConfig
from markdown_tts.tts.base import SpeechRequest


class PrefillCalibrationError(ValueError):
    """Raised when calibration metadata is missing, invalid, or incompatible."""


class PrefillRequestDecorator:
    """Prepend one configured warm-up sentence to a provider request."""

    def __init__(self, config: PrefillConfig) -> None:
        self._config = config

    @property
    def reserved_characters(self) -> int:
        """Return the exact request capacity consumed by the prefill."""
        return self._config.reserved_characters

    def decorate(self, request: SpeechRequest) -> SpeechRequest:
        """Return a request whose body follows the fixed prefill and separator."""
        return replace(request, text=f"{self._config.request_prefix}{request.text}")


@dataclass(frozen=True, slots=True)
class PrefillCalibration:
    """Measured prefill duration bound to one exact synthesis configuration."""

    schema_version: int
    configuration_sha256: str
    prefill_text: str
    prefill_separator: str
    profile_name: str
    voice: str
    speed: float
    instructions_sha256: str
    model: str
    provider: str
    response_format: str
    stream_format: str
    duration_seconds: float
    sample_rate: int
    channels: int
    sample_width_bytes: int

    @classmethod
    def create(
        cls,
        config: PrefillConfig,
        profile: SpeechProfile,
        provider: TTSProviderConfig,
        *,
        duration_seconds: float,
        sample_rate: int,
        channels: int,
        sample_width_bytes: int,
    ) -> PrefillCalibration:
        """Create calibration metadata from one measured WAV synthesis."""
        return cls(
            schema_version=3,
            configuration_sha256=prefill_configuration_fingerprint(
                config,
                profile,
                provider,
            ),
            prefill_text=config.text,
            prefill_separator=config.separator,
            profile_name=profile.name,
            voice=profile.voice,
            speed=profile.speed,
            instructions_sha256=_instructions_digest(profile.instructions),
            model=provider.model,
            provider=provider.provider,
            response_format=provider.response_format.casefold(),
            stream_format=provider.stream_format.casefold(),
            duration_seconds=duration_seconds,
            sample_rate=sample_rate,
            channels=channels,
            sample_width_bytes=sample_width_bytes,
        )

    @classmethod
    def from_file(cls, path: str | Path) -> PrefillCalibration:
        """Load and validate calibration metadata from JSON."""
        calibration_path = Path(path)
        try:
            raw: Any = json.loads(calibration_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise PrefillCalibrationError(
                f"Prefill-Kalibrierung '{calibration_path}' konnte nicht gelesen werden: {error}"
            ) from error
        if not isinstance(raw, dict):
            raise PrefillCalibrationError("Prefill-Kalibrierung muss ein JSON-Objekt sein.")
        try:
            calibration = cls(
                schema_version=int(raw["schema_version"]),
                configuration_sha256=str(raw["configuration_sha256"]),
                prefill_text=str(raw["prefill_text"]),
                prefill_separator=str(raw["prefill_separator"]),
                profile_name=str(raw["profile_name"]),
                voice=str(raw["voice"]),
                speed=float(raw["speed"]),
                instructions_sha256=str(raw["instructions_sha256"]),
                model=str(raw["model"]),
                provider=str(raw["provider"]),
                response_format=str(raw["response_format"]),
                stream_format=str(raw["stream_format"]),
                duration_seconds=float(raw["duration_seconds"]),
                sample_rate=int(raw["sample_rate"]),
                channels=int(raw["channels"]),
                sample_width_bytes=int(raw["sample_width_bytes"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise PrefillCalibrationError(
                "Prefill-Kalibrierung enthält unvollständige oder ungültige Werte."
            ) from error
        if calibration.schema_version != 3:
            raise PrefillCalibrationError(
                f"Nicht unterstützte Prefill-Kalibrierungsversion: "
                f"{calibration.schema_version}."
            )
        if calibration.duration_seconds <= 0:
            raise PrefillCalibrationError("Kalibrierte Prefill-Dauer muss positiv sein.")
        if min(
            calibration.sample_rate,
            calibration.channels,
            calibration.sample_width_bytes,
        ) <= 0:
            raise PrefillCalibrationError("Kalibrierte WAV-Parameter müssen positiv sein.")
        return calibration

    def assert_compatible(
        self,
        config: PrefillConfig,
        profile: SpeechProfile,
        provider: TTSProviderConfig,
    ) -> None:
        """Reject stale calibration before any paid provider request begins."""
        expected = {
            "Konfigurations-Fingerprint": (
                self.configuration_sha256,
                prefill_configuration_fingerprint(config, profile, provider),
            ),
            "Vorspannsatz": (self.prefill_text, config.text),
            "Vorspann-Trenner": (self.prefill_separator, config.separator),
            "Profil": (self.profile_name, profile.name),
            "Stimme": (self.voice, profile.voice),
            "Geschwindigkeit": (self.speed, profile.speed),
            "Instructions": (
                self.instructions_sha256,
                _instructions_digest(profile.instructions),
            ),
            "Modell": (self.model, provider.model),
            "Provider": (self.provider, provider.provider),
            "Ausgabeformat": (
                self.response_format.casefold(),
                provider.response_format.casefold(),
            ),
            "Streamformat": (
                self.stream_format.casefold(),
                provider.stream_format.casefold(),
            ),
        }
        mismatch = next(
            (name for name, (actual, required) in expected.items() if actual != required),
            None,
        )
        if mismatch is not None:
            raise PrefillCalibrationError(
                f"Prefill-Kalibrierung passt nicht zur aktuellen Einstellung '{mismatch}'. "
                "Bitte neu kalibrieren."
            )

    def write(self, path: str | Path, *, overwrite: bool = False) -> Path:
        """Publish calibration metadata atomically."""
        destination = Path(path)
        if destination.exists() and not overwrite:
            raise PrefillCalibrationError(
                f"Kalibrierungsdatei '{destination}' existiert bereits. "
                "Zum Ersetzen ausdrücklich '--overwrite' verwenden."
            )
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.stem}-",
                suffix=f"{destination.suffix}.part",
                dir=destination.parent,
            )
            os.close(descriptor)
        except OSError as error:
            raise PrefillCalibrationError(
                f"Temporäre Kalibrierungsdatei für '{destination}' konnte nicht "
                "angelegt werden. Bitte Zielpfad und Schreibrechte prüfen."
            ) from error
        temporary_path = Path(temporary_name)
        try:
            temporary_path.write_text(
                json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            if destination.exists() and not overwrite:
                raise PrefillCalibrationError(
                    f"Kalibrierungsdatei '{destination}' wurde zwischenzeitlich angelegt."
                )
            temporary_path.replace(destination)
        except OSError as error:
            raise PrefillCalibrationError(
                f"Kalibrierungsdatei '{destination}' konnte nicht gespeichert werden. "
                "Bitte Zielpfad und freien Speicher prüfen."
            ) from error
        finally:
            temporary_path.unlink(missing_ok=True)
        return destination


def _instructions_digest(instructions: str) -> str:
    return hashlib.sha256(instructions.strip().encode("utf-8")).hexdigest()


def prefill_configuration_fingerprint(
    config: PrefillConfig,
    profile: SpeechProfile,
    provider: TTSProviderConfig,
) -> str:
    """Hash the canonical values that can affect prefill synthesis and its boundary."""
    effective_configuration = {
        # Version 3 also binds calibration to the provider stream format; SSE
        # usage reporting can alter the wire representation of streamed WAVs.
        "fingerprint_schema": 3,
        "prefill": {
            "text": config.text,
            "separator": config.separator,
        },
        "profile": {
            "name": profile.name,
            "voice": profile.voice,
            "speed": profile.speed,
            "instructions": profile.instructions.strip(),
        },
        "provider": {
            "name": provider.provider,
            "model": provider.model,
            "response_format": provider.response_format.casefold(),
            "stream_format": provider.stream_format.casefold(),
        },
    }
    canonical_json = json.dumps(
        effective_configuration,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def prefill_calibration_cache_path(
    cache_directory: str | Path,
    config: PrefillConfig,
    profile: SpeechProfile,
    provider: TTSProviderConfig,
) -> Path:
    """Return a deterministic cache path for one effective synthesis configuration."""
    safe_profile_name = re.sub(r"[^A-Za-z0-9._-]+", "-", profile.name).strip("-.")
    if not safe_profile_name:
        safe_profile_name = "profile"
    fingerprint = prefill_configuration_fingerprint(config, profile, provider)
    return Path(cache_directory) / f"{safe_profile_name}-{fingerprint}.json"


def prefill_calibration_audio_path(calibration_path: str | Path) -> Path:
    """Return the persistent normalized WAV belonging to calibration metadata."""
    return Path(calibration_path).with_suffix(".wav")
