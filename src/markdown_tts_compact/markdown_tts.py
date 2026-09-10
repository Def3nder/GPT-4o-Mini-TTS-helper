# /// script
# requires-python = ">=3.12"
# dependencies = ["markdown-it-py>=3.0,<5.0", "mdit-py-plugins>=0.5,<1.0", "openai>=2.0,<3.0"]
# ///
"""Markdown -> MP3. Usage: uv run markdown_tts.py input.md

Settings live beside this file in config.json; the API key stays in the environment.
Short text uses one MP3 request. Long text uses calibrated, trimmed WAV chunks.
Requires ffmpeg/ffprobe for long text only. Cache lives beside this script;
temporary audio lives beside the output and is retained on failure for diagnosis.
The final MP3 is written beside the input and never overwrites an existing file.
No imports from the original markdown_tts package are required.
"""

from __future__ import annotations

import base64
import hashlib
from itertools import chain
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import wave

from markdown_it import MarkdownIt
from mdit_py_plugins.footnote import footnote_plugin
from openai import OpenAI

ROOT = Path(__file__).resolve().parent


def load_config():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8-sig"))
    # Validate before any paid request. Only settings used by this workflow exist.
    for section in ("parser", "renderer", "chunking", "tts", "prefill", "audio"):
        if not isinstance(cfg.get(section), dict):
            raise ValueError(f"Konfigurationsabschnitt fehlt: {section}")
    for section, keys in {
        "chunking": ("max_characters", "preferred_minimum_characters", "minimum_split_ratio"),
        "tts": ("speed", "timeout_seconds"),
        "prefill": ("analysis_window_milliseconds", "minimum_quiet_milliseconds", "minimum_remaining_seconds"),
        "audio": ("timeout_seconds", "duration_tolerance_seconds"),
    }.items():
        for key in keys:
            value = cfg[section][key]
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{section}.{key} muss eine positive Zahl sein.")
    c, p, t = cfg["chunking"], cfg["prefill"], cfg["tts"]
    if type(c["max_characters"]) is not int or not 0 < c["minimum_split_ratio"] <= 1:
        raise ValueError("Ungültiges Chunk-Limit oder Teilungsverhältnis.")
    if not 0 < c["preferred_minimum_characters"] <= c["max_characters"]:
        raise ValueError("Ungültige bevorzugte Chunk-Mindestlänge.")
    for key in ("text", "separator"):
        if not isinstance(p[key], str) or not p[key]:
            raise ValueError(f"prefill.{key} darf nicht leer sein.")
    if len(p["text"] + p["separator"]) >= c["max_characters"]:
        raise ValueError("Pre-Fill lässt keinen Platz für Nutztext.")
    for key in ("search_before_seconds", "search_after_seconds", "cut_safety_seconds"):
        if type(p[key]) not in (int, float) or not math.isfinite(p[key]) or p[key] < 0:
            raise ValueError(f"Ungültiger Wert: prefill.{key}")
    if not math.isfinite(p["quiet_threshold_dbfs"]) or p["quiet_threshold_dbfs"] >= 0:
        raise ValueError("Der Ruhepegel muss endlich und negativ sein.")
    if type(t["max_retries"]) is not int or t["max_retries"] < 0:
        raise ValueError("max_retries muss eine nichtnegative Ganzzahl sein.")
    for key in ("model", "voice", "instructions", "api_key_environment_variable"):
        if not isinstance(t[key], str) or not t[key].strip():
            raise ValueError(f"tts.{key} darf nicht leer sein.")
    re.compile(cfg["parser"]["url_pattern"])
    re.compile(cfg["parser"]["date_line_pattern"])
    return cfg


def speech_blocks(markdown, cfg):
    """Render Markdown tokens directly to (kind, text), without an extra AST.

    Tables, fenced code, HTML, images and footnotes are silent, as in the
    original default profile. Inline code and visible link labels are spoken.
    """
    p, r = cfg["parser"], cfg["renderer"]
    lines = markdown.splitlines(keepends=True)
    if lines and lines[0].strip() == p["front_matter_delimiter"]:
        for i in range(1, len(lines)):
            if lines[i].strip() == p["front_matter_delimiter"]:
                markdown = "".join(lines[i + 1:])
                break
    tokens = MarkdownIt("commonmark", {"html": True}).enable("table").use(footnote_plugin).parse(markdown)

    def inline(children):
        kept, line, previous_break = [], [], ""
        for token in [*children, None]:
            if token is None or token.type in ("softbreak", "hardbreak"):
                text = "".join(line)
                filtered = any(text.lstrip().startswith(s) for s in p["source_prefixes"])
                if not filtered and not re.fullmatch(p["date_line_pattern"], text.lstrip()):
                    if kept:
                        kept.append(previous_break)
                    kept.append(text)
                    previous_break = "\n" if token and token.type == "hardbreak" else " "
                line = []
            elif token.type in ("text", "code_inline"):
                line.append(re.sub(p["url_pattern"], "", token.content))
        return "".join(kept).strip()

    def walk(index, stop=None):
        blocks = []
        while index < len(tokens):
            token = tokens[index]
            kind = token.type
            index += 1
            if kind == stop:
                return blocks, index
            if kind in ("paragraph_open", "heading_open"):
                text = inline(tokens[index].children or [])
                index += 2
                heading = kind == "heading_open"
                if text and heading and not text.endswith(r["heading_suffix"]):
                    text += r["heading_suffix"]
                if text and (heading or any(ch.isalnum() for ch in text)):
                    blocks.append(("heading" if heading else "paragraph", text))
            elif kind in ("bullet_list_open", "ordered_list_open"):
                ordered = kind == "ordered_list_open"
                number = int(token.attrGet("start") or 1)
                items = []
                while tokens[index].type == "list_item_open":
                    children, index = walk(index + 1, "list_item_close")
                    text = r["list_item_separator"].join(t for _, t in children)
                    if text:
                        markers = r["ordered_list_markers"]
                        marker = (markers[number - 1] if 1 <= number <= len(markers)
                                  else r["ordered_list_fallback"].format(number=number)) if ordered else ""
                        items.append((marker + r["list_marker_suffix"] if marker else "") + text)
                    number += 1
                index += 1
                if items:
                    blocks.append(("list", r["list_item_separator"].join(items)))
            elif kind == "blockquote_open":
                children, index = walk(index, "blockquote_close")
                if children:
                    blocks.append(("quote", r["block_separator"].join(t for _, t in children)))
            elif kind in ("table_open", "footnote_block_open"):
                end = kind.replace("_open", "_close")
                while index < len(tokens) and tokens[index].type != end:
                    index += 1
                index += 1
        return blocks, index

    return walk(0)[0]


def chunk_text(blocks, cfg):
    c = cfg["chunking"]
    separator = cfg["renderer"]["block_separator"]
    limit = c["max_characters"] - len(cfg["prefill"]["text"] + cfg["prefill"]["separator"])
    chunks, current = [], []

    def flush():
        if current:
            chunks.append(separator.join(t for _, t in current))
            current.clear()

    def split_at(text, available):
        minimum = max(1, int(available * c["minimum_split_ratio"]))
        for characters in c["boundary_groups"]:
            for i in range(min(available - 1, len(text) - 1), minimum - 1, -1):
                if text[i] in characters and (i + 1 == len(text) or text[i + 1].isspace()):
                    return i + 1
        for i in range(min(available, len(text) - 1), 0, -1):
            if text[i].isspace():
                return i
        return 0

    for kind, text in blocks:
        if kind == "heading":
            flush()
        while text:
            available = limit - len(separator.join(t for _, t in current)) - (len(separator) if current else 0)
            if len(text) <= available:
                current.append((kind, text))
                break
            heading_needs_content = len(current) == 1 and current[0][0] == "heading"
            if current and ((len(text) <= limit and not heading_needs_content)
                            or not (heading_needs_content or available >= c["preferred_minimum_characters"])):
                flush()
                continue
            cut = split_at(text, available)
            if not cut:
                if current:
                    flush()
                    continue
                raise ValueError("Textabschnitt überschreitet das Limit ohne trennbare Wortgrenze.")
            current.append((kind, text[:cut].strip()))
            text = text[cut:].strip()
            flush()
    flush()
    return chunks


def synthesize(client, text, path, cfg):
    """Decode SSE audio; cost-reporting and provider abstractions are omitted."""
    t = cfg["tts"]
    if not text.strip() or len(text) > cfg["chunking"]["max_characters"]:
        raise ValueError("Leerer Sprechtext oder Request-Limit überschritten.")
    done, data = False, []
    with client.audio.speech.with_streaming_response.create(
        model=t["model"], voice=t["voice"], instructions=t["instructions"].strip(),
        speed=t["speed"], input=text, response_format=path.suffix[1:],
        stream_format="sse", extra_headers={"Accept": "text/event-stream"},
    ) as response, path.open("wb") as output:
        for line in chain(response.iter_lines(), [""]):
            if line.startswith("data:"):
                data.append(line[5:].lstrip())
            elif not line and data:
                payload = "\n".join(data)
                data.clear()
                # SSE terminates with a non-JSON marker after speech.audio.done.
                # The marker alone does not prove that synthesis completed.
                if payload.strip() == "[DONE]":
                    continue
                event = json.loads(payload)
                if not isinstance(event, dict):
                    raise RuntimeError("TTS-Audiostream enthält ein ungültiges SSE-Ereignis.")
                if event.get("type") == "speech.audio.delta":
                    output.write(base64.b64decode(event["audio"], validate=True))
                elif event.get("type") == "speech.audio.done":
                    done = True
                elif event.get("type") == "error":
                    raise RuntimeError("TTS-Dienst meldet einen Fehler im Audiostream.")
    if not done or not path.stat().st_size:
        raise RuntimeError("TTS-Audiostream ist leer oder unvollständig.")


def read_wav(path):
    """Read actual PCM bytes, tolerating streaming placeholder header lengths."""
    with wave.open(str(path), "rb") as source:
        signature = (source.getnchannels(), source.getsampwidth(), source.getframerate())
        if source.getcomptype() != "NONE" or signature[1] not in (1, 2, 3, 4):
            raise ValueError("Nicht unterstütztes WAV-PCM-Format.")
        data = b"".join(iter(lambda: source.readframes(65536), b""))
    if min(signature) <= 0 or not data or len(data) % (signature[0] * signature[1]):
        raise ValueError("WAV enthält keine vollständigen PCM-Frames.")
    return signature, data


def write_wav(path, signature, data):
    with wave.open(str(path), "wb") as target:
        target.setnchannels(signature[0])
        target.setsampwidth(signature[1])
        target.setframerate(signature[2])
        target.writeframes(data)


def trim_prefill(signature, data, expected_seconds, cfg):
    """Same window/region selection and safety margin as the original trimmer."""
    p = cfg["prefill"]
    channels, width, rate = signature
    frame_bytes = channels * width
    frames = len(data) // frame_bytes
    start = max(0, math.floor((expected_seconds - p["search_before_seconds"]) * rate))
    end = min(frames, math.ceil((expected_seconds + p["search_after_seconds"]) * rate))
    window = max(1, round(p["analysis_window_milliseconds"] * rate / 1000))
    minimum = math.ceil(p["minimum_quiet_milliseconds"] * rate / 1000)
    regions, active = [], None
    for pos in range(start, end, window):
        stop = min(pos + window, end)
        raw = data[pos * frame_bytes:stop * frame_bytes]
        samples = [int.from_bytes(raw[i:i + width], "little", signed=width != 1)
                   - (128 if width == 1 else 0) for i in range(0, len(raw), width)]
        rms = math.sqrt(sum(s * s for s in samples) / len(samples))
        dbfs = 20 * math.log10(rms / (1 << (8 * width - 1))) if rms else -math.inf
        if dbfs <= p["quiet_threshold_dbfs"]:
            if active is None:
                active = pos
        elif active is not None:
            if pos - active >= minimum:
                regions.append((active, pos))
            active = None
    if active is not None and end - active >= minimum:
        regions.append((active, end))
    safe = [(a, b) for a, b in regions if a <= round(expected_seconds * rate)]
    if not safe:
        raise ValueError("Keine sichere Ruhephase an der Pre-Fill-Grenze gefunden; Schnitt abgebrochen.")
    a, b = max(safe)
    cut = max(a, (a + b) // 2 - round(p["cut_safety_seconds"] * rate))
    if frames - cut < math.ceil(p["minimum_remaining_seconds"] * rate):
        raise ValueError("Nach dem Pre-Fill-Schnitt verbleibt zu wenig Audio.")
    return data[cut * frame_bytes:]


def calibration(client, cfg, work):
    key = {"schema": 1, "tts": cfg["tts"], "prefill": cfg["prefill"]}
    digest = hashlib.sha256(json.dumps(key, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    cache = ROOT / ".cache" / (digest + ".wav")
    if cache.is_file():
        try:
            signature, data = read_wav(cache)
            return signature, len(data) / math.prod(signature)
        except (OSError, ValueError, EOFError, wave.Error):
            pass  # An invalid cache is rebuilt; never use a guessed boundary.
    print("Pre-Fill wird kalibriert.")
    raw = work / "calibration.wav"
    synthesize(client, cfg["prefill"]["text"], raw, cfg)
    signature, data = read_wav(raw)
    cache.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=cache.parent, suffix=".wav")
    os.close(fd)
    temporary = Path(name)
    try:
        write_wav(temporary, signature, data)
        temporary.replace(cache)
    finally:
        temporary.unlink(missing_ok=True)
    return signature, len(data) / math.prod(signature)


def encode_mp3(source, target, cfg, expected_duration):
    a = cfg["audio"]
    subprocess.run([a["ffmpeg"], "-nostdin", "-v", "error", "-n", "-i", str(source),
                    "-c:a", "libmp3lame", "-b:a", a["bitrate"], str(target)],
                   check=True, capture_output=True, timeout=a["timeout_seconds"])
    result = subprocess.run([a["ffprobe"], "-v", "error", "-show_entries",
                             "stream=codec_name:format=duration", "-of", "json", str(target)],
                            check=True, capture_output=True, timeout=a["timeout_seconds"])
    info = json.loads(result.stdout)
    duration = float(info["format"]["duration"])
    if (not any(s.get("codec_name") == "mp3" for s in info["streams"])
            or not math.isfinite(duration)
            or abs(duration - expected_duration) > a["duration_tolerance_seconds"]):
        raise ValueError("MP3-Prüfung fehlgeschlagen: Codec oder Dauer stimmen nicht.")


def convert(input_path, cfg, client=None):
    source = Path(input_path).resolve()
    target = source.with_suffix(".mp3")
    if target.exists():
        raise FileExistsError(f"Ausgabedatei existiert bereits: {target}")
    blocks = speech_blocks(source.read_text(encoding="utf-8-sig"), cfg)
    text = cfg["renderer"]["block_separator"].join(t for _, t in blocks)
    if not text.strip():
        raise ValueError("Das Dokument enthält keinen sprechbaren Text.")
    long_text = len(text) > cfg["chunking"]["max_characters"]
    chunks = chunk_text(blocks, cfg) if long_text else [text]
    if long_text:
        for tool in ("ffmpeg", "ffprobe"):
            if not shutil.which(cfg["audio"][tool]):
                raise ValueError(f"{tool} wurde nicht gefunden.")
    owned_client = client is None
    if owned_client:
        t = cfg["tts"]
        api_key = os.environ.get(t["api_key_environment_variable"], "").strip()
        if not api_key:
            raise ValueError(f"API-Key fehlt in Umgebungsvariable {t['api_key_environment_variable']}.")
        client = OpenAI(api_key=api_key, timeout=t["timeout_seconds"], max_retries=t["max_retries"])
    work = Path(tempfile.mkdtemp(prefix=".markdown-tts-", dir=target.parent))
    try:
        staged = work / "output.mp3"
        if not long_text:
            print(f"Direkte Synthese: {len(text)} Zeichen, ohne Pre-Fill.")
            synthesize(client, text, staged, cfg)
        else:
            signature, duration = calibration(client, cfg, work)
            total_bytes = 0
            combined = work / "combined.wav"
            with wave.open(str(combined), "wb") as joined:
                joined.setnchannels(signature[0])
                joined.setsampwidth(signature[1])
                joined.setframerate(signature[2])
                for index, chunk in enumerate(chunks, 1):
                    print(f"Chunk {index}/{len(chunks)} mit Pre-Fill.")
                    raw = work / f"chunk-{index:03}.wav"
                    synthesize(client, cfg["prefill"]["text"] + cfg["prefill"]["separator"] + chunk, raw, cfg)
                    actual, data = read_wav(raw)
                    if actual != signature:
                        raise ValueError("WAV-Parameter weichen von der Pre-Fill-Kalibrierung ab.")
                    trimmed = trim_prefill(signature, data, duration, cfg)
                    joined.writeframesraw(trimmed)
                    total_bytes += len(trimmed)
            encode_mp3(combined, staged, cfg, total_bytes / math.prod(signature))
        # Same-filesystem hard link publishes atomically and refuses overwrite,
        # including a destination created by another process during synthesis.
        os.link(staged, target)
    except BaseException:
        print(f"Verarbeitung fehlgeschlagen; Arbeitsdateien bleiben erhalten: {work}", file=sys.stderr)
        raise
    else:
        shutil.rmtree(work)
    finally:
        if owned_client:
            client.close()
    return target


def main():
    if len(sys.argv) == 2 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    if len(sys.argv) != 2:
        print("Aufruf: uv run markdown_tts.py input.md", file=sys.stderr)
        return 2
    try:
        print(f"Audiodatei erzeugt: {convert(sys.argv[1], load_config())}")
        return 0
    except Exception as error:
        print(f"Fehler: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
