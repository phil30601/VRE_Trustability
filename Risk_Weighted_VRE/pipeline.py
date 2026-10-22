"""Cell-disjoint, risk-weighted RF-RFE and ENN experiments.

Risk labels and sample weights are derived from measured *training* NEP only.
The held-out NEP is loaded solely for evaluation, never for prediction.
"""

from __future__ import annotations

import gc
import json
import os
import pickle
import platform
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from pyarrow.parquet import ParquetFile
from sklearn.ensemble import RandomForestRegressor
from sklearn.feature_selection import RFE
from sklearn.preprocessing import RobustScaler


TEST_CELLS = (3, 8, 15, 19, 30, 31, 34, 51)
PAPER_FEATURES = ("Energy", "Capacity", "Voltage-8", "Energy-8", "Power-8")
INDEX_COLUMNS = ("cell_num", "cycle")


@dataclass(frozen=True)
class RiskConfig:
    threshold_v: float = 0.0
    risky_weight: float = 3.0
    unrisky_weight: float = 1.0

    def validate(self) -> None:
        if not np.isfinite(self.threshold_v):
            raise ValueError("Risk threshold must be finite")
        if not (np.isfinite(self.risky_weight) and self.risky_weight > 0):
            raise ValueError("Risky weight must be finite and positive")
        if not (np.isfinite(self.unrisky_weight) and self.unrisky_weight > 0):
            raise ValueError("Unrisky weight must be finite and positive")


@dataclass(frozen=True)
class RFEConfig:
    sample_stride: int = 8
    n_estimators: int = 30
    n_jobs: int = 32
    n_features_to_select: int = 5
    step: int = 15
    random_state: int | None = None  # the released RFE did not set a seed


@dataclass(frozen=True)
class ENNConfig:
    seed: int = 1
    epochs: int = 70
    batch_size: int = 256
    bootstrap_fraction: float = 0.70
    num_models: int = 5
    learning_rate: float = 0.001
    momentum: float = 0.001
    steps_per_execution: int = 64
    device_mode: str = "cpu"


def risk_weights(y_train: np.ndarray, risk: RiskConfig) -> np.ndarray:
    """Return weights in the same order as the measured training labels."""
    risk.validate()
    values = np.asarray(y_train).reshape(-1)
    if not np.isfinite(values).all():
        raise ValueError("Training NEP contains a non-finite value")
    return np.where(
        values < risk.threshold_v, risk.risky_weight, risk.unrisky_weight
    ).astype(np.float32)


def paper_cells(feature_root: Path) -> tuple[list[int], list[int]]:
    manifest_path = Path(feature_root) / "manifest.csv"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing feature manifest: {manifest_path}")
    manifest = pd.read_csv(manifest_path)
    cells = sorted(manifest["cell_num"].astype(int).tolist())
    if cells != list(range(1, 56)):
        raise ValueError("Full run requires exactly the completed cells 1..55")
    return [cell for cell in cells if cell not in TEST_CELLS], list(TEST_CELLS)


def load_selected_features(
    artifact_path: Path,
    feature_root: Path,
    train_cells: list[int],
    test_cells: list[int],
    risk: RiskConfig,
) -> tuple[list[str], Path]:
    """Read a completed weighted RFE selection without fitting another forest."""
    artifact_path = Path(artifact_path).resolve()
    if artifact_path.is_dir():
        rfe_dir = artifact_path / "rf_rfe" if (artifact_path / "rf_rfe").is_dir() else artifact_path
        selected_path = rfe_dir / "selected_features.json"
    else:
        selected_path = artifact_path
        rfe_dir = selected_path.parent
    run_path = rfe_dir / "run.json"
    if not selected_path.is_file() or not run_path.is_file():
        raise FileNotFoundError(
            f"Need selected_features.json and completed run.json in {rfe_dir}"
        )
    selected_data = json.loads(selected_path.read_text(encoding="utf-8"))
    run_data = json.loads(run_path.read_text(encoding="utf-8"))
    selected = selected_data.get("selected_features")
    if (not isinstance(selected, list) or len(selected) != 5
            or any(not isinstance(name, str) for name in selected)
            or len(set(selected)) != 5):
        raise ValueError("Saved RFE selection must contain five unique feature names")
    if run_data.get("status") != "complete":
        raise ValueError("RFE run is not marked complete")
    if run_data.get("risk") != asdict(risk):
        raise ValueError("RFE risk threshold/weights differ from this ENN run")
    if (run_data.get("train_cells") != train_cells
            or run_data.get("test_cells_excluded") != test_cells):
        raise ValueError("RFE train/test cells differ from this ENN run")
    if run_data.get("selected_features") != selected:
        raise ValueError("RFE run.json and selected_features.json disagree")
    manifest = pd.read_csv(Path(feature_root) / "manifest.csv").set_index("cell_num")
    if int(manifest.loc[train_cells, "feature_rows"].sum()) != run_data.get("total_train_rows"):
        raise ValueError("RFE training row count differs from current feature manifest")
    available = all_feature_names(feature_root, train_cells[0])
    if run_data.get("feature_names") != available:
        raise ValueError("RFE feature schema/order differs from current Parquet data")
    return selected, selected_path


def all_feature_names(feature_root: Path, first_cell: int) -> list[str]:
    path = Path(feature_root) / "x" / f"cell_{first_cell:03d}.parquet"
    if not path.is_file():
        raise FileNotFoundError(path)
    names = [
        name
        for name in ParquetFile(path).schema_arrow.names
        if name not in INDEX_COLUMNS
    ]
    if len(names) != 65 or not set(PAPER_FEATURES).issubset(names):
        raise ValueError(f"Expected 65 paper features in {path}; found {names}")
    return names


def _cell_frames(
    feature_root: Path, cell: int, names: list[str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    root = Path(feature_root)
    x_path = root / "x" / f"cell_{cell:03d}.parquet"
    y_path = root / "y" / f"cell_{cell:03d}.parquet"
    if not x_path.is_file() or not y_path.is_file():
        raise FileNotFoundError(f"Missing cell {cell} feature/target partition")
    x = pd.read_parquet(x_path, columns=[*INDEX_COLUMNS, *names])
    y = pd.read_parquet(y_path, columns=[*INDEX_COLUMNS, "NEP"])
    if len(x) != len(y) or not np.array_equal(
        x[list(INDEX_COLUMNS)].to_numpy(), y[list(INDEX_COLUMNS)].to_numpy()
    ):
        raise ValueError(f"Feature/NEP row alignment failed for cell {cell}")
    if not (x["cell_num"] == cell).all():
        raise ValueError(f"Unexpected cell number in {x_path}")
    if not np.isfinite(x[names].to_numpy()).all() or not np.isfinite(y["NEP"]).all():
        raise ValueError(f"Non-finite feature or NEP in cell {cell}")
    return x, y


def load_rfe_sample(
    feature_root: Path,
    train_cells: list[int],
    names: list[str],
    stride: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray], int]:
    """Equivalent to concatenated training x/y followed by global [::stride]."""
    if stride < 1 or not train_cells:
        raise ValueError("RFE requires train cells and stride >= 1")
    xs, ys, cell_ids, cycles, positions = [], [], [], [], []
    offset = 0
    for cell in train_cells:
        x, y = _cell_frames(feature_root, cell, names)
        local = np.arange((-offset) % stride, len(x), stride, dtype=np.int64)
        xs.append(x[names].to_numpy(dtype=np.float32)[local])
        ys.append(y["NEP"].to_numpy(dtype=np.float32)[local])
        cell_ids.append(x["cell_num"].to_numpy(dtype=np.int16)[local])
        cycles.append(x["cycle"].to_numpy(dtype=np.int16)[local])
        positions.append(offset + local)
        offset += len(x)
        print(f"RF-RFE cell {cell:02d}: {len(local):,} / {len(x):,} rows", flush=True)
        del x, y
        gc.collect()
    index = {
        "global_train_row": np.concatenate(positions),
        "cell_num": np.concatenate(cell_ids),
        "cycle": np.concatenate(cycles),
    }
    if not np.array_equal(index["global_train_row"], np.arange(0, offset, stride)):
        raise AssertionError("Global stride sampling lost row alignment")
    return np.concatenate(xs), np.concatenate(ys), index, offset


def load_split(
    feature_root: Path,
    train_cells: list[int],
    test_cells: list[int],
    names: list[str],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, np.ndarray]]:
    """Load a cell-disjoint regression split with explicit feature order."""
    if not train_cells or not test_cells or set(train_cells) & set(test_cells):
        raise ValueError("Train/test cells must be nonempty and disjoint")
    if not names or len(names) != len(set(names)):
        raise ValueError("Feature names must be nonempty and unique")

    def collect(cells: list[int], with_index: bool):
        xs, ys, ids, cycles = [], [], [], []
        for cell in cells:
            x, y = _cell_frames(feature_root, cell, names)
            xs.append(x[names].to_numpy(dtype=np.float32, copy=True))
            ys.append(y["NEP"].to_numpy(dtype=np.float32, copy=True))
            if with_index:
                ids.append(x["cell_num"].to_numpy(dtype=np.int16, copy=True))
                cycles.append(x["cycle"].to_numpy(dtype=np.int16, copy=True))
            del x, y
            gc.collect()
        index = (
            {"cell_num": np.concatenate(ids), "cycle": np.concatenate(cycles)}
            if with_index else {}
        )
        return np.concatenate(xs), np.concatenate(ys), index

    x_train, y_train, _ = collect(train_cells, False)
    x_test, y_test, test_index = collect(test_cells, True)
    return x_train, y_train, x_test, y_test, test_index


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, allow_nan=False), encoding="utf-8")


def _new_dir(path: Path) -> Path:
    path = Path(path).resolve()
    path.mkdir(parents=True, exist_ok=False)
    return path


def run_rfe(
    feature_root: Path,
    train_cells: list[int],
    artifact_dir: Path,
    risk: RiskConfig,
    config: RFEConfig,
) -> list[str]:
    if (not train_cells or config.n_features_to_select != 5 or config.step < 1
            or config.n_estimators < 1 or config.n_jobs == 0):
        raise ValueError("RFE must select five features using positive step/tree count")
    artifact_dir = _new_dir(artifact_dir)
    names = all_feature_names(feature_root, train_cells[0])
    start = time.perf_counter()
    x, y, index, total_train_rows = load_rfe_sample(
        feature_root, train_cells, names, config.sample_stride
    )
    weights = risk_weights(y, risk)
    np.savez_compressed(artifact_dir / "sample_index.npz", **index)
    scaler = RobustScaler()
    x = scaler.fit_transform(x).astype(np.float32, copy=False)
    with (artifact_dir / "scaler.pkl").open("wb") as handle:
        pickle.dump(scaler, handle)
    del scaler
    gc.collect()
    estimator = RandomForestRegressor(
        n_estimators=config.n_estimators,
        n_jobs=config.n_jobs,
        random_state=config.random_state,
    )
    rfe = RFE(
        estimator=estimator,
        n_features_to_select=config.n_features_to_select,
        step=config.step,
        verbose=2,
    )
    rfe.fit(x, y, sample_weight=weights)
    with (artifact_dir / "rfe_model.pkl").open("wb") as handle:
        pickle.dump(rfe, handle)
    support = np.asarray(rfe.support_, dtype=bool)
    selected = [name for name, is_selected in zip(names, support, strict=True) if is_selected]
    final_rf = RandomForestRegressor(
        n_estimators=config.n_estimators,
        n_jobs=config.n_jobs,
        random_state=config.random_state,
    )
    final_rf.fit(x[:, support], y, sample_weight=weights)
    with (artifact_dir / "importance_rf.pkl").open("wb") as handle:
        pickle.dump(final_rf, handle)
    np.savez_compressed(
        artifact_dir / "sample_predictions.npz",
        y_true=y,
        y_pred=final_rf.predict(x[:, support]).astype(np.float32),
        sample_weight=weights,
    )
    ranking = pd.DataFrame(
        {"feature": names, "selected": support, "ranking": rfe.ranking_}
    )
    ranking["selected_importance"] = np.nan
    ranking.loc[support, "selected_importance"] = final_rf.feature_importances_
    ranking.to_csv(artifact_dir / "feature_ranking.csv", index=False)
    _write_json(
        artifact_dir / "selected_features.json",
        {"selected_features": selected,
         "selected_feature_importances": dict(zip(selected, map(float, final_rf.feature_importances_), strict=True))},
    )
    _write_json(
        artifact_dir / "run.json",
        {
            "status": "complete",
            "risk": asdict(risk), "config": asdict(config),
            "train_cells": train_cells,
            "test_cells_excluded": list(TEST_CELLS),
            "total_train_rows": total_train_rows,
            "sampled_rows": len(y),
            "sampled_risky_rows": int((y < risk.threshold_v).sum()),
            "feature_names": names,
            "selected_features": selected,
            "elapsed_seconds": time.perf_counter() - start,
            "scikit_learn": sklearn.__version__,
        },
    )
    return selected


def configure_tensorflow(config: ENNConfig):
    """Choose device before TensorFlow creates its execution context."""
    mode = config.device_mode.strip().lower()
    if mode not in {"cpu", "gpu", "auto"}:
        raise ValueError("device_mode must be cpu, gpu, or auto")
    if mode == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    elif os.environ.get("CUDA_VISIBLE_DEVICES") == "-1":
        raise RuntimeError(
            "CUDA_VISIBLE_DEVICES=-1 is set. Restart the Python process/kernel "
            "without it before selecting GPU."
        )
    random.seed(config.seed)
    np.random.seed(config.seed)
    import tensorflow as tf

    if mode == "cpu":
        try:
            tf.config.set_visible_devices([], "GPU")
        except RuntimeError as exc:
            raise RuntimeError("Restart the Python kernel before switching to CPU") from exc
    visible = tf.config.get_visible_devices("GPU")
    if mode == "gpu" and not visible:
        raise RuntimeError("GPU mode requested but TensorFlow sees no GPU")
    for device in visible:
        try:
            tf.config.experimental.set_memory_growth(device, True)
        except (RuntimeError, ValueError):
            pass
    tf.keras.utils.set_random_seed(config.seed)
    print("TensorFlow", tf.__version__, "device", "/GPU:0" if visible else "/CPU:0")
    return tf


def build_model(tf, feature_count: int, config: ENNConfig):
    """Match the released 5→5→256→256→1 ENN and SGD optimizer."""
    model = tf.keras.Sequential(
        [
            tf.keras.layers.Input(shape=(feature_count,)),
            tf.keras.layers.Dense(5, kernel_initializer="normal",
                                  bias_initializer=tf.keras.initializers.HeNormal(), activation="relu"),
            tf.keras.layers.Dense(256, kernel_initializer="normal",
                                  bias_initializer=tf.keras.initializers.HeNormal(), activation="relu"),
            tf.keras.layers.Dense(256, kernel_initializer="normal",
                                  bias_initializer=tf.keras.initializers.HeNormal()),
            tf.keras.layers.LeakyReLU(negative_slope=0.2),
            tf.keras.layers.Dense(1, activation="linear", dtype="float32"),
        ]
    )
    model.compile(
        loss="mse",
        optimizer=tf.keras.optimizers.SGD(
            learning_rate=config.learning_rate, momentum=config.momentum
        ),
        metrics=["mse", "mape"],
        steps_per_execution=config.steps_per_execution,
    )
    return model


def _error_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    if len(y_true) == 0:
        return {"rows": 0, "rmse_v": None, "mae_v": None, "bias_v": None}
    residual = np.asarray(y_pred, dtype=np.float64) - np.asarray(y_true, dtype=np.float64)
    return {
        "rows": int(len(y_true)),
        "rmse_v": float(np.sqrt(np.mean(residual**2))),
        "mae_v": float(np.mean(np.abs(residual))),
        "bias_v": float(np.mean(residual)),
    }


def evaluate(
    y_true: np.ndarray, y_pred: np.ndarray, cell_num: np.ndarray, risk: RiskConfig
) -> dict:
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    cell_num = np.asarray(cell_num)
    if any(values.ndim != 1 for values in (y_true, y_pred, cell_num)):
        raise ValueError("Evaluation arrays must be one-dimensional")
    if not (len(y_true) == len(y_pred) == len(cell_num)):
        raise ValueError("Evaluation arrays must be row-aligned")
    if not np.isfinite(y_true).all() or not np.isfinite(y_pred).all():
        raise ValueError("Evaluation NEP values must be finite")
    risky = y_true < risk.threshold_v
    missed = risky & (y_pred >= risk.threshold_v)
    risky_count = int(risky.sum())
    per_cell = {}
    for cell in np.unique(cell_num):
        cell_mask = cell_num == cell
        cell_risky = cell_mask & risky
        cell_unrisky = cell_mask & ~risky
        cell_missed = int((missed & cell_mask).sum())
        cell_risky_count = int(cell_risky.sum())
        cell_count = int(cell_mask.sum())
        per_cell[str(int(cell))] = {
            "overall": _error_metrics(y_true[cell_mask], y_pred[cell_mask]),
            "risky": _error_metrics(y_true[cell_risky], y_pred[cell_risky]),
            "unrisky": _error_metrics(y_true[cell_unrisky], y_pred[cell_unrisky]),
            "missed_risk": {
                "count": cell_missed,
                "conditional_denominator_risky_rows": cell_risky_count,
                "conditional_fraction": (
                    cell_missed / cell_risky_count if cell_risky_count else None
                ),
                "full_cell_denominator_rows": cell_count,
                "full_cell_fraction": cell_missed / cell_count if cell_count else None,
            },
        }
    return {
        "overall": _error_metrics(y_true, y_pred),
        "risky": _error_metrics(y_true[risky], y_pred[risky]),
        "unrisky": _error_metrics(y_true[~risky], y_pred[~risky]),
        "missed_risk": {
            "count": int(missed.sum()),
            "conditional_denominator_risky_rows": risky_count,
            "conditional_fraction": float(missed.sum() / risky_count) if risky_count else None,
            "full_test_denominator_rows": int(len(y_true)),
            "full_test_fraction": float(missed.mean()) if len(y_true) else None,
        },
        "per_cell": per_cell,
    }


def compare_baseline(
    baseline_path: Path | None,
    y_test: np.ndarray,
    test_index: dict[str, np.ndarray],
    risk: RiskConfig,
) -> dict | None:
    if baseline_path is None or not Path(baseline_path).is_file():
        return None
    with np.load(baseline_path, allow_pickle=False) as saved:
        required = {"y_true", "y_pred", "cell_num", "cycle"}
        if not required.issubset(saved.files):
            return {"status": "skipped", "reason": "Baseline predictions lack required arrays"}
        same = (
            np.array_equal(saved["y_true"], y_test)
            and np.array_equal(saved["cell_num"], test_index["cell_num"])
            and np.array_equal(saved["cycle"], test_index["cycle"])
        )
        if not same:
            return {"status": "skipped", "reason": "Baseline test values/order differ"}
        y_pred = np.asarray(saved["y_pred"])
    return {"status": "matched", "artifact": str(Path(baseline_path).resolve()),
            "metrics": evaluate(y_test, y_pred, test_index["cell_num"], risk)}


def run_enn(
    tf,
    feature_root: Path,
    train_cells: list[int],
    test_cells: list[int],
    feature_names: list[str],
    artifact_dir: Path,
    risk: RiskConfig,
    config: ENNConfig,
    baseline_path: Path | None = None,
) -> dict:
    if len(feature_names) != 5:
        raise ValueError("The paper ENN expects exactly five input features")
    if config.num_models < 1 or config.epochs < 1 or config.batch_size < 1:
        raise ValueError("ENN models, epochs and batch size must be positive")
    if not 0 < config.bootstrap_fraction <= 1:
        raise ValueError("bootstrap_fraction must be in (0, 1]")
    artifact_dir = _new_dir(artifact_dir)
    start = time.perf_counter()
    tf.keras.utils.set_random_seed(config.seed)
    x_train, y_train, x_test, y_test, test_index = load_split(
        feature_root, train_cells, test_cells, feature_names
    )
    weights = risk_weights(y_train, risk)
    scaler = RobustScaler()
    x_train = scaler.fit_transform(x_train).astype(np.float32, copy=False)
    x_test = scaler.transform(x_test).astype(np.float32, copy=False)
    with (artifact_dir / "scaler.pkl").open("wb") as handle:
        pickle.dump(scaler, handle)
    del scaler
    gc.collect()

    rng = np.random.default_rng(config.seed)
    member_predictions = []
    histories = []
    bootstrap_weight_summaries = []
    device = "/GPU:0" if tf.config.get_visible_devices("GPU") else "/CPU:0"
    for member in range(config.num_models):
        sample_size = int(len(x_train) * config.bootstrap_fraction)
        rows = rng.choice(len(x_train), size=sample_size, replace=True)
        np.save(artifact_dir / f"bootstrap_rows_{member}.npy", rows)
        sampled_weights = weights[rows]
        bootstrap_weight_summaries.append({
            "rows": len(rows),
            "risky_rows": int((y_train[rows] < risk.threshold_v).sum()),
            "weight_sum": float(sampled_weights.sum(dtype=np.float64)),
        })
        model = build_model(tf, len(feature_names), config)
        with tf.device(device):
            history = model.fit(
                x_train[rows], y_train[rows], sample_weight=sampled_weights,
                epochs=config.epochs, batch_size=config.batch_size,
                shuffle=True, verbose=2,
            )
            prediction = model.predict(
                x_test, batch_size=config.batch_size * 4, verbose=0
            ).reshape(-1)
        model.save(artifact_dir / f"model_{member}.keras")
        histories.append(history.history)
        member_predictions.append(prediction)
        del model, history, rows, sampled_weights
        gc.collect()

    stacked = np.stack(member_predictions)
    ensemble = np.mean(stacked, axis=0)
    np.savez_compressed(
        artifact_dir / "predictions.npz",
        y_true=y_test, y_pred=ensemble, member_predictions=stacked,
        cell_num=test_index["cell_num"], cycle=test_index["cycle"],
    )
    metrics = evaluate(y_test, ensemble, test_index["cell_num"], risk)
    baseline = compare_baseline(baseline_path, y_test, test_index, risk)
    result = {
        "status": "complete",
        "risk": asdict(risk), "config": asdict(config),
        "feature_names": feature_names,
        "train_cells": train_cells, "test_cells": test_cells,
        "train_rows": len(y_train), "test_rows": len(y_test),
        "train_risky_rows": int((y_train < risk.threshold_v).sum()),
        "bootstrap_weight_summaries": bootstrap_weight_summaries,
        "device": device,
        "tensorflow": tf.__version__,
        "python": platform.python_version(),
        "metrics": metrics, "baseline": baseline,
        "histories": histories,
        "elapsed_seconds": time.perf_counter() - start,
    }
    _write_json(artifact_dir / "run.json", result)
    return result


def run_experiment(
    tf,
    feature_root: Path,
    run_root: Path,
    train_cells: list[int],
    test_cells: list[int],
    risk: RiskConfig,
    rfe_config: RFEConfig,
    enn_config: ENNConfig,
    baseline_path: Path | None = None,
) -> dict:
    """Run RF-RFE followed by both weighted five-feature ENN branches."""
    if not train_cells or not test_cells or set(train_cells) & set(test_cells):
        raise ValueError("Train/test cells must be nonempty and disjoint")
    run_root = _new_dir(run_root)
    selected = run_rfe(feature_root, train_cells, run_root / "rf_rfe", risk, rfe_config)
    paper = run_enn(
        tf, feature_root, train_cells, test_cells, list(PAPER_FEATURES),
        run_root / "paper_features", risk, enn_config, baseline_path,
    )
    selected_run = run_enn(
        tf, feature_root, train_cells, test_cells, selected,
        run_root / "rfe_features", risk, enn_config, baseline_path,
    )
    summary = {
        "status": "complete", "risk": asdict(risk),
        "rfe_selected_features": selected,
        "paper_feature_metrics": paper["metrics"],
        "rfe_feature_metrics": selected_run["metrics"],
        "baseline": paper["baseline"],
        "feature_root": str(Path(feature_root).resolve()),
        "run_root": str(run_root),
    }
    _write_json(run_root / "summary.json", summary)
    return summary


def run_enn_only(
    tf,
    feature_root: Path,
    run_root: Path,
    train_cells: list[int],
    test_cells: list[int],
    risk: RiskConfig,
    enn_config: ENNConfig,
    baseline_path: Path | None = None,
    selected_features_path: Path | None = None,
) -> dict:
    """Train one weighted ENN, using paper features or a saved RFE selection."""
    if not train_cells or not test_cells or set(train_cells) & set(test_cells):
        raise ValueError("Train/test cells must be nonempty and disjoint")
    if selected_features_path is None:
        features = list(PAPER_FEATURES)
        source = "paper_fixed_five"
        branch = "paper_features"
    else:
        features, selected_path = load_selected_features(
            selected_features_path, feature_root, train_cells, test_cells, risk
        )
        source = str(selected_path)
        branch = "rfe_features"
    run_root = _new_dir(run_root)
    result = run_enn(
        tf, feature_root, train_cells, test_cells, features,
        run_root / branch, risk, enn_config, baseline_path,
    )
    summary = {
        "status": "complete",
        "run_type": "weighted_enn_only",
        "risk": asdict(risk),
        "feature_source": source,
        "feature_names": features,
        "branch": branch,
        "metrics": result["metrics"],
        "baseline": result["baseline"],
        "feature_root": str(Path(feature_root).resolve()),
        "run_root": str(run_root),
    }
    _write_json(run_root / "summary.json", summary)
    return summary
