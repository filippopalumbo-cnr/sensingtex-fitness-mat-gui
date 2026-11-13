"""Score-blind, recording-level features; no claim of exercise-event recognition."""
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np
from scipy.ndimage import gaussian_filter1d

from .config import ExtractionConfig
from .recording import RecordingError, filename_metadata, read_recording

FEATURE_NAMES = ("cop_speed", "cop_ellipse", "load_cv", "contact_cv")
CHI2_95_2D = 5.991464547  # Preserve the constant used in the original analysis.


@dataclass
class ExtractionResult:
    audit: dict
    features: list[dict]
    trace: dict = field(default_factory=dict)


def occupied_bouts(mask, timestamps, max_gap_seconds):
    """Split at unloaded frames AND acquisition gaps; never bridge a long gap."""
    idx = np.flatnonzero(mask)
    if not len(idx):
        return []
    breaks = (np.diff(idx) > 1) | (np.diff(timestamps[idx]) > max_gap_seconds)
    return np.split(idx, np.flatnonzero(breaks) + 1)


def describe_segment(time, signals):
    """Signals are [total response, active cells, CoP row, CoP column]."""
    duration = float(time[-1] - time[0])
    xy = signals[:, 2:4]
    path_length = float(np.linalg.norm(np.diff(xy, axis=0), axis=1).sum())
    covariance = np.cov(xy, rowvar=False)  # Sample covariance (N-1).
    ellipse = np.pi * CHI2_95_2D * np.sqrt(max(float(np.linalg.det(covariance)), 0.0))
    load_cv = float(signals[:, 0].std(ddof=0) / signals[:, 0].mean())
    contact_cv = float(signals[:, 1].std(ddof=0) / signals[:, 1].mean())
    return dict(cop_speed=path_length / duration, cop_ellipse=float(ellipse),
                load_cv=load_cv, contact_cv=contact_cv,
                cop_path_length=path_length, load_cv_pct=100 * load_cv,
                contact_cv_pct=100 * contact_cv)


def longest_identical_run(t, raw, occupied, max_gap_seconds):
    same = (np.all(raw[1:] == raw[:-1], axis=1) & occupied[1:] & occupied[:-1]
            & (np.diff(t) <= max_gap_seconds))
    best, start = 0.0, 0
    for i, identical in enumerate(same, start=1):
        if not identical:
            start = i
        else:
            best = max(best, float(t[i] - t[start]))
    return best


def _signals(raw, threshold, config):
    p = np.where(raw >= threshold, raw, 0)
    load = p.sum(axis=1)
    positive = load[load > 0]
    gate = max(config.min_total_response, config.relative_occupancy * np.median(positive)) if len(positive) else config.min_total_response
    occupied = load >= gate
    row_coord = np.repeat(np.arange(config.rows), config.cols)
    col_coord = np.tile(np.arange(config.cols), config.rows)
    z = np.column_stack((load, (p > 0).sum(axis=1),
                         (p @ row_coord) / np.maximum(load, 1),
                         (p @ col_coord) / np.maximum(load, 1)))
    return p, occupied, z, float(gate)


def _variants(config, sensitivity):
    pairs = [(config.threshold, config.trim_fraction)]
    if sensitivity:
        pairs += [(threshold, trim) for threshold in (100.0, 150.0, 200.0) for trim in (0.0, 0.1)]
    return list(dict.fromkeys(pairs))


def extract_arrays(timestamps, raw, config=None, *, filename="recording.csv", sensitivity=False):
    """Extract without modifying input arrays; ineligible segments have blank features.

    Sensor coordinates are native zero-based row/column indices. No GUI rotation,
    spatial opening, body-weight normalization, or score/GUI-condition inputs.
    """
    config = config or ExtractionConfig()
    t, raw = np.asarray(timestamps, dtype=float), np.asarray(raw, dtype=float)
    if t.ndim != 1 or raw.ndim != 2 or raw.shape != (len(t), config.rows * config.cols):
        raise RecordingError(f"Expected time vector and N x {config.rows*config.cols} sensor array")
    if len(t) < 3:
        raise RecordingError("At least three frames are required")
    if not np.isfinite(t).all() or not np.isfinite(raw).all():
        raise RecordingError("Nonfinite timestamp or sensor value")
    dt = np.diff(t)
    if np.any(dt <= 0):
        raise RecordingError("Timestamps must be strictly increasing Unix seconds")
    if np.any(raw < 0) or np.any(raw > 65535) or np.any(raw != np.floor(raw)):
        raise RecordingError("Sensor values must be unsigned 16-bit integer counts (0..65535)")
    meta = filename_metadata(filename, t, config)
    median_dt, duration = float(np.median(dt)), float(t[-1] - t[0])
    gap_loss = float(np.maximum(dt[dt > config.max_gap_seconds] - median_dt, 0).sum())
    audit = dict(meta, n_frames=len(t), duration=duration, hz=1 / median_dt,
                 median_dt=median_dt, dt_p95=float(np.quantile(dt, .95)),
                 gaps_over_limit=int((dt > config.max_gap_seconds).sum()),
                 long_gap_loss_seconds=gap_loss, long_gap_loss_fraction=gap_loss / duration,
                 nonzero_below_threshold=int(((raw > 0) & (raw < config.threshold)).sum()),
                 max_value=float(raw.max()))
    features, trace = [], {}
    pairs = _variants(config, sensitivity)
    for threshold in dict.fromkeys(pair[0] for pair in pairs):
        p, occupied, z, gate = _signals(raw, threshold, config)
        all_bouts = occupied_bouts(occupied, t, config.max_gap_seconds)
        candidates = [b for b in all_bouts if len(b) >= config.min_frames
                      and t[b[-1]] - t[b[0]] >= config.min_segment_seconds]
        selected = max(candidates, key=lambda b: t[b[-1]] - t[b[0]]) if candidates else None
        if selected is not None:
            step = float(np.median(np.diff(t[selected])))
            # Absolute-time grid and excluded end point reproduce the earlier pipeline.
            grid = np.arange(t[selected[0]], t[selected[-1]], step)
            smooth = np.column_stack([np.interp(grid, t[selected], z[selected, k]) for k in range(4)])
            if config.smoothing_seconds > 0:
                smooth = gaussian_filter1d(smooth, sigma=config.smoothing_seconds / step, axis=0, mode="nearest")
        for _, trim in (pair for pair in pairs if pair[0] == threshold):
            primary = threshold == config.threshold and trim == config.trim_fraction
            row = dict(meta, threshold=threshold, trim=trim, is_primary=primary,
                       status="ineligible", reason="no_eligible_occupied_segment",
                       occupied_fraction=float(occupied.mean()), occupancy_gate=gate,
                       n_occupied_bouts=len(all_bouts), n_eligible_bouts=len(candidates))
            if selected is not None:
                start = int(len(grid) * trim)
                end = len(grid) - start
                tt, zz = grid[start:end], smooth[start:end]
                row.update(segment_start=float(tt[0] - t[0]), segment_end=float(tt[-1] - t[0]),
                           segment_duration=float(tt[-1] - tt[0]), n_segment_samples=len(tt),
                           native_median_interval=step,
                           raw_segment_first_index=int(selected[0]), raw_segment_last_index=int(selected[-1]))
                if len(tt) >= config.min_frames:
                    row.update(status="ok", reason="", **describe_segment(tt, zz))
                else:
                    row["reason"] = "too_few_resampled_frames"
                if primary:
                    trace.update(time=tt - t[0], signals=zz,
                                 median_map=np.median(p[selected], axis=0).reshape(config.rows, config.cols),
                                 representative_map=p[selected[len(selected)//2]].reshape(config.rows, config.cols))
            if primary:
                trace.update(raw_time=t - t[0], raw_signals=z, occupied=occupied,
                             start_unix_seconds=np.array(t[0]))
                audit["longest_identical_run_seconds"] = longest_identical_run(t, raw, occupied, config.max_gap_seconds)
            features.append(row)
    primary_row = next(row for row in features if row["is_primary"])
    flags = []
    if audit["long_gap_loss_fraction"] > config.qc_max_gap_loss_fraction:
        flags.append("excessive_gap_loss")
    if audit["longest_identical_run_seconds"] >= config.qc_frozen_seconds:
        flags.append("identical_occupied_frames")
    if primary_row["status"] != "ok":
        flags.append("no_eligible_primary_features")
    elif primary_row["segment_duration"] < config.qc_min_segment_seconds:
        flags.append("short_selected_segment")
    audit.update(primary_feature_eligible=primary_row["status"] == "ok",
                 selected_segment_seconds=primary_row.get("segment_duration", ""),
                 qc_pass=not flags, qc_flags=";".join(flags))
    for row in features:
        row.update(qc_pass=audit["qc_pass"], qc_flags=audit["qc_flags"])
    return ExtractionResult(audit, features, trace)


def extract_file(path, config=None, *, sensitivity=False):
    config = config or ExtractionConfig()
    t, raw, identity = read_recording(path, config)
    result = extract_arrays(t, raw, config, filename=Path(path).name, sensitivity=sensitivity)
    result.audit.update(identity)
    for row in result.features:
        row.update(sha256=identity["sha256"], n_frames=len(t),
                   first_data_row_skipped=identity["first_data_row_skipped"])
    return result
