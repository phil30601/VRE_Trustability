"""Run the measured-NEP risk-weighted RF-RFE + two ENN experiments.

Examples:
    python cli.py --mode smoke
    python cli.py --mode full --device cpu
    python cli.py --mode full --device gpu
"""

from __future__ import annotations

import argparse
import json
import pickle
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from pipeline import (
    ENNConfig,
    RFEConfig,
    RiskConfig,
    TEST_CELLS,
    all_feature_names,
    configure_tensorflow,
    load_rfe_sample,
    load_split,
    paper_cells,
    risk_weights,
    run_enn_only,
    run_experiment,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FEATURE_ROOT = WORKSPACE_ROOT / "data/processed/features_linux_v1"
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "runs"
DEFAULT_BASELINE = (
    WORKSPACE_ROOT / "artifacts/rocm_tf220_paper_reproduction/Full/predictions.npz"
)
BASE_FEATURES = (
    "Voltage", "Current", "Throughput", "Energy", "Capacity", "Time",
    "Overpotential", "dQ_dV", "dVoltage/dt", "dEnergy/dt",
    "dCapacity/dt", "dOverpotential/dt", "Power",
)
SYNTHETIC_FEATURES = [
    *BASE_FEATURES,
    *(f"{feature}-{lag}" for lag in (8, 6, 4, 2) for feature in BASE_FEATURES),
]


def create_synthetic_features(root: Path, rows_per_cell: int = 40) -> None:
    """Small 55-cell fixture; its values are artificial, never paper data."""
    (root / "x").mkdir(parents=True)
    (root / "y").mkdir()
    rng = np.random.default_rng(109)
    manifest = []
    for cell in range(1, 56):
        cycle = np.arange(rows_per_cell, dtype=np.int16)
        values = rng.normal(0, 1, size=(rows_per_cell, len(SYNTHETIC_FEATURES)))
        values = values.astype(np.float32)
        nep = (
            0.06 * values[:, SYNTHETIC_FEATURES.index("Energy")]
            + 0.04 * values[:, SYNTHETIC_FEATURES.index("Capacity")]
            - 0.01
            + cell * 0.0001
        ).astype(np.float32)
        x = pd.DataFrame(values, columns=SYNTHETIC_FEATURES)
        x.insert(0, "cycle", cycle)
        x.insert(0, "cell_num", np.full(rows_per_cell, cell, dtype=np.int16))
        y = pd.DataFrame({
            "cell_num": np.full(rows_per_cell, cell, dtype=np.int16),
            "cycle": cycle,
            "NEP": nep,
        })
        x.to_parquet(root / "x" / f"cell_{cell:03d}.parquet", index=False)
        y.to_parquet(root / "y" / f"cell_{cell:03d}.parquet", index=False)
        manifest.append({"cell_num": cell, "feature_rows": rows_per_cell})
    pd.DataFrame(manifest).to_csv(root / "manifest.csv", index=False)


def check_synthetic_alignment(
    feature_root: Path, risk: RiskConfig, *, include_rfe_sample: bool = True
) -> None:
    """Assert cell separation, NEP weights, and optional RF-RFE stride."""
    train_cells, test_cells = paper_cells(feature_root)
    names = all_feature_names(feature_root, train_cells[0])
    total = 47 * 40
    if include_rfe_sample:
        x, y, index, sampled_total = load_rfe_sample(
            feature_root, train_cells, names, 8
        )
        if sampled_total != total or len(y) != (total + 7) // 8:
            raise AssertionError("Unexpected synthetic train/sample size")
        if not np.array_equal(index["global_train_row"], np.arange(total)[::8]):
            raise AssertionError("Global sample positions differ from [::8]")
        if set(index["cell_num"]) & set(test_cells):
            raise AssertionError("Test cell entered RF-RFE sample")
        expected = np.where(
            y < risk.threshold_v, risk.risky_weight, risk.unrisky_weight
        ).astype(np.float32)
        if not np.array_equal(risk_weights(y, risk), expected):
            raise AssertionError("Sampled NEP-to-weight alignment failed")
        if (x.shape[1] != 65 or not (expected == risk.risky_weight).any()
                or not (expected == risk.unrisky_weight).any()):
            raise AssertionError("Synthetic sample lacks valid features/risk classes")
    x_train, y_train, x_test, y_test, test_index = load_split(
        feature_root, train_cells, test_cells, names[:5]
    )
    if len(x_train) != total or len(x_test) != 8 * 40:
        raise AssertionError("Train/test row counts changed")
    if not set(np.unique(test_index["cell_num"])) == set(TEST_CELLS):
        raise AssertionError("Test cells changed")
    weights = risk_weights(y_train, risk)
    if not (weights == risk.risky_weight).any() or not (weights == risk.unrisky_weight).any():
        raise AssertionError("Synthetic training split lacks both risk classes")
    if include_rfe_sample:
        if not np.array_equal(x_train[::8], x[:, :5]):
            raise AssertionError("Sampled features are not aligned with train split")
        if not np.array_equal(y_train[::8], y):
            raise AssertionError("Sampled NEP is not aligned with train split")
    print("Synthetic feature, NEP, weight, and cell-split alignment: PASS", flush=True)


def check_smoke_artifacts(
    feature_root: Path, run_root: Path, risk: RiskConfig, seed: int,
    *, enn_only: bool = False,
) -> None:
    """Reload saved arrays/models and check bootstrap weight row alignment."""
    import tensorflow as tf

    train_cells, _ = paper_cells(feature_root)
    if enn_only:
        if (run_root / "rf_rfe").exists():
            raise AssertionError("ENN-only run unexpectedly created RF-RFE artifacts")
    else:
        with (run_root / "rf_rfe" / "rfe_model.pkl").open("rb") as handle:
            rfe = pickle.load(handle)
        with (run_root / "rf_rfe" / "importance_rf.pkl").open("rb") as handle:
            importance_rf = pickle.load(handle)
        with np.load(run_root / "rf_rfe" / "sample_predictions.npz",
                     allow_pickle=False) as sampled:
            if (len(sampled["y_true"]) != len(sampled["sample_weight"])
                    or len(sampled["y_true"]) != len(sampled["y_pred"])):
                raise AssertionError("RF-RFE saved sample predictions do not align")
        if int(rfe.support_.sum()) != 5 or len(importance_rf.feature_importances_) != 5:
            raise AssertionError("RF-RFE models cannot be reloaded")
        print("rf_rfe: models and sampled predictions PASS", flush=True)
    branches = ("paper_features",) if enn_only else ("paper_features", "rfe_features")
    for branch in branches:
        branch_root = run_root / branch
        report = json.loads((branch_root / "run.json").read_text(encoding="utf-8"))
        _, y_train, _, _, _ = load_split(
            feature_root, train_cells, list(TEST_CELLS), report["feature_names"]
        )
        rows = np.load(branch_root / "bootstrap_rows_0.npy", allow_pickle=False)
        expected = np.random.default_rng(seed).choice(
            len(y_train), size=int(len(y_train) * 0.70), replace=True
        )
        if not np.array_equal(rows, expected):
            raise AssertionError(f"{branch}: bootstrap rows changed")
        sampled_weights = risk_weights(y_train, risk)[rows]
        weight_summary = report["bootstrap_weight_summaries"][0]
        if (weight_summary["rows"] != len(rows)
                or weight_summary["weight_sum"] != float(sampled_weights.sum(dtype=np.float64))
                or weight_summary["risky_rows"] != int((y_train[rows] < 0).sum())):
            raise AssertionError(f"{branch}: bootstrap weights do not align")
        with np.load(branch_root / "predictions.npz", allow_pickle=False) as predictions:
            if not np.array_equal(predictions["y_true"],
                                  load_split(feature_root, train_cells, list(TEST_CELLS),
                                             report["feature_names"])[3]):
                raise AssertionError(f"{branch}: predictions/targets do not align")
            if predictions["y_pred"].shape != predictions["y_true"].shape:
                raise AssertionError(f"{branch}: prediction shape changed")
        model = tf.keras.models.load_model(branch_root / "model_0.keras")
        if model.input_shape[-1] != 5:
            raise AssertionError(f"{branch}: saved model cannot be reloaded")
        for region in ("overall", "risky", "unrisky", "per_cell"):
            if region not in report["metrics"]:
                raise AssertionError(f"{branch}: missing {region} metrics")
        print(f"{branch}: artifacts and bootstrap weights PASS", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("smoke", "full"), default="smoke")
    parser.add_argument("--device", choices=("cpu", "gpu", "auto"), default="cpu")
    parser.add_argument("--feature-root", type=Path, default=DEFAULT_FEATURE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE,
                        help="Reference predictions.npz; used only if test values/order match")
    parser.add_argument("--enn-only", action="store_true",
                        help="Skip RF-RFE and train just one weighted ENN")
    parser.add_argument("--selected-features", type=Path,
                        help="Existing weighted RFE run directory or selected_features.json; "
                             "requires --enn-only (default: paper fixed five features)")
    args = parser.parse_args()
    if args.selected_features is not None and not args.enn_only:
        parser.error("--selected-features requires --enn-only")
    if args.mode == "smoke" and args.selected_features is not None:
        parser.error("--selected-features is for real Parquet runs; smoke uses synthetic data")

    risk = RiskConfig()
    enn = ENNConfig(device_mode=args.device)
    rfe = RFEConfig()
    if args.mode == "smoke":
        enn = replace(enn, num_models=1, epochs=1, batch_size=16,
                      steps_per_execution=1)
        rfe = replace(rfe, n_estimators=2, n_jobs=1, random_state=1)

    tf = configure_tensorflow(enn)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    prefix = f"enn_only_{args.mode}" if args.enn_only else args.mode
    run_root = args.output_root / f"{prefix}_{stamp}"
    if args.mode == "smoke":
        with TemporaryDirectory(prefix="risk_weighted_vre_") as temp:
            feature_root = Path(temp) / "features"
            create_synthetic_features(feature_root)
            check_synthetic_alignment(feature_root, risk,
                                      include_rfe_sample=not args.enn_only)
            train_cells, test_cells = paper_cells(feature_root)
            if args.enn_only:
                run_enn_only(tf, feature_root, run_root, train_cells, test_cells,
                             risk, enn, args.baseline)
            else:
                run_experiment(tf, feature_root, run_root, train_cells, test_cells,
                               risk, rfe, enn, args.baseline)
            check_smoke_artifacts(feature_root, run_root, risk, enn.seed,
                                  enn_only=args.enn_only)
    else:
        feature_root = args.feature_root.resolve()
        train_cells, test_cells = paper_cells(feature_root)
        if args.enn_only:
            run_enn_only(tf, feature_root, run_root, train_cells, test_cells,
                         risk, enn, args.baseline, args.selected_features)
        else:
            run_experiment(tf, feature_root, run_root, train_cells, test_cells,
                           risk, rfe, enn, args.baseline)

    print(f"Completed {args.mode} experiment: {run_root.resolve()}")


if __name__ == "__main__":
    main()
