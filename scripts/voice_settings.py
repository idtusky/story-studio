"""Local Doubao voice profile and optional protected credential storage."""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import sys
import uuid

from studio_runtime import ROOT, data_dir

RESOURCES = {"seed-tts-2.0", "seed-icl-2.0"}


class VoiceConfigError(ValueError):
    pass


def outside_source(path: Path) -> Path:
    path = path.expanduser().resolve()
    if path.is_relative_to(ROOT):
        raise VoiceConfigError("Voice configuration must stay outside the skill source")
    return path


def profile_path() -> Path:
    return outside_source(data_dir() / "voice.json")


def secret_path() -> Path:
    return outside_source(data_dir() / ("doubao-key.dpapi" if os.name == "nt" else "doubao-key.secret"))


def validate_profile(profile: dict) -> dict:
    allowed = {"speaker", "resource_id", "model", "speech_rate", "loudness_rate"}
    if not isinstance(profile, dict) or set(profile) - allowed:
        raise VoiceConfigError("Voice profile contains unsupported fields")
    speaker = profile.get("speaker")
    if not isinstance(speaker, str) or not speaker.strip() or any(c.isspace() for c in speaker):
        raise VoiceConfigError("A nonempty speaker ID without whitespace is required")
    if profile.get("resource_id") not in RESOURCES:
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
    return {"speaker": speaker, "resource_id": profile["resource_id"], "model": model,
            "speech_rate": profile.get("speech_rate", 0), "loudness_rate": profile.get("loudness_rate", 0)}


def load_profile() -> dict:
    path = profile_path()
    if not path.is_file():
        raise VoiceConfigError("Configure the speaker ID and model resource before synthesis")
    return validate_profile(json.loads(path.read_text(encoding="utf-8-sig")))


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


def save_api_key(value: str) -> None:
    value = value.strip()
    if not value or len(value) > 65536 or any(c.isspace() for c in value):
        raise VoiceConfigError("The speech API key must be a nonempty single token")
    payload = value.encode("utf-8")
    private_write(secret_path(), windows_protect(payload) if os.name == "nt" else payload)


def api_key_present() -> bool:
    return bool(os.environ.get("DOUBAO_TTS_API_KEY", "").strip()) or secret_path().is_file()


def read_api_key() -> str:
    value = os.environ.get("DOUBAO_TTS_API_KEY", "").strip()
    if value:
        return value
    path = secret_path()
    if not path.is_file():
        raise VoiceConfigError("Configure DOUBAO_TTS_API_KEY or a local speech credential")
    payload = path.read_bytes()
    return (windows_protect(payload, decrypt=True) if os.name == "nt" else payload).decode("utf-8").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "configure"))
    parser.add_argument("--speaker")
    parser.add_argument("--resource-id", choices=sorted(RESOURCES))
    parser.add_argument("--model")
    parser.add_argument("--speech-rate", type=int, default=0)
    parser.add_argument("--loudness-rate", type=int, default=0)
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--key-stdin", action="store_true", help="Save a key received through private stdin; never use command arguments")
    inputs.add_argument("--prompt-key", action="store_true", help="Hidden local input, when the host provides an interactive terminal")
    args = parser.parse_args()
    try:
        if args.action == "configure":
            profile = validate_profile({"speaker": args.speaker, "resource_id": args.resource_id,
                                        "model": args.model, "speech_rate": args.speech_rate,
                                        "loudness_rate": args.loudness_rate})
            if args.key_stdin or args.prompt_key:
                key = sys.stdin.readline(65538) if args.key_stdin else getpass.getpass("Doubao speech API key: ")
                save_api_key(key)
            private_write(profile_path(), (json.dumps(profile, ensure_ascii=False, indent=2) + "\n").encode())
        try:
            profile = load_profile()
            profile_ready = True
        except ValueError:
            profile, profile_ready = None, False
        report = {"profile_ready": profile_ready, "api_key_present": api_key_present(),
                  "voice": profile, "network_verified": False, "billable_request_sent": False}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if profile_ready and report["api_key_present"] else 1
    except (OSError, ValueError):
        print(json.dumps({"ready": False, "error": "Voice configuration failed; check the selected profile and local credential access"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
