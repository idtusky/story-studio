"""MiMo TTS provider tests: profile rules, request construction and workflow guards; no paid service calls."""
from __future__ import annotations

import base64
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import mimo_tts as mimo
import voice_settings as settings

MIMO_TTS = {"provider": "mimo", "model": "mimo-v2.5-tts", "voice": "冰糖", "style": None, "voice_sample": None}
MIMO_DESIGN = {"provider": "mimo", "model": "mimo-v2.5-tts-voicedesign",
               "voice": None, "style": "温柔沉稳的中年女声", "voice_sample": None}


def sample_file(directory: str, suffix=".mp3") -> Path:
    path = Path(directory) / ("sample" + suffix)
    path.write_bytes(b"fixture-sample-audio-data")
    return path


class VoiceSettingsProviderTests(unittest.TestCase):
    def test_doubao_profile_remains_the_default_provider(self):
        profile = settings.validate_profile({"speaker": "fixture-voice", "resource_id": "seed-tts-2.0"})
        self.assertEqual(profile["provider"], "doubao")

    def test_cross_provider_fields_are_rejected(self):
        with self.assertRaises(ValueError):
            settings.validate_profile(dict(MIMO_TTS, speaker="fixture-voice"))
        with self.assertRaises(ValueError):
            settings.validate_profile({"provider": "doubao", "speaker": "s", "resource_id": "seed-tts-2.0",
                                       "voice": "冰糖"})

    def test_mimo_model_whitelist_and_preset_voice(self):
        with self.assertRaises(ValueError):
            settings.validate_profile(dict(MIMO_TTS, model="mimo-v2.4-tts"))
        profile = settings.validate_profile(dict(MIMO_TTS, voice=None))
        self.assertNotIn("voice", profile)
        with self.assertRaises(ValueError):
            settings.validate_profile(dict(MIMO_TTS, voice="bad sample with spaces"))

    def test_voicedesign_rejects_preset_voice_and_requires_style(self):
        with self.assertRaises(ValueError):
            settings.validate_profile(dict(MIMO_DESIGN, voice="冰糖", style=None))
        with self.assertRaises(ValueError):
            settings.validate_profile(dict(MIMO_DESIGN, style=None))
        self.assertEqual(settings.validate_profile(MIMO_DESIGN)["model"], "mimo-v2.5-tts-voicedesign")

    def test_voiceclone_requires_an_existing_sample_with_valid_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            valid = sample_file(directory)
            profile = settings.validate_profile({"provider": "mimo", "model": "mimo-v2.5-tts-voiceclone",
                                                 "voice_sample": str(valid)})
            self.assertIn("voice_sample", profile)
            with self.assertRaises(ValueError):
                settings.validate_profile({"provider": "mimo", "model": "mimo-v2.5-tts-voiceclone",
                                           "voice_sample": str(Path(directory) / "missing.mp3")})
            other = sample_file(directory, ".txt")
            with self.assertRaises(ValueError):
                settings.validate_profile({"provider": "mimo", "model": "mimo-v2.5-tts-voiceclone",
                                           "voice_sample": str(other)})
            with self.assertRaises(ValueError):
                settings.validate_profile(dict(MIMO_TTS, voice_sample=str(valid)))

    def test_mimo_configure_saves_separate_secret_and_provider_profile(self):
        marker = "fixture-mimo-key-not-real"
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(settings, "data_dir", return_value=Path(temporary)), \
             patch.dict(os.environ, {"DOUBAO_TTS_API_KEY": "", "MIMO_API_KEY": ""}), \
             patch.object(sys, "argv", ["voice_settings.py", "configure", "--provider", "mimo",
                                        "--model", "mimo-v2.5-tts", "--voice", "冰糖", "--key-stdin"]), \
             patch.object(sys, "stdin", io.StringIO(marker + "\n")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(settings.main(), 0)
            self.assertNotIn(marker, output.getvalue())
            stored = json.loads(settings.profile_path().read_text(encoding="utf-8-sig"))
            self.assertEqual(stored["provider"], "mimo")
            self.assertEqual(stored["model"], "mimo-v2.5-tts")
            self.assertEqual(stored["voice"], "冰糖")
            self.assertEqual(settings.read_api_key("mimo"), marker)
            self.assertFalse(settings.secret_path("doubao").is_file())
            self.assertEqual(settings.secret_path("mimo").name, "mimo-key.secret")

    def test_check_reports_per_provider_readiness_without_network(self):
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(settings, "data_dir", return_value=Path(temporary)), \
             patch.dict(os.environ, {"DOUBAO_TTS_API_KEY": "", "MIMO_API_KEY": ""}), \
             patch.object(sys, "argv", ["voice_settings.py", "check"]), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(settings.main(), 1)
        report = json.loads(output.getvalue())
        self.assertFalse(report["profile_ready"])
        self.assertFalse(report["api_key_present"])
        self.assertFalse(report["network_verified"])
        self.assertEqual(set(report["providers"]), {"doubao", "mimo"})

    def test_user_data_dotenv_loads_keys_and_real_environment_wins(self):
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(settings, "data_dir", return_value=Path(temporary)), \
             patch.dict(os.environ, {"DOUBAO_TTS_API_KEY": "", "MIMO_API_KEY": ""}):
            (Path(temporary) / ".env").write_text(
                "# 用户数据目录内的 .env 加载测试\nMIMO_API_KEY=sk-file-fixture\nDOUBAO_TTS_API_KEY=db-file-fixture\n",
                encoding="utf-8")
            self.assertTrue(settings.api_key_present("mimo"))
            self.assertTrue(settings.api_key_present("doubao"))
            self.assertEqual(settings.read_api_key("mimo"), "sk-file-fixture")
            self.assertEqual(settings.read_api_key("doubao"), "db-file-fixture")
            with patch.dict(os.environ, {"MIMO_API_KEY": "sk-env-fixture"}):
                self.assertEqual(settings.read_api_key("mimo"), "sk-env-fixture")
        with patch.dict(os.environ, {"MIMO_API_KEY": "", "DOUBAO_TTS_API_KEY": ""}):
            self.assertFalse(settings.api_key_present("mimo"))


class MimoRequestTests(unittest.TestCase):
    def test_preset_voice_defaults_and_text_rides_in_assistant_message(self):
        body = mimo.request_body(dict(MIMO_TTS, voice=None), "整篇正文不能丢。")
        self.assertEqual(body["stream"], False)
        self.assertEqual(body["audio"], {"format": "mp3", "voice": "mimo_default"})
        self.assertEqual(body["messages"], [{"role": "assistant", "content": "整篇正文不能丢。"}])

    def test_style_lands_in_user_message_and_preset_voice_is_kept(self):
        profile = settings.validate_profile(dict(MIMO_TTS, style="沉稳克制的历史纪录片旁白"))
        body = mimo.request_body(profile, "正文。")
        self.assertEqual(body["messages"][0], {"role": "user", "content": "沉稳克制的历史纪录片旁白"})
        self.assertEqual(body["audio"]["voice"], "冰糖")

    def test_voicedesign_requires_style_and_omits_voice_field(self):
        body = mimo.request_body(settings.validate_profile(MIMO_DESIGN), "正文。")
        self.assertEqual(body["audio"], {"format": "mp3"})
        self.assertEqual(body["messages"][0]["role"], "user")

    def test_voiceclone_sends_data_uri_with_mime_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            sample = sample_file(directory)
            profile = settings.validate_profile({"provider": "mimo", "model": "mimo-v2.5-tts-voiceclone",
                                                 "voice_sample": str(sample)})
            body = mimo.request_body(profile, "正文。")
        self.assertTrue(body["audio"]["voice"].startswith("data:audio/mpeg;base64,"))
        self.assertEqual(base64.b64decode(body["audio"]["voice"].split(",", 1)[1]), b"fixture-sample-audio-data")

    def test_parse_audio_extracts_base64_and_usage(self):
        payload = {"choices": [{"finish_reason": "stop", "message": {"audio": {"data": base64.b64encode(b"\x00\x01").decode()}}}],
                   "usage": {"total_tokens": 3}}
        audio, usage = mimo.parse_audio(payload)
        self.assertEqual(audio, b"\x00\x01")
        self.assertEqual(usage["total_tokens"], 3)

    def test_parse_audio_rejects_missing_data_and_early_stop(self):
        with self.assertRaisesRegex(mimo.TtsError, "without audio"):
            mimo.parse_audio({"choices": [{"finish_reason": "stop", "message": {"audio": {}}}]})
        with self.assertRaisesRegex(mimo.TtsError, "stopped early"):
            mimo.parse_audio({"choices": [{"finish_reason": "length", "message": {"audio": {"data": "AA=="}}}]})
        with self.assertRaisesRegex(mimo.TtsError, "invalid base64"):
            mimo.parse_audio({"choices": [{"finish_reason": "stop", "message": {"audio": {"data": "not-base64!!"}}}]})


class MimoWorkflowTests(unittest.TestCase):
    def invoke(self, directory, extra, **patches):
        text = Path(directory) / "narration.txt"
        text.write_text("原始正文。", encoding="utf-8")
        output = Path(directory) / "narration.mp3"
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(sys, "argv", ["mimo_tts.py", "--text-file", str(text), "--output", str(output), *extra]))
            stack.enter_context(patch.object(mimo, "load_profile", return_value=MIMO_TTS))
            mocks = {name: stack.enter_context(patch.object(mimo, name, **options)) for name, options in patches.items()}
            captured = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            code = mimo.main()
        return code, json.loads(captured.getvalue()), mocks

    def test_dry_run_never_reads_key_or_starts_network(self):
        with tempfile.TemporaryDirectory() as directory:
            code, report, mocks = self.invoke(directory, ["--dry-run"], read_api_key={}, synthesize={})
            self.assertEqual(code, 0)
            self.assertFalse(report["network"])
            mocks["read_api_key"].assert_not_called()
            mocks["synthesize"].assert_not_called()

    def test_missing_confirmation_stops_before_credentials_and_network(self):
        with tempfile.TemporaryDirectory() as directory:
            code, report, mocks = self.invoke(directory, [], read_api_key={}, synthesize={})
            self.assertEqual(code, 2)
            self.assertFalse(report["request_may_have_been_billed"])
            mocks["read_api_key"].assert_not_called()

    def test_completed_result_keeps_key_and_sample_path_private(self):
        key = "fixture-private-mimo-key"
        with tempfile.TemporaryDirectory() as directory:
            sample = sample_file(directory)
            profile = settings.validate_profile({"provider": "mimo", "model": "mimo-v2.5-tts-voiceclone",
                                                 "voice_sample": str(sample)})
            with patch.object(mimo, "load_profile", return_value=profile), \
                 patch.object(mimo.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "")), \
                 patch.object(mimo, "read_api_key", return_value=key), \
                 patch.object(mimo, "find_executable", return_value="fixture-media-tool"), \
                 patch.object(mimo, "synthesize", side_effect=lambda text, profile, key, partial: (
                     partial.write_bytes(b"fixture-mimo-mp3"), 12, {"total_tokens": 4})[1:]), \
                 patch.object(mimo, "validate_audio", return_value=1.0), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                text = Path(directory) / "narration.txt"
                text.write_text("原始正文。", encoding="utf-8")
                out = Path(directory) / "narration.mp3"
                with patch.object(sys, "argv", ["mimo_tts.py", "--text-file", str(text), "--output", str(out), "--voice-confirmed"]):
                    code = mimo.main()
            self.assertEqual(code, 0)
            report = json.loads(output.getvalue())
            self.assertNotIn(key, json.dumps(report))
            self.assertNotIn(str(sample), json.dumps(report))
            self.assertEqual(len(report["voice_sample_sha256"]), 64)
            metadata = (Path(directory) / "narration.voice.json").read_text(encoding="utf-8")
            self.assertNotIn(key, metadata)
            self.assertNotIn(str(sample), metadata)

    def test_http_error_reports_status_without_echoing_body(self):
        with tempfile.TemporaryDirectory() as directory:
            text = Path(directory) / "narration.txt"
            text.write_text("正文。", encoding="utf-8")
            out = Path(directory) / "narration.mp3"
            with patch.object(sys, "argv", ["mimo_tts.py", "--text-file", str(text), "--output", str(out), "--voice-confirmed"]), \
                 patch.object(mimo, "load_profile", return_value=MIMO_TTS), \
                 patch.object(mimo.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "")), \
                 patch.object(mimo, "read_api_key", return_value="fixture"), \
                 patch.object(mimo, "find_executable", return_value="fixture-media-tool"), \
                 patch.object(mimo.urllib.request, "urlopen",
                              side_effect=mimo.urllib.error.HTTPError(mimo.URL, 403, "Forbidden", {}, None)), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                code = mimo.main()
                body = json.loads(output.getvalue())
            self.assertEqual(code, 2)
            self.assertIn("403", body["error"])
            self.assertTrue(body["request_may_have_been_billed"])
            self.assertFalse(body["automatic_retry"])

    def test_existing_mp3_is_not_replaced_or_synthesized_again(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "narration.mp3"
            output.write_bytes(b"keep prior success")
            code, report, mocks = self.invoke(directory, ["--voice-confirmed"], synthesize={})
            self.assertEqual(code, 2)
            self.assertEqual(output.read_bytes(), b"keep prior success")
            mocks["synthesize"].assert_not_called()


if __name__ == "__main__":
    unittest.main()