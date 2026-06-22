#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Triangulacion/trilateracion de tags UWB a partir de distancias a anclas.

Uso rapido:
    python pr.py
    python pr.py --log 2026-05-27_13-33-13_Rxfile.txt --no-show

El script:
- Lee anchors.json y un log *_Rxfile.txt.
- Estima una posicion por cada medida util.
- Fusiona los dos tags en una trayectoria continua escogiendo la mejor lectura
  por ventana temporal.
- Dibuja un dashboard con plano XY, altura frente a tiempo y trayectoria 3D.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import math
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Optional

import numpy as np


DEFAULT_MIN_DISTANCE_M = 0.10
DEFAULT_MAX_DISTANCE_M = 30.0
DEFAULT_MIN_ANCHORS_3D = 4
DEFAULT_TIME_WINDOW_MS = 300.0
DEFAULT_HOLD_MAX_GAP_MS = 1200.0
DEFAULT_FIXED_HEIGHT_M = 1.70
DEFAULT_MAX_ANCHORS = 0
DEFAULT_BOUNDS_MARGIN_XY_M = 2.0
DEFAULT_BOUNDS_MARGIN_Z_M = 2.0
DEFAULT_ANCHOR_OUTLIER_M = 1.25
DEFAULT_MAX_JUMP_M = 2.50
DEFAULT_SMOOTH_ALPHA = 0.35
DEFAULT_TEMPORAL_WEIGHT = 7.0
DEFAULT_Z_MODE = "robust"
DEFAULT_Z_MIN_M = 0.60
DEFAULT_Z_MAX_M = 2.40
DEFAULT_Z_SPEED_MPS = 0.80
DEFAULT_Z_ALPHA = 0.45
DEFAULT_Z_PRIOR_SCALE_M = 0.70
DEFAULT_Z_IMPOSSIBLE_TOLERANCE_M = 0.35


@dataclass
class Measurement:
    line_num: int
    sdr_rssi: Optional[float]
    distances: dict[str, float]
    anchor_rssis: dict[str, float]
    tag_id: int
    timestamp_ms: float
    temperature_c: Optional[float]


@dataclass
class PositionFix:
    line_num: int
    timestamp_ms: float
    tag_id: int
    position: np.ndarray
    mode: str
    anchor_count: int
    rmse_m: Optional[float]
    max_error_m: Optional[float]
    avg_anchor_rssi: Optional[float]
    quality: float
    used_anchor_ids: tuple[str, ...] = ()
    rejected_anchor_ids: tuple[str, ...] = ()
    held: bool = False


@dataclass
class FusedFix:
    timestamp_ms: float
    position: np.ndarray
    raw_position: np.ndarray
    source_tag: int
    line_num: int
    mode: str
    rmse_m: Optional[float]
    quality: float
    held: bool
    motion_rejected: bool = False
    z_raw_m: Optional[float] = None
    z_candidates: int = 0
    z_mode: str = ""


@dataclass
class SolveCandidate:
    position: np.ndarray
    mode: str
    used_indices: tuple[int, ...]
    rmse_m: float
    max_error_m: float
    score: float


def is_finite_number(value: object) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def find_latest_file(directory: Path, patterns: list[str]) -> Optional[Path]:
    for pattern in patterns:
        matches = [path for path in directory.glob(pattern) if path.is_file()]
        if matches:
            return max(matches, key=lambda path: path.stat().st_mtime)
    return None


def resolve_input_path(raw_path: Optional[str], base_dir: Path, patterns: list[str]) -> Optional[Path]:
    if raw_path:
        path = Path(raw_path)
        if not path.is_absolute():
            path = base_dir / path
        return path
    return find_latest_file(base_dir, patterns)


def load_anchors(path: Path) -> dict[str, np.ndarray]:
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    anchors: dict[str, np.ndarray] = {}
    for anchor_id, coords in raw.items():
        if not isinstance(coords, list) or len(coords) != 3:
            raise ValueError(f"Anchor {anchor_id} debe tener coordenadas [x, y, z].")
        anchors[str(anchor_id)] = np.array(coords, dtype=float)
    return anchors


def parse_log(path: Path, max_records: int = 0) -> list[Measurement]:
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

            try:
                if len(parsed) >= 6 and isinstance(parsed[1], dict) and isinstance(parsed[2], dict):
                    sdr_rssi = float(parsed[0]) if is_finite_number(parsed[0]) else None
                    distances = parsed[1]
                    anchor_rssis = parsed[2]
                    tag_id = int(parsed[3])
                    timestamp_ms = float(parsed[4])
                    temperature_c = float(parsed[5]) if is_finite_number(parsed[5]) else None
                elif len(parsed) >= 5 and isinstance(parsed[1], dict):
                    sdr_rssi = float(parsed[0]) if is_finite_number(parsed[0]) else None
                    distances = parsed[1]
                    anchor_rssis = {}
                    tag_id = int(parsed[2])
                    timestamp_ms = float(parsed[3])
                    temperature_c = float(parsed[4]) if is_finite_number(parsed[4]) else None
                else:
                    continue
            except (TypeError, ValueError):
                continue

            clean_distances = {
                str(anchor_id): float(distance)
                for anchor_id, distance in distances.items()
                if is_finite_number(distance)
            }
            clean_rssis = {
                str(anchor_id): float(rssi)
                for anchor_id, rssi in anchor_rssis.items()
                if is_finite_number(rssi)
            }

            records.append(
                Measurement(
                    line_num=line_num,
                    sdr_rssi=sdr_rssi,
                    distances=clean_distances,
                    anchor_rssis=clean_rssis,
                    tag_id=tag_id,
                    timestamp_ms=timestamp_ms,
                    temperature_c=temperature_c,
                )
            )

            if max_records and len(records) >= max_records:
                break

    records.sort(key=lambda record: record.timestamp_ms)
    return records


def rssi_to_weight(rssi: Optional[float]) -> float:
    if rssi is None:
        return 1.0
    # -100 dBm queda bajo pero no nulo; -65 dBm se considera fuerte.
    normalized = float(np.clip((rssi + 100.0) / 35.0, 0.0, 1.0))
    return 0.30 + 1.70 * normalized


def make_position_bounds(
    anchors: dict[str, np.ndarray],
    margin_xy_m: float,
    margin_z_m: float,
) -> tuple[np.ndarray, np.ndarray]:
    coords = np.array(list(anchors.values()), dtype=float)
    lower = coords.min(axis=0)
    upper = coords.max(axis=0)
    lower[:2] -= margin_xy_m
    upper[:2] += margin_xy_m
    lower[2] = 0.0
    upper[2] = upper[2] + margin_z_m
    return lower, upper


def filtered_anchor_data(
    measurement: Measurement,
    anchors: dict[str, np.ndarray],
    min_distance_m: float,
    max_distance_m: float,
    max_anchors: int,
) -> tuple[list[str], np.ndarray, np.ndarray, np.ndarray, Optional[float]]:
    valid: list[tuple[str, float, Optional[float]]] = []
    for anchor_id, distance in measurement.distances.items():
        if anchor_id not in anchors:
            continue
        if not (min_distance_m <= distance <= max_distance_m):
            continue
        valid.append((anchor_id, float(distance), measurement.anchor_rssis.get(anchor_id)))

    if max_anchors > 0 and len(valid) > max_anchors:
        valid.sort(key=lambda item: rssi_to_weight(item[2]), reverse=True)
        valid = valid[:max_anchors]

    valid.sort(key=lambda item: item[0])
    anchor_ids = [item[0] for item in valid]
    anchor_coords = np.array([anchors[anchor_id] for anchor_id in anchor_ids], dtype=float)
    measured_distances = np.array([item[1] for item in valid], dtype=float)
    weights = np.array([rssi_to_weight(item[2]) for item in valid], dtype=float)

    rssi_values = [item[2] for item in valid if item[2] is not None]
    avg_rssi = float(np.mean(rssi_values)) if rssi_values else measurement.sdr_rssi
    return anchor_ids, anchor_coords, measured_distances, weights, avg_rssi


def initial_guess(
    previous_position: Optional[np.ndarray],
    anchor_coords: np.ndarray,
    measured_distances: np.ndarray,
    weights: np.ndarray,
    lower_bounds: np.ndarray,
    upper_bounds: np.ndarray,
    fixed_height: Optional[float] = None,
) -> np.ndarray:
    if previous_position is not None:
        guess = previous_position.astype(float).copy()
    elif len(anchor_coords):
        safe_distances = np.maximum(measured_distances, 0.20)
        guess_weights = weights / safe_distances
        guess = np.average(anchor_coords, axis=0, weights=guess_weights)
    else:
        guess = (lower_bounds + upper_bounds) / 2.0

    if fixed_height is not None:
        guess[2] = fixed_height
    return np.clip(guess, lower_bounds, upper_bounds)


def levenberg_marquardt(
    initial_point: np.ndarray,
    lower_bounds: np.ndarray,
    upper_bounds: np.ndarray,
    residuals_and_jacobian,
    max_iter: int,
) -> Optional[np.ndarray]:
    point = np.clip(initial_point.astype(float), lower_bounds, upper_bounds)
    damping = 1e-2

    for _ in range(max_iter):
        residuals, jacobian = residuals_and_jacobian(point)
        if not np.all(np.isfinite(residuals)) or not np.all(np.isfinite(jacobian)):
            return None

        cost = 0.5 * float(residuals @ residuals)
        normal = jacobian.T @ jacobian
        gradient = jacobian.T @ residuals

        if np.linalg.norm(gradient, ord=np.inf) < 1e-7:
            break

        try:
            step = np.linalg.solve(normal + damping * np.eye(len(point)), -gradient)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(normal + damping * np.eye(len(point)), -gradient, rcond=None)[0]

        if not np.all(np.isfinite(step)):
            return None

        step_norm = float(np.linalg.norm(step))
        if step_norm > 2.0:
            step *= 2.0 / step_norm

        candidate = np.clip(point + step, lower_bounds, upper_bounds)
        candidate_residuals, _ = residuals_and_jacobian(candidate)
        candidate_cost = 0.5 * float(candidate_residuals @ candidate_residuals)

        if candidate_cost < cost:
            if np.linalg.norm(candidate - point) < 1e-5:
                point = candidate
                break
            point = candidate
            damping = max(damping * 0.4, 1e-9)
        else:
            damping = min(damping * 8.0, 1e9)

    return point


def distance_errors(point: np.ndarray, anchor_coords: np.ndarray, measured_distances: np.ndarray) -> np.ndarray:
    return np.linalg.norm(anchor_coords - point, axis=1) - measured_distances


def solve_3d_position(
    anchor_coords: np.ndarray,
    measured_distances: np.ndarray,
    weights: np.ndarray,
    guess: np.ndarray,
    lower_bounds: np.ndarray,
    upper_bounds: np.ndarray,
) -> tuple[Optional[np.ndarray], Optional[float], Optional[float]]:
    sqrt_weights = np.sqrt(weights)

    def residuals_and_jacobian(point: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        delta = point - anchor_coords
        calculated = np.linalg.norm(delta, axis=1)
        safe_calculated = np.maximum(calculated, 1e-9)
        residuals = sqrt_weights * (calculated - measured_distances)
        jacobian = sqrt_weights[:, None] * (delta / safe_calculated[:, None])
        return residuals, jacobian

    position = levenberg_marquardt(
        guess,
        lower_bounds,
        upper_bounds,
        residuals_and_jacobian,
        max_iter=90,
    )
    if position is None:
        return None, None, None

    errors = distance_errors(position, anchor_coords, measured_distances)
    rmse = float(np.sqrt(np.mean(errors**2)))
    max_error = float(np.max(np.abs(errors)))
    return position, rmse, max_error


def solve_xy_with_locked_height(
    anchor_coords: np.ndarray,
    measured_distances: np.ndarray,
    weights: np.ndarray,
    guess: np.ndarray,
    lower_bounds: np.ndarray,
    upper_bounds: np.ndarray,
    fixed_height: float,
) -> tuple[Optional[np.ndarray], Optional[float], Optional[float]]:
    sqrt_weights = np.sqrt(weights)
    xy_guess = np.clip(guess[:2], lower_bounds[:2], upper_bounds[:2])

    def residuals_and_jacobian(xy: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        point = np.array([xy[0], xy[1], fixed_height], dtype=float)
        delta = point - anchor_coords
        calculated = np.linalg.norm(delta, axis=1)
        safe_calculated = np.maximum(calculated, 1e-9)
        residuals = sqrt_weights * (calculated - measured_distances)
        jacobian = sqrt_weights[:, None] * (delta[:, :2] / safe_calculated[:, None])
        return residuals, jacobian

    xy_position = levenberg_marquardt(
        xy_guess,
        lower_bounds[:2],
        upper_bounds[:2],
        residuals_and_jacobian,
        max_iter=80,
    )
    if xy_position is None:
        return None, None, None

    point = np.array([xy_position[0], xy_position[1], fixed_height], dtype=float)
    errors = distance_errors(point, anchor_coords, measured_distances)
    rmse = float(np.sqrt(np.mean(errors**2)))
    max_error = float(np.max(np.abs(errors)))
    return point, rmse, max_error


def quality_score(
    anchor_count: int,
    rmse_m: Optional[float],
    avg_anchor_rssi: Optional[float],
    held: bool = False,
) -> float:
    if held:
        return -1_000_000.0
    rmse_penalty = 30.0 * (rmse_m if rmse_m is not None else 5.0)
    rssi_bonus = 0.35 * ((avg_anchor_rssi if avg_anchor_rssi is not None else -90.0) + 100.0)
    return 12.0 * anchor_count + rssi_bonus - rmse_penalty


def subset_index_options(anchor_count: int, min_subset_size: int) -> list[tuple[int, ...]]:
    indices = tuple(range(anchor_count))
    if anchor_count < min_subset_size:
        return []

    options: list[tuple[int, ...]] = []
    for subset_size in range(anchor_count, min_subset_size - 1, -1):
        options.extend(combinations(indices, subset_size))
    return options


def temporal_jump_penalty(
    position: np.ndarray,
    previous_position: Optional[np.ndarray],
    timestamp_ms: float,
    previous_timestamp_ms: Optional[float],
    max_jump_m: float,
    temporal_weight: float,
) -> float:
    if previous_position is None or previous_timestamp_ms is None or max_jump_m <= 0:
        return 0.0

    jump_m = float(np.linalg.norm(position - previous_position))
    dt_s = max((timestamp_ms - previous_timestamp_ms) / 1000.0, 0.05)
    allowed_jump = max(max_jump_m, max_jump_m * dt_s)
    excess = max(0.0, jump_m - allowed_jump)
    return temporal_weight * excess * excess


def score_candidate(
    candidate_position: np.ndarray,
    used_indices: tuple[int, ...],
    all_anchor_coords: np.ndarray,
    all_distances: np.ndarray,
    rmse_m: float,
    max_error_m: float,
    previous_position: Optional[np.ndarray],
    timestamp_ms: float,
    previous_timestamp_ms: Optional[float],
    max_jump_m: float,
    temporal_weight: float,
    anchor_outlier_m: float,
) -> float:
    all_errors = np.abs(distance_errors(candidate_position, all_anchor_coords, all_distances))
    used_set = set(used_indices)
    excluded_errors = [float(error) for index, error in enumerate(all_errors) if index not in used_set]
    suspicious_excluded = sum(1 for error in excluded_errors if error > anchor_outlier_m)
    dropped_non_outlier = sum(1 for error in excluded_errors if error <= anchor_outlier_m)

    drop_count = len(all_distances) - len(used_indices)
    temporal_penalty = temporal_jump_penalty(
        candidate_position,
        previous_position,
        timestamp_ms,
        previous_timestamp_ms,
        max_jump_m,
        temporal_weight,
    )

    return (
        42.0 * rmse_m
        + 7.0 * max_error_m
        + 4.0 * drop_count
        + 6.0 * dropped_non_outlier
        - 2.0 * suspicious_excluded
        - 1.2 * len(used_indices)
        + temporal_penalty
    )


def solve_best_anchor_subset(
    anchor_ids: list[str],
    anchor_coords: np.ndarray,
    measured_distances: np.ndarray,
    weights: np.ndarray,
    previous_position: Optional[np.ndarray],
    previous_timestamp_ms: Optional[float],
    timestamp_ms: float,
    min_anchors_3d: int,
    default_fixed_height_m: float,
    lower_bounds: np.ndarray,
    upper_bounds: np.ndarray,
    anchor_outlier_m: float,
    max_jump_m: float,
    temporal_weight: float,
) -> Optional[SolveCandidate]:
    min_subset_size = 3
    best: Optional[SolveCandidate] = None

    for used_indices in subset_index_options(len(anchor_ids), min_subset_size):
        subset_anchor_coords = anchor_coords[list(used_indices)]
        subset_distances = measured_distances[list(used_indices)]
        subset_weights = weights[list(used_indices)]

        position = None
        rmse = None
        max_error = None
        mode = ""

        if len(used_indices) >= min_anchors_3d:
            guess = initial_guess(
                previous_position,
                subset_anchor_coords,
                subset_distances,
                subset_weights,
                lower_bounds,
                upper_bounds,
            )
            position, rmse, max_error = solve_3d_position(
                subset_anchor_coords,
                subset_distances,
                subset_weights,
                guess,
                lower_bounds,
                upper_bounds,
            )
            mode = "3d_robust_wls"
        elif len(used_indices) >= 3:
            fixed_height = float(previous_position[2]) if previous_position is not None else default_fixed_height_m
            guess = initial_guess(
                previous_position,
                subset_anchor_coords,
                subset_distances,
                subset_weights,
                lower_bounds,
                upper_bounds,
                fixed_height=fixed_height,
            )
            position, rmse, max_error = solve_xy_with_locked_height(
                subset_anchor_coords,
                subset_distances,
                subset_weights,
                guess,
                lower_bounds,
                upper_bounds,
                fixed_height,
            )
            mode = "xy_robust_height_locked"

        if position is None or rmse is None or max_error is None:
            continue

        score = score_candidate(
            position,
            used_indices,
            anchor_coords,
            measured_distances,
            rmse,
            max_error,
            previous_position,
            timestamp_ms,
            previous_timestamp_ms,
            max_jump_m,
            temporal_weight,
            anchor_outlier_m,
        )
        height_reference = float(previous_position[2]) if previous_position is not None else default_fixed_height_m
        height_excess = max(0.0, abs(float(position[2]) - height_reference) - 0.80)
        score += 5.0 * height_excess * height_excess

        lower_margin = position - lower_bounds
        upper_margin = upper_bounds - position
        near_boundary = np.minimum(lower_margin, upper_margin)
        score += 25.0 * float(np.sum(near_boundary < 0.05))

        candidate = SolveCandidate(
            position=position,
            mode=mode,
            used_indices=tuple(used_indices),
            rmse_m=rmse,
            max_error_m=max_error,
            score=score,
        )

        if best is None or candidate.score < best.score:
            best = candidate

    return best


def estimate_positions(
    measurements: list[Measurement],
    anchors: dict[str, np.ndarray],
    target_tag: Optional[int],
    min_distance_m: float,
    max_distance_m: float,
    min_anchors_3d: int,
    max_anchors: int,
    hold_max_gap_ms: float,
    default_fixed_height_m: float,
    lower_bounds: np.ndarray,
    upper_bounds: np.ndarray,
    anchor_outlier_m: float,
    max_jump_m: float,
    temporal_weight: float,
) -> list[PositionFix]:
    fixes: list[PositionFix] = []
    previous_by_tag: dict[int, np.ndarray] = {}
    previous_time_by_tag: dict[int, float] = {}

    for measurement in measurements:
        if target_tag is not None and measurement.tag_id != target_tag:
            continue

        anchor_ids, anchor_coords, measured_distances, weights, avg_rssi = filtered_anchor_data(
            measurement,
            anchors,
            min_distance_m,
            max_distance_m,
            max_anchors,
        )
        anchor_count = len(measured_distances)
        previous = previous_by_tag.get(measurement.tag_id)
        previous_time = previous_time_by_tag.get(measurement.tag_id)

        position = None
        rmse = None
        max_error = None
        mode = ""
        used_anchor_ids: tuple[str, ...] = ()
        rejected_anchor_ids: tuple[str, ...] = ()

        candidate = solve_best_anchor_subset(
            anchor_ids,
            anchor_coords,
            measured_distances,
            weights,
            previous,
            previous_time,
            measurement.timestamp_ms,
            min_anchors_3d,
            default_fixed_height_m,
            lower_bounds,
            upper_bounds,
            anchor_outlier_m,
            max_jump_m,
            temporal_weight,
        )

        if candidate is not None:
            position = candidate.position
            rmse = candidate.rmse_m
            max_error = candidate.max_error_m
            mode = candidate.mode
            used_anchor_ids = tuple(anchor_ids[index] for index in candidate.used_indices)
            rejected_anchor_ids = tuple(anchor_id for anchor_id in anchor_ids if anchor_id not in set(used_anchor_ids))

            if rejected_anchor_ids:
                mode = f"{mode}_drop_{'-'.join(rejected_anchor_ids)}"

        if position is not None and previous is not None and max_jump_m > 0:
            jump_m = float(np.linalg.norm(position - previous))
            dt_s = max((measurement.timestamp_ms - (previous_time or measurement.timestamp_ms)) / 1000.0, 0.05)
            allowed_jump = max(max_jump_m, max_jump_m * dt_s)
            if jump_m > allowed_jump * 2.5 and anchor_count >= 3:
                # Si ni el selector robusto consigue una solucion temporalmente creible,
                # preferimos mantener la ultima posicion en vez de fabricar un salto falso.
                position = None
                rmse = None
                max_error = None
                mode = ""
                used_anchor_ids = ()
                rejected_anchor_ids = tuple(anchor_ids)

        if position is None and previous is not None:
            gap_ms = measurement.timestamp_ms - previous_time_by_tag.get(measurement.tag_id, measurement.timestamp_ms)
            if hold_max_gap_ms <= 0 or gap_ms <= hold_max_gap_ms:
                position = previous.copy()
                mode = "hold_previous"
                used_anchor_ids = ()
                rejected_anchor_ids = tuple(anchor_ids)
                fixes.append(
                    PositionFix(
                        line_num=measurement.line_num,
                        timestamp_ms=measurement.timestamp_ms,
                        tag_id=measurement.tag_id,
                        position=position,
                        mode=mode,
                        anchor_count=anchor_count,
                        rmse_m=None,
                        max_error_m=None,
                        avg_anchor_rssi=avg_rssi,
                        quality=quality_score(anchor_count, None, avg_rssi, held=True),
                        used_anchor_ids=used_anchor_ids,
                        rejected_anchor_ids=rejected_anchor_ids,
                        held=True,
                    )
                )
            continue

        if position is None:
            continue

        fix = PositionFix(
            line_num=measurement.line_num,
            timestamp_ms=measurement.timestamp_ms,
            tag_id=measurement.tag_id,
            position=position,
            mode=mode,
            anchor_count=anchor_count,
            rmse_m=rmse,
            max_error_m=max_error,
            avg_anchor_rssi=avg_rssi,
            quality=quality_score(len(used_anchor_ids), rmse, avg_rssi),
            used_anchor_ids=used_anchor_ids,
            rejected_anchor_ids=rejected_anchor_ids,
            held=False,
        )
        fixes.append(fix)
        previous_by_tag[measurement.tag_id] = position
        previous_time_by_tag[measurement.tag_id] = measurement.timestamp_ms

    fixes.sort(key=lambda fix: fix.timestamp_ms)
    return fixes


def fuse_fixes_by_time(fixes: list[PositionFix], window_ms: float) -> list[FusedFix]:
    if not fixes:
        return []

    fused: list[FusedFix] = []
    bucket: list[PositionFix] = []
    bucket_start = fixes[0].timestamp_ms

    def flush() -> None:
        if not bucket:
            return
        solved = [fix for fix in bucket if not fix.held]
        candidates = solved if solved else bucket
        best = max(candidates, key=lambda fix: fix.quality)
        fused.append(
            FusedFix(
                timestamp_ms=best.timestamp_ms,
                position=best.position.copy(),
                raw_position=best.position.copy(),
                source_tag=best.tag_id,
                line_num=best.line_num,
                mode=best.mode,
                rmse_m=best.rmse_m,
                quality=best.quality,
                held=best.held,
                z_raw_m=float(best.position[2]),
            )
        )

    for fix in fixes:
        if bucket and fix.timestamp_ms - bucket_start > window_ms:
            flush()
            bucket = []
            bucket_start = fix.timestamp_ms
        bucket.append(fix)

    flush()
    return fused


def smooth_fused_fixes(fixes: list[FusedFix], max_jump_m: float, alpha: float) -> list[FusedFix]:
    if not fixes:
        return []

    alpha = float(np.clip(alpha, 0.0, 1.0))
    raw_positions = [fix.position.copy() for fix in fixes]
    repaired_positions = [position.copy() for position in raw_positions]
    motion_rejected_flags = [False] * len(fixes)

    if max_jump_m > 0 and len(fixes) > 1:
        for index in range(1, len(fixes)):
            prev_position = repaired_positions[index - 1]
            current_position = raw_positions[index]
            dt_prev_s = max((fixes[index].timestamp_ms - fixes[index - 1].timestamp_ms) / 1000.0, 0.05)
            allowed_prev = max(max_jump_m, max_jump_m * dt_prev_s)
            jump_prev = float(np.linalg.norm(current_position - prev_position))

            if jump_prev <= allowed_prev:
                continue

            if index + 1 < len(fixes):
                next_position = raw_positions[index + 1]
                dt_next_s = max((fixes[index + 1].timestamp_ms - fixes[index].timestamp_ms) / 1000.0, 0.05)
                allowed_next = max(max_jump_m, max_jump_m * dt_next_s)
                jump_next = float(np.linalg.norm(current_position - next_position))
                bridge_jump = float(np.linalg.norm(next_position - prev_position))

                if jump_next > allowed_next and bridge_jump <= allowed_prev + allowed_next:
                    repaired_positions[index] = (prev_position + next_position) / 2.0
                    motion_rejected_flags[index] = True
                    continue

            if jump_prev > allowed_prev * 2.0:
                repaired_positions[index] = prev_position.copy()
                motion_rejected_flags[index] = True

    smoothed: list[FusedFix] = []
    current_position: Optional[np.ndarray] = None

    for index, fix in enumerate(fixes):
        raw_position = raw_positions[index]
        repaired_position = repaired_positions[index]
        motion_rejected = motion_rejected_flags[index]

        if current_position is None:
            new_position = repaired_position
            mode = fix.mode
            held = fix.held
        else:
            if motion_rejected:
                new_position = repaired_position
                held = True
                mode = f"{fix.mode}_motion_hold"
            else:
                new_position = alpha * repaired_position + (1.0 - alpha) * current_position
                held = fix.held
                mode = f"{fix.mode}_smooth" if alpha < 1.0 else fix.mode

        smoothed.append(
            FusedFix(
                timestamp_ms=fix.timestamp_ms,
                position=new_position.copy(),
                raw_position=raw_position,
                source_tag=fix.source_tag,
                line_num=fix.line_num,
                mode=mode,
                rmse_m=fix.rmse_m,
                quality=fix.quality,
                held=held,
                motion_rejected=motion_rejected,
                z_raw_m=fix.z_raw_m,
                z_candidates=fix.z_candidates,
                z_mode=fix.z_mode,
            )
        )
        current_position = new_position.copy()

    return smoothed


def weighted_median(values: list[float], weights: list[float]) -> float:
    if not values:
        raise ValueError("weighted_median necesita al menos un valor")

    pairs = sorted(zip(values, weights), key=lambda pair: pair[0])
    total_weight = sum(max(0.0, weight) for _, weight in pairs)
    if total_weight <= 0:
        return float(np.median(np.array(values, dtype=float)))

    cumulative = 0.0
    for value, weight in pairs:
        cumulative += max(0.0, weight)
        if cumulative >= total_weight / 2.0:
            return float(value)
    return float(pairs[-1][0])


def robust_height_candidates(
    xy: np.ndarray,
    measurement: Measurement,
    anchors: dict[str, np.ndarray],
    z_reference: float,
    z_min_m: float,
    z_max_m: float,
    z_prior_scale_m: float,
    impossible_tolerance_m: float,
    min_distance_m: float,
    max_distance_m: float,
) -> tuple[list[float], list[float]]:
    candidates: list[float] = []
    candidate_weights: list[float] = []

    usable_items = []
    for anchor_id, distance in measurement.distances.items():
        if anchor_id not in anchors:
            continue
        if not (min_distance_m <= distance <= max_distance_m):
            continue
        usable_items.append((anchor_id, float(distance), measurement.anchor_rssis.get(anchor_id)))

    if not usable_items:
        return candidates, candidate_weights

    all_anchor_coords = np.array([anchors[anchor_id] for anchor_id, _, _ in usable_items], dtype=float)
    all_distances = np.array([distance for _, distance, _ in usable_items], dtype=float)
    all_weights = np.array([rssi_to_weight(rssi) for _, _, rssi in usable_items], dtype=float)

    for anchor_id, distance, rssi in usable_items:
        anchor = anchors[anchor_id]
        horizontal_sq = float(np.sum((xy - anchor[:2]) ** 2))
        vertical_sq = distance * distance - horizontal_sq
        tolerance_sq = impossible_tolerance_m * impossible_tolerance_m

        if vertical_sq < -tolerance_sq:
            continue

        root = math.sqrt(max(0.0, vertical_sq))
        for z_candidate in (float(anchor[2] + root), float(anchor[2] - root)):
            if not (z_min_m <= z_candidate <= z_max_m):
                continue

            point = np.array([xy[0], xy[1], z_candidate], dtype=float)
            errors = np.linalg.norm(all_anchor_coords - point, axis=1) - all_distances
            weighted_rmse = float(np.sqrt(np.average(errors**2, weights=all_weights)))
            consistency = 1.0 / (1.0 + (weighted_rmse / 0.35) ** 2)
            vertical_leverage = abs(z_candidate - float(anchor[2])) / max(distance, 0.20)
            prior = 1.0 / (1.0 + (abs(z_candidate - z_reference) / max(z_prior_scale_m, 0.05)) ** 2)
            weight = rssi_to_weight(rssi) * max(0.08, vertical_leverage) * consistency * prior

            candidates.append(z_candidate)
            candidate_weights.append(float(weight))

    return candidates, candidate_weights


def apply_robust_z_filter(
    fixes: list[FusedFix],
    measurements_by_line: dict[int, Measurement],
    anchors: dict[str, np.ndarray],
    z_mode: str,
    z_reference_m: float,
    z_min_m: float,
    z_max_m: float,
    z_speed_mps: float,
    z_alpha: float,
    z_prior_scale_m: float,
    impossible_tolerance_m: float,
    min_distance_m: float,
    max_distance_m: float,
) -> list[FusedFix]:
    if not fixes or z_mode == "free":
        return fixes

    z_alpha = float(np.clip(z_alpha, 0.0, 1.0))
    filtered: list[FusedFix] = []
    previous_z: Optional[float] = None
    previous_time: Optional[float] = None

    for fix in fixes:
        raw_z = float(fix.position[2])
        z_candidates = 0
        mode_suffix = z_mode

        if z_mode == "fixed":
            target_z = float(np.clip(z_reference_m, z_min_m, z_max_m))
        else:
            measurement = measurements_by_line.get(fix.line_num)
            if measurement is None:
                candidates: list[float] = []
                weights: list[float] = []
            else:
                reference = previous_z if previous_z is not None else z_reference_m
                candidates, weights = robust_height_candidates(
                    fix.position[:2],
                    measurement,
                    anchors,
                    reference,
                    z_min_m,
                    z_max_m,
                    z_prior_scale_m,
                    impossible_tolerance_m,
                    min_distance_m,
                    max_distance_m,
                )

            z_candidates = len(candidates)
            if candidates:
                target_z = weighted_median(candidates, weights)
            else:
                target_z = float(np.clip(raw_z, z_min_m, z_max_m))
                mode_suffix = "z_fallback_raw"

        if previous_z is None:
            filtered_z = target_z
        else:
            dt_s = max((fix.timestamp_ms - (previous_time or fix.timestamp_ms)) / 1000.0, 0.05)
            max_delta = z_speed_mps * dt_s if z_speed_mps > 0 else float("inf")
            limited_z = previous_z + float(np.clip(target_z - previous_z, -max_delta, max_delta))
            filtered_z = z_alpha * limited_z + (1.0 - z_alpha) * previous_z

        new_position = fix.position.copy()
        new_position[2] = filtered_z
        new_mode = f"{fix.mode}_{mode_suffix}" if mode_suffix not in fix.mode else fix.mode

        filtered.append(
            FusedFix(
                timestamp_ms=fix.timestamp_ms,
                position=new_position,
                raw_position=fix.raw_position.copy(),
                source_tag=fix.source_tag,
                line_num=fix.line_num,
                mode=new_mode,
                rmse_m=fix.rmse_m,
                quality=fix.quality,
                held=fix.held,
                motion_rejected=fix.motion_rejected,
                z_raw_m=raw_z,
                z_candidates=z_candidates,
                z_mode=mode_suffix,
            )
        )
        previous_z = filtered_z
        previous_time = fix.timestamp_ms

    return filtered


def write_positions_csv(path: Path, fixes: list[PositionFix], fused: list[FusedFix]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "kind",
                "timestamp_ms",
                "tag_id",
                "x_m",
                "y_m",
                "z_m",
                "mode",
                "anchor_count",
                "rmse_m",
                "max_error_m",
                "avg_anchor_rssi_dbm",
                "quality",
                "held",
                "motion_rejected",
                "raw_x_m",
                "raw_y_m",
                "raw_z_m",
                "z_candidates",
                "z_mode",
                "used_anchors",
                "rejected_anchors",
                "line_num",
            ]
        )
        for fix in fixes:
            writer.writerow(
                [
                    "tag",
                    f"{fix.timestamp_ms:.3f}",
                    fix.tag_id,
                    f"{fix.position[0]:.6f}",
                    f"{fix.position[1]:.6f}",
                    f"{fix.position[2]:.6f}",
                    fix.mode,
                    fix.anchor_count,
                    "" if fix.rmse_m is None else f"{fix.rmse_m:.6f}",
                    "" if fix.max_error_m is None else f"{fix.max_error_m:.6f}",
                    "" if fix.avg_anchor_rssi is None else f"{fix.avg_anchor_rssi:.3f}",
                    f"{fix.quality:.6f}",
                    int(fix.held),
                    0,
                    f"{fix.position[0]:.6f}",
                    f"{fix.position[1]:.6f}",
                    f"{fix.position[2]:.6f}",
                    "",
                    "",
                    "|".join(fix.used_anchor_ids),
                    "|".join(fix.rejected_anchor_ids),
                    fix.line_num,
                ]
            )
        for fix in fused:
            writer.writerow(
                [
                    "fused",
                    f"{fix.timestamp_ms:.3f}",
                    fix.source_tag,
                    f"{fix.position[0]:.6f}",
                    f"{fix.position[1]:.6f}",
                    f"{fix.position[2]:.6f}",
                    fix.mode,
                    "",
                    "" if fix.rmse_m is None else f"{fix.rmse_m:.6f}",
                    "",
                    "",
                    f"{fix.quality:.6f}",
                    int(fix.held),
                    int(fix.motion_rejected),
                    f"{fix.raw_position[0]:.6f}",
                    f"{fix.raw_position[1]:.6f}",
                    f"{(fix.z_raw_m if fix.z_raw_m is not None else fix.raw_position[2]):.6f}",
                    fix.z_candidates,
                    fix.z_mode,
                    "",
                    "",
                    fix.line_num,
                ]
            )


def set_equal_3d_axes(ax, points: np.ndarray) -> None:
    if points.size == 0:
        return
    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    centers = (mins + maxs) / 2.0
    radius = max(float(np.max(maxs - mins)) / 2.0, 0.5)
    ax.set_xlim(centers[0] - radius, centers[0] + radius)
    ax.set_ylim(centers[1] - radius, centers[1] + radius)
    ax.set_zlim(max(0.0, centers[2] - radius), centers[2] + radius)


def plot_dashboard(
    anchors: dict[str, np.ndarray],
    tag_fixes: list[PositionFix],
    fused_fixes: list[FusedFix],
    log_path: Path,
    output_path: Optional[Path],
    show: bool,
) -> bool:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print(">> Aviso: matplotlib no esta instalado; se omite la representacion grafica.")
        return False

    fig = plt.figure(figsize=(16, 9))
    grid = fig.add_gridspec(2, 2, width_ratios=[1.35, 1.0], height_ratios=[1.0, 1.0])
    ax_xy = fig.add_subplot(grid[:, 0])
    ax_z = fig.add_subplot(grid[0, 1])
    ax_3d = fig.add_subplot(grid[1, 1], projection="3d")

    anchor_points = np.array(list(anchors.values()), dtype=float)
    for anchor_id, coords in anchors.items():
        ax_xy.scatter(coords[0], coords[1], c="#c62828", marker="^", s=135, zorder=5)
        ax_xy.text(coords[0] + 0.10, coords[1] + 0.10, f"A{anchor_id}", color="#8e0000", fontweight="bold")
        ax_3d.scatter(coords[0], coords[1], coords[2], c="#c62828", marker="^", s=80)
        ax_3d.text(coords[0], coords[1], coords[2] + 0.15, f"A{anchor_id}", color="#8e0000")

    by_tag: dict[int, list[PositionFix]] = {}
    for fix in tag_fixes:
        by_tag.setdefault(fix.tag_id, []).append(fix)

    tag_colors = ["#1976d2", "#f57c00", "#388e3c", "#7b1fa2"]
    for index, (tag_id, fixes) in enumerate(sorted(by_tag.items())):
        solved = [fix for fix in fixes if not fix.held]
        if not solved:
            continue
        coords = np.array([fix.position for fix in solved], dtype=float)
        color = tag_colors[index % len(tag_colors)]
        ax_xy.plot(coords[:, 0], coords[:, 1], color=color, alpha=0.22, linewidth=1.0, label=f"Tag {tag_id}")
        ax_xy.scatter(coords[:, 0], coords[:, 1], color=color, alpha=0.22, s=18)

    if fused_fixes:
        fused_coords = np.array([fix.position for fix in fused_fixes], dtype=float)
        fused_times = np.array([fix.timestamp_ms for fix in fused_fixes], dtype=float)
        held_mask = np.array([fix.held for fix in fused_fixes], dtype=bool)

        ax_xy.plot(fused_coords[:, 0], fused_coords[:, 1], color="#263238", linewidth=1.8, alpha=0.75, zorder=3)
        scatter = ax_xy.scatter(
            fused_coords[:, 0],
            fused_coords[:, 1],
            c=fused_times,
            cmap="viridis",
            s=44,
            edgecolor="#101010",
            linewidth=0.4,
            zorder=4,
            label="Trayectoria fusionada",
        )
        if np.any(held_mask):
            ax_xy.scatter(
                fused_coords[held_mask, 0],
                fused_coords[held_mask, 1],
                marker="x",
                c="#d32f2f",
                s=54,
                linewidth=1.5,
                zorder=6,
                label="Ultima posicion mantenida",
            )
        ax_xy.scatter(fused_coords[0, 0], fused_coords[0, 1], c="#2e7d32", marker="s", s=90, edgecolor="black", zorder=7, label="Inicio")
        ax_xy.scatter(fused_coords[-1, 0], fused_coords[-1, 1], c="#d32f2f", marker="X", s=110, edgecolor="black", zorder=7, label="Fin")
        colorbar = fig.colorbar(scatter, ax=ax_xy, fraction=0.030, pad=0.02)
        colorbar.set_label("Timestamp")

        ax_z.plot(fused_times, fused_coords[:, 2], color="#263238", linewidth=1.4, alpha=0.75)
        ax_z.scatter(fused_times, fused_coords[:, 2], c=fused_times, cmap="viridis", s=28, edgecolor="#101010", linewidth=0.3)
        raw_z_values = np.array(
            [fix.z_raw_m if fix.z_raw_m is not None else fix.raw_position[2] for fix in fused_fixes],
            dtype=float,
        )
        if not np.allclose(raw_z_values, fused_coords[:, 2], atol=0.02):
            ax_z.plot(fused_times, raw_z_values, color="#9e9e9e", linewidth=1.0, linestyle="--", alpha=0.65, label="Z cruda")
        for tag_id in sorted({fix.source_tag for fix in fused_fixes}):
            tag_mask = np.array([fix.source_tag == tag_id for fix in fused_fixes], dtype=bool)
            ax_z.scatter(
                fused_times[tag_mask],
                fused_coords[tag_mask, 2],
                s=16,
                label=f"Origen Tag {tag_id}",
                alpha=0.85,
            )

        ax_3d.plot(fused_coords[:, 0], fused_coords[:, 1], fused_coords[:, 2], color="#263238", linewidth=1.2, alpha=0.75)
        ax_3d.scatter(
            fused_coords[:, 0],
            fused_coords[:, 1],
            fused_coords[:, 2],
            c=fused_times,
            cmap="viridis",
            s=24,
            edgecolor="#101010",
            linewidth=0.25,
        )

        all_points = np.vstack([anchor_points, fused_coords])
    else:
        ax_xy.text(0.5, 0.5, "No hay posiciones validas", transform=ax_xy.transAxes, ha="center", va="center")
        all_points = anchor_points

    ax_xy.set_title(f"Plano XY - {log_path.name}")
    ax_xy.set_xlabel("X (m)")
    ax_xy.set_ylabel("Y (m)")
    ax_xy.grid(True, linestyle=":", alpha=0.7)
    ax_xy.set_aspect("equal", adjustable="datalim")
    ax_xy.legend(loc="best")

    ax_z.set_title("Altura estimada")
    ax_z.set_xlabel("Timestamp (ms)")
    ax_z.set_ylabel("Z (m)")
    ax_z.grid(True, linestyle=":", alpha=0.7)
    ax_z.legend(loc="best")

    ax_3d.set_title("Trayectoria 3D")
    ax_3d.set_xlabel("X (m)")
    ax_3d.set_ylabel("Y (m)")
    ax_3d.set_zlabel("Z (m)")
    set_equal_3d_axes(ax_3d, all_points)

    fig.tight_layout()
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=160, bbox_inches="tight")
    if show:
        plt.show()
    else:
        plt.close(fig)
    return True


def parse_target_tag(value: str) -> Optional[int]:
    normalized = value.strip().lower()
    if normalized in {"all", "todos", "0", "*"}:
        return None
    return int(normalized)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Triangula posiciones UWB y genera una representacion grafica.")
    parser.add_argument("--anchors", help="Archivo JSON con coordenadas de anclas. Por defecto usa el ultimo *.json.")
    parser.add_argument("--log", help="Archivo de medidas. Por defecto usa el ultimo *_Rxfile.txt.")
    parser.add_argument("--tag", default="all", help="Tag a procesar: all, 1, 2, ...")
    parser.add_argument("--time-window-ms", type=float, default=DEFAULT_TIME_WINDOW_MS, help="Ventana para fusionar tags.")
    parser.add_argument("--hold-max-gap-ms", type=float, default=DEFAULT_HOLD_MAX_GAP_MS, help="Maximo salto temporal para mantener posicion anterior. 0 = sin limite.")
    parser.add_argument("--fixed-height", type=float, default=DEFAULT_FIXED_HEIGHT_M, help="Altura usada si solo hay 3 anclas y no existe posicion previa.")
    parser.add_argument("--min-distance", type=float, default=DEFAULT_MIN_DISTANCE_M, help="Distancia minima valida en metros.")
    parser.add_argument("--max-distance", type=float, default=DEFAULT_MAX_DISTANCE_M, help="Distancia maxima valida en metros.")
    parser.add_argument("--min-anchors-3d", type=int, default=DEFAULT_MIN_ANCHORS_3D, help="Anclas necesarias para resolver 3D completo.")
    parser.add_argument("--max-anchors", type=int, default=DEFAULT_MAX_ANCHORS, help="Usar solo las N anclas con mejor RSSI. 0 = todas.")
    parser.add_argument("--anchor-outlier", type=float, default=DEFAULT_ANCHOR_OUTLIER_M, help="Error en metros para considerar que una ancla descartada era sospechosa.")
    parser.add_argument("--max-jump", type=float, default=DEFAULT_MAX_JUMP_M, help="Salto maximo entre posiciones fusionadas antes de mantener la anterior. 0 = desactivado.")
    parser.add_argument("--smooth-alpha", type=float, default=DEFAULT_SMOOTH_ALPHA, help="Suavizado de trayectoria fusionada: 1 = sin suavizado, 0 = congelada.")
    parser.add_argument("--temporal-weight", type=float, default=DEFAULT_TEMPORAL_WEIGHT, help="Peso de coherencia temporal al elegir subconjuntos de anclas.")
    parser.add_argument("--z-mode", choices=["robust", "fixed", "free"], default=DEFAULT_Z_MODE, help="Modo de altura: robust calcula Z por anclas, fixed fija Z, free usa la Z 3D libre.")
    parser.add_argument("--z-min", type=float, default=DEFAULT_Z_MIN_M, help="Altura minima plausible en metros para el filtro de Z.")
    parser.add_argument("--z-max", type=float, default=DEFAULT_Z_MAX_M, help="Altura maxima plausible en metros para el filtro de Z.")
    parser.add_argument("--z-speed", type=float, default=DEFAULT_Z_SPEED_MPS, help="Velocidad vertical maxima en m/s. 0 = sin limite.")
    parser.add_argument("--z-alpha", type=float, default=DEFAULT_Z_ALPHA, help="Suavizado de Z robusta: 1 = sin suavizado, 0 = congelada.")
    parser.add_argument("--z-prior-scale", type=float, default=DEFAULT_Z_PRIOR_SCALE_M, help="Tolerancia de la Z robusta frente a la altura anterior/referencia.")
    parser.add_argument("--z-impossible-tolerance", type=float, default=DEFAULT_Z_IMPOSSIBLE_TOLERANCE_M, help="Tolerancia para distancias que no alcanzan horizontalmente el X/Y.")
    parser.add_argument("--max-records", type=int, default=0, help="Limita muestras para pruebas rapidas. 0 = todo el archivo.")
    parser.add_argument("--csv", default="pr_triangulated_positions.csv", help="CSV de salida. Usa '' para no guardar.")
    parser.add_argument("--plot", default="pr_triangulation_dashboard.png", help="PNG de salida. Usa '' para no guardar.")
    parser.add_argument("--no-show", action="store_true", help="No abre la ventana de matplotlib.")
    parser.add_argument("--no-plot", action="store_true", help="No genera la representacion grafica.")
    parser.add_argument("--no-save", action="store_true", help="No guarda ni CSV ni PNG.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent

    anchors_path = resolve_input_path(args.anchors, script_dir, ["anchors.json", "*.json"])
    log_path = resolve_input_path(args.log, script_dir, ["*_Rxfile.txt", "*.txt"])

    if anchors_path is None or not anchors_path.exists():
        print(">> Error: no se encontro archivo de anclas JSON.")
        return 1
    if log_path is None or not log_path.exists():
        print(">> Error: no se encontro archivo de log TXT.")
        return 1

    if args.no_show and not args.no_plot:
        try:
            import matplotlib

            matplotlib.use("Agg")
        except ImportError:
            pass

    target_tag = parse_target_tag(args.tag)
    anchors = load_anchors(anchors_path)
    measurements = parse_log(log_path, max_records=args.max_records)
    measurements_by_line = {measurement.line_num: measurement for measurement in measurements}

    lower_bounds, upper_bounds = make_position_bounds(
        anchors,
        margin_xy_m=DEFAULT_BOUNDS_MARGIN_XY_M,
        margin_z_m=DEFAULT_BOUNDS_MARGIN_Z_M,
    )
    tag_fixes = estimate_positions(
        measurements,
        anchors,
        target_tag=target_tag,
        min_distance_m=args.min_distance,
        max_distance_m=args.max_distance,
        min_anchors_3d=args.min_anchors_3d,
        max_anchors=args.max_anchors,
        hold_max_gap_ms=args.hold_max_gap_ms,
        default_fixed_height_m=args.fixed_height,
        lower_bounds=lower_bounds,
        upper_bounds=upper_bounds,
        anchor_outlier_m=args.anchor_outlier,
        max_jump_m=args.max_jump,
        temporal_weight=args.temporal_weight,
    )
    fused_raw_fixes = fuse_fixes_by_time(tag_fixes, args.time_window_ms)
    fused_fixes = smooth_fused_fixes(fused_raw_fixes, args.max_jump, args.smooth_alpha)
    fused_fixes = apply_robust_z_filter(
        fused_fixes,
        measurements_by_line,
        anchors,
        z_mode=args.z_mode,
        z_reference_m=args.fixed_height,
        z_min_m=args.z_min,
        z_max_m=args.z_max,
        z_speed_mps=args.z_speed,
        z_alpha=args.z_alpha,
        z_prior_scale_m=args.z_prior_scale,
        impossible_tolerance_m=args.z_impossible_tolerance,
        min_distance_m=args.min_distance,
        max_distance_m=args.max_distance,
    )

    if not args.no_save and args.csv:
        csv_path = Path(args.csv)
        if not csv_path.is_absolute():
            csv_path = script_dir / csv_path
        write_positions_csv(csv_path, tag_fixes, fused_fixes)
    else:
        csv_path = None

    if not args.no_save and args.plot:
        plot_path = Path(args.plot)
        if not plot_path.is_absolute():
            plot_path = script_dir / plot_path
    else:
        plot_path = None

    plot_done = False
    if not args.no_plot:
        plot_done = plot_dashboard(anchors, tag_fixes, fused_fixes, log_path, plot_path, show=not args.no_show)

    solved = sum(1 for fix in tag_fixes if not fix.held)
    held = sum(1 for fix in tag_fixes if fix.held)
    robust_drops = sum(1 for fix in tag_fixes if fix.rejected_anchor_ids and not fix.held)
    motion_rejected = sum(1 for fix in fused_fixes if fix.motion_rejected)
    z_filtered = sum(1 for fix in fused_fixes if fix.z_mode)
    z_candidate_total = sum(fix.z_candidates for fix in fused_fixes)
    tag_summary: dict[int, int] = {}
    for fix in fused_fixes:
        tag_summary[fix.source_tag] = tag_summary.get(fix.source_tag, 0) + 1

    print(f">> Anchors: {anchors_path}")
    print(f">> Log: {log_path}")
    print(f">> Medidas leidas: {len(measurements)}")
    print(f">> Posiciones por tag: {len(tag_fixes)} ({solved} resueltas, {held} mantenidas)")
    print(f">> Posiciones fusionadas: {len(fused_fixes)}")
    print(f">> Lecturas con anclas descartadas por robustez: {robust_drops}")
    print(f">> Saltos fusionados rechazados por movimiento: {motion_rejected}")
    print(f">> Modo Z: {args.z_mode} ({z_filtered} puntos filtrados, {z_candidate_total} candidatas de altura)")
    if tag_summary:
        print(">> Origen de posiciones fusionadas: " + ", ".join(f"Tag {tag}: {count}" for tag, count in sorted(tag_summary.items())))
    if csv_path is not None:
        print(f">> CSV guardado en: {csv_path}")
    if plot_path is not None and plot_done:
        print(f">> Grafica guardada en: {plot_path}")

    return 0 if fused_fixes else 2


if __name__ == "__main__":
    raise SystemExit(main())
