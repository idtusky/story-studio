"""Check storyboard text coverage and distribution; does not estimate timing."""

import argparse
import json
import sys
from pathlib import Path


def effective_length(text):
    return sum(char.isalnum() for char in text)


def check(data, target=None):
    manuscript = data.get("manuscript")
    shots = data.get("shots")
    if not isinstance(manuscript, str) or not manuscript:
        raise ValueError("manuscript must be a nonempty string")
    if not isinstance(shots, list) or not shots:
        raise ValueError("shots must be a nonempty list")
    declared_target = data.get("target_shots")
    if target is not None and declared_target is not None and target != declared_target:
        raise ValueError("CLI target conflicts with target_shots in the file")
    target = declared_target if target is None else target
    if target is not None and (type(target) is not int or target < 1):
        raise ValueError("target_shots must be a positive integer")

    cursor = 0
    weights = []
    ids = []
    for index, shot in enumerate(shots):
        if not isinstance(shot, dict):
            raise ValueError(f"shot {index + 1} must be an object")
        start, end = shot.get("source_start"), shot.get("source_end")
        if (type(start) is not int or type(end) is not int
                or start != cursor or not start < end <= len(manuscript)):
            raise ValueError(f"shot {index + 1}: invalid or discontinuous source range")
        text = manuscript[start:end]
        if shot.get("narration") != text:
            raise ValueError(f"shot {index + 1}: narration differs from source")
        shot_id = shot.get("id")
        if not isinstance(shot_id, str) or not shot_id or shot_id in ids:
            raise ValueError(f"shot {index + 1}: missing or duplicate id")
        weight = effective_length(text)
        if not weight:
            raise ValueError(f"shot {shot_id}: no letters or numbers")
        ids.append(shot_id)
        weights.append(weight)
        cursor = end
    if cursor != len(manuscript):
        raise ValueError("shots do not cover the end of manuscript")

    count = len(shots)
    total = sum(weights)
    average = total / count
    warnings = []
    if target is not None and count != target:
        warnings.append({"code": "count_mismatch", "expected": target, "actual": count})
    cumulative = 0
    rows = []
    max_drift = 0
    for index, (shot_id, weight) in enumerate(zip(ids, weights), 1):
        cumulative += weight
        ratio = weight / average
        # Negative drift means too many images have been spent early in the text.
        drift = cumulative / average - index
        max_drift = max(max_drift, abs(drift))
        rows.append({"id": shot_id, "effective_chars": weight,
                     "relative_to_mean": round(ratio, 3),
                     "cumulative_drift_shots": round(drift, 3)})
        if ratio < 0.5 or ratio > 1.6:
            warnings.append({"code": "short_shot" if ratio < 0.5 else "long_shot",
                             "id": shot_id})
        if index < count and abs(drift) > 1.0 + 1e-9:
            warnings.append({"code": "cumulative_imbalance", "id": shot_id})
    tail_count = min(2, count)
    tail_share = sum(weights[-tail_count:]) / total
    if tail_share > 1.6 * tail_count / count + 1e-9:
        warnings.append({"code": "tail_overloaded"})
    return {"measurement_basis": "unicode_letters_and_numbers_not_audio_duration",
            "coverage_valid": True, "target_shots": target, "actual_shots": count,
            "total_effective_chars": total, "mean_chars": round(average, 3),
            "min_chars": min(weights), "max_chars": max(weights),
            "tail_shots": tail_count, "tail_share": round(tail_share, 4),
            "max_cumulative_drift_shots": round(max_drift, 3),
            "shots": rows, "warnings": warnings,
            "status": "review_required" if warnings else "within_text_guidelines"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("storyboard", type=Path)
    parser.add_argument("--target-shots", type=int)
    args = parser.parse_args()
    try:
        data = json.loads(args.storyboard.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError("storyboard must be a JSON object")
        result = check(data, args.target_shots)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "invalid_input", "error": str(error)}, ensure_ascii=True))
        return 2
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 1 if result["warnings"] else 0


if __name__ == "__main__":
    sys.exit(main())
