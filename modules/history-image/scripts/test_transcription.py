"""Offline tests for transcription before a storyboard exists."""
import unittest
from transcribe_with_coli import build_cues, srt_text


class TranscriptionTests(unittest.TestCase):
    def sample(self, text="少年在乡里读书。成年以后赴京应试。"):
        return {"tokens": list(text), "timestamps": [0.4+i*.2 for i in range(len(text))], "duration": len(text)*.2+1}

    def test_without_storyboard(self):
        asr = self.sample()
        cues = build_cues(asr)
        self.assertEqual("".join(c["text"] for c in cues), "".join(asr["tokens"]))
        self.assertEqual(cues[0]["start"], 0.4)
        self.assertEqual(cues[-1]["end"], asr["duration"])
        for c in cues:
            self.assertEqual(c["start"], asr["timestamps"][c["token_start"]])
        self.assertIn("00:00:00,400", srt_text(cues))

    def test_no_punctuation_still_uses_token_times(self):
        asr = self.sample("少年在乡里读书成年以后赴京应试后来返回家乡教书育人直至晚年")
        cues = build_cues(asr)
        self.assertGreater(len(cues), 1)
        self.assertTrue(all(c["start"] in asr["timestamps"] for c in cues))

    def test_missing_timestamps(self):
        asr = self.sample(); asr["timestamps"].pop()
        with self.assertRaises(ValueError): build_cues(asr)

    def test_nonmonotonic(self):
        asr = self.sample(); asr["timestamps"][2] = 0.1
        with self.assertRaises(ValueError): build_cues(asr)

    def test_invalid_duration(self):
        asr = self.sample(); asr["duration"] = float("nan")
        with self.assertRaises(ValueError): build_cues(asr)

    def test_equal_onsets_do_not_make_empty_cue(self):
        asr = {"tokens": ["第一句。", "第二句。", "结束。"], "timestamps": [1,1,3], "duration":4}
        cues = build_cues(asr)
        self.assertEqual(len(cues), 2)
        self.assertTrue(all(c["end"]>c["start"] for c in cues))

    def test_multichar_token_is_not_interpolated(self):
        asr = {"tokens": ["少年读书。", "成年应试。"], "timestamps": [0.5,3], "duration":5}
        cues = build_cues(asr)
        self.assertEqual([c["start"] for c in cues], [0.5,3])


if __name__ == "__main__":
    unittest.main()
