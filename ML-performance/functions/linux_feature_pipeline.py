"""Memory-aware Linux feature pipeline for the VRE paper dataset.

The original notebook builds one ~78 million-row DataFrame before filtering it.
This module processes one cell at a time and stores one Parquet partition per
cell.  The feature definitions intentionally follow FeatureEngineering_with_dvdq.py.
"""

from __future__ import annotations

import gc
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from zipfile import ZipFile

import numpy as np
import pandas as pd
from scipy.interpolate import interp1d


RAW_COLUMNS = {
    "Voltage (V)": "Voltage",
    "Current (A)": "Current",
    "Step Time (s)": "Time",
    "Test Time (s)": "TotTime",
    "Aux_Voltage_1 (V)": "NEP",
    "Step Index": "Step_Index",
    "Cycle Index": "Cycle_Index",
    "Charge Capacity (Ah)": "Charge_Capacity",
    "Discharge Capacity (Ah)": "Discharge_Capacity",
    "Charge Energy (Wh)": "Charge_Energy",
}

PAPER_TEST_CELLS = [3, 8, 15, 19, 30, 31, 34, 51]
MANIFEST_COLUMNS = [
    "cell_num",
    "protocol",
    "raw_rows",
    "feature_rows",
    "cycles",
    "x_path",
    "y_path",
]


@dataclass
class CellResult:
    cell_num: int
    protocol: str
    raw_rows: int
    feature_rows: int
    cycles: int
    x_path: str
    y_path: str


def extract_release_csv(zip_path: Path, destination: Path) -> Path:
    """Extract only CSV and the battery index table, skipping duplicate XLSX files."""
    zip_path = Path(zip_path).resolve()
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with ZipFile(zip_path) as archive:
        members = [
            item
            for item in archive.infolist()
            if item.is_dir()
            or item.filename.lower().endswith(".csv")
            or item.filename.endswith("Battery index table.txt")
        ]
        archive.extractall(destination, members=members)
    data_root = destination / "Open-source data"
    if not data_root.is_dir():
        raise FileNotFoundError(f"Expected extracted directory: {data_root}")
    return data_root


def parse_battery_index(index_path: Path) -> pd.DataFrame:
    """Read the authoritative cell-number mapping distributed with the dataset."""
    text = Path(index_path).read_text(encoding="utf-8", errors="replace")
    matches = re.findall(r"Cell #(\d+)\s+([^\r\n]+)", text)
    if len(matches) != 55:
        raise ValueError(f"Expected 55 cells in index table, found {len(matches)}")
    records = []
    for number, windows_path in matches:
        relative = Path(*windows_path.strip().split("\\"))
        protocol_dir = relative.parts[0]
        protocol = "stepped" if protocol_dir.lower() == "stepped" else protocol_dir.removesuffix("C")
        records.append(
            {
                "cell_num": int(number),
                "relative_path": relative.as_posix(),
                "protocol": protocol,
            }
        )
    return pd.DataFrame(records).set_index("cell_num")


def _workbook_number(path: Path) -> tuple[int, str]:
    match = re.search(r"_Wb_(\d+)\.csv$", path.name, flags=re.IGNORECASE)
    return (int(match.group(1)) if match else 10**9, path.name)


def _usable_csv_files(cell_dir: Path) -> list[Path]:
    files = sorted(cell_dir.glob("*.csv"), key=_workbook_number)
    return [
        path
        for path in files
        if not any(token in str(path) for token in ("GITT", "11.81ohm", "SEM", "021623_channel_17_2023_02_16_163747"))
    ]


def resolve_raw_cell_files(cell_dir: Path) -> tuple[Path, list[Path]]:
    """Resolve a release directory, tolerating only a unique final-timestamp typo."""
    cell_dir = Path(cell_dir)
    files = _usable_csv_files(cell_dir)
    if files:
        return cell_dir, files

    # The released index names cell 49 with a final time of 170050, while the
    # archive directory ends in 160050. Restrict fallback matching to the same
    # parent and the complete basename before its final timestamp, then require
    # exactly one directory containing usable CSV files.
    basename_parts = cell_dir.name.rsplit("_", maxsplit=1)
    candidates: list[tuple[Path, list[Path]]] = []
    if len(basename_parts) == 2 and cell_dir.parent.is_dir():
        for candidate in sorted(cell_dir.parent.glob(f"{basename_parts[0]}_*")):
            candidate_files = _usable_csv_files(candidate)
            if candidate.is_dir() and candidate_files:
                candidates.append((candidate, candidate_files))
    if len(candidates) == 1:
        resolved, files = candidates[0]
        print(
            f"Index/archive path mismatch; using {resolved.name} "
            f"instead of {cell_dir.name}",
            flush=True,
        )
        return resolved, files
    if len(candidates) > 1:
        matches = [str(candidate) for candidate, _ in candidates]
        raise FileNotFoundError(
            f"No CSV files found in {cell_dir}; timestamp fallback is ambiguous: {matches}"
        )
    raise FileNotFoundError(f"No CSV files found in {cell_dir}")


def load_raw_cell(cell_dir: Path, cell_num: int, protocol: str) -> pd.DataFrame:
    cell_dir, files = resolve_raw_cell_files(Path(cell_dir))
    if not files:
        raise FileNotFoundError(f"No CSV files found in {cell_dir}")
    frames = []
    for path in files:
        frame = pd.read_csv(path, usecols=list(RAW_COLUMNS), low_memory=False)
        frame.rename(columns=RAW_COLUMNS, inplace=True)
        frames.append(frame)
    data = pd.concat(frames, ignore_index=True, copy=False)
    data["cell_num"] = np.int16(cell_num)
    data["C-rate"] = protocol
    data.sort_values("TotTime", kind="stable", inplace=True)
    data.reset_index(drop=True, inplace=True)
    return data


def _reference_curve(data: pd.DataFrame, nominal_capacity: float):
    activation = data.loc[(data["Step_Index"] == 5) & (data["TotTime"] > 100_000)].copy()
    if activation.empty:
        raise ValueError("No activation data found (Step_Index == 5 and TotTime > 100000)")
    gaps = np.flatnonzero(activation["TotTime"].diff().to_numpy() > 20_000)
    if len(gaps):
        activation = activation.iloc[gaps[0] : -1]
    if len(activation) < 4:
        raise ValueError("Insufficient activation data for cubic interpolation")
    soc = activation["Charge_Capacity"].to_numpy(dtype=np.float64) / nominal_capacity * 100.0
    voltage = activation["Voltage"].to_numpy(dtype=np.float64)
    order = np.argsort(soc, kind="stable")
    soc, voltage = soc[order], voltage[order]
    soc_unique, unique_idx = np.unique(soc, return_index=True)
    voltage_unique = voltage[unique_idx]
    if len(soc_unique) < 4:
        raise ValueError("Reference curve has fewer than four unique SOC points")
    return interp1d(
        soc_unique,
        voltage_unique,
        kind="cubic",
        fill_value=(float(voltage_unique.min()), float(voltage_unique.max())),
        bounds_error=False,
    )


def _assign_cycles(data: pd.DataFrame, cell_num: int, protocol: str) -> pd.DataFrame:
    data = data.loc[data["Step_Index"] > 9].copy()
    stepped = protocol == "stepped" or cell_num in (48, 49)
    rest_step = 18 if cell_num == 12 and stepped else (17 if stepped else 14)
    split_positions = np.flatnonzero(data["Step_Index"].to_numpy() == rest_step)
    cycles = np.full(len(data), -1, dtype=np.int16)
    relative_time = np.zeros(len(data), dtype=np.float64)
    total_time = data["TotTime"].to_numpy(dtype=np.float64)
    start = 0
    cycle = 1
    for stop in split_positions:
        segment = slice(start, stop + 1)
        cycles[segment] = cycle
        relative_time[segment] = total_time[segment] - total_time[segment].min()
        start = stop + 1
        cycle += 1
    data["cycle"] = cycles
    data["Time"] = relative_time
    return data.loc[(data["cycle"] >= 2) & (data["cycle"] <= 100)].copy()


def _dq_dv(group: pd.DataFrame) -> pd.Series:
    voltage = group["Voltage"].to_numpy(dtype=np.float64)
    capacity = group["Capacity"].to_numpy(dtype=np.float64)
    order = np.argsort(voltage, kind="stable")
    unique_voltage, unique_idx = np.unique(voltage[order], return_index=True)
    unique_capacity = capacity[order][unique_idx]
    if len(unique_voltage) < 2:
        values = np.zeros(len(group), dtype=np.float64)
    else:
        q_of_v = interp1d(
            unique_voltage,
            unique_capacity,
            kind="nearest",
            fill_value="extrapolate",
            bounds_error=False,
        )
        values = (capacity - q_of_v(voltage - 0.0005)) / 0.0005
        values[voltage - 0.0005 < voltage.min()] = 0.0
    return pd.Series(values, index=group.index)


def engineer_features(
    prepared: pd.DataFrame,
    reference_curve,
    nominal_capacity: float = 0.0031,
    nominal_energy: float = 0.0062,
) -> tuple[pd.DataFrame, pd.Series]:
    index_cols = ["cell_num", "cycle"]
    prepared = prepared.set_index(index_cols).sort_index(kind="stable")
    x = prepared[["Voltage", "Current", "Throughput", "Energy", "Capacity", "Time"]].copy()
    y = prepared["NEP"].copy()

    x["Capacity"] = (x["Capacity"] / nominal_capacity * 100.0).clip(0.0, 100.0)
    x["Overpotential"] = x["Voltage"] - reference_curve(x["Capacity"].to_numpy())
    x["dQ_dV"] = (
        x.groupby(level=index_cols, group_keys=False, sort=False)
        .apply(_dq_dv, include_groups=False)
        .sort_index(kind="stable")
    )
    x["Energy"] = x["Energy"].abs() / nominal_energy * 100.0
    x["Throughput"] = x["Throughput"] / nominal_capacity * 100.0

    derivatives = x.groupby(level=index_cols, sort=False).diff().fillna(0.0)
    derivatives.columns = [f"d{column}/dt" for column in x.columns]
    derivatives.drop(columns=["dTime/dt", "dCurrent/dt", "dThroughput/dt", "ddQ_dV/dt"], inplace=True)
    x = pd.concat([x, derivatives], axis=1)
    x["Power"] = x["Voltage"] * x["Current"]

    base_columns = list(x.columns)
    lagged = [x]
    grouped = x.groupby(level=index_cols, sort=False)
    for lag in (8, 6, 4, 2):
        shifted = grouped[base_columns].shift(lag)
        shifted.columns = [f"{column}-{lag}" for column in base_columns]
        lagged.append(shifted)
    x = pd.concat(lagged, axis=1)
    valid = np.isfinite(x.to_numpy()).all(axis=1) & y.notna().to_numpy()
    x = x.loc[valid].astype(np.float32)
    y = y.loc[valid].astype(np.float32)
    if x.shape[1] != 65:
        raise AssertionError(f"Expected 65 features, got {x.shape[1]}")
    return x, y


def process_cell(
    data_root: Path,
    output_root: Path,
    cell_num: int,
    relative_path: str,
    protocol: str,
    rolling_window: int = 25,
    nominal_capacity: float = 0.0031,
) -> CellResult:
    raw = load_raw_cell(Path(data_root) / relative_path, cell_num, protocol)
    raw_rows = len(raw)
    reference = _reference_curve(raw, nominal_capacity)
    data = _assign_cycles(raw, cell_num, protocol)
    del raw
    gc.collect()

    data["Capacity"] = data["Charge_Capacity"]
    data["Energy"] = data["Charge_Energy"]
    data["Throughput"] = data["Capacity"].diff().abs().cumsum()

    cycle_capacity = data.groupby("cycle", sort=True)["Capacity"].max()
    first_capacity = float(cycle_capacity.iloc[0])
    keep_cycles = cycle_capacity.index[cycle_capacity / first_capacity >= 0.80]
    data = data.loc[data["cycle"].isin(keep_cycles)].copy()

    mask = (
        (data["Current"] > 0)
        & ((data["Voltage"] - 3.6).abs() > 1e-3)
        & (data["Voltage"] > 3.3)
        & (data["NEP"] > -0.15)
    )
    data = data.loc[mask].dropna().drop_duplicates().copy()

    data["NEP"] = data.groupby("cycle", sort=False)["NEP"].transform(
        lambda values: values.rolling(rolling_window).mean()
    )
    data.dropna(subset=["NEP"], inplace=True)
    x, y = engineer_features(data, reference, nominal_capacity=nominal_capacity)

    x_dir = Path(output_root) / "x"
    y_dir = Path(output_root) / "y"
    x_dir.mkdir(parents=True, exist_ok=True)
    y_dir.mkdir(parents=True, exist_ok=True)
    x_path = x_dir / f"cell_{cell_num:03d}.parquet"
    y_path = y_dir / f"cell_{cell_num:03d}.parquet"
    x.reset_index().to_parquet(x_path, index=False, compression="zstd")
    y.rename("NEP").reset_index().to_parquet(y_path, index=False, compression="zstd")
    return CellResult(
        cell_num=cell_num,
        protocol=protocol,
        raw_rows=raw_rows,
        feature_rows=len(x),
        cycles=int(x.index.get_level_values("cycle").nunique()),
        x_path=str(x_path),
        y_path=str(y_path),
    )


def _partition_paths(output_root: Path, cell_num: int) -> tuple[Path, Path]:
    return (
        output_root / "x" / f"cell_{cell_num:03d}.parquet",
        output_root / "y" / f"cell_{cell_num:03d}.parquet",
    )


def _load_completed_rows(output_root: Path, index: pd.DataFrame) -> dict[int, dict]:
    """Load valid completed cells, recovering partitions not yet in the manifest."""
    manifest_path = output_root / "manifest.csv"
    previous: dict[int, dict] = {}
    if manifest_path.exists():
        old_manifest = pd.read_csv(manifest_path)
        if "cell_num" not in old_manifest:
            raise ValueError(f"Invalid manifest without cell_num column: {manifest_path}")
        previous = {
            int(row["cell_num"]): row.to_dict()
            for _, row in old_manifest.iterrows()
        }

    completed: dict[int, dict] = {}
    for cell_num in index.index.astype(int):
        x_path, y_path = _partition_paths(output_root, cell_num)
        if not (x_path.exists() and y_path.exists()):
            continue

        old = previous.get(cell_num)
        if old is not None:
            old.update(
                {
                    "cell_num": cell_num,
                    "protocol": str(index.loc[cell_num, "protocol"]),
                    "x_path": str(x_path),
                    "y_path": str(y_path),
                }
            )
            completed[cell_num] = old
            continue

        # A crash can occur after both Parquet files are committed but before
        # manifest.csv is updated. Read only the index columns to recover it.
        x_index = pd.read_parquet(x_path, columns=["cell_num", "cycle"])
        y_index = pd.read_parquet(y_path, columns=["cell_num", "cycle"])
        if len(x_index) != len(y_index):
            print(
                f"Cell {cell_num:02d} has mismatched partitions; it will be rebuilt.",
                flush=True,
            )
            continue
        completed[cell_num] = asdict(
            CellResult(
                cell_num=cell_num,
                protocol=str(index.loc[cell_num, "protocol"]),
                raw_rows=-1,
                feature_rows=len(x_index),
                cycles=int(x_index["cycle"].nunique()),
                x_path=str(x_path),
                y_path=str(y_path),
            )
        )
    return completed


def _write_build_state(output_root: Path, completed: dict[int, dict]) -> pd.DataFrame:
    """Atomically publish progress so an interrupted full run can resume."""
    if completed:
        manifest = pd.DataFrame(completed.values(), columns=MANIFEST_COLUMNS)
        manifest = manifest.sort_values("cell_num").reset_index(drop=True)
    else:
        manifest = pd.DataFrame(columns=MANIFEST_COLUMNS)

    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = output_root / "manifest.csv"
    manifest_tmp = output_root / "manifest.csv.tmp"
    manifest.to_csv(manifest_tmp, index=False)
    manifest_tmp.replace(manifest_path)

    metadata_path = output_root / "metadata.json"
    metadata_tmp = output_root / "metadata.json.tmp"
    metadata_tmp.write_text(
        json.dumps(
            {
                "format_version": 2,
                "feature_count": 65,
                "dtype": "float32",
                "test_cells": PAPER_TEST_CELLS,
                "completed_cells": manifest["cell_num"].astype(int).tolist(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    metadata_tmp.replace(metadata_path)
    return manifest


def build_dataset(
    data_root: Path,
    output_root: Path,
    cells: Iterable[int] | None = None,
    resume: bool = True,
    overwrite: bool = False,
) -> pd.DataFrame:
    data_root = Path(data_root).resolve()
    output_root = Path(output_root).resolve()
    index = parse_battery_index(data_root / "Battery index table.txt")
    selected = [int(cell) for cell in (index.index if cells is None else cells)]
    unknown = sorted(set(selected) - set(index.index.astype(int)))
    if unknown:
        raise ValueError(f"Unknown cell numbers: {unknown}")

    completed = _load_completed_rows(output_root, index) if resume else {}
    for cell_num in selected:
        if cell_num in completed and not overwrite:
            print(f"Skipping completed cell {cell_num:02d}/55", flush=True)
            continue
        row = index.loc[cell_num]
        print(f"Processing cell {cell_num:02d}/55: {row.relative_path}", flush=True)
        result = process_cell(
            data_root=data_root,
            output_root=output_root,
            cell_num=int(cell_num),
            relative_path=row.relative_path,
            protocol=row.protocol,
        )
        completed[cell_num] = asdict(result)
        _write_build_state(output_root, completed)
        gc.collect()
    return _write_build_state(output_root, completed)
