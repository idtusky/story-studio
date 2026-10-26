"""Diagnose measured display timing; does not align narration or judge semantics."""
import argparse
import json
import math
import statistics
from pathlib import Path


def check(plan):
    shots = plan.get("shots")
    if not isinstance(shots, list) or not shots:
        raise ValueError("shots must be a nonempty list")
    durations, rows, warnings = [], [], []
    cursor = 0.0
    ids = set()
    for shot in shots:
        sid = shot.get("id")
        if not isinstance(sid, str) or not sid or sid in ids:
            raise ValueError("missing or duplicate shot id")
        ids.add(sid)
        start, end = shot.get("start"), shot.get("end")
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end)):
            raise ValueError(f"{sid}: finite numeric start/end required")
        if abs(start - cursor) > 1e-6 or end <= start:
            raise ValueError(f"{sid}: timeline must be positive, continuous and start at zero")
        duration = end - start
        durations.append(duration)
        rows.append({"id": sid, "duration": round(duration, 3),
                     "exception": shot.get("pacing_exception")})
        cursor = end
    mean = statistics.mean(durations)
    cumulative = 0.0
    for i, duration in enumerate(durations):
        sid = rows[i]["id"]
        def warn(code):
            warnings.append({"code": code, "id": sid})
        if duration < 5 or duration > 12:
            warn("outside_typical_5_12_seconds")
        if duration < 3 or duration > 16:
            warn("very_short" if duration < 3 else "very_long")
        if duration < 0.5 * mean or duration > 1.6 * mean:
            warn("relative_imbalance")
        if i and max(duration, durations[i-1]) / min(duration, durations[i-1]) > 2:
            warn("adjacent_duration_jump")
        if i >= 2 and all(d < 5 for d in durations[i-2:i+1]):
            warn("three_consecutive_short_shots")
        cumulative += duration
        if i < len(durations)-1 and abs(cumulative / mean - (i+1)) > 1 + 1e-9:
            warn("cumulative_imbalance")
    tail_count = min(2, len(durations))
    tail_share = sum(durations[-tail_count:]) / cursor
    if tail_share > 1.6 * tail_count / len(durations) + 1e-9:
        warnings.append({"code": "tail_overloaded"})
    return {"status": "review_required" if warnings else "within_timing_guidelines",
            "basis": "plan_display_times_not_semantic_verification",
            "count": len(durations), "total_seconds": cursor,
            "min_seconds": min(durations), "max_seconds": max(durations),
            "median_seconds": statistics.median(durations), "mean_seconds": mean,
            "tail_share": tail_share, "shots": rows, "warnings": warnings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    args = parser.parse_args()
    try:
        result = check(json.loads(args.plan.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        print(json.dumps({"status": "invalid_input", "error": str(exc)}))
        return 2
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 1 if result["warnings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
