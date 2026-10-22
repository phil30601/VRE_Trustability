"""TensorFlow 2.20 / ROCm training utilities for the Linux VRE notebooks."""

from __future__ import annotations

import json
import os
import pickle
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import RobustScaler


PAPER_FEATURES = ["Energy", "Capacity", "Voltage-8", "Energy-8", "Power-8"]
PAPER_TEST_CELLS = [3, 8, 15, 19, 30, 31, 34, 51]


@dataclass
class SmokeConfig:
    seed: int = 1
    epochs: int = 1
    batch_size: int = 1024
    bootstrap_fraction: float = 0.70
    num_models: int = 1
    learning_rate: float = 0.001
    momentum: float = 0.001
    steps_per_execution: int = 1
    device_mode: str = "gpu"
    deterministic_ops: bool = False
    max_train_rows: int | None = None


def configure_tensorflow(config: SmokeConfig):
    device_mode = config.device_mode.strip().lower()
    if device_mode not in {"gpu", "cpu", "auto"}:
        raise ValueError(
            "device_mode must be one of 'gpu', 'cpu', or 'auto'; "
            f"got {config.device_mode!r}"
        )
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "1")
    # TensorFlow device visibility must be selected before the runtime creates
    # a GPU context. CUDA_VISIBLE_DEVICES is also honored by ROCm TensorFlow.
    if device_mode == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    random.seed(config.seed)
    np.random.seed(config.seed)
    import tensorflow as tf

    if device_mode == "cpu":
        try:
            tf.config.set_visible_devices([], "GPU")
        except RuntimeError as exc:
            raise RuntimeError(
                "TensorFlow already initialized a GPU context. Restart the "
                "Jupyter Python kernel, set device_mode='cpu', and run the "
                "notebook from the first cell."
            ) from exc
        # Do not enumerate physical GPUs in forced-CPU mode: enumeration can
        # initialize HIP even though TensorFlow will not execute on the GPU.
        physical_gpus = []
    else:
        physical_gpus = tf.config.list_physical_devices("GPU")

    tf.keras.utils.set_random_seed(config.seed)
    if config.deterministic_ops:
        try:
            tf.config.experimental.enable_op_determinism()
        except Exception as exc:  # ROCm may not implement every deterministic kernel.
            print(f"Deterministic-op request was not fully enabled: {exc}")
    visible_gpus = tf.config.get_visible_devices("GPU")
    if device_mode == "gpu" and not visible_gpus:
        raise RuntimeError(
            "device_mode='gpu', but TensorFlow detected no visible GPU. "
            "ROCm/ROCDXG may not be ready; refusing to silently run on CPU."
        )
    for gpu in visible_gpus:
        try:
            tf.config.experimental.set_memory_growth(gpu, True)
        except (RuntimeError, ValueError):
            pass
    execution_device = "/GPU:0" if visible_gpus else "/CPU:0"
    print("TensorFlow:", tf.__version__)
    print("Requested device mode:", device_mode)
    print("Physical GPUs:", physical_gpus)
    print("Visible GPUs:", visible_gpus)
    print("Execution device:", execution_device)
    print("Build:", tf.sysconfig.get_build_info())
    return tf


def _load_cells(feature_root: Path, cells: list[int], feature_names: list[str]):
    x_frames = []
    y_frames = []
    for cell in cells:
        x_path = feature_root / "x" / f"cell_{cell:03d}.parquet"
        y_path = feature_root / "y" / f"cell_{cell:03d}.parquet"
        if not x_path.exists() or not y_path.exists():
            raise FileNotFoundError(f"Missing feature partition for cell {cell}: {x_path} / {y_path}")
        x = pd.read_parquet(x_path, columns=["cell_num", "cycle", *feature_names])
        y = pd.read_parquet(y_path, columns=["cell_num", "cycle", "NEP"])
        if len(x) != len(y):
            raise ValueError(f"Feature/target length mismatch for cell {cell}: {len(x)} vs {len(y)}")
        x_frames.append(x)
        y_frames.append(y)
    x_all = pd.concat(x_frames, ignore_index=True, copy=False)
    y_all = pd.concat(y_frames, ignore_index=True, copy=False)
    index = pd.MultiIndex.from_frame(x_all[["cell_num", "cycle"]])
    x_values = x_all[feature_names].to_numpy(dtype=np.float32, copy=True)
    y_values = y_all["NEP"].to_numpy(dtype=np.float32, copy=True)
    return x_values, y_values, index


def load_cell_split(
    feature_root: Path,
    train_cells: list[int],
    test_cells: list[int],
    feature_names: list[str] | None = None,
):
    """Load an explicit cell-disjoint split for a small pipeline smoke test."""
    feature_root = Path(feature_root).resolve()
    feature_names = PAPER_FEATURES if feature_names is None else feature_names
    train_cells = [int(cell) for cell in train_cells]
    test_cells = [int(cell) for cell in test_cells]
    if not train_cells or not test_cells:
        raise ValueError("Both train_cells and test_cells must be non-empty")
    overlap = sorted(set(train_cells) & set(test_cells))
    if overlap:
        raise ValueError(f"Train/test cell leakage: {overlap}")

    manifest_path = feature_root / "manifest.csv"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Missing {manifest_path}. Run Feature_Engineering_Group_Linux.ipynb first."
        )
    available = set(pd.read_csv(manifest_path)["cell_num"].astype(int))
    requested = set(train_cells) | set(test_cells)
    missing = sorted(requested - available)
    if missing:
        raise ValueError(
            f"Requested smoke-test cells are missing: {missing}. "
            "In Feature_Engineering_Group_Linux.ipynb use "
            "RUN_FULL = False and SMOKE_CELLS = [1, 3]."
        )

    x_train, y_train, train_index = _load_cells(feature_root, train_cells, feature_names)
    x_test, y_test, test_index = _load_cells(feature_root, test_cells, feature_names)
    return x_train, y_train, x_test, y_test, train_index, test_index, train_cells


def load_paper_split(feature_root: Path, feature_names: list[str] | None = None):
    feature_root = Path(feature_root).resolve()
    feature_names = PAPER_FEATURES if feature_names is None else feature_names
    manifest = pd.read_csv(feature_root / "manifest.csv")
    available = manifest["cell_num"].astype(int).tolist()
    missing = sorted(set(range(1, 56)) - set(available))
    if missing:
        raise ValueError(
            "Full paper split needs cells 1..55; "
            f"completed {len(available)}/55, missing {missing}. "
            "Open Feature_Engineering_Group_Linux.ipynb, set RUN_FULL = True, "
            "and rerun the build cell. The resumable builder skips completed cells."
        )
    train_cells = [cell for cell in available if cell not in PAPER_TEST_CELLS]
    return load_cell_split(
        feature_root,
        train_cells=train_cells,
        test_cells=PAPER_TEST_CELLS,
        feature_names=feature_names,
    )


def scale_features(x_train: np.ndarray, x_test: np.ndarray, artifact_dir: Path):
    scaler = RobustScaler()
    x_train = scaler.fit_transform(x_train).astype(np.float32, copy=False)
    x_test = scaler.transform(x_test).astype(np.float32, copy=False)
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    scaler_path = artifact_dir / "scaler.pkl"
    if scaler_path.exists():
        raise FileExistsError(
            f"Run directory already contains {scaler_path.name}: {artifact_dir}. "
            "Rerun the notebook initialization cell to create a new timestamped run."
        )
    with scaler_path.open("wb") as handle:
        pickle.dump(scaler, handle)
    return x_train, x_test, scaler


def build_model(tf, input_dim: int, config: SmokeConfig):
    model = tf.keras.Sequential(
        [
            tf.keras.layers.Input(shape=(input_dim,)),
            tf.keras.layers.Dense(
                5,
                kernel_initializer="normal",
                bias_initializer=tf.keras.initializers.HeNormal(),
                activation="relu",
            ),
            tf.keras.layers.Dense(
                256,
                kernel_initializer="normal",
                bias_initializer=tf.keras.initializers.HeNormal(),
                activation="relu",
            ),
            tf.keras.layers.Dense(
                256,
                kernel_initializer="normal",
                bias_initializer=tf.keras.initializers.HeNormal(),
            ),
            tf.keras.layers.LeakyReLU(negative_slope=0.2),
            tf.keras.layers.Dense(1, activation="linear", dtype="float32"),
        ]
    )
    optimizer = tf.keras.optimizers.SGD(
        learning_rate=config.learning_rate,
        momentum=config.momentum,
    )
    # Match Model_Performance_3_10.ipynb. These reporting metrics do not
    # influence the MSE optimization, but MAPE is retained for parity.
    if config.steps_per_execution < 1:
        raise ValueError("steps_per_execution must be at least 1")
    model.compile(
        loss="mse",
        optimizer=optimizer,
        metrics=["mse", "mape"],
        steps_per_execution=config.steps_per_execution,
    )
    return model


def train_smoke(
    tf,
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_test: np.ndarray,
    y_test: np.ndarray,
    test_index: pd.MultiIndex,
    artifact_dir: Path,
    config: SmokeConfig,
):
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    protected_outputs = [
        artifact_dir / "run.json",
        artifact_dir / "predictions.npz",
        *artifact_dir.glob("bootstrap_rows_*.npy"),
        *artifact_dir.glob("model_*.keras"),
    ]
    existing_outputs = [path.name for path in protected_outputs if path.exists()]
    if existing_outputs:
        raise FileExistsError(
            f"Refusing to overwrite existing run outputs in {artifact_dir}: "
            f"{sorted(existing_outputs)}. Rerun the notebook initialization cell "
            "to create a new timestamped run."
        )
    run_started_at = datetime.now()
    rng = np.random.default_rng(config.seed)
    if config.max_train_rows is not None:
        limit = min(config.max_train_rows, len(x_train))
        x_train = x_train[:limit]
        y_train = y_train[:limit]
    predictions = []
    histories = []
    for member in range(config.num_models):
        sample_size = int(len(x_train) * config.bootstrap_fraction)
        rows = rng.choice(len(x_train), size=sample_size, replace=True)
        np.save(artifact_dir / f"bootstrap_rows_{member}.npy", rows)
        model = build_model(tf, x_train.shape[1], config)
        execution_device = "/GPU:0" if tf.config.get_visible_devices("GPU") else "/CPU:0"
        with tf.device(execution_device):
            history = model.fit(
                x_train[rows],
                y_train[rows],
                epochs=config.epochs,
                batch_size=config.batch_size,
                shuffle=True,
                verbose=2,
            )
            prediction = model.predict(x_test, batch_size=config.batch_size * 4, verbose=1).reshape(-1)
        model.save(artifact_dir / f"model_{member}.keras")
        histories.append(history.history)
        predictions.append(prediction)
    ensemble_prediction = np.mean(np.stack(predictions), axis=0)
    rmse = float(np.sqrt(mean_squared_error(y_test, ensemble_prediction)))
    mae = float(mean_absolute_error(y_test, ensemble_prediction))
    correlation = float(pearsonr(y_test, ensemble_prediction).statistic)
    r_squared = float(r2_score(y_test, ensemble_prediction))
    bias = float(np.mean(ensemble_prediction - y_test))
    metrics = {
        "rmse_v": rmse,
        "mae_v": mae,
        "bias_v": bias,
        "pearson_r": correlation,
        "r2": r_squared,
    }

    per_cell = {}
    cell_values = test_index.get_level_values("cell_num").to_numpy()
    for cell in sorted(np.unique(cell_values)):
        mask = cell_values == cell
        per_cell[str(cell)] = {
            "rows": int(mask.sum()),
            "rmse_v": float(np.sqrt(mean_squared_error(y_test[mask], ensemble_prediction[mask]))),
            "mae_v": float(mean_absolute_error(y_test[mask], ensemble_prediction[mask])),
        }
    np.savez_compressed(
        artifact_dir / "predictions.npz",
        y_true=y_test,
        y_pred=ensemble_prediction,
        member_predictions=np.stack(predictions),
        cell_num=cell_values,
        cycle=test_index.get_level_values("cycle").to_numpy(),
    )
    (artifact_dir / "run.json").write_text(
        json.dumps(
            {
                "run_started_at_utc": run_started_at.isoformat(),
                "run_finished_at_utc": datetime.now().isoformat(),
                "artifact_dir": str(artifact_dir.resolve()),
                "config": asdict(config),
                "metrics": metrics,
                "per_cell": per_cell,
                "tensorflow": tf.__version__,
                "physical_gpus": (
                    []
                    if config.device_mode.strip().lower() == "cpu"
                    else [str(gpu) for gpu in tf.config.list_physical_devices("GPU")]
                ),
                "visible_gpus": [str(gpu) for gpu in tf.config.get_visible_devices("GPU")],
                "execution_device": (
                    "/GPU:0" if tf.config.get_visible_devices("GPU") else "/CPU:0"
                ),
                "histories": histories,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return metrics, per_cell, ensemble_prediction
