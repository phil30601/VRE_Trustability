# WSL2 / AMD ROCm / TensorFlow GPU setup

This project uses one matched stack:

- Windows 11 and WSL2
- Ubuntu 24.04
- AMD's WSL-capable Windows display driver
- ROCm 7.2.1 and ROCDXG (`librocdxg`) 1.2.0
- Python 3.12 and TensorFlow ROCm 2.20

Do not mix this setup with `tensorflow[and-cuda]` (NVIDIA only), a native-Linux
AMDGPU DKMS driver, or older ROCm 6.4 packages.

AMD supports TensorFlow 2.20 with ROCm 7.2.1 on only a limited set of Radeon
7000/9000 and Radeon Pro GPUs. Check the exact GPU first:

- [AMD WSL compatibility matrix](https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/compatibility/compatibilityrad/wsl/wsl_compatibility.html)
- [AMD ROCDXG compatibility matrix](https://github.com/ROCm/librocdxg#readme)

ROCDXG 1.2.0 is the release explicitly listed for ROCm 7.2.x. A newer ROCDXG
package is not automatically a better match for this fixed environment.

## Current machine status (checked 2026-10-16)

The inspected environment is Ubuntu 24.04 with Python 3.12, about 23 GiB RAM,
and 6 GiB swap. ROCm 7.2.1, `rocminfo`, ROCDXG, and the TensorFlow ROCm 2.20
wheel are installed. `/usr/lib/wsl/lib/libdxcore.so` and
`/opt/rocm/lib/librocdxg.so` are present. The remaining blocker in the inspected
process is that `/dev/dxg` is not visible, so TensorFlow reports
`HIP_ERROR_NoDevice` and an empty GPU list.

Recheck the final item in a normal WSL terminal because the development sandbox
can hide host devices. If `/dev/dxg` is also absent there, stop: no Ubuntu
package can repair that Windows/WSL driver boundary.

## 1. Windows-side prerequisites

Run in **Windows PowerShell as Administrator**, not Ubuntu:

```powershell
Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion
wsl --version
wsl --update
wsl --list --verbose
```

Confirm all of the following:

1. The GPU model is in AMD's WSL/ROCDXG compatibility matrix.
2. The distribution is `Ubuntu-24.04` and its WSL version is `2`.
3. The Windows AMD driver is the WSL-capable Adrenalin driver recommended by
   AMD's current guide (the ROCDXG production guide names 26.2.2).

Install/update the Windows driver if needed, reboot Windows, then run:

```powershell
wsl --shutdown
wsl -d Ubuntu-24.04
```

References: [AMD WSL with ROCDXG guide](https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/install/installrad/wsl/howto_wsl.html),
[Microsoft WSL guide](https://learn.microsoft.com/windows/wsl/install).

## 2. Gate 1: verify the Windows GPU bridge in WSL

Run in a normal **Ubuntu WSL** terminal:

```bash
uname -a
cat /etc/os-release
test -c /dev/dxg && echo "PASS: /dev/dxg exists" || echo "FAIL: /dev/dxg missing"
test -f /usr/lib/wsl/lib/libdxcore.so \
  && echo "PASS: DXCore exists" \
  || echo "FAIL: libdxcore.so missing"
```

Both checks must pass. If `/dev/dxg` is missing, return to Windows, update WSL
and the AMD WSL driver, reboot, run `wsl --shutdown`, and test again.

`/dev/kfd` and `/dev/dri` are native-Linux ROCm nodes. The current WSL ROCDXG
path uses `/dev/dxg`, so their absence is not the deciding failure here.

## 3. Replace the old 6.4.2 repository registration

Inspect the installed packages and sources:

```bash
dpkg-query -W -f='${Package}\t${Version}\n' 'amdgpu-install' 'rocm*' 2>/dev/null
grep -R "repo.radeon.com" /etc/apt/sources.list.d /etc/apt/preferences.d
```

If ROCm 6.4 packages were previously installed, uninstall that stack first:

```bash
sudo amdgpu-uninstall
```

If only the repository/installer package was installed, as currently observed:

```bash
sudo apt remove -y amdgpu-install
cd /tmp
wget https://repo.radeon.com/amdgpu-install/7.2.1/ubuntu/noble/amdgpu-install_7.2.1.70201-1_all.deb
sudo apt install -y ./amdgpu-install_7.2.1.70201-1_all.deb
sudo apt update
```

Verify that no active source still names 6.4:

```bash
grep -R "repo.radeon.com" /etc/apt/sources.list.d /etc/apt/preferences.d
apt-cache policy rocm-core
```

The active ROCm repository must show 7.2.1. AMD does not support in-place stack
upgrades; mixed repositories commonly cause ABI/package conflicts.

## 4. Install ROCm 7.2.1 user-space packages

Do not install DKMS in WSL. The kernel/display driver remains on Windows.

```bash
sudo apt install -y \
  rocm \
  python3-venv \
  python3-pip \
  python3-dev \
  build-essential
```

Check the installed release:

```bash
cat /opt/rocm/.info/version
dpkg-query -W -f='${Package}\t${Version}\n' 'rocm-core' 'rocminfo'
```

It must be 7.2.1. Installing `rocm` alone is insufficient on this WSL path;
ROCDXG is the user-mode bridge between ROCm and `/dev/dxg`.

## 5. Install the matching ROCDXG bridge

```bash
cd /tmp
wget https://github.com/ROCm/librocdxg/releases/download/v1.2.0/rocdxg-roct_1.2.0_amd64.deb
sudo apt install -y ./rocdxg-roct_1.2.0_amd64.deb
sudo ldconfig
```

ROCm 7.2.1 needs DXG detection enabled:

```bash
grep -qxF 'export HSA_ENABLE_DXG_DETECTION=1' ~/.bashrc \
  || echo 'export HSA_ENABLE_DXG_DETECTION=1' >> ~/.bashrc
grep -qxF 'export PATH=/opt/rocm/bin:$PATH' ~/.bashrc \
  || echo 'export PATH=/opt/rocm/bin:$PATH' >> ~/.bashrc
source ~/.bashrc
```

Verify the bridge and loader:

```bash
test -f /opt/rocm/lib/librocdxg.so && echo "PASS: ROCDXG installed"
ldconfig -p | grep -E 'librocdxg|libhsa-runtime64'
rocminfo | grep -E 'Agent|Name:|Marketing Name:'
```

`rocminfo` must show an AMD GPU agent such as `gfx1100`; a CPU agent alone is
not success. Fix this layer before installing TensorFlow.

## 6. Create the project TensorFlow environment

```bash
cd /home/phil30601/BatteryML/TrustworthyTest
python3 -m venv .venv-rocm
source .venv-rocm/bin/activate
python -m pip install --upgrade pip wheel setuptools
```

Install AMD's Python 3.12 / ROCm 7.2.1 wheel. Do not subsequently run
`pip install tensorflow`, which can replace the ROCm build.

```bash
python -m pip install \
  'https://repo.radeon.com/rocm/manylinux/rocm-rel-7.2.1/tensorflow_rocm-2.20.0.dev0%2Bselfbuilt-cp312-cp312-manylinux_2_28_x86_64.whl'
python -m pip install -r 'VRE_Trustability/ML performance/requirements-linux-rocm.txt'
python -m pip check
```

AMD lists TensorFlow 2.20 as production-supported for ROCm 7.2.1, although the
published wheel version string contains `dev0+selfbuilt`.

## 7. Gate 2: prove TensorFlow executes on GPU

Listing a GPU is necessary, but an actual operation is a stronger test:

```bash
source /home/phil30601/BatteryML/TrustworthyTest/.venv-rocm/bin/activate
export HSA_ENABLE_DXG_DETECTION=1

python - <<'PY'
import tensorflow as tf

print("TensorFlow:", tf.__version__)
gpus = tf.config.list_physical_devices("GPU")
print("Physical GPUs:", gpus)
if not gpus:
    raise SystemExit("FAIL: TensorFlow sees no ROCm GPU")

with tf.device("/GPU:0"):
    a = tf.random.normal((2048, 2048))
    b = tf.random.normal((2048, 2048))
    c = tf.matmul(a, b)

print("Tensor device:", c.device)
print("Checksum:", float(tf.reduce_sum(c)))
if "GPU:0" not in c.device:
    raise SystemExit("FAIL: operation did not execute on GPU:0")
print("PASS: TensorFlow ROCm GPU execution works")
PY
```

The result must show a non-empty `Physical GPUs` list and `GPU:0` tensor
placement. TensorFlow's ROCm backend still labels the device `GPU`; that does
not imply CUDA or NVIDIA.

## 8. Register the Jupyter kernel

```bash
python -m ipykernel install --user \
  --name vre-rocm-tf220 \
  --display-name 'VRE ROCm TF 2.20'
jupyter kernelspec list
```

Select **VRE ROCm TF 2.20** in VS Code/Jupyter. Then use:

1. `Feature_Engineering_Group_Linux.ipynb`
2. `Model_Performance_Linux_ROCm.ipynb`

The model notebook uses `DEVICE_MODE = 'gpu'`, `'cpu'`, or `'auto'`. GPU mode
refuses silent CPU fallback, CPU mode hides all GPUs before TensorFlow runtime
initialization, and auto mode uses a visible GPU or falls back to CPU. Restart
the Jupyter Python kernel after changing the mode, then run from the first cell.

## Optional: tested Docker image

AMD recommends its prebuilt TensorFlow image for dependency isolation:

```bash
cd '/home/phil30601/BatteryML/TrustworthyTest/VRE_Trustability/ML performance'
docker build -f Dockerfile.rocm -t vre-rocm-tf220 .
```

ROCDXG containers require WSL-specific mounts and `/dev/dxg`:

```bash
docker run --rm -it \
  --device=/dev/dxg \
  -v /usr/lib/wsl/lib/libdxcore.so:/usr/lib/libdxcore.so \
  -v /opt/rocm/lib/librocdxg.so:/usr/lib/librocdxg.so \
  -v /opt/rocm/share/rocdxg/dids.conf:/usr/share/rocdxg/dids.conf \
  -e HSA_ENABLE_DXG_DETECTION=1 \
  --ipc=host \
  --shm-size=8G \
  -p 8888:8888 \
  -v /home/phil30601/BatteryML/TrustworthyTest:/workspace \
  vre-rocm-tf220
```

Docker Desktop's WSL integration for `Ubuntu-24.04` must be enabled first.

## Troubleshooting by layer

### `/dev/dxg` is missing

This is a Windows driver/WSL problem, not Python. Update the Windows AMD WSL
driver and WSL, reboot Windows, then run `wsl --shutdown`.

### `rocminfo` is missing or shows only a CPU

```bash
ls -l /dev/dxg
ls -l /usr/lib/wsl/lib/libdxcore.so
ls -l /opt/rocm/lib/librocdxg.so
echo "$HSA_ENABLE_DXG_DETECTION"
dpkg -l | grep rocm
```

### TensorFlow imports but reports `Physical GPUs: []`

Check for a mixed stack and loader errors:

```bash
python -m pip show tensorflow tensorflow-rocm
python -m pip check
HSA_ENABLE_DXG_DETECTION=1 LD_DEBUG=libs \
  python -c 'import tensorflow as tf; print(tf.config.list_physical_devices("GPU"))' \
  2> /tmp/tf-loader.log
grep -E 'not found|libhsa|librocdxg|libamdhip' /tmp/tf-loader.log | tail -100
```

Only `tensorflow-rocm` should supply TensorFlow. Confirm that
`/opt/rocm/.info/version` and the wheel both target ROCm 7.2.1.

### Out of memory during training

The feature pipeline writes per-cell Parquet partitions to avoid holding the
original roughly 78-million-row dataset in one DataFrame. First run with
`RUN_FULL=False`, restart the kernel after full preprocessing, and only then
start model training.

## Data and validation sequence

The archive is expected at `TrustworthyTest/Open-source-data.zip`. Generated
partitions are stored under:

```text
TrustworthyTest/data/processed/features_linux_v1/
  x/cell_001.parquet
  x/cell_003.parquet
  y/cell_001.parquet
  y/cell_003.parquet
  manifest.csv
  metadata.json
```

Recommended test order:

1. Run feature engineering with `RUN_FULL=False`; this prepares cells 1 and 3.
2. Confirm that both partitions contain 65 features.
3. Run the model notebook with `FULL_PAPER_SPLIT=False` for the two-cell,
   one-epoch integration test. These metrics are not paper-comparable.
4. Confirm non-empty `Physical GPUs` and `GPU:0` tensor placement.
5. Set feature engineering `RUN_FULL=True`; the resumable builder skips cells
   1 and 3 and processes the remaining cells.
6. Restart the kernel to release preprocessing memory, set
   `FULL_PAPER_SPLIT=True`, and run the paper split.
7. Compare overall and per-cell metrics with the Windows TensorFlow 2.10 run.

The one-epoch test validates the stack; it is not expected to reproduce the
final 70-epoch paper result.
