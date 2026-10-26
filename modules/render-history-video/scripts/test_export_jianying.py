"""Native-library integration tests using temporary media and draft roots."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

if importlib.util.find_spec("pyJianYingDraft") is None:
    raise unittest.SkipTest("Run with the configured media interpreter")

from PIL import Image
import export_jianying as exporter
from render import load_plan


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


class DraftExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="studio-native-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.drafts = self.root / "drafts"
        for sid, color in [("S001", (25, 50, 75)), ("S002", (75, 50, 25))]:
            Image.new("RGB", (180, 320), color).save(self.root / (sid + ".png"))
        self.audio(16)
        self.plan = {"width": 1080, "height": 1920, "fps": 30, "audio": "narration.wav", "shots": [
            {"id": "S001", "image": "S001.png", "start": 0, "end": 8, "zoom": [1, 1.052], "pivot": [0.45, 0.5]},
            {"id": "S002", "image": "S002.png", "start": 8, "end": 16, "zoom": [1.052, 1], "pivot": [0.5, 0.45]},
        ]}
        self.plan_path = self.root / "plan.json"

    def audio(self, seconds):
        with wave.open(str(self.root / "narration.wav"), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(16000)
            stream.writeframes(b"\0\0" * round(16000 * seconds))

    def export(self, **kwargs):
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
        info = exporter.export_plan(self.plan_path, "case", drafts_root=str(self.drafts), **kwargs)
        content = json.loads(Path(info["draft_content"]).read_text(encoding="utf-8"))
        return info, content

    def test_native_version_tracks_and_mirrored_files(self):
        info, content = self.export()
        self.assertEqual(info["backend_version"], "0.3.1")
        self.assertEqual(content["duration"], 16_000_000)
        self.assertEqual([(track["type"], len(track["segments"])) for track in content["tracks"]], [("video", 2), ("audio", 1)])
        self.assertEqual(Path(info["draft_content"]).read_bytes(), Path(info["draft_info"]).read_bytes())
        self.assertEqual(content["canvas_config"]["width"], 1080)
        self.assertFalse(list(self.root.rglob("*.mp4")))

    def test_copied_materials_survive_original_removal(self):
        info, content = self.export()
        target = Path(info["draft_path"])
        for name in ("S001.png", "S002.png", "narration.wav"):
            (self.root / name).unlink()
        for item in content["materials"]["videos"] + content["materials"]["audios"]:
            path = Path(item["path"])
            self.assertTrue(path.is_file())
            self.assertTrue(path.is_relative_to(target / "materials"))
        self.assertNotIn(".story-studio-", json.dumps(content))

    def test_existing_draft_is_unchanged_without_overwrite(self):
        info, _ = self.export()
        before = hashes(Path(info["draft_path"]))
        with self.assertRaises(FileExistsError):
            self.export()
        self.assertEqual(hashes(Path(info["draft_path"])), before)

    def test_explicit_overwrite_keeps_previous_draft_backup(self):
        info, _ = self.export()
        before = hashes(Path(info["draft_path"]) / "materials")
        replacement, _ = self.export(overwrite=True)
        backup = Path(replacement["previous_draft_backup"])
        self.assertEqual(hashes(backup / "materials"), before)
        content = json.loads((backup / "draft_content.json").read_text(encoding="utf-8"))
        self.assertEqual(content["name"], backup.name)
        for item in content["materials"]["videos"] + content["materials"]["audios"]:
            self.assertTrue(Path(item["path"]).is_relative_to(backup))
            self.assertTrue(Path(item["path"]).is_file())

    def test_failed_import_does_not_replace_existing_draft(self):
        info, _ = self.export()
        before = hashes(Path(info["draft_path"]))
        with patch.object(exporter.draft, "VideoMaterial", side_effect=ValueError("fixture parse failure")):
            with self.assertRaises(ValueError):
                self.export(overwrite=True)
        self.assertEqual(hashes(Path(info["draft_path"])), before)
        self.assertEqual([p.name for p in self.drafts.iterdir()], ["case"])

    def test_failed_final_commit_restores_old_project_and_paths(self):
        info, _ = self.export()
        target = Path(info["draft_path"])
        before = hashes(target)
        original_rename = Path.rename

        def rename(path, destination):
            if path.name.startswith(".story-studio-"):
                raise OSError("fixture commit failure")
            return original_rename(path, destination)

        with patch.object(Path, "rename", new=rename):
            with self.assertRaises(OSError):
                self.export(overwrite=True)
        self.assertEqual(hashes(target), before)
        self.assertEqual([p.name for p in self.drafts.iterdir()], ["case"])

    def test_subtitles_are_written_only_when_selected(self):
        (self.root / "captions.srt").write_text("1\n00:00:00,000 --> 00:00:08,000\n第一段\n\n2\n00:00:08,000 --> 00:00:16,000\n第二段\n", encoding="utf-8")
        self.plan["subtitles"] = "captions.srt"
        info, content = self.export()
        self.assertEqual(info["subtitle_cues"], 2)
        self.assertEqual(content["tracks"][-1]["type"], "text")
        info, content = self.export(overwrite=True, no_subtitles=True)
        self.assertFalse(info["subtitles"])
        self.assertNotIn("text", [track["type"] for track in content["tracks"]])

    def test_keyframes_match_shared_curve_at_every_frame(self):
        _, content = self.export()
        plan = load_plan(self.plan_path)
        for shot, segment in zip(plan["shots"], content["tracks"][0]["segments"]):
            channel = next(item for item in segment["common_keyframes"] if item["property_type"] in {"KFTypeScaleX", "UNIFORM_SCALE"})
            keys = channel["keyframe_list"]
            expected = exporter.motion_samples(shot, plan["fps"])
            cover = exporter.cover_scale(180, 320, 1080, 1920)
            self.assertEqual(len(keys), len(expected))
            for key, (stamp, zoom) in zip(keys, expected):
                self.assertEqual(key["time_offset"], stamp)
                self.assertAlmostEqual(key["values"][0], zoom * cover, places=10)
            self.assertLess(keys[-1]["time_offset"], segment["target_timerange"]["duration"])

    def test_silent_draft_and_native_reopen(self):
        self.plan.pop("audio")
        info, content = self.export()
        self.assertFalse(info["audio"])
        self.assertEqual(len(content["tracks"]), 1)
        reopened = exporter.draft.DraftFolder(str(self.drafts)).load_template("case")
        self.assertEqual(reopened.duration, content["duration"])

    def test_audio_tail_is_preserved_with_frame_extension(self):
        self.audio(16.003)
        info, content = self.export()
        video_end = sum(s["target_timerange"]["duration"] for s in content["tracks"][0]["segments"])
        audio_end = content["tracks"][1]["segments"][0]["target_timerange"]["duration"]
        self.assertGreaterEqual(video_end, audio_end)
        self.assertGreater(info["duration"], 16)
        self.assertLessEqual(info["duration"]-16, 1/30+1e-6)
        self.assertTrue(info["warnings"])

    def test_parent_directory_names_are_rejected(self):
        for name in ("..", "../../escape", "", "CON"):
            with self.assertRaises(ValueError):
                exporter.safe_name(name)


if __name__ == "__main__":
    unittest.main()
