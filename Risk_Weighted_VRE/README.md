# 實測 NEP 風險加權實驗

此資料夾與既有 `ML-performance` 流程分開。定義 `measured NEP < 0 V` 為 **risky**，僅從訓練資料產生逐筆權重：risky = 3，unrisky = 1。這是負 NEP 的熱力學風險代理標籤，不代表已確認析鋰。測試資料不重抽樣、不加權；推論輸入只有五個特徵，**不使用測試 NEP**。

在 `TrustworthyTest` 目錄執行：

```bash
# 55-cell 合成資料：RF-RFE（2 棵樹）及兩條 ENN（各 1 模型 × 1 epoch）
VRE_Trustability/.venv-rocm/bin/python VRE_Trustability/Risk_Weighted_VRE/cli.py --mode smoke --device cpu

# 完整實驗：真實 Parquet、47/8 cell、30 棵樹、兩條 ENN 各 5 × 70 epochs
VRE_Trustability/.venv-rocm/bin/python VRE_Trustability/Risk_Weighted_VRE/cli.py --mode full --device cpu

# 有可用 TensorFlow ROCm GPU 時，只有 ENN 訓練/推論切到 GPU；RF-RFE 仍在 CPU
VRE_Trustability/.venv-rocm/bin/python VRE_Trustability/Risk_Weighted_VRE/cli.py --mode full --device gpu

# 跳過 RF-RFE：只訓練論文固定五特徵的一條 weighted ENN
VRE_Trustability/.venv-rocm/bin/python VRE_Trustability/Risk_Weighted_VRE/cli.py --mode full --enn-only --device gpu

# 或只訓練既有 weighted RF-RFE 選出的五特徵，不重新篩選
VRE_Trustability/.venv-rocm/bin/python VRE_Trustability/Risk_Weighted_VRE/cli.py --mode full --enn-only --device gpu --selected-features VRE_Trustability/Risk_Weighted_VRE/runs/full_20261021T222656_317017Z/rf_rfe/selected_features.json
```

`--mode full` **不會**由 smoke test 自動啟動。預設輸入為 `data/processed/features_linux_v1`，預設輸出為此資料夾下的 `runs/<mode>_<UTC 時間戳>/`。可用 `--feature-root`、`--output-root`、`--baseline` 更換位置。切換 CPU/GPU 時使用新的 Python 程序或重啟 Jupyter kernel。`--device gpu` 若 TensorFlow 看不到 GPU，會直接報錯。ROCm 不會加速 scikit-learn 的 RF-RFE。

`--enn-only` 會另建 `runs/enn_only_full_<UTC>/`，不執行或複製 RF-RFE，也不覆寫先前的執行。預設使用論文固定五特徵；`--selected-features` 可指定既有 weighted RF-RFE 的 `selected_features.json`、其 `rf_rfe` 目錄或整個 run 目錄。讀取時檢查 RFE 已完成、風險權重、47/8 cell、訓練列數及 65 特徵欄位順序，再訓練一條 ENN。本次 `full_20261021T222656_317017Z` 選出的五特徵恰好與論文固定五特徵相同，因此兩種指令的**輸入特徵相同**，通常只需執行其中一種。

完整 RF-RFE 保持全域 `[::8]`（不是每個 cell 各自 `[::8]`）、`RobustScaler`、30-tree `RandomForestRegressor`、`RFE(step=15)` 的 65→50→35→20→5。RF-RFE 的每輪 forest 與最後 importance forest 都使用同一組從**抽樣訓練 NEP**計算的權重。ENN 保持原本五層網路、70% 有放回 bootstrap、SGD（learning rate 0.001、momentum 0.001）、batch 256、5 個模型、70 epochs。兩條 ENN 的差別只有五個輸入特徵：論文固定特徵與加權 RF-RFE 選出的特徵。`sample_weight` 跟著各個 bootstrap row index 抽取；沒有重複 risky 資料列來實施加權。`steps_per_execution=64` 僅減少 TensorFlow 執行開銷，不改變 optimizer 更新次數。

輸出結構：

```text
runs/full_<UTC>/
  summary.json
  rf_rfe/
    run.json, scaler.pkl, sample_index.npz, sample_predictions.npz
    rfe_model.pkl, importance_rf.pkl
    selected_features.json, feature_ranking.csv
  paper_features/
    run.json, scaler.pkl, predictions.npz
    model_0.keras ... model_4.keras
    bootstrap_rows_0.npy ... bootstrap_rows_4.npy
  rfe_features/
    （同 paper_features）

runs/enn_only_full_<UTC>/
  summary.json
  paper_features/ 或 rfe_features/
    run.json, scaler.pkl, predictions.npz
    model_0.keras ... model_4.keras
    bootstrap_rows_0.npy ... bootstrap_rows_4.npy
```

ENN `run.json` 包含整體、實測 risky/unrisky、逐 cell 的 RMSE/MAE/bias，另有「實測 risky、預測非 risky」（預測 NEP ≥ 0 V）的數量與兩個分母：實測 risky 筆數、全測試筆數。逐 cell 也有各自分母。ENN `predictions.npz` 包含未加權的完整測試集 `y_true`、`y_pred`、各 member 預測、`cell_num`、`cycle`，列順序不變。RF-RFE 的 `sample_predictions.npz` 是**訓練抽樣資料的 in-sample 診斷預測**，不可當測試表現。若 `Full/predictions.npz` 的 `y_true`、cell 與 cycle 順序**完全一致**，`run.json` 額外給出未加權 baseline 指標；否則標註 skipped，不做不可靠比較。舊論文 notebook 的訓練列數和目前 Parquet 不同，不能直接當作同一資料集的對照。

完整訓練需預留數 GB RAM（建議在 32 GB 主機上避免同時執行其他大型工作）及足夠磁碟保存兩條分支的模型、bootstrap 索引與完整測試預測。完整 RF-RFE 可能比 ENN 更久；CLI 會依次執行 RF-RFE、論文五特徵 ENN、RFE 五特徵 ENN，不做 checkpoint resume。每次建立新 UTC 目錄，不覆蓋舊結果。若執行中斷，保留已完成的階段檔案，但頂層 `summary.json` 只在全部完成後建立。
