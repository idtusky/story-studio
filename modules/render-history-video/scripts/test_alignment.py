"""Offline regression cases for narration boundary alignment."""
import unittest
from align_with_coli import align_storyboard, norm


class AlignmentTests(unittest.TestCase):
    def fixture(self, parts):
        text = "".join(parts)
        sb = {"manuscript": text, "shots": []}
        cursor = 0
        for i, part in enumerate(parts):
            sb["shots"].append({"id": f"S{i+1:03}", "narration": part,
                                "source_start": cursor, "source_end": cursor+len(part)})
            cursor += len(part)
        return sb, {"tokens": list(text), "timestamps": [0.5+i*0.2 for i in range(len(text))],
                    "duration": 1+len(text)*0.2}

    def test_exact_boundaries_and_initial_silence(self):
        sb, asr = self.fixture(["少年在乡里读书。", "成年以后他赴京应试。", "晚年回乡教授学生。"])
        rows, duration = align_storyboard(sb, asr)
        self.assertEqual(rows[0]["start"], 0)
        self.assertEqual(rows[0]["audio_start"], 0.5)
        self.assertAlmostEqual(rows[1]["start"], asr["timestamps"][len(sb["shots"][0]["narration"])])
        self.assertEqual(rows[-1]["end"], duration)
        self.assertTrue(all(r["semantic_review_status"] == "pending" for r in rows))

    def test_repeated_short_phrase_uses_context(self):
        sb, asr = self.fixture(["第一次出征之前，他回到故乡筹集粮草。", "他回到故乡以后，招募更多兵卒继续前行。"])
        rows, _ = align_storyboard(sb, asr)
        self.assertAlmostEqual(rows[1]["start"], asr["timestamps"][len(sb["shots"][0]["narration"])])

    def test_repeated_full_context_is_not_guessed(self):
        sb, asr = self.fixture(["他回到故乡招募兵卒继续前行。"]*3)
        with self.assertRaises(ValueError): align_storyboard(sb, asr)

    def test_deleted_opening_word(self):
        sb, asr = self.fixture(["少年在乡里读书。", "成年以后他赴京应试。"])
        asr["tokens"][0] = ""
        with self.assertRaises(ValueError): align_storyboard(sb, asr)

    def test_partial_timestamps(self):
        sb, asr = self.fixture(["少年在乡里读书。"])
        asr["timestamps"].pop()
        with self.assertRaises(ValueError): align_storyboard(sb, asr)

    def test_substitution_does_not_become_verified(self):
        sb, asr = self.fixture(["少年在乡里读书。", "成年以后他赴京应试。"])
        asr["tokens"][2] = "不"
        with self.assertRaises(ValueError): align_storyboard(sb, asr)

    def test_inside_multicharacter_token(self):
        sb, asr = self.fixture(["少年在乡里读书", "成年以后他赴京应试"])
        asr["tokens"] = ["".join(asr["tokens"])]
        asr["timestamps"] = [0.5]
        with self.assertRaises(ValueError): align_storyboard(sb, asr)

    def test_nonmonotonic_timestamp(self):
        sb, asr = self.fixture(["少年在乡里读书。"])
        asr["timestamps"][3] = 0.1
        with self.assertRaises(ValueError): align_storyboard(sb, asr)

    def test_year_and_names_are_not_rewritten(self):
        self.assertEqual(norm("一九四九年，明臣。"), "一九四九年明臣")

    def test_wrong_source_offset(self):
        sb, asr = self.fixture(["少年在乡里读书。"])
        sb["shots"][0]["source_start"] = 1
        with self.assertRaises(ValueError): align_storyboard(sb, asr)


if __name__ == "__main__":
    unittest.main()
