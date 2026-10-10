"""Explicit Gradium voice commands. tts/stt spend credits; credits/voices are read-only."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from _paths import ROOT
from guide2build.core.environment import load_local_environment
from guide2build.voice.gradium import GradiumClient, GradiumError

CONTENT_TYPES = {".wav": "audio/wav", ".pcm": "audio/pcm", ".ogg": "audio/ogg", ".opus": "audio/opus"}
EXTENSIONS = {"wav": ".wav", "opus": ".ogg"}


def write_receipt(folder: Path, receipt: dict) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = folder / f"{receipt['command']}-{stamp}-{receipt['input_sha256'][:12]}.json"
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    return path


def run(args, client_factory=GradiumClient) -> dict:
    load_local_environment(ROOT)
    out_dir = args.data_dir / "gradium"
    with client_factory() as client:
        if args.command == "credits":
            return {"status": "ok", "credits": client.credits()}
        if args.command == "voices":
            voices = client.voices(include_catalog=not args.custom_only)
            return {"status": "ok", "count": len(voices), "voices": voices}
        started = time.monotonic()
        if args.command == "tts":
            digest = hashlib.sha256(json.dumps([args.text, args.voice_id, args.format]).encode()).hexdigest()
            receipt = {"command": "tts", "endpoint": "POST /post/speech/tts", "input_sha256": digest,
                       "voice_id": args.voice_id, "output_format": args.format, "characters": len(args.text)}
            try:
                audio = client.tts(args.text, args.voice_id, output_format=args.format)
            except GradiumError as error:
                write_receipt(out_dir, receipt | {"status": "failed", "code": error.code,
                                                  "elapsed_seconds": time.monotonic() - started})
                raise
            output = args.out or out_dir / f"tts-{digest[:12]}{EXTENSIONS.get(args.format, '.pcm')}"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(audio)
            receipt |= {"status": "completed", "output": str(output), "output_bytes": len(audio),
                        "output_sha256": hashlib.sha256(audio).hexdigest(),
                        "elapsed_seconds": time.monotonic() - started}
        else:
            audio = args.audio.read_bytes()
            content_type = args.content_type or CONTENT_TYPES.get(args.audio.suffix.lower(), "audio/wav")
            receipt = {"command": "stt", "endpoint": "POST /post/speech/asr",
                       "input_sha256": hashlib.sha256(audio).hexdigest(), "input_bytes": len(audio),
                       "content_type": content_type, "language": args.language}
            try:
                transcript = client.stt(audio, content_type=content_type, language=args.language)
            except GradiumError as error:
                write_receipt(out_dir, receipt | {"status": "failed", "code": error.code,
                                                  "elapsed_seconds": time.monotonic() - started})
                raise
            receipt |= {"status": "completed", "transcript": transcript,
                        "elapsed_seconds": time.monotonic() - started}
        receipt["receipt"] = str(write_receipt(out_dir, receipt))
        return receipt


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--data-dir", type=Path, default=ROOT / "var")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("credits", help="Show remaining Gradium credits (free)")
    voices = commands.add_parser("voices", help="List available voices (free)")
    voices.add_argument("--custom-only", action="store_true", help="Exclude the Gradium catalog voices")
    tts = commands.add_parser("tts", help="Synthesize text to an audio file (spends credits)")
    tts.add_argument("--text", required=True)
    tts.add_argument("--voice-id", required=True)
    tts.add_argument("--format", default="wav")
    tts.add_argument("--out", type=Path)
    stt = commands.add_parser("stt", help="Transcribe an audio file (spends credits)")
    stt.add_argument("--audio", type=Path, required=True)
    stt.add_argument("--language", default="en")
    stt.add_argument("--content-type")
    return root


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        result = run(args)
    except GradiumError as error:
        print(json.dumps({"status": "blocked", "code": error.code, "message": str(error)}))
        return 2
    except OSError as error:
        print(json.dumps({"status": "blocked", "code": "invalid_input", "message": type(error).__name__}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
