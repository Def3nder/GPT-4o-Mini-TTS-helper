"""Replaceable audio postprocessing interfaces and implementations."""

from markdown_tts.audio.base import (
    AudioCompatibilityError,
    AudioDependencyError,
    AudioJoinError,
    AudioJoiner,
    AudioOutputExistsError,
    AudioProcessingError,
)
from markdown_tts.audio.encoder import (
    AudioEncoder,
    AudioEncodingError,
    FFmpegAudioEncoder,
    UnsupportedAudioEncoderError,
    create_audio_encoder,
)
from markdown_tts.audio.factory import UnsupportedAudioJoinerError, create_audio_joiner
from markdown_tts.audio.ffmpeg_joiner import AudioProperties, FFmpegAudioJoiner
from markdown_tts.audio.prefill_trimmer import (
    PrefillTrimError,
    PrefillTrimResult,
    WavPrefillTrimmer,
)
from markdown_tts.audio.wav_joiner import WavAudioJoiner
from markdown_tts.audio.wav_support import (
    WavProperties,
    configure_pcm_wav_writer,
    inspect_wav,
)

__all__ = [
    "AudioCompatibilityError",
    "AudioDependencyError",
    "AudioJoinError",
    "AudioJoiner",
    "AudioOutputExistsError",
    "AudioProcessingError",
    "AudioProperties",
    "AudioEncoder",
    "AudioEncodingError",
    "FFmpegAudioJoiner",
    "FFmpegAudioEncoder",
    "PrefillTrimError",
    "PrefillTrimResult",
    "UnsupportedAudioJoinerError",
    "UnsupportedAudioEncoderError",
    "WavAudioJoiner",
    "WavPrefillTrimmer",
    "WavProperties",
    "configure_pcm_wav_writer",
    "create_audio_encoder",
    "create_audio_joiner",
    "inspect_wav",
]
