"""Ken Burns plus a slow cut-punch zoom used by local render and Jianying export.

Slow push/pull still covers the shot. At the hard cut the outgoing shot keeps a
real punch-in and the incoming shot keeps a real punch-out, but both take longer
than a snap cut. Jianying intro/outro animations stay off by default: 动感缩小
and 放大 flash a black frame on the cut.
"""
from __future__ import annotations

import math

DEFAULTS = {
    "cut_punch": True,
    "punch_in": 1.50,
    "punch_in_dur": 1.80,
    "punch_out": 1.28,
    "punch_out_dur": 1.00,
    "cut_punch_anim": False,
}

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _finite(value, lo: float, hi: float, name: str, sid: str) -> float:
    v = float(value)
    if not math.isfinite(v) or not lo <= v <= hi:
        raise ValueError(f"{sid}: {name} must be a finite value in {lo}..{hi}")
    return v


def ease_out_cubic(u: float) -> float:
    u = _clamp(u, 0.0, 1.0)
    return 1.0 - (1.0 - u) ** 3


def ease_in_cubic(u: float) -> float:
    u = _clamp(u, 0.0, 1.0)
    return u ** 3


def smoothstep(u: float) -> float:
    u = _clamp(u, 0.0, 1.0)
    return u * u * (3.0 - 2.0 * u)


def resolve_plan_motion(plan: dict) -> None:
    """Fill punch fields on the plan and every shot. Mutates plan in place."""
    plan.setdefault("cut_punch", DEFAULTS["cut_punch"])
    plan.setdefault("punch_in", DEFAULTS["punch_in"])
    plan.setdefault("punch_in_dur", DEFAULTS["punch_in_dur"])
    plan.setdefault("punch_out", DEFAULTS["punch_out"])
    plan.setdefault("punch_out_dur", DEFAULTS["punch_out_dur"])
    plan.setdefault("cut_punch_anim", DEFAULTS["cut_punch_anim"])

    plan["punch_in"] = _finite(plan["punch_in"], 1.0, 3.0, "punch_in", "plan")
    plan["punch_out"] = _finite(plan["punch_out"], 1.0, 3.0, "punch_out", "plan")
    plan["punch_in_dur"] = _finite(plan["punch_in_dur"], 0.0, 4.0, "punch_in_dur", "plan")
    plan["punch_out_dur"] = _finite(plan["punch_out_dur"], 0.0, 3.0, "punch_out_dur", "plan")

    shots = plan["shots"]
    n = len(shots)
    for i, shot in enumerate(shots):
        sid = shot["id"]
        dur = float(shot.get("duration_s", shot["end"] - shot["start"]))
        image_shot = bool(shot.get("image"))
        default_on = bool(plan["cut_punch"]) and image_shot and dur >= 5.0
        enabled = bool(shot.get("cut_punch", default_on))

        pin = _finite(shot.get("punch_in", plan["punch_in"]), 1.0, 3.0, "punch_in", sid)
        pout = _finite(shot.get("punch_out", plan["punch_out"]), 1.0, 3.0, "punch_out", sid)
        pin_dur = _finite(
            shot.get("punch_in_dur", plan["punch_in_dur"]), 0.0, 4.0, "punch_in_dur", sid
        )
        pout_dur = _finite(
            shot.get("punch_out_dur", plan["punch_out_dur"]), 0.0, 3.0, "punch_out_dur", sid
        )

        pin_dur = min(pin_dur, dur * 0.40, 2.2)
        pout_dur = min(pout_dur, dur * 0.28, 1.4)
        if pin_dur + pout_dur > dur * 0.55 and dur > 0:
            scale = (dur * 0.55) / (pin_dur + pout_dur)
            pin_dur *= scale
            pout_dur *= scale

        has_in = enabled and pin > 1.001 and pin_dur >= 0.10 and dur >= 0.55
        has_out = (
            enabled
            and i < n - 1
            and pout > 1.001
            and pout_dur >= 0.08
            and dur >= 0.70
        )
        anim = bool(shot.get("cut_punch_anim", plan["cut_punch_anim"])) and enabled

        shot.update(
            duration_s=dur,
            cut_punch=enabled,
            punch_in=pin,
            punch_out=pout,
            punch_in_dur=pin_dur if has_in else 0.0,
            punch_out_dur=pout_dur if has_out else 0.0,
            has_punch_in=has_in,
            has_punch_out=has_out,
            cut_punch_anim=anim,
        )


def zoom_at(shot: dict, t_rel: float, duration_s: float | None = None) -> float:
    """Zoom at t seconds from the start of the shot, including cut punch."""
    z0, z1 = (float(shot["zoom"][0]), float(shot["zoom"][1]))
    dur = float(duration_s if duration_s is not None else shot.get("duration_s", 0.0))
    if dur <= 0:
        return z0
    t = _clamp(float(t_rel), 0.0, dur)
    tin = float(shot["punch_in_dur"]) if shot.get("has_punch_in") else 0.0
    out_len = float(shot["punch_out_dur"]) if shot.get("has_punch_out") else 0.0
    t_out = dur - out_len

    if tin > 1e-6 and t <= tin:
        z_from = z0 * float(shot["punch_in"])
        return z_from + (z0 - z_from) * ease_out_cubic(t / tin)
    if out_len > 1e-6 and t >= t_out:
        z_to = z1 * float(shot["punch_out"])
        return z1 + (z_to - z1) * ease_in_cubic((t - t_out) / out_len)
    span = t_out - tin
    if span <= 1e-6:
        return z0
    return z0 + (z1 - z0) * smoothstep((t - tin) / span)
