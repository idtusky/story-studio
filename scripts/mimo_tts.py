"""Xiaomi MiMo TTS via the OpenAI-compatible chat completions endpoint to a verified MP3.

Uses only the Python standard library for the HTTP request; no automatic retries.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request
import uuid

from studio_runtime import activate_runtime, find_executable
from voice_settings import VoiceConfigError, load_profile, read_api_key, validate_profile
from doubao_tts import TtsError, validate_audio

URL = "https://api.xiaomimimo.com/v1/chat/completions"
SAMPLE_MIME = {".mp3": "audio/mpeg", ".wav": "audio/wav"}


def request_body(profile: dict, text: str) -> dict:
    model = profile["model"]
    messages = []
    style = profile.get("style")
    if style:
        messages.append({"role": "user", "content": style})
    elif model == "mimo-v2.5-tts-voicedesign":
        raise TtsError("voicedesign requires a voice design description before synthesis")
    # The text to speak always travels in the assistant message, never in user content.
    messages.append({"role": "assistant", "content": text})
    audio = {"format": "mp3"}
    if model == "mimo-v2.5-tts":
        audio["voice"] = profile.get("voice") or "mimo_default"
    elif model == "mimo-v2.5-tts-voiceclone":
        sample = Path(profile["voice_sample"])
        payload = sample.read_bytes()
        audio["voice"] = "data:{};base64,{}".format(
            SAMPLE_MIME[sample.suffix.lower()], base64.b64encode(payload).decode("ascii"))
    return {"model": model, "messages": messages, "audio": audio, "stream": False}


def parse_audio(body: object) -> tuple[bytes, object]:
    if not isinstance(body, dict):
        raise TtsError("MiMo returned a non-object response")
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise TtsError("MiMo completed without choices")
    finish = choices[0].get("finish_reason")
    if finish == "length":
        raise TtsError("MiMo generation stopped early; split the narration into segments and reassemble")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise TtsError("MiMo completed without a message")
    audio = message.get("audio")
    if not isinstance(audio, dict):
        raise TtsError("MiMo completed without audio")
    data = audio.get("data")
    if not isinstance(data, str) or not data:
        raise TtsError("MiMo completed without audio data")
    try:
        return base64.b64decode(data.encode("ascii"), validate=True), body.get("usage")
    except (ValueError, UnicodeEncodeError):
        raise TtsError("MiMo returned invalid base64 audio") from None


def synthesize(text: str, profile: dict, key: str, partial: Path) -> tuple[int, object]:
    payload = request_body(profile, text)
    request = urllib.request.Request(URL, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "api-key": key},
                                     method="POST")
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        # Never echo provider payloads; the status and Agent review are enough to act on.
        raise TtsError(
            "MiMo HTTP {}; inspect the speech-key access, quota and request parameters".format(error.code)) from None
    except urllib.error.URLError as error:
        raise TtsError("MiMo network request failed; Agent must inspect connectivity or proxy settings") from error
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise TtsError("MiMo returned an unreadable response; treat the request as possibly billed") from None
    audio, usage = parse_audio(body)
    if not audio:
        raise TtsError("MiMo completed without audio bytes")
    with partial.open("xb") as output:
        output.write(audio)
    return len(audio), usage


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model")
    parser.add_argument("--voice")
    parser.add_argument("--style")
    parser.add_argument("--voice-sample")
    parser.add_argument("--voice-confirmed", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    paid_attempt = False
    try:
        text = args.text_file.read_text(encoding="utf-8-sig")
        if not text.strip() or args.output.suffix.lower() != ".mp3":
            raise TtsError("A nonempty narration file and .mp3 output are required")
        overrides = {"model": args.model, "voice": args.voice, "style": args.style, "voice_sample": args.voice_sample}
        profile = (validate_profile({key: value for key, value in overrides.items() if value is not None},
                                    provider="mimo")
                   if any(overrides.values()) else load_profile("mimo"))
        report = {"provider": "mimo",
                  # Local voice-sample paths stay out of saved metadata; a hash identifies the sample instead.
                  "voice": {key: value for key, value in profile.items() if key != "voice_sample"},
                  "text_sha256": hashlib.sha256(text.encode()).hexdigest(), "characters": len(text),
                  "protocol": "mimo-tts-chat-completions"}
        if profile.get("voice_sample"):
            report["voice_sample_sha256"] = hashlib.sha256(Path(profile["voice_sample"]).read_bytes()).hexdigest()
        if args.dry_run:
            print(json.dumps(dict(report, network=False, billable_request_sent=False), ensure_ascii=False))
            return 0
        if not args.voice_confirmed:
            raise TtsError("Confirm the narration and exact voice parameters with the user first")
        if args.output.exists():
            raise TtsError("Output exists; reuse it or select a new version")
        metadata = args.output.with_suffix(".voice.json")
        if metadata.exists():
            raise TtsError("Voice metadata exists; select a new output version")
        ffmpeg, ffprobe = find_executable("ffmpeg"), find_executable("ffprobe")
        if not ffmpeg or not ffprobe:
            raise TtsError("Initialize the tts dependency profile before synthesis")
        for tool in (ffmpeg, ffprobe):
            subprocess.run([tool, "-version"], capture_output=True, check=True, timeout=20)
        key = read_api_key("mimo")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        partial = args.output.with_name(args.output.name + "." + uuid.uuid4().hex + ".partial")
        paid_attempt = True
        size, usage = synthesize(text, profile, key, partial)
        duration = validate_audio(partial, ffprobe, ffmpeg)
        # Windows rename refuses to replace an existing file; POSIX requires link.
        if os.name == "nt":
            partial.rename(args.output)
        else:
            os.link(partial, args.output)
            partial.unlink()
        report.update(duration=duration, audio_sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
                      usage=usage, output=str(args.output.resolve()), voice_confirmed=True,
                      structure_verified=True, listening_verified=False, billable_request_sent=True,
                      received_bytes=size)
        with metadata.open("x", encoding="utf-8") as output:
            json.dump(report, output, ensure_ascii=False, indent=2)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        # Never print provider payloads, headers or credential values.
        message = str(exc) if isinstance(exc, (TtsError, VoiceConfigError)) else "MiMo TTS failed; Agent must inspect authentication, resource access, network or local audio tools"
        print(json.dumps({"ready": False, "error": message, "request_may_have_been_billed": paid_attempt,
                          "automatic_retry": False, "partial_output_retained": paid_attempt}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    activate_runtime()
    raise SystemExit(main())