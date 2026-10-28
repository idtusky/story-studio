"""Local TTS voice profiles and optional protected per-provider credential storage."""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import re
import sys
import uuid

from studio_runtime import ROOT, data_dir

PROVIDERS = ("doubao", "mimo")
DOUBAO_RESOURCES = {"seed-tts-2.0", "seed-icl-2.0"}
MIMO_MODELS = {"mimo-v2.5-tts", "mimo-v2.5-tts-voicedesign", "mimo-v2.5-tts-voiceclone"}
KEY_ENV = {"doubao": "DOUBAO_TTS_API_KEY", "mimo": "MIMO_API_KEY"}
SECRET_NAME = {"doubao": "doubao-key", "mimo": "mimo-key"}


class VoiceConfigError(ValueError):
    pass


def outside_source(path: Path) -> Path:
    path = path.expanduser().resolve()
    if path.is_relative_to(ROOT):
        raise VoiceConfigError("Voice configuration must stay outside the skill source")
    return path


def profile_path() -> Path:
    return outside_source(data_dir() / "voice.json")


def secret_path(provider: str = "doubao") -> Path:
    if provider not in PROVIDERS:
        raise VoiceConfigError(f"Unsupported TTS provider {provider!r}")
    name = SECRET_NAME[provider] + (".dpapi" if os.name == "nt" else ".secret")
    return outside_source(data_dir() / name)


def validate_profile(profile: dict, provider: str | None = None) -> dict:
    if not isinstance(profile, dict):
        raise VoiceConfigError("Voice profile must be an object")
    selected = profile.get("provider") or provider or "doubao"
    if selected not in PROVIDERS:
        raise VoiceConfigError(f"Unsupported TTS provider {selected!r}")
    allowed = {"provider"}
    if selected == "doubao":
        allowed |= {"speaker", "resource_id", "model", "speech_rate", "loudness_rate"}
    else:
        allowed |= {"model", "voice", "style", "voice_sample"}
    if set(profile) - allowed:
        raise VoiceConfigError(f"Voice profile contains unsupported fields for {selected}")
    result = {"provider": selected}
    if selected == "doubao":
        speaker = profile.get("speaker")
        if not isinstance(speaker, str) or not speaker.strip() or any(c.isspace() for c in speaker):
            raise VoiceConfigError("A nonempty speaker ID without whitespace is required")
        if profile.get("resource_id") not in DOUBAO_RESOURCES:
            raise VoiceConfigError("Select seed-tts-2.0 or seed-icl-2.0 for this V3 adapter")
        model = profile.get("model")
        if model is not None and (not isinstance(model, str) or not model.strip() or any(c.isspace() for c in model)):
            raise VoiceConfigError("Model must be a nonempty model ID")
        if model and profile["resource_id"] != "seed-icl-2.0":
            raise VoiceConfigError("The explicit model parameter is reserved for cloned voices")
        for name in ("speech_rate", "loudness_rate"):
            value = profile.get(name, 0)
            if type(value) is not int or not -50 <= value <= 100:
                raise VoiceConfigError("Speech and loudness rates must be integers in -50..100")
        return {"provider": selected, "speaker": speaker, "resource_id": profile["resource_id"],
                "model": model, "speech_rate": profile.get("speech_rate", 0),
                "loudness_rate": profile.get("loudness_rate", 0)}
    model = profile.get("model")
    if model not in MIMO_MODELS:
        raise VoiceConfigError(f"Select a MiMo TTS model from {', '.join(sorted(MIMO_MODELS))}")
    voice = profile.get("voice")
    if voice is not None and (not isinstance(voice, str) or not voice.strip() or any(c.isspace() for c in voice)):
        raise VoiceConfigError("A nonempty voice ID without whitespace is required")
    if voice is not None and model != "mimo-v2.5-tts":
        raise VoiceConfigError("Preset voices are only used with mimo-v2.5-tts")
    style = profile.get("style")
    if style is not None and (not isinstance(style, str) or not style.strip()):
        raise VoiceConfigError("Style must be a nonempty description")
    sample = profile.get("voice_sample")
    if model == "mimo-v2.5-tts-voiceclone":
        if not isinstance(sample, str) or not sample.strip():
            raise VoiceConfigError("voiceclone requires a local mp3/wav voice sample path")
        path = Path(sample).expanduser()
        if not path.is_file():
            raise VoiceConfigError("Voice sample file is missing")
        if path.suffix.lower() not in {".mp3", ".wav"}:
            raise VoiceConfigError("Voice sample must be an mp3 or wav file")
        if path.stat().st_size > 7 * 1024 * 1024:
            raise VoiceConfigError("Voice sample exceeds the 10 MB base64 limit")
        result["voice_sample"] = str(path.resolve())
    elif sample is not None:
        raise VoiceConfigError("A voice sample is reserved for the voiceclone model")
    if model == "mimo-v2.5-tts-voicedesign" and style is None:
        raise VoiceConfigError("voicedesign requires a voice design description in style")
    result["model"] = model
    if voice is not None:
        result["voice"] = voice
    if style is not None:
        result["style"] = style
    return result


def load_profile(provider: str | None = None) -> dict:
    path = profile_path()
    if not path.is_file():
        raise VoiceConfigError("Configure the voice profile before synthesis")
    profile = validate_profile(json.loads(path.read_text(encoding="utf-8-sig")))
    if provider is not None and profile["provider"] != provider:
        raise VoiceConfigError(
            f"Voice profile is configured for {profile['provider']}; configure {provider} or pass its parameters")
    return profile


def private_write(path: Path, payload: bytes) -> None:
    path = outside_source(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def windows_protect(payload: bytes, decrypt: bool = False) -> bytes:
    """DPAPI binds a saved key to the current Windows user; no third-party library."""
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    buffer = (ctypes.c_ubyte * len(payload)).from_buffer_copy(payload)
    source = Blob(len(payload), buffer)
    result = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    method = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    method.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob), ctypes.c_void_p,
                       ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    method.restype = wintypes.BOOL
    if not method(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise VoiceConfigError("Windows could not protect or unlock the local speech credential")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(result.data)


def save_api_key(value: str, provider: str = "doubao") -> None:
    value = value.strip()
    if not value or len(value) > 65536 or any(c.isspace() for c in value):
        raise VoiceConfigError("The speech API key must be a nonempty single token")
    payload = value.encode("utf-8")
    private_write(secret_path(provider), windows_protect(payload) if os.name == "nt" else payload)


def load_env_file() -> None:
    """Load DOUBAO/MIMO keys from <user data dir>/.env, if present; real env vars always win."""
    path = data_dir() / ".env"
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*[\"']?(.*?)[\"']?\s*$", line)
        if match:
            key, value = match.group(1), match.group(2)
            if not os.environ.get(key, "").strip():
                os.environ[key] = value


def api_key_present(provider: str = "doubao") -> bool:
    load_env_file()
    return bool(os.environ.get(KEY_ENV[provider], "").strip()) or secret_path(provider).is_file()


def read_api_key(provider: str = "doubao") -> str:
    load_env_file()
    value = os.environ.get(KEY_ENV[provider], "").strip()
    if value:
        return value
    path = secret_path(provider)
    if not path.is_file():
        raise VoiceConfigError(f"Configure {KEY_ENV[provider]} or a local speech credential")
    payload = path.read_bytes()
    return (windows_protect(payload, decrypt=True) if os.name == "nt" else payload).decode("utf-8").strip()


def provider_readiness(provider: str) -> dict:
    profile_ready = False
    profile = None
    try:
        profile = load_profile(provider)
        profile_ready = True
    except (OSError, ValueError):
        pass
    try:
        key_present = api_key_present(provider)
    except (OSError, ValueError):
        key_present = False
    return {"profile_ready": profile_ready, "api_key_present": key_present, "voice": profile}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "configure"))
    parser.add_argument("--provider", choices=PROVIDERS, default=None)
    parser.add_argument("--speaker")
    parser.add_argument("--resource-id", choices=sorted(DOUBAO_RESOURCES))
    parser.add_argument("--model")
    parser.add_argument("--speech-rate", type=int, default=0)
    parser.add_argument("--loudness-rate", type=int, default=0)
    parser.add_argument("--voice")
    parser.add_argument("--style")
    parser.add_argument("--voice-sample")
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--key-stdin", action="store_true", help="Save a key received through private stdin; never use command arguments")
    inputs.add_argument("--prompt-key", action="store_true", help="Hidden local input, when the host provides an interactive terminal")
    args = parser.parse_args()
    try:
        if args.action == "configure":
            provider = args.provider or "doubao"
            if provider == "doubao":
                profile = validate_profile({"provider": "doubao", "speaker": args.speaker,
                                            "resource_id": args.resource_id, "model": args.model,
                                            "speech_rate": args.speech_rate, "loudness_rate": args.loudness_rate})
            else:
                profile = validate_profile({"provider": "mimo", "model": args.model, "voice": args.voice,
                                            "style": args.style, "voice_sample": args.voice_sample})
            if args.key_stdin or args.prompt_key:
                key = sys.stdin.readline(65538) if args.key_stdin else getpass.getpass(
                    f"{'Doubao speech' if provider == 'doubao' else 'MiMo'} API key: ")
                save_api_key(key, provider)
            private_write(profile_path(), (json.dumps(profile, ensure_ascii=False, indent=2) + "\n").encode())
        provider = args.provider
        if provider is None:
            # Without an explicit flag, check follows the configured provider (default doubao).
            path = profile_path()
            provider = "doubao"
            if path.is_file():
                provider = json.loads(path.read_text(encoding="utf-8-sig")).get("provider") or "doubao"
        status = provider_readiness(provider)
        report = {"provider": provider, "profile_ready": status["profile_ready"],
                  "api_key_present": status["api_key_present"], "voice": status["voice"],
                  "providers": {item: provider_readiness(item) for item in PROVIDERS},
                  "network_verified": False, "billable_request_sent": False}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if status["profile_ready"] and status["api_key_present"] else 1
    except (OSError, ValueError):
        print(json.dumps({"ready": False, "error": "Voice configuration failed; check the selected profile and local credential access"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())