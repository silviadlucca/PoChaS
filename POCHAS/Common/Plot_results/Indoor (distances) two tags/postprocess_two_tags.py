#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Postprocess PoChaS indoor measurements with two UWB tags.

The script reads a *_Rxfile.txt log plus anchors.json, filters malformed or weak
measurements, estimates tag positions with robust weighted least squares, chooses
the best tag per time window, and exports:

- filtered_positions.csv
- summary.txt
- postprocess_dashboard.png

Usage:
    python postprocess_two_tags.py
    python postprocess_two_tags.py --log 2026-05-27_13-33-13_Rxfile.txt
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import least_squares


DEFAULT_TIME_WINDOW_MS = 300.0
DEFAULT_MIN_ANCHORS_3D = 4
DEFAULT_MIN_DISTANCE_M = 0.10
DEFAULT_MAX_DISTANCE_M = 30.0
DEFAULT_MAX_JUMP_M = 1.20
DEFAULT_HEIGHT_JUMP_M = 0.70
DEFAULT_SMOOTH_ALPHA = 0.35


@dataclass
class Measurement:
    line_num: int
    sdr_rssi: float
    distances: dict[str, float]
    anchor_rssis: dict[str, float]
    tag_id: int
    timestamp_ms: float
    temperature_c: float
    valid_distances: dict[str, float] = field(default_factory=dict)
    valid_rssis: dict[str, float] = field(default_factory=dict)
    position: Optional[np.ndarray] = None
    rmse_m: Optional[float] = None
    max_error_m: Optional[float] = None
    condition: Optional[float] = None
    quality: float = -999.0
    solve_ok: bool = False
    reject_reason: str = ""

    @property
    def anchor_count(self) -> int:
        return len(self.valid_distances)

    @property
    def avg_anchor_rssi(self) -> Optional[float]:
        values = [v for v in self.valid_rssis.values() if is_finite_number(v)]
        if not values:
            return None
        return float(np.mean(values))

    @property
    def best_anchor_rssi(self) -> Optional[float]:
        values = [v for v in self.valid_rssis.values() if is_finite_number(v)]
        if not values:
            return None
        return float(np.max(values))


@dataclass
class Epoch:
    index: int
    timestamp_ms: float
    records: dict[int, Measurement]
    fused_raw_position: Optional[np.ndarray] = None
    fused_position: Optional[np.ndarray] = None
    fused_tag: Optional[int] = None
    fused_rmse_m: Optional[float] = None
    flags: list[str] = field(default_factory=list)


def is_finite_number(value: object) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def find_latest_file(directory: Path, pattern: str) -> Path:
    matches = [p for p in directory.glob(pattern) if p.is_file()]
    if not matches:
        raise FileNotFoundError(f"No files matching {pattern!r} in {directory}")
    return max(matches, key=lambda p: p.stat().st_mtime)


def load_anchors(path: Path) -> dict[str, np.ndarray]:
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    anchors: dict[str, np.ndarray] = {}
    for anchor_id, coords in raw.items():
        if len(coords) != 3:
            raise ValueError(f"Anchor {anchor_id} must have [x, y, z] coordinates")
        anchors[str(anchor_id)] = np.array(coords, dtype=float)
    return anchors


def parse_log(path: Path) -> list[Measurement]:
    records: list[Measurement] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_num, raw_line in enumerate(handle, 1):
            line = raw_line.strip()
            if not line or line.startswith("#") or "RSSI" in line:
                continue

            try:
                parsed = ast.literal_eval(f"({line})")
            except (SyntaxError, ValueError):
                continue

            if len(parsed) < 6:
                continue

            sdr_rssi, distances, anchor_rssis, tag_id, timestamp_ms, temperature_c = parsed[:6]
            if not isinstance(distances, dict) or not isinstance(anchor_rssis, dict):
                continue
            if int(tag_id) not in (1, 2):
                continue

            records.append(
                Measurement(
                    line_num=line_num,
                    sdr_rssi=float(sdr_rssi),
                    distances={str(k): float(v) for k, v in distances.items() if is_finite_number(v)},
                    anchor_rssis={str(k): float(v) for k, v in anchor_rssis.items() if is_finite_number(v)},
                    tag_id=int(tag_id),
                    timestamp_ms=float(timestamp_ms),
                    temperature_c=float(temperature_c),
                )
            )

    records.sort(key=lambda item: item.timestamp_ms)
    return records


def prepare_valid_anchor_sets(
    records: list[Measurement],
    anchors: dict[str, np.ndarray],
    min_distance_m: float,
    max_distance_m: float,
) -> None:
    for record in records:
        for anchor_id, distance in record.distances.items():
            if anchor_id not in anchors:
                continue
            if not (min_distance_m <= distance <= max_distance_m):
                continue
            record.valid_distances[anchor_id] = float(distance)
            record.valid_rssis[anchor_id] = float(record.anchor_rssis.get(anchor_id, -100.0))


def rssi_to_weight(rssi: float) -> float:
    # Smooth mapping: -100 dBm -> low but usable, -65 dBm -> strong.
    normalized = np.clip((float(rssi) + 100.0) / 35.0, 0.0, 1.0)
    return float(0.25 + 1.75 * normalized)


def make_position_bounds(anchors: dict[str, np.ndarray], margin_xy_m: float, z_margin_m: float) -> tuple[np.ndarray, np.ndarray]:
    coords = np.array(list(anchors.values()), dtype=float)
    lower = coords.min(axis=0)
    upper = coords.max(axis=0)
    lower[:2] -= margin_xy_m
    upper[:2] += margin_xy_m
    lower[2] = min(0.0, lower[2] - z_margin_m)
    upper[2] = upper[2] + z_margin_m
    return lower, upper


def initial_guess_for(record: Measurement, anchors: dict[str, np.ndarray]) -> np.ndarray:
    coords = []
    weights = []
    for anchor_id, distance in record.valid_distances.items():
        coords.append(anchors[anchor_id])
        weights.append(rssi_to_weight(record.valid_rssis.get(anchor_id, -100.0)) / max(distance, 0.20))

    if not coords:
        return np.mean(np.array(list(anchors.values())), axis=0)

    return np.average(np.array(coords), axis=0, weights=np.array(weights))


def solve_measurement_position(
    record: Measurement,
    anchors: dict[str, np.ndarray],
    min_anchors_3d: int,
    lower_bounds: np.ndarray,
    upper_bounds: np.ndarray,
    previous_by_tag: dict[int, np.ndarray],
) -> None:
    if record.anchor_count < min_anchors_3d:
        record.reject_reason = f"not_enough_anchors_{record.anchor_count}"
        return

    anchor_ids = list(record.valid_distances.keys())
    anchor_coords = np.array([anchors[anchor_id] for anchor_id in anchor_ids], dtype=float)
    measured_distances = np.array([record.valid_distances[anchor_id] for anchor_id in anchor_ids], dtype=float)
    weights = np.array([rssi_to_weight(record.valid_rssis.get(anchor_id, -100.0)) for anchor_id in anchor_ids], dtype=float)

    x0 = previous_by_tag.get(record.tag_id)
    if x0 is None:
        x0 = initial_guess_for(record, anchors)
    x0 = np.clip(np.array(x0, dtype=float), lower_bounds, upper_bounds)

    def residuals(position: np.ndarray) -> np.ndarray:
        predicted = np.linalg.norm(position - anchor_coords, axis=1)
        return np.sqrt(weights) * (predicted - measured_distances)

    try:
        result = least_squares(
            residuals,
            x0,
            bounds=(lower_bounds, upper_bounds),
            loss="soft_l1",
            f_scale=0.50,
            max_nfev=400,
        )
    except Exception as exc:
        record.reject_reason = f"solver_error_{type(exc).__name__}"
        return

    if not result.success:
        record.reject_reason = "solver_not_converged"
        return

    position = result.x
    plain_errors = np.linalg.norm(position - anchor_coords, axis=1) - measured_distances
    rmse = float(np.sqrt(np.mean(plain_errors**2)))
    max_error = float(np.max(np.abs(plain_errors)))
    condition = compute_geometry_condition(position, anchor_coords)

    avg_rssi = record.avg_anchor_rssi if record.avg_anchor_rssi is not None else -100.0
    z_span = float(np.max(anchor_coords[:, 2]) - np.min(anchor_coords[:, 2]))
    condition_penalty = 0.0 if not math.isfinite(condition) else math.log10(max(condition, 1.0))
    z_penalty = 1.0 if z_span < 0.40 else 0.0

    record.position = position
    record.rmse_m = rmse
    record.max_error_m = max_error
    record.condition = condition
    record.quality = (
        3.0 * record.anchor_count
        + (avg_rssi + 100.0) / 5.0
        - 4.0 * rmse
        - condition_penalty
        - z_penalty
    )
    record.solve_ok = True
    record.reject_reason = ""
    previous_by_tag[record.tag_id] = position


def compute_geometry_condition(position: np.ndarray, anchor_coords: np.ndarray) -> float:
    rows = []
    for coord in anchor_coords:
        diff = position - coord
        distance = np.linalg.norm(diff)
        if distance <= 1e-9:
            continue
        rows.append(diff / distance)

    if len(rows) < 3:
        return float("inf")

    jacobian = np.array(rows, dtype=float)
    try:
        return float(np.linalg.cond(jacobian))
    except np.linalg.LinAlgError:
        return float("inf")


def build_epochs(records: list[Measurement], time_window_ms: float) -> list[Epoch]:
    epochs: list[Epoch] = []
    current_records: dict[int, Measurement] = {}
    current_start: Optional[float] = None

    def better_record(candidate: Measurement, existing: Measurement) -> Measurement:
        if candidate.solve_ok != existing.solve_ok:
            return candidate if candidate.solve_ok else existing
        if candidate.anchor_count != existing.anchor_count:
            return candidate if candidate.anchor_count > existing.anchor_count else existing
        return candidate if candidate.quality > existing.quality else existing

    def flush() -> None:
        nonlocal current_records, current_start
        if not current_records:
            return
        timestamps = [item.timestamp_ms for item in current_records.values()]
        epochs.append(Epoch(index=len(epochs), timestamp_ms=float(np.mean(timestamps)), records=dict(current_records)))
        current_records = {}
        current_start = None

    for record in records:
        if current_start is None:
            current_start = record.timestamp_ms

        if record.timestamp_ms - current_start > time_window_ms:
            flush()
            current_start = record.timestamp_ms

        existing = current_records.get(record.tag_id)
        current_records[record.tag_id] = record if existing is None else better_record(record, existing)

    flush()
    return epochs


def choose_fused_positions(
    epochs: list[Epoch],
    max_jump_m: float,
    height_jump_m: float,
    smooth_alpha: float,
) -> None:
    previous_position: Optional[np.ndarray] = None
    previous_z: Optional[float] = None
    rejected_streak = 0

    for epoch in epochs:
        tag1 = epoch.records.get(1)
        tag2 = epoch.records.get(2)
        tag1_ok = bool(tag1 and tag1.solve_ok)
        tag2_ok = bool(tag2 and tag2.solve_ok)

        if not tag1_ok:
            epoch.flags.append("tag1_no_3d_fix")
        if not tag2_ok:
            epoch.flags.append("tag2_no_3d_fix")
        if not tag1_ok and not tag2_ok:
            epoch.flags.append("both_tags_no_3d_fix")
            continue
        if tag1_ok and not tag2_ok:
            epoch.flags.append("tag1_saves_epoch")
        if tag2_ok and not tag1_ok:
            epoch.flags.append("tag2_saves_epoch")

        candidates = [record for record in (tag1, tag2) if record is not None and record.solve_ok and record.position is not None]
        scored_candidates = []
        for record in candidates:
            score = record.quality
            if previous_position is not None:
                jump = float(np.linalg.norm(record.position - previous_position))
                if jump > max_jump_m:
                    score -= 8.0 * (jump - max_jump_m)
            scored_candidates.append((score, record))

        scored_candidates.sort(key=lambda item: item[0], reverse=True)
        selected = scored_candidates[0][1]
        if previous_position is not None:
            for _, candidate in scored_candidates:
                assert candidate.position is not None
                if float(np.linalg.norm(candidate.position - previous_position)) <= max_jump_m:
                    selected = candidate
                    break

        assert selected.position is not None
        epoch.fused_raw_position = selected.position
        epoch.fused_tag = selected.tag_id
        epoch.fused_rmse_m = selected.rmse_m

        if previous_position is None:
            fused = selected.position.copy()
        else:
            jump = float(np.linalg.norm(selected.position - previous_position))
            if jump > max_jump_m:
                if rejected_streak < 2:
                    epoch.flags.append("fused_jump_rejected")
                    rejected_streak += 1
                    continue
                epoch.flags.append("trajectory_reset_after_gap")
                fused = selected.position.copy()
                rejected_streak = 0
            else:
                fused = smooth_alpha * selected.position + (1.0 - smooth_alpha) * previous_position
                rejected_streak = 0

        if previous_z is not None and abs(float(fused[2]) - previous_z) > height_jump_m:
            epoch.flags.append("height_jump_warning")

        if selected.rmse_m is not None and selected.rmse_m > 0.75:
            epoch.flags.append("high_residual_warning")

        if selected.condition is not None and selected.condition > 25.0:
            epoch.flags.append("weak_height_geometry")

        epoch.fused_position = fused
        previous_position = fused
        previous_z = float(fused[2])


def export_csv(epochs: list[Epoch], output_path: Path) -> None:
    fieldnames = [
        "epoch",
        "timestamp_ms",
        "tag1_anchor_count",
        "tag1_avg_rssi",
        "tag1_solve_ok",
        "tag1_x",
        "tag1_y",
        "tag1_z",
        "tag1_rmse_m",
        "tag2_anchor_count",
        "tag2_avg_rssi",
        "tag2_solve_ok",
        "tag2_x",
        "tag2_y",
        "tag2_z",
        "tag2_rmse_m",
        "fused_tag",
        "fused_x",
        "fused_y",
        "fused_z",
        "fused_rmse_m",
        "flags",
    ]

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for epoch in epochs:
            row = {
                "epoch": epoch.index,
                "timestamp_ms": round(epoch.timestamp_ms, 3),
                "fused_tag": epoch.fused_tag or "",
                "fused_rmse_m": round(epoch.fused_rmse_m, 4) if epoch.fused_rmse_m is not None else "",
                "flags": ";".join(epoch.flags),
            }
            add_record_to_row(row, "tag1", epoch.records.get(1))
            add_record_to_row(row, "tag2", epoch.records.get(2))
            if epoch.fused_position is not None:
                row["fused_x"] = round(float(epoch.fused_position[0]), 4)
                row["fused_y"] = round(float(epoch.fused_position[1]), 4)
                row["fused_z"] = round(float(epoch.fused_position[2]), 4)
            else:
                row["fused_x"] = row["fused_y"] = row["fused_z"] = ""
            writer.writerow(row)


def add_record_to_row(row: dict[str, object], prefix: str, record: Optional[Measurement]) -> None:
    if record is None:
        row[f"{prefix}_anchor_count"] = 0
        row[f"{prefix}_avg_rssi"] = ""
        row[f"{prefix}_solve_ok"] = False
        row[f"{prefix}_x"] = row[f"{prefix}_y"] = row[f"{prefix}_z"] = ""
        row[f"{prefix}_rmse_m"] = ""
        return

    row[f"{prefix}_anchor_count"] = record.anchor_count
    row[f"{prefix}_avg_rssi"] = round(record.avg_anchor_rssi, 3) if record.avg_anchor_rssi is not None else ""
    row[f"{prefix}_solve_ok"] = record.solve_ok
    row[f"{prefix}_rmse_m"] = round(record.rmse_m, 4) if record.rmse_m is not None else ""
    if record.position is not None:
        row[f"{prefix}_x"] = round(float(record.position[0]), 4)
        row[f"{prefix}_y"] = round(float(record.position[1]), 4)
        row[f"{prefix}_z"] = round(float(record.position[2]), 4)
    else:
        row[f"{prefix}_x"] = row[f"{prefix}_y"] = row[f"{prefix}_z"] = ""


def write_summary(
    output_path: Path,
    log_path: Path,
    anchors_path: Path,
    records: list[Measurement],
    epochs: list[Epoch],
    anchors: dict[str, np.ndarray],
) -> None:
    total_epochs = len(epochs)
    both_lost = [epoch for epoch in epochs if "both_tags_no_3d_fix" in epoch.flags]
    tag1_saves = [epoch for epoch in epochs if "tag1_saves_epoch" in epoch.flags]
    tag2_saves = [epoch for epoch in epochs if "tag2_saves_epoch" in epoch.flags]
    fused_epochs = [epoch for epoch in epochs if epoch.fused_position is not None]
    source_counts = {
        1: sum(1 for epoch in fused_epochs if epoch.fused_tag == 1),
        2: sum(1 for epoch in fused_epochs if epoch.fused_tag == 2),
    }

    fused_positions = np.array([epoch.fused_position for epoch in fused_epochs], dtype=float) if fused_epochs else np.empty((0, 3))
    z_values = fused_positions[:, 2] if len(fused_positions) else np.array([])
    y_values = fused_positions[:, 1] if len(fused_positions) else np.array([])
    height_corr = safe_corrcoef(y_values, z_values)
    height_range = float(np.max(z_values) - np.min(z_values)) if len(z_values) else float("nan")
    z_jumps = count_height_jumps(fused_epochs, threshold_m=DEFAULT_HEIGHT_JUMP_M)
    weak_height = [epoch for epoch in epochs if "weak_height_geometry" in epoch.flags]
    high_residual = [epoch for epoch in epochs if "high_residual_warning" in epoch.flags]
    rejected_jumps = [epoch for epoch in epochs if "fused_jump_rejected" in epoch.flags]
    longest_both_lost = longest_flag_streak(epochs, "both_tags_no_3d_fix")

    anchor_availability = compute_anchor_availability(records, anchors)

    lines = [
        "PoChaS two-tag postprocess summary",
        "=" * 38,
        f"Log: {log_path}",
        f"Anchors: {anchors_path}",
        f"Measurements parsed: {len(records)}",
        f"Epochs paired/analyzed: {total_epochs}",
        "",
        "Coverage",
        "--------",
        f"Fused valid epochs: {len(fused_epochs)} ({percent(len(fused_epochs), total_epochs)})",
        f"Both tags without 3D fix: {len(both_lost)} ({percent(len(both_lost), total_epochs)})",
        f"Longest both-tags loss streak: {longest_both_lost[0]} epochs, ~{longest_both_lost[1]:.0f} ms",
        f"Tag 1 saved epochs: {len(tag1_saves)}",
        f"Tag 2 saved epochs: {len(tag2_saves)}",
        f"Fused source Tag 1: {source_counts[1]} epochs",
        f"Fused source Tag 2: {source_counts[2]} epochs",
        f"Rejected fused jumps: {len(rejected_jumps)}",
        "",
        "Height",
        "------",
        f"Fused Z range: {height_range:.3f} m" if math.isfinite(height_range) else "Fused Z range: n/a",
        f"Correlation Y/Z: {height_corr:.3f}" if math.isfinite(height_corr) else "Correlation Y/Z: n/a",
        f"Height jump warnings: {z_jumps}",
        f"Weak height geometry epochs: {len(weak_height)}",
        f"High residual epochs: {len(high_residual)}",
        "",
        "Anchor availability by tag",
        "--------------------------",
    ]

    for tag_id in (1, 2):
        for anchor_id in sorted(anchors.keys(), key=anchor_sort_key):
            lines.append(f"Tag {tag_id} / Anchor {anchor_id}: {anchor_availability.get((tag_id, anchor_id), '0.0%')}")

    lines.extend(["", "Reading guide", "-------------"])
    if both_lost:
        lines.append("There are epochs where neither tag provides enough anchors for a 3D fix. Check the shaded red bands in the dashboard.")
    else:
        lines.append("No epoch lost 3D coverage in both tags at the same time with the current filters.")

    if source_counts[1] != source_counts[2]:
        best_source = 1 if source_counts[1] > source_counts[2] else 2
        lines.append(f"Tag {best_source} is selected more often by the fusion rule; inspect whether its orientation or antenna placement is more favorable.")

    if math.isfinite(height_corr):
        if abs(height_corr) >= 0.65:
            lines.append("The fused height has a clear relationship with corridor progress (Y), which is a good sign for stairs.")
        elif len(fused_epochs) >= 5:
            lines.append("The fused height does not strongly follow corridor progress (Y). Review anchor geometry, calibration, and outlier filtering.")

    if weak_height:
        lines.append("Some epochs have weak vertical geometry. More anchors with different heights usually improve Z estimation.")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def safe_corrcoef(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3 or len(b) < 3:
        return float("nan")
    if float(np.std(a)) < 1e-9 or float(np.std(b)) < 1e-9:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def count_height_jumps(epochs: list[Epoch], threshold_m: float) -> int:
    previous_z: Optional[float] = None
    count = 0
    for epoch in epochs:
        if epoch.fused_position is None:
            continue
        z = float(epoch.fused_position[2])
        if previous_z is not None and abs(z - previous_z) > threshold_m:
            count += 1
        previous_z = z
    return count


def longest_flag_streak(epochs: list[Epoch], flag: str) -> tuple[int, float]:
    best_count = 0
    best_duration = 0.0
    current_count = 0
    start_time = 0.0
    previous_time = 0.0

    for epoch in epochs:
        if flag in epoch.flags:
            if current_count == 0:
                start_time = epoch.timestamp_ms
            current_count += 1
            previous_time = epoch.timestamp_ms
            duration = max(0.0, previous_time - start_time)
            if current_count > best_count:
                best_count = current_count
                best_duration = duration
        else:
            current_count = 0

    return best_count, best_duration


def compute_anchor_availability(records: list[Measurement], anchors: dict[str, np.ndarray]) -> dict[tuple[int, str], str]:
    result: dict[tuple[int, str], str] = {}
    for tag_id in (1, 2):
        tag_records = [record for record in records if record.tag_id == tag_id]
        for anchor_id in sorted(anchors.keys(), key=anchor_sort_key):
            seen = sum(1 for record in tag_records if anchor_id in record.valid_distances)
            result[(tag_id, anchor_id)] = percent(seen, len(tag_records))
    return result


def percent(value: int, total: int) -> str:
    if total <= 0:
        return "0.0%"
    return f"{100.0 * value / total:.1f}%"


def anchor_sort_key(anchor_id: str) -> tuple[int, str]:
    try:
        return int(anchor_id), anchor_id
    except ValueError:
        return 999999, anchor_id


def plot_dashboard(
    output_path: Path,
    epochs: list[Epoch],
    anchors: dict[str, np.ndarray],
    log_name: str,
    min_anchors_3d: int,
) -> None:
    fig = plt.figure(figsize=(17, 11))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.15, 1.0])
    ax_xy = fig.add_subplot(gs[0, 0])
    ax_z = fig.add_subplot(gs[0, 1])
    ax_cov = fig.add_subplot(gs[1, 0])
    ax_heat = fig.add_subplot(gs[1, 1])

    plot_xy(ax_xy, epochs, anchors)
    plot_height(ax_z, epochs, anchors)
    plot_coverage(ax_cov, epochs, min_anchors_3d)
    plot_anchor_heatmap(ax_heat, epochs, anchors)

    fig.suptitle(f"PoChaS two-tag postprocess - {log_name}", fontsize=15, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_xy(ax: plt.Axes, epochs: list[Epoch], anchors: dict[str, np.ndarray]) -> None:
    for anchor_id, coords in sorted(anchors.items(), key=lambda item: anchor_sort_key(item[0])):
        ax.scatter(coords[0], coords[1], marker="^", s=120, color="#c0392b", edgecolor="black", zorder=5)
        ax.text(coords[0] + 0.10, coords[1] + 0.10, f"A{anchor_id} z={coords[2]:.2f}", fontsize=9, color="#7b241c")

    for tag_id, color in ((1, "#2e86de"), (2, "#f39c12")):
        xs, ys = [], []
        for epoch in epochs:
            record = epoch.records.get(tag_id)
            if record is not None and record.position is not None:
                xs.append(float(record.position[0]))
                ys.append(float(record.position[1]))
        if xs:
            ax.scatter(xs, ys, s=16, color=color, alpha=0.35, label=f"Tag {tag_id} solved")

    fused = [(epoch, epoch.fused_position) for epoch in epochs if epoch.fused_position is not None]
    if fused:
        xs = [float(position[0]) for _, position in fused]
        ys = [float(position[1]) for _, position in fused]
        source_colors = ["#1f618d" if epoch.fused_tag == 1 else "#b9770e" for epoch, _ in fused]
        ax.plot(xs, ys, color="#34495e", linewidth=1.5, alpha=0.60, label="Fused trajectory")
        ax.scatter(xs, ys, c=source_colors, s=28, edgecolor="white", linewidth=0.4, zorder=4)
        ax.scatter(xs[0], ys[0], marker="s", s=90, color="#27ae60", edgecolor="black", label="Start", zorder=6)
        ax.scatter(xs[-1], ys[-1], marker="X", s=100, color="#e74c3c", edgecolor="black", label="End", zorder=6)

    ax.set_title("XY trajectory and anchors")
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.grid(True, linestyle=":", alpha=0.45)
    ax.set_aspect("equal", adjustable="datalim")
    ax.legend(loc="best", fontsize=8)


def plot_height(ax: plt.Axes, epochs: list[Epoch], anchors: dict[str, np.ndarray]) -> None:
    x = np.arange(len(epochs))

    for tag_id, color in ((1, "#2e86de"), (2, "#f39c12")):
        xs, zs = [], []
        for epoch in epochs:
            record = epoch.records.get(tag_id)
            if record is not None and record.position is not None:
                xs.append(epoch.index)
                zs.append(float(record.position[2]))
        if xs:
            ax.scatter(xs, zs, s=14, color=color, alpha=0.35, label=f"Tag {tag_id} Z")

    fused_x, fused_z = [], []
    for epoch in epochs:
        if epoch.fused_position is not None:
            fused_x.append(epoch.index)
            fused_z.append(float(epoch.fused_position[2]))
    if fused_x:
        ax.plot(fused_x, fused_z, color="#111111", linewidth=2.0, label="Fused Z")

    for anchor_id, coords in sorted(anchors.items(), key=lambda item: anchor_sort_key(item[0])):
        ax.axhline(float(coords[2]), color="#c0392b", linewidth=0.7, alpha=0.25)
        ax.text(0, float(coords[2]), f"A{anchor_id}", fontsize=8, color="#7b241c", va="bottom")

    shade_flag_regions(ax, epochs, "both_tags_no_3d_fix", color="#e74c3c", alpha=0.12)
    ax.set_title("Height over time")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Z (m)")
    ax.grid(True, linestyle=":", alpha=0.45)
    ax.legend(loc="best", fontsize=8)
    ax.set_xlim(-1, max(len(x), 1))


def plot_coverage(ax: plt.Axes, epochs: list[Epoch], min_anchors_3d: int) -> None:
    xs = np.arange(len(epochs))
    counts_by_tag = {1: [], 2: []}
    for epoch in epochs:
        for tag_id in (1, 2):
            record = epoch.records.get(tag_id)
            counts_by_tag[tag_id].append(record.anchor_count if record is not None else 0)

    ax.step(xs, counts_by_tag[1], where="mid", color="#2e86de", label="Tag 1 anchors")
    ax.step(xs, counts_by_tag[2], where="mid", color="#f39c12", label="Tag 2 anchors")
    ax.axhline(min_anchors_3d, color="#2c3e50", linestyle="--", linewidth=1.0, label=f"3D threshold ({min_anchors_3d})")
    shade_flag_regions(ax, epochs, "both_tags_no_3d_fix", color="#e74c3c", alpha=0.16)
    shade_flag_regions(ax, epochs, "fused_jump_rejected", color="#8e44ad", alpha=0.10)
    ax.set_title("Coverage over time")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Valid anchors")
    ax.set_ylim(-0.2, max(max(counts_by_tag[1] or [0]), max(counts_by_tag[2] or [0]), min_anchors_3d) + 1)
    ax.grid(True, linestyle=":", alpha=0.45)
    ax.legend(loc="best", fontsize=8)


def plot_anchor_heatmap(ax: plt.Axes, epochs: list[Epoch], anchors: dict[str, np.ndarray]) -> None:
    anchor_ids = sorted(anchors.keys(), key=anchor_sort_key)
    rows = []
    labels = []

    for tag_id in (1, 2):
        for anchor_id in anchor_ids:
            rows.append([
                1.0 if (epoch.records.get(tag_id) is not None and anchor_id in epoch.records[tag_id].valid_distances) else 0.0
                for epoch in epochs
            ])
            labels.append(f"T{tag_id}-A{anchor_id}")

    matrix = np.array(rows, dtype=float) if rows else np.empty((0, len(epochs)))
    ax.imshow(matrix, aspect="auto", interpolation="nearest", cmap="Greens", vmin=0, vmax=1)
    ax.set_title("Anchor availability")
    ax.set_xlabel("Epoch")
    ax.set_yticks(np.arange(len(labels)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xticks(np.linspace(0, max(len(epochs) - 1, 0), num=min(6, max(len(epochs), 1)), dtype=int))


def shade_flag_regions(ax: plt.Axes, epochs: list[Epoch], flag: str, color: str, alpha: float) -> None:
    start: Optional[int] = None
    last_idx: Optional[int] = None
    for epoch in epochs:
        has_flag = flag in epoch.flags
        if has_flag and start is None:
            start = epoch.index
        if not has_flag and start is not None:
            ax.axvspan(start - 0.5, (last_idx if last_idx is not None else start) + 0.5, color=color, alpha=alpha, linewidth=0)
            start = None
        if has_flag:
            last_idx = epoch.index
    if start is not None:
        ax.axvspan(start - 0.5, (last_idx if last_idx is not None else start) + 0.5, color=color, alpha=alpha, linewidth=0)


def run(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    script_dir = Path(__file__).resolve().parent
    log_path = Path(args.log).resolve() if args.log else find_latest_file(script_dir, "*_Rxfile.txt")
    anchors_path = Path(args.anchors).resolve() if args.anchors else script_dir / "anchors.json"
    if not anchors_path.exists():
        anchors_path = find_latest_file(script_dir, "*.json")

    anchors = load_anchors(anchors_path)
    records = parse_log(log_path)
    if not records:
        raise RuntimeError(f"No valid two-tag measurements found in {log_path}")

    prepare_valid_anchor_sets(records, anchors, args.min_distance_m, args.max_distance_m)
    lower_bounds, upper_bounds = make_position_bounds(anchors, args.bounds_margin_xy_m, args.bounds_margin_z_m)

    previous_by_tag: dict[int, np.ndarray] = {}
    for record in records:
        solve_measurement_position(
            record=record,
            anchors=anchors,
            min_anchors_3d=args.min_anchors_3d,
            lower_bounds=lower_bounds,
            upper_bounds=upper_bounds,
            previous_by_tag=previous_by_tag,
        )

    epochs = build_epochs(records, args.time_window_ms)
    choose_fused_positions(epochs, args.max_jump_m, args.height_jump_m, args.smooth_alpha)

    output_dir = Path(args.output_dir).resolve() if args.output_dir else script_dir / "postprocess_out" / log_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / "filtered_positions.csv"
    summary_path = output_dir / "summary.txt"
    dashboard_path = output_dir / "postprocess_dashboard.png"

    export_csv(epochs, csv_path)
    write_summary(summary_path, log_path, anchors_path, records, epochs, anchors)
    plot_dashboard(dashboard_path, epochs, anchors, log_path.name, args.min_anchors_3d)

    if args.show:
        image = plt.imread(dashboard_path)
        plt.figure(figsize=(14, 9))
        plt.imshow(image)
        plt.axis("off")
        plt.show()

    return csv_path, summary_path, dashboard_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Postprocess PoChaS two-tag indoor logs.")
    parser.add_argument("--log", help="Path to a *_Rxfile.txt measurement log. Defaults to the newest log in this folder.")
    parser.add_argument("--anchors", help="Path to anchors.json. Defaults to anchors.json in this folder.")
    parser.add_argument("--output-dir", help="Output directory. Defaults to postprocess_out/<log_stem>.")
    parser.add_argument("--time-window-ms", type=float, default=DEFAULT_TIME_WINDOW_MS, help="Pairing window for Tag 1 and Tag 2 records.")
    parser.add_argument("--min-anchors-3d", type=int, default=DEFAULT_MIN_ANCHORS_3D, help="Minimum anchors required for a 3D fix.")
    parser.add_argument("--min-distance-m", type=float, default=DEFAULT_MIN_DISTANCE_M, help="Drop distances below this value.")
    parser.add_argument("--max-distance-m", type=float, default=DEFAULT_MAX_DISTANCE_M, help="Drop distances above this value.")
    parser.add_argument("--max-jump-m", type=float, default=DEFAULT_MAX_JUMP_M, help="Reject fused trajectory jumps above this value.")
    parser.add_argument("--height-jump-m", type=float, default=DEFAULT_HEIGHT_JUMP_M, help="Flag height jumps above this value.")
    parser.add_argument("--smooth-alpha", type=float, default=DEFAULT_SMOOTH_ALPHA, help="EMA smoothing factor for fused trajectory.")
    parser.add_argument("--bounds-margin-xy-m", type=float, default=4.0, help="XY margin around anchor bounding box for solver bounds.")
    parser.add_argument("--bounds-margin-z-m", type=float, default=2.0, help="Z margin above/below anchor heights for solver bounds.")
    parser.add_argument("--show", action="store_true", help="Show the generated dashboard after saving.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    csv_path, summary_path, dashboard_path = run(args)
    print("Postprocess complete:")
    print(f"  CSV: {csv_path}")
    print(f"  Summary: {summary_path}")
    print(f"  Dashboard: {dashboard_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
