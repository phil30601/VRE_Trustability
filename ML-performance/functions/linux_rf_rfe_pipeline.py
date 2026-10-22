"""Linux-compatible reproduction of the released RF-RFE feature selection.

The estimator and selection configuration intentionally match cells 9--13 of
``Model_Performance_3_10.ipynb``.  The only structural change is input I/O:
Parquet partitions are read one cell at a time and the global ``[::8]`` sample
is retained, avoiding construction of the complete 7.7M x 65 feature frame.
"""

from __future__ import annotations

import gc
import hashlib
import json
import os
import pickle
import platform
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import sklearn
from pyarrow.parquet import ParquetFile
from sklearn.ensemble import RandomForestRegressor
from sklearn.feature_selection import RFE
from sklearn.preprocessing import RobustScaler


PAPER_TEST_CELLS = [3, 8, 15, 19, 30, 31, 34, 51]
INDEX_COLUMNS = ["cell_num", "cycle"]
RELEASED_NOTEBOOK_TRAIN_ROWS = 7_523_137


@dataclass(frozen=True)
class RFRFEConfig:
    """Parameters copied from the released RF-RFE notebook cells."""

    sample_stride: int = 8
    n_estimators: int = 30
    n_jobs: int = 32
    n_features_to_select: int = 5
    step: int = 15
    rfe_verbose: int = 2
    importance_verbose: int = 2
    random_state: int | None = None


def _validate_config(config: RFRFEConfig) -> None:
    if config.sample_stride < 1:
        raise ValueError("sample_stride must be at least 1")
    if config.n_estimators < 1:
        raise ValueError("n_estimators must be at least 1")
    if config.n_jobs == 0:
        raise ValueError("n_jobs cannot be zero")
    if config.n_features_to_select < 1:
        raise ValueError("n_features_to_select must be at least 1")
    if config.step < 1:
        raise ValueError("step must be at least 1")


def _load_manifest(feature_root: Path) -> tuple[pd.DataFrame, list[int]]:
    feature_root = Path(feature_root).resolve()
    manifest_path = feature_root / "manifest.csv"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Missing {manifest_path}. Run Feature_Engineering_Group_Linux.ipynb first."
        )
    manifest = pd.read_csv(manifest_path).sort_values("cell_num").reset_index(drop=True)
    available = manifest["cell_num"].astype(int).tolist()
    missing = sorted(set(range(1, 56)) - set(available))
    if missing:
        raise ValueError(
            "Paper RF-RFE needs all cells 1..55 before applying the fixed test split; "
            f"missing {missing}."
        )
    train_cells = [cell for cell in available if cell not in PAPER_TEST_CELLS]
    return manifest, train_cells


def _feature_names(feature_root: Path, first_cell: int) -> list[str]:
    x_path = feature_root / "x" / f"cell_{first_cell:03d}.parquet"
    if not x_path.is_file():
        raise FileNotFoundError(f"Missing feature partition: {x_path}")
    columns = ParquetFile(x_path).schema_arrow.names
    feature_names = [column for column in columns if column not in INDEX_COLUMNS]
    if len(feature_names) != 65:
        raise ValueError(
            f"Expected the released 65-feature matrix, found {len(feature_names)} "
            f"columns in {x_path}: {feature_names}"
        )
    return feature_names


def describe_plan(feature_root: Path, config: RFRFEConfig) -> dict[str, Any]:
    """Return row counts and matrix-size estimates without loading feature values."""
    _validate_config(config)
    feature_root = Path(feature_root).resolve()
    manifest, train_cells = _load_manifest(feature_root)
    feature_names = _feature_names(feature_root, train_cells[0])
    row_map = manifest.set_index("cell_num")["feature_rows"].astype(int)
    train_rows = int(row_map.loc[train_cells].sum())
    sampled_rows = (train_rows + config.sample_stride - 1) // config.sample_stride
    released_sampled_rows = (
        RELEASED_NOTEBOOK_TRAIN_ROWS + config.sample_stride - 1
    ) // config.sample_stride
    matrix_bytes = sampled_rows * len(feature_names) * np.dtype(np.float32).itemsize
    return {
        "feature_root": str(feature_root),
        "train_cells": train_cells,
        "test_cells_excluded": PAPER_TEST_CELLS,
        "train_rows": train_rows,
        "released_notebook_train_rows": RELEASED_NOTEBOOK_TRAIN_ROWS,
        "train_row_delta_from_released_notebook": (
            train_rows - RELEASED_NOTEBOOK_TRAIN_ROWS
        ),
        "sample_stride": config.sample_stride,
        "sampled_rows": sampled_rows,
        "released_notebook_sampled_rows": released_sampled_rows,
        "sampled_row_delta_from_released_notebook": (
            sampled_rows - released_sampled_rows
        ),
        "features": len(feature_names),
        "one_float32_matrix_mib": matrix_bytes / 1024**2,
        "rfe_feature_counts": _rfe_feature_counts(
            len(feature_names), config.n_features_to_select, config.step
        ),
    }


def _rfe_feature_counts(total: int, selected: int, step: int) -> list[int]:
    counts = []
    current = total
    while current > selected:
        counts.append(current)
        current = max(selected, current - step)
    counts.append(selected)
    return counts


def load_global_stride_sample(
    feature_root: Path,
    config: RFRFEConfig,
) -> tuple[np.ndarray, np.ndarray, pd.DataFrame, list[str], list[int], int]:
    """Load the exact global training-row ``[::sample_stride]`` selection.

    Sampling does not restart at cell boundaries.  For the ordered concatenated
    training set this is equivalent to the released ``xTrain.iloc[::8]`` and
    ``yTrain.iloc[::8]`` operations.
    """
    _validate_config(config)
    feature_root = Path(feature_root).resolve()
    manifest, train_cells = _load_manifest(feature_root)
    feature_names = _feature_names(feature_root, train_cells[0])
    manifest_rows = manifest.set_index("cell_num")["feature_rows"].astype(int)

    x_parts: list[np.ndarray] = []
    y_parts: list[np.ndarray] = []
    cell_parts: list[np.ndarray] = []
    cycle_parts: list[np.ndarray] = []
    global_row_parts: list[np.ndarray] = []
    global_offset = 0

    for number, cell in enumerate(train_cells, start=1):
        x_path = feature_root / "x" / f"cell_{cell:03d}.parquet"
        y_path = feature_root / "y" / f"cell_{cell:03d}.parquet"
        if not x_path.is_file() or not y_path.is_file():
            raise FileNotFoundError(
                f"Missing cell {cell} partition: {x_path} / {y_path}"
            )

        x_cell = pd.read_parquet(x_path, columns=[*INDEX_COLUMNS, *feature_names])
        y_cell = pd.read_parquet(y_path, columns=[*INDEX_COLUMNS, "NEP"])
        if len(x_cell) != len(y_cell):
            raise ValueError(
                f"Feature/target length mismatch for cell {cell}: "
                f"{len(x_cell):,} vs {len(y_cell):,}"
            )
        expected_rows = int(manifest_rows.loc[cell])
        if len(x_cell) != expected_rows:
            raise ValueError(
                f"Manifest/partition row mismatch for cell {cell}: "
                f"{expected_rows:,} vs {len(x_cell):,}"
            )
        if not np.array_equal(
            x_cell[INDEX_COLUMNS].to_numpy(), y_cell[INDEX_COLUMNS].to_numpy()
        ):
            raise ValueError(f"Feature/target index mismatch for cell {cell}")

        first_local = (-global_offset) % config.sample_stride
        positions = np.arange(
            first_local,
            len(x_cell),
            config.sample_stride,
            dtype=np.int64,
        )
        x_values = x_cell[feature_names].to_numpy(dtype=np.float32, copy=False)
        y_values = y_cell["NEP"].to_numpy(dtype=np.float32, copy=False)
        x_parts.append(x_values[positions].copy())
        y_parts.append(y_values[positions].copy())
        cell_parts.append(
            x_cell["cell_num"].to_numpy(dtype=np.int16, copy=False)[positions].copy()
        )
        cycle_parts.append(
            x_cell["cycle"].to_numpy(dtype=np.int16, copy=False)[positions].copy()
        )
        global_row_parts.append(global_offset + positions)

        global_offset += len(x_cell)
        print(
            f"Loaded train cell {cell:02d} ({number:02d}/{len(train_cells)}): "
            f"{len(x_cell):,} rows -> {len(positions):,} sampled; "
            f"global rows {global_offset:,}",
            flush=True,
        )
        del x_cell, y_cell, x_values, y_values, positions
        gc.collect()

    x_sample = np.concatenate(x_parts, axis=0)
    y_sample = np.concatenate(y_parts, axis=0)
    sample_index = pd.DataFrame(
        {
            "global_train_row": np.concatenate(global_row_parts),
            "cell_num": np.concatenate(cell_parts),
            "cycle": np.concatenate(cycle_parts),
        }
    )
    expected_sample_rows = (
        global_offset + config.sample_stride - 1
    ) // config.sample_stride
    if len(x_sample) != expected_sample_rows:
        raise AssertionError(
            f"Global stride produced {len(x_sample):,} rows; "
            f"expected {expected_sample_rows:,}"
        )
    expected_global_rows = np.arange(
        0, global_offset, config.sample_stride, dtype=np.int64
    )
    if not np.array_equal(
        sample_index["global_train_row"].to_numpy(), expected_global_rows
    ):
        raise AssertionError("Streaming sample does not match global [::stride] positions")
    return (
        x_sample,
        y_sample,
        sample_index,
        feature_names,
        train_cells,
        global_offset,
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


def _write_status(
    artifact_dir: Path,
    stage: str,
    started_at: datetime,
    config: RFRFEConfig,
    **details: Any,
) -> None:
    _write_json(
        artifact_dir / "run_status.json",
        {
            "status": "running" if stage != "complete" else "complete",
            "stage": stage,
            "run_started_at_utc": started_at.isoformat(),
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "artifact_dir": str(artifact_dir.resolve()),
            "config": asdict(config),
            **details,
        },
    )


def run_paper_rf_rfe(
    feature_root: Path,
    artifact_dir: Path,
    config: RFRFEConfig | None = None,
) -> dict[str, Any]:
    """Execute and save the released RF-RFE computation."""
    config = RFRFEConfig() if config is None else config
    _validate_config(config)
    feature_root = Path(feature_root).resolve()
    artifact_dir = Path(artifact_dir).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(path.name for path in artifact_dir.iterdir())
    if existing:
        raise FileExistsError(
            f"Refusing to overwrite non-empty RF-RFE run directory {artifact_dir}: "
            f"{existing}. Rerun the notebook initialization cell for a new timestamp."
        )

    run_started = datetime.now(timezone.utc)
    overall_start = time.perf_counter()
    durations: dict[str, float] = {}
    _write_status(artifact_dir, "loading_sample", run_started, config)

    stage_start = time.perf_counter()
    (
        x_sample,
        y_sample,
        sample_index,
        feature_names,
        train_cells,
        train_rows,
    ) = load_global_stride_sample(feature_root, config)
    durations["load_sample_seconds"] = time.perf_counter() - stage_start
    sample_hashes = {
        "x_sample_sha256": hashlib.sha256(x_sample).hexdigest(),
        "y_sample_sha256": hashlib.sha256(y_sample).hexdigest(),
    }
    np.savez_compressed(
        artifact_dir / "sample_index.npz",
        global_train_row=sample_index["global_train_row"].to_numpy(dtype=np.int64),
        cell_num=sample_index["cell_num"].to_numpy(dtype=np.int16),
        cycle=sample_index["cycle"].to_numpy(dtype=np.int16),
    )
    del sample_index
    gc.collect()

    _write_status(
        artifact_dir,
        "scaling",
        run_started,
        config,
        train_rows=train_rows,
        sampled_rows=len(x_sample),
        feature_count=len(feature_names),
    )
    stage_start = time.perf_counter()
    scaler = RobustScaler()
    x_scaled = scaler.fit_transform(x_sample).astype(np.float32, copy=False)
    durations["scale_seconds"] = time.perf_counter() - stage_start
    with (artifact_dir / "scaler.pkl").open("wb") as handle:
        pickle.dump(scaler, handle)
    del scaler, x_sample
    gc.collect()

    _write_status(
        artifact_dir,
        "rf_rfe",
        run_started,
        config,
        train_rows=train_rows,
        sampled_rows=len(x_scaled),
        feature_count=len(feature_names),
        rfe_feature_counts=_rfe_feature_counts(
            len(feature_names), config.n_features_to_select, config.step
        ),
    )
    stage_start = time.perf_counter()
    rfr = RandomForestRegressor(
        n_estimators=config.n_estimators,
        n_jobs=config.n_jobs,
        random_state=config.random_state,
    )
    rfe = RFE(
        estimator=rfr,
        n_features_to_select=config.n_features_to_select,
        step=config.step,
        verbose=config.rfe_verbose,
    )
    rfe.fit(x_scaled, y_sample)
    durations["rfe_seconds"] = time.perf_counter() - stage_start
    support = np.asarray(rfe.support_, dtype=bool)
    ranking = np.asarray(rfe.ranking_, dtype=np.int16)
    selected_features = [
        feature for feature, selected in zip(feature_names, support, strict=True) if selected
    ]
    rfe_final_importance = np.asarray(
        rfe.estimator_.feature_importances_, dtype=np.float64
    )

    _write_status(
        artifact_dir,
        "selected_feature_importance",
        run_started,
        config,
        selected_features=selected_features,
    )
    stage_start = time.perf_counter()
    forest_regr = RandomForestRegressor(
        n_estimators=config.n_estimators,
        n_jobs=config.n_jobs,
        verbose=config.importance_verbose,
        random_state=config.random_state,
    )
    forest_regr.fit(x_scaled[:, support], y_sample)
    selected_importance = np.asarray(
        forest_regr.feature_importances_, dtype=np.float64
    )
    durations["selected_feature_importance_seconds"] = (
        time.perf_counter() - stage_start
    )

    ranking_frame = pd.DataFrame(
        {
            "feature": feature_names,
            "selected": support,
            "ranking": ranking,
            "selected_importance": np.nan,
            "rfe_final_estimator_importance": np.nan,
        }
    )
    ranking_frame.loc[support, "selected_importance"] = selected_importance
    ranking_frame.loc[support, "rfe_final_estimator_importance"] = rfe_final_importance
    ranking_frame.to_csv(artifact_dir / "feature_ranking.csv", index=False)

    durations["total_seconds"] = time.perf_counter() - overall_start
    finished_at = datetime.now(timezone.utc)
    result: dict[str, Any] = {
        "run_started_at_utc": run_started.isoformat(),
        "run_finished_at_utc": finished_at.isoformat(),
        "artifact_dir": str(artifact_dir),
        "feature_root": str(feature_root),
        "config": asdict(config),
        "paper_test_cells_excluded": PAPER_TEST_CELLS,
        "train_cells": train_cells,
        "train_rows_before_stride": train_rows,
        "released_notebook_train_rows": RELEASED_NOTEBOOK_TRAIN_ROWS,
        "train_row_delta_from_released_notebook": (
            train_rows - RELEASED_NOTEBOOK_TRAIN_ROWS
        ),
        "sampled_rows": int(len(x_scaled)),
        "released_notebook_sampled_rows": (
            RELEASED_NOTEBOOK_TRAIN_ROWS + config.sample_stride - 1
        ) // config.sample_stride,
        "sample_hashes": sample_hashes,
        "feature_count": len(feature_names),
        "feature_names": feature_names,
        "rfe_feature_counts": _rfe_feature_counts(
            len(feature_names), config.n_features_to_select, config.step
        ),
        "selected_features": selected_features,
        "selected_feature_importances": {
            feature: float(importance)
            for feature, importance in zip(
                selected_features, selected_importance, strict=True
            )
        },
        "rfe_final_estimator_importances": {
            feature: float(importance)
            for feature, importance in zip(
                selected_features, rfe_final_importance, strict=True
            )
        },
        "durations": durations,
        "software": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "hardware": {
            "logical_cpus": os.cpu_count(),
            "gpu_used": False,
        },
    }
    _write_json(
        artifact_dir / "selected_features.json",
        {
            "selected_features": selected_features,
            "selected_feature_importances": result["selected_feature_importances"],
            "rfe_final_estimator_importances": result[
                "rfe_final_estimator_importances"
            ],
        },
    )
    _write_json(artifact_dir / "run.json", result)
    _write_status(
        artifact_dir,
        "complete",
        run_started,
        config,
        run_finished_at_utc=finished_at.isoformat(),
        selected_features=selected_features,
        durations=durations,
    )
    return result
