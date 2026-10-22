# Lee-Hsun 研究計畫分析：Trustworthy Virtual Reference Electrode

## 1. 結論與建議定位

Lee-Hsun 的題目應明確定位為：**讓 VRE 從「能預測負極電位」進一步成為「知道何時不該被信任、並能觸發安全降級」的虛擬感測器**。

Yu et al. (2026) 已證明，以一般二電極電池可取得的訊號，可以估計負極電位（negative electrode potential, NEP；內部計畫亦稱 AV），在測試集達到約 23 mV RMSE，並能用預測值控制充電、降低鋰析出風險。Lee-Hsun 不應把主要工作放在再降低幾 mV 的平均誤差，而應回答三個尚未被原論文完整回答的問題：

1. 每一個 VRE 預測的誤差界線是多少？
2. 新 cell、protocol、temperature、age 或 form factor 超出訓練分布時，模型能否在出現危險錯誤前察覺？
3. BMS 如何把不確定度轉為具體且可驗證的降電流、回退或拒絕決策？

最適合作為碩士研究主線的題目是：

> **Risk-calibrated virtual reference electrode for safe lithium-plating-aware charging under distribution shift**

核心成果不是「有一個 uncertainty score」，而是證明：在指定的 coverage 或充電代價下，該分數能顯著降低 plating false negative，並能形成可重現的安全決策規則。

## 2. 原論文提供的研究起點

原論文建立了以下基礎：

- 資料來自 55 顆 Gr‖LFP 三電極 coin cells，約 9.8 million 筆量測，主要在 25 °C 下以多種 constant-current 與 stepped-current protocol 產生。
- 從 65 個候選特徵，以 random-forest recursive feature elimination 選出 5 個特徵；重要訊息主要來自 voltage、capacity/energy，以及 8 秒前的歷史訊號。
- 預測器是 5 個 feedforward neural networks 的 ensemble。每個成員以 training data 的 70% bootstrap sample 訓練，最後平均輸出。
- 測試集整體 RMSE 約 0.023 V、MAE 約 0.018 V；論文亦測試未見過的 C-rate、不同 batch cell 與動態 stepped charging。
- SI Table S2 確認資料是嚴格依 cell 切分：47 顆 training cells（7,623,689 points）與 8 顆 unseen test cells（2,162,149 points），沒有同一顆 cell 的 cycle 或 time-series data 跨越切分。
- SI Table S9 顯示 test-cell 間表現並不一致：per-cell RMSE 的平均為 0.0263 V、標準差為 0.0088 V；per-cell MAE 的平均為 0.0217 V、標準差為 0.0085 V。
- SI Table S5 在完整 test set 上報告 `measured NEP < 0 V` 且 `predicted NEP ≥ threshold` 的 point-wise 比例：0 mV、10 mV 與 20 mV threshold 分別為 2.140%、1.445% 與 0.947%。這是高度時間相關的 point fraction，不等於 event-level 或 cell-level false-negative probability。
- SI Table S8 已提供部分 generalization baseline：unseen 7-step smart charging 在 cycle 1 與 cycle 300 的 RMSE 為 0.0205/0.0227 V；只用 CC cells 訓練、再於 stepped cells 測試時 RMSE 增至 0.0382 V。
- Smart charging 在預測 NEP 到達 0.02 V 時逐步降低電流；在論文的低 N/P ratio 條件下，相較 CC-CV baseline，cycle life 增加 8.25 倍。
- 作者不只以 NEP 當 plating proxy。在預測 NEP 為 +10、0、−10 與 −20 mV 時停充，每個條件拆解 3 顆獨立 2E cells 做 SEM/光學驗證。SI Table S6 的 pixel-area Li coverage 平均值依序為 0.08%、0.30%、26.57% 與 50.99%；greyscale 方法為 0%、3.67%、13.26% 與 56.22%。
- SI Table S7 顯示 predicted NEP 與 Li coverage 有強負相關：pixel-area Spearman `ρ = -0.950`，greyscale `ρ = -0.978`，且兩者均有統計顯著性。但每條件只有 3 顆 cell，且 SI 自身提醒 negative-NEP 條件的區間很寬，反映 localized/heterogeneous plating。
- 控制系統約有 115 ms end-to-end latency，並已有 communication、input 或 model failure 時回退到保守 CC-CV 的機制。

這些結果提供了 Lee-Hsun 最好的起點：現有五模型 ensemble 已天然產生 member disagreement；現有 smart-charging controller 已有可插入 confidence gate 的位置；現有 3E 資料則能直接檢驗「模型自認不確定時是否真的比較容易錯」。

因此，不能再把「NEP 與 plating 是否有實驗對照」寫成原論文完全沒有做的缺口。原論文已證明，在其測試的 Gr‖LFP、1 C、25 °C 與特定取樣區域下，predicted NEP 變負與 ex-situ Li coverage/morphology 增加具有明確關聯，並在 20 mV smart-charging cells 的 end-of-life post-mortem SEM 中報告 0% detectable Li coverage。

真正尚未完整回答的是：他們使用全域固定 20 mV threshold 與 aggregate point-wise false-negative analysis，但沒有建立經正式校準的 per-sample prediction bound，也沒有系統性證明 ensemble spread 能抓到高誤差事件。現有 plating 實驗也未回答這個 NEP–coverage 關係在 temperature、C-rate、SOH、cycling history、cell design 與取樣位置改變時是否仍成立。因此 Lee-Hsun 的缺口應改寫為 **risk calibration 與 distribution-shift transferability**，而不是從零開始證明 NEP 和 plating 有關。

## 3. 建議收斂後的研究問題與假說

### Primary research question

在嚴格以 cell/domain 隔離的測試條件下，VRE 的 ensemble disagreement、距離訓練分布的程度與 conformal calibration，能否形成一個**單側安全下界**，使 BMS 在 true NEP 可能低於 0 V 前可靠地降級？

### 可驗證假說

- **H1：誤差排序。** Ensemble disagreement 或 representation-space distance 與 absolute error、尤其 near-zero NEP error 呈顯著正相關。
- **H2：in-domain calibration。** 以未參與訓練與選模的 calibration cells 建立的單側 conformal bound，可在 unseen in-domain cells 達到預先設定的 marginal coverage。
- **H3：OOD safety。** 單獨的 conformal interval 在 domain shift 下可能失效；加入 explicit OOD score 或 domain-conditional calibration 後，能降低高信心的危險錯誤。
- **H4：decision utility。** 以 lower confidence bound 控制充電，比固定 0.02 V point-estimate threshold 產生更少 plating false negatives，且充電時間與 intervention rate 維持在可接受範圍。

H3 很關鍵：conformal prediction 的 coverage 依賴 calibration 與 test data 的交換性。它不能被宣稱為任意 OOD 情況下的安全保證。因此，「區間校準」與「OOD 偵測」必須各自評估，再由 decision policy 結合。

## 4. 建議的最小可發表研究設計

### Aim 0：重現與固定基準

先完整重現原論文的 preprocessing、5-feature pipeline、五模型 ensemble 與約 23 mV benchmark。這一步應固定：

- cell IDs 與 train/validation/calibration/test assignments；
- smoothing window、normalization 與 feature calculation 的 fit 範圍；
- five ensemble members 的 bootstrap samples 與 random seeds；
- 每個模型版本、資料版本與 code commit；
- overall、per-cell、per-cycle 及 near-zero NEP metrics。

SI Table S2 已確認原論文採用 **strict cell-level split**，8 顆 test cells 的所有 cycles/time points 均未出現於 training set。實作時仍應以 released code 重現 cell IDs 與 preprocessing，並另切出完全獨立的 calibration cells，避免用 final test cells 調 uncertainty threshold。

### Aim 1：建立 uncertainty baselines

先比較簡單且可部署的方法，不要一開始就擴充複雜架構：

1. Ensemble standard deviation 或 robust spread。
2. Standardized 5-feature space 的 k-nearest-neighbor distance。
3. Regularized Mahalanobis distance。
4. 最後一層 latent representation 的 distance。
5. Validation/calibration residual 所建立的 global 與 condition-aware scale baseline。

先檢驗 score 是否能**排序風險**，再談 calibration。若五個 ensemble members 的 disagreement 幾乎相同或普遍過小，可能是成員高度相關，而不是 VRE 本身沒有 epistemic uncertainty。此時可比較不同 cell-bootstrap、不同 initialization，或較多 ensemble members，但模型複雜化應放在 baseline 失敗後。

### Aim 2：校準單側安全界線

對安全控制而言，對稱的 95% prediction interval 不是最直接的輸出。建議建立 true NEP 的 lower prediction bound：

\[
L(x)=\hat{V}_{NE}(x)-q(x)
\]

其中 `q(x)` 由完全獨立的 calibration cells 決定。控制邏輯可先在 offline replay 中定義為：

- `L(x) > safety_margin`：允許 VRE 正常控制；
- `L(x) <= safety_margin`：降低充電電流或進入 conservative mode；
- OOD score 超過門檻或 input QC fail：直接 abstain/fallback。

應同時測試 global split conformal、normalized conformal（以 ensemble spread 或 local residual scale 正規化）及少量 group/condition-aware 版本。方法選擇以 held-out calibration 結果為準，不能用 final test domain 調門檻。

#### One-sided bound 不是把 ground truth 校準到 0 V

`0 V` 只是最後的物理決策邊界，不是 regression 或 calibration 的目標值。在 calibration point (i) 上，真實值 (y_i) 會沿整條 NEP trajectory 變化。對 plating safety 而言，危險方向是模型高估 NEP，因此可定義單側 residual：

\[
s_i=\hat y_i-y_i.
\]

以獨立 calibration set 的 (s_i) 取有限樣本修正後的 (1-\alpha) quantile (q_{1-\alpha})，得到：

\[
L(x)=\hat y(x)-q_{1-\alpha}.
\]

若誤差幅度隨 cell state 改變，可以 ensemble spread 或另一個 scale model 得到 \(\hat\sigma(x)\)，再以

\[
s_i=\frac{\hat y_i-y_i}{\hat\sigma_i+\epsilon},\qquad
L(x)=\hat y(x)-q_{1-\alpha}\bigl(\hat\sigma(x)+\epsilon\bigr)
\]

建立 heteroscedastic lower bound。例如 calibration 顯示 95th-percentile 的高估誤差為 28 mV：當預測值為 +25 mV 時，(L=-3) mV，控制器不應宣告安全；當預測值為 +60 mV 時，(L=+32) mV。因此 lower bound 會隨預測與 local scale 變動，不會全部停在 0 V。

#### 如何提高 near-zero/負 NEP 的安全權重

這應分成「訓練」與「校準」兩層：

1. **訓練 point predictor：** 使用平滑的 near-boundary weight，不只對 (y<0) 硬切。可將 −20 至 +50 mV 當候選 risk band，並對「預測比真值高」的方向加重：

\[
\mathcal L_i=w(y_i)\left[
\lambda_{\rm over}(\hat y_i-y_i)_+^2+
\lambda_{\rm under}(y_i-\hat y_i)_+^2
\right],
\qquad \lambda_{\rm over}>\lambda_{\rm under}.
\]

   (w(y)) 在 near-zero/負 NEP 區域較大。Mini-batch 也應以 cell/cycle/window 分層抽樣，避免一段很長的負 NEP trajectory 以數千個高度相關 points 主導 loss。
2. **校準 lower bound：** global residual quantile 可能被大量容易的高 NEP points 主導。可在部署時也可觀察的條件上做 Mondrian/group calibration，例如 predicted-NEP band、SOC range、C-rate、temperature 或 age group。不可只以 test-time 不可知的 true (y<0) 當分組條件，否則無法在部署時選擇對應的 bound。
3. **直接校準 safety risk：** 在獨立 calibration trajectories 上選擇 (q) 或 control margin，使 `measured NEP < 0` 但 policy 判 safe 的 event-level risk 上界低於預先設定的容忍值。這比單純增加 negative points 權重更直接對應最終 BMS 目標。
4. **可選 risk head：** 另加 (P(NEP<0\mid x)) 分類 head，使用 weighted BCE/focal loss，但仍要在獨立 cells 上校準 probability。這個 head 是 lower bound 的輔助證據，不應自動取代連續 NEP regression。

建議第一階段先 freeze 原 VRE，只在獨立 calibration cells 上建 lower bound，以確定問題是否能由 post-hoc calibration 解決。只有當 near-zero 區域的高估誤差仍無法控制時，再引入 asymmetric weighted loss 重訓模型。訓練、hyperparameter selection、calibration 與 final test 必須依 cell 完全分開。

### Aim 3：自然 OOD challenge suite

OOD 測試應從「原論文尚未覆蓋或覆蓋不足的真實 domain shift」定義，不要只靠人工加噪聲。建議分三層：

| 層級 | 首選測試 | 研究用途 |
|---|---|---|
| In-domain holdout | 同 chemistry、form factor、temperature 與 protocol family 的 unseen cells | 驗證基本 calibration 與 cell-to-cell transfer |
| Near OOD | 重現 SI 的 held-out C-rate/unseen protocol，再加 late-life 或不同 aging path | 把已有 generalization result 轉成 uncertainty/OOD benchmark，檢驗輕度 shift 與偵測延遲 |
| Far OOD | 不同 temperature、coin-to-pouch、field-BMS signal/domain；資料成熟後再加入 chemistry shift | 檢驗 abstention 是否能避免 silent failure |

碩士主線建議承諾 **兩種 near/real OOD shift** 即可，例如 protocol shift 加 temperature 或 aging shift。跨 chemistry、form factor 與 EV field data 可列為 stretch goal，否則資料依賴過多、容易讓論文失焦。

### Aim 4：從 uncertainty 到安全決策

第一階段用記錄完成的 3E trajectory 做 closed-loop replay，比較：

1. 固定 point estimate threshold（原論文 baseline）；
2. point estimate 加固定 20 mV margin；
3. lower-bound controller；
4. lower-bound 加 OOD abstention/fallback。

只有在離線結果達到預先設定的 safety gate 後，才進行 supervised smart-charging experiment。線上驗證應保留 cycler hard limits、input sanity checks、timeout 與 conservative CC-CV fallback。

## 5. 評估指標

整體 RMSE 只作相容性指標。主結果應包含：

### Prediction 與 calibration

- RMSE、MAE、bias：overall、per cell、per cycle、各 NEP bin。
- Empirical coverage 與 average interval width。
- Worst-group coverage：依 protocol、C-rate、age、temperature/domain 分組。
- Near-threshold coverage：例如 measured NEP 位於 `[-20, +50] mV` 的區域；最終範圍應依資料分布預先註冊。

### Error/OOD detection

- uncertainty score 與 absolute error 的 Spearman correlation。
- High-error event detection 的 AUROC 與 AUPRC；high-error 門檻需在看 final test 前定義。
- OOD detection 的 AUROC/AUPRC、FPR at 95% TPR，以及 trajectory-level detection latency。
- Risk-coverage curve 與 area under risk-coverage curve：模型拒絕多少資料後，保留資料的風險下降多少。

### Safety 與 control

- **Thermodynamic-risk false negative**：measured NEP 已低於 0 V，但 policy 仍判定安全。這是可由 3E data 大規模計算的主要 proxy metric。
- **Confirmed-plating false negative**：pressure、relaxation、EIS、titration、microscopy 等獨立證據確認 plating，但 policy 仍判安全。它的樣本通常較少，卻更接近真正 safety endpoint。
- Event-level sensitivity：連續一段 plating-risk／confirmed-plating event 是否至少被及時攔截一次，不能只計算高度相關的每秒 datapoints。
- Time-to-warning：相對 measured NEP 首次跨過 0 V，以及相對獨立方法確認的 onset，分別計算提前或延遲多久觸發降級。
- Charge time、energy/capacity delivered、current-reduction 次數、fallback/abstention rate。
- 若做線上試驗，再比較 cycle life、capacity retention 與 post-mortem plating evidence。

安全資料高度時間相關。統計 bootstrap 或 confidence interval 應以 **cell 或完整 trajectory** 為單位，不能把數百萬個每秒 datapoints 當成數百萬個獨立樣本。

## 6. 與其他成員的邊界

- **Thelonius / Interpretability**：回答模型為何成功或失敗；Lee-Hsun 使用其 failure explanation 改善 risk detector，但主要 deliverable 是可校準的風險與決策。
- **Yiping / Lifetime-adaptive VRE**：建立 aging shift 與 adaptation；Lee-Hsun 把其 frozen-model failures 當 OOD challenge，不負責重新設計完整 aging-adaptive model。
- **Katie / Minimal-BMS robustness**：產生 sampling、noise、dropout 等 signal degradation curves；Lee-Hsun 判斷何時這些 degradation 應導致 abstention。
- **Jiayi / Active learning**：可使用 Lee-Hsun 的 uncertainty 作 acquisition signal；uncertainty 是否適合安全決策與是否適合選實驗，必須分開驗證。
- **Haoming / World model**：提供 controlled synthetic OOD sweep；合成資料可用於壓力測試，但不能取代真實 OOD validation。
- **Erina / Atlas-QC**：提供 input/data quality flags。資料毀損應由 QC gate 處理，不應全被包裝成 model uncertainty。
- **Yunseo / VRE 2.0 與 transfer**：需共同固定 model checkpoint、feature schema 與 transfer datasets，避免 OOD benchmark 隨模型開發反覆變動。

## 7. 建議時程與決策門檻

| 時程 | 主要工作 | Go/No-go 證據 |
|---|---|---|
| Month 1–2 | 閱讀 paper/SI、重現 pipeline、審核 cell split | unseen-cell benchmark 接近 23 mV；資料 lineage 完整 |
| Month 3–4 | Ensemble/distance baselines、error maps | 至少一個 score 對 high-error detection 有穩定增益 |
| Month 5–6 | One-sided conformal calibration | in-domain cell-level coverage 達標，且 interval width 可用 |
| Month 7–9 | 兩個自然 OOD domains、risk-coverage analysis | 能辨識至少一類 silent high-error shift；清楚呈現失敗類型 |
| Month 10–11 | Offline controller replay、threshold selection | false negative 顯著下降，charge-time/coverage 代價量化 |
| Month 12+ | Supervised online validation、論文整理 | 只有通過 offline safety gate 才進入閉環實驗 |

若 Month 3–4 發現 ensemble spread 無法預測 error，這仍是有價值的結果：主線應轉為「為什麼 standard deep ensemble uncertainty 對 VRE 失效，以及 representation-distance／residual calibration 如何補足」，而不是盲目增加更複雜模型。

## 8. 目前計畫中需要補強的地方

1. **安全需求要量化。** 「acceptable uncertainty」需改為目標 false-negative rate、coverage 與 charge-time cost。
2. **拆開 uncertainty、OOD 與 QC。** 三者的失敗原因和處置不同，不應由單一 score 混合解釋。
3. **先定義 calibration protocol。** Calibration cells 不可同時用於 hyperparameter selection，final OOD test 不可用來調 threshold。
4. **改用單側風險。** 對 plating safety 而言，lower bound 比對稱 interval 更符合決策問題。
5. **限制 OOD 範圍。** 先完成兩種有真實 3E ground truth 的 shift，再拓展 chemistry/form factor/EV。
6. **以事件和 cell 為統計單位。** 每秒資料量很大，但有效獨立樣本數由 cells、cycles 與 protocols 決定。
7. **預先定義 fallback。** Abstention 後採取哪個 conservative action，是研究結果的一部分，而非只輸出「不知道」。

## 9. 接下來兩週可直接執行的清單

1. 取得並逐段核對原論文 Supplementary Information、released code、cell split table 與五個 ensemble checkpoints。
2. 建立 `data_manifest`：cell、batch、protocol、C-rate、cycle、age/SOH、temperature、form factor、sample count、partition。
3. 重現每個 ensemble member 的 prediction，保留五個個別輸出，不只保留平均值。
4. 產生四張第一版圖：`error vs ensemble spread`、`error vs kNN distance`、near-zero NEP reliability、risk-coverage curve。
5. 與 Yunseo/Jiayi 固定一版 frozen VRE benchmark，與 Yiping/Katie 選定兩個最早可取得 ground truth 的 shift。
6. 在分析前寫下 success criteria，例如希望在 90% retained coverage 下，將 plating-event false negative 降低多少；數值應由現有事件數與實驗風險共同決定。

## 10. 細節名詞解釋

### 10.1 電池、電極與電位

**正極／負極（positive/negative electrode）與陰極／陽極（cathode/anode）**

充電與放電時，cathode/anode 所代表的反應方向會互換，因此電池工程通常直接說正極與負極以避免混淆。本文件中的 anode voltage、anode potential、AV 與 negative electrode potential、NEP，皆指石墨負極相對於 `Li/Li+` reference 的電位。

**2E 與 3E cell**

- 二電極（2E）cell 只有正、負兩個 terminal，量到的是 full-cell voltage：`V_cell ≈ V_positive − V_negative`。單看這個差值，無法唯一知道是哪一側電極的電位發生變化。
- 三電極（3E）cell 額外加入 reference electrode，可分別量到正極與負極相對 reference 的電位。它提供 VRE 的 NEP ground truth，但 reference 的位置、局部電流分布、reference stability 與量測雜訊仍可能造成誤差；因此「ground truth」是最佳可得量測，不是數學上毫無誤差的真值。

**Reference electrode（RE）**

RE 應盡量維持穩定電位且只承擔極小量測電流。Yu et al. 使用 Li reference，因此 NEP 的單位可寫成 `V vs. Li/Li+`。商用 cell 難以加入 RE，正是 VRE 有價值的原因。

**Virtual reference electrode（VRE）**

VRE 不是一支真正的電極，而是由一般 BMS 可取得的 voltage、current、capacity、history 等訊號，估計本來要靠 RE 才能量到的 NEP。它是 soft sensor／virtual sensor：輸入可量測外部量，輸出難量測的內部狀態。

**NEP／AV 與 full-cell voltage 的差別**

Full-cell voltage 即使仍在正常範圍，NEP 也可能已接近 plating-risk region。LFP 的正極電位平台較平，使 full-cell voltage 對負極細微變化更不敏感，這也是原論文選 Gr‖LFP 驗證 VRE 的難點之一。

**SOC、SOH 與 cycle age**

- State of charge（SOC）描述目前剩餘或已充入的相對容量，近似「現在有多滿」。
- State of health（SOH）描述相對於新電池的健康狀態，常以 capacity retention 或 resistance growth 表示，近似「還有多健康」。
- Cycle age 是循環次數或累積使用量；相同 cycle number 不保證相同 SOH，因為溫度、倍率與 protocol 會改變老化速度與機理。

**C-rate**

`1C` 代表理想上約 1 小時充完額定容量的電流，`2C` 約半小時，`C/2` 約兩小時。它是正規化後的倍率，但不同 cell 的 electrode loading、temperature、SOH 與 diffusion limitation 不同，所以相同 C-rate 不代表相同 plating risk。

**N/P ratio**

N/P 是負極可用容量與正極可用容量的比值。N/P 越小，負極容納 Li 的餘裕越少；接近滿鋰化時仍繼續充入 Li，更容易轉向表面 metal deposition。原 VRE 論文用約 `N/P = 1.0` 作為容易發生 plating 的壓力測試，不能直接視為所有商用電池的典型設計。

**CC、CV 與 CC-CV charging**

- Constant current（CC）：固定電流充電，cell voltage 隨 SOC 上升。
- Constant voltage（CV）：到達 voltage limit 後固定電壓，電流逐漸下降。
- CC-CV：先 CC、後 CV，是常見充電方式。固定 protocol 無法主動觀察內部 NEP，因此在低溫、老化或 cell variation 下可能變得過度激進或過度保守。

### 10.2 Li plating 的物理與化學名詞

**Intercalation（嵌入）**

正常充電時，Li+ 經 electrolyte、SEI 與 charge-transfer process 進入 graphite layer，形成不同 stage 的 `LixC6`。這個路徑需要完成 electrolyte transport、desolvation、穿越 SEI、界面反應與 graphite solid diffusion；其中任何一步變慢，都可能讓負極表面的 Li+ 供應速度超過 graphite 吸收速度。

**Lithium plating（鋰析出／鍍鋰）**

Li+ 沒有進入 graphite，而在負極表面取得電子形成金屬 Li：

\[
\mathrm{Li^+ + e^- \rightarrow Li^0}
\]

這是與 intercalation 競爭的旁反應。高充電倍率、低溫、高 SOC、低 N/P、老化造成的 resistance rise，以及局部電流／溫度不均，都會增加其機率。[Lin et al. 的綜述](https://doi.org/10.1016/j.pecs.2021.100953)整理了機理、偵測、模型與抑制方法。

**為何常用 0 V vs. Li/Li+ 作界線**

相對 Li/Li+ 而言，當負極電位降到約 0 V，金屬 Li deposition 在熱力學上變得有利。因此 VRE 把 NEP 接近 0 V 視為清楚且物理可解釋的 risk signal。

但 `NEP < 0 V` 不是所有 cell、所有局部位置都完全等價的 binary ground truth。實際 onset 還取決於 nucleation barrier、charge-transfer kinetics、graphite surface Li concentration、局部 temperature/current heterogeneity 與 reference measurement 的空間平均。[2024 年的 triggering-criterion 研究](https://doi.org/10.1039/D4TA00244J)顯示，某些高倍率 pulse 下，graphite potential 明顯低於 0 V 後才觀察到 plating。相反地，局部不均勻也可能讓 cell-level 量測尚未顯示負值時，局部區域已開始 deposition。因此本研究應稱 0 V 為 **thermodynamic risk boundary**，並以 microscopy、XRD、NMR、titration、pressure 或其他獨立證據驗證真正 plating onset。

原 VRE 論文的 SI 已對此做了重要但有邊界的驗證。作者在 predicted NEP 為 +10、0、−10 與 −20 mV 時停充，透過 SEM 對每個條件的 3 顆獨立 cells 量化 Li coverage。兩種影像方法均顯示：+10 mV 幾乎無 detectable Li，0 mV 僅有很低 coverage，−10 mV 已明顯出現 nuclei/deposition，−20 mV 則出現更廣泛的 mossy/filamentary Li。因此，在該實驗 domain 中，predicted NEP 不只與風險關聯，也與 plating severity 有實驗上的單調關係。

但這不是 universal onset law：測試集中在 +10 mV 的 pixel-area 平均 coverage 仍為 0.08%，0 V 時兩種分析為 0.30% 與 3.67%；負 NEP 條件的 95% CI 很寬，且 SEM 只取樣 graphite inner-ring edge 的代表區域。SI Note #3 也明確說明，局部 plating 可能在 spatially averaged NEP 仍略為正值時發生。所以原論文提供了強而有限定條件的 evidence；Lee-Hsun 要檢驗的是它在 cell/state/domain shift 下的可轉移性與不確定度。

**Polarization（極化）**

實際負極電位偏離 equilibrium potential 的總效果，通常包含：

- Ohmic polarization：電子與離子傳輸的電阻壓降。
- Charge-transfer polarization：界面反應速度有限造成的 overpotential。
- Concentration polarization：Li+ transport 或 graphite diffusion 跟不上，使界面濃度與 bulk 不同。

低溫會降低 electrolyte conductivity、charge transfer 與 solid diffusion；高電流會放大各種 polarization；高 SOC 則減少 graphite 尚可接收 Li 的空間。三者疊加時 plating risk 特別高。

**Nucleation、mossy Li 與 dendrite**

Plating 通常先有金屬 Li nuclei，之後可能長成較緻密、mossy 或 filamentary/dendritic morphology。並非所有 plated Li 都形成會刺穿 separator 的長 dendrite，但更高 surface area 的 morphology 會加速與 electrolyte 反應；嚴重情況下也會提高 internal short 與 thermal runaway 風險。

**Reversible plated Li、irreversible Li 與 dead Li**

- Reversible portion 在 rest 或 discharge 時仍與電子網路連接，可被 stripped 或重新 intercalate。
- 一部分 Li 會和 electrolyte 反應形成新的 SEI，消耗 cyclable lithium。
- 與 electrode 電子接觸中斷的 metallic Li 稱 dead Li，無法再被正常利用。

因此一次 plating event 不一定立刻造成相同程度的永久容量損失；其 reversibility 取決於 morphology、時間、溫度、pressure 與後續 protocol。

**SEI（solid electrolyte interphase）**

SEI 是 electrolyte 在負極表面還原形成的鈍化層。理想 SEI 讓 Li+ 通過、阻止持續 electrolyte decomposition。Plated Li 的高 surface area 會促進額外 SEI 生長，消耗 electrolyte 與 lithium inventory、提高 impedance，形成「plating → SEI/dead Li → resistance rise → 更容易 plating」的正回饋。

**LLI 與 LAM**

- Loss of lithium inventory（LLI）：可循環 Li 被 SEI、dead Li 等鎖住。
- Loss of active material（LAM）：electrode cracking、delamination 或 active sites 失效，使材料不能再儲鋰。

Li plating 可同時造成 LLI，並藉由膨脹、裂紋與 pore blockage 間接造成 LAM。

### 10.3 Trustworthy ML 名詞

**Point estimate、residual、bias、RMSE 與 MAE**

- Point estimate `ŷ`：模型對單一時間點輸出的 NEP 預測值。
- Residual 可定義為 `e = y − ŷ`；報告中必須固定符號，避免安全上下界方向寫反。
- Bias：平均 residual，顯示系統性高估或低估。
- MAE：`mean(|e|)`，容易解釋為平均絕對偏差。
- RMSE：`sqrt(mean(e²))`，對少數大錯誤給更高懲罰。

整體 23 mV RMSE 不代表每個 cell、每個 protocol 或 0 V 附近都有 23 mV 的可靠誤差界線。

**Aleatoric 與 epistemic uncertainty**

- Aleatoric uncertainty：資料本身的隨機性或無法由現有輸入辨識的變異，例如 sensor noise、unobserved temperature gradient、reference noise。同樣輸入也可能對應不同 ground truth。
- Epistemic uncertainty：模型因 training coverage 不足而「不知道」，例如未見過的 temperature、chemistry 或 aging mode。增加有代表性的資料通常可降低它。

Deep ensemble disagreement 主要被當作 epistemic signal，但實際也會混入 training randomness；若 ensemble members 高度相似，它會低估未知風險。

**Deep ensemble 與 bootstrap**

Deep ensemble 是獨立訓練多個 neural networks，再平均預測。Bootstrap 是每個模型從 training units 有放回抽樣；對本題而言，應優先以 **cell-level bootstrap** 建立多樣性，因為逐 datapoint bootstrap 會把高度相關的同一 trajectory 拆散。[Lakshminarayanan et al.](https://proceedings.neurips.cc/paper/2017/hash/9ef2ed4b7fd2c810847ffa5fa85bce38-Abstract.html)是 deep ensemble uncertainty 的代表性工作。

**Ensemble disagreement／spread**

可用五個 member prediction 的 standard deviation、median absolute deviation 或 quantile range 表示。Spread 大表示模型彼此意見不同；spread 小只代表彼此一致，不能保證它們沒有一起犯錯，所以必須以 held-out error 實證驗證。

**Calibration（校準）**

校準問的是「模型宣稱的信心水準是否和實際頻率一致」。例如 nominal 90% interval 在許多 unseen cells 上應約有 90% true NEP 落在區間內。好的 calibration 仍可能給很寬、沒有控制價值的 interval，因此必須同時報 coverage 與 width。

**Conformal prediction**

Conformal prediction 用獨立 calibration set 的 residual 排序，替既有模型建立 finite-sample prediction interval，不需要假設 residual 是 Gaussian。[Angelopoulos and Bates](https://arxiv.org/abs/2107.07511)提供完整入門。

對單側 lower bound，可在 calibration cells 計算 underestimation-risk score，例如：

\[
s_i=\hat{y}_i-y_i,\qquad L(x)=\hat{y}(x)-q_{1-\alpha}(s)
\]

在 exchangeability 成立且 finite-sample quantile 正確處理時，可得到 marginal coverage `P(Y ≥ L(X)) ≥ 1−α`。若 `L(x) > 0 V`，才有依校準資料支持的證據認為 true NEP 高於 plating thermodynamic boundary。

這是**對測試分布整體的 marginal guarantee**，不是每一個 x 都有 `1−α` 的條件機率，也不是 arbitrary OOD guarantee。Time-series autocorrelation 與 cell/domain shift 會破壞簡單 exchangeability，因此 partition 和 calibration unit 應以 cell/trajectory 設計。

**OOD、domain shift、covariate shift 與 concept shift**

- Out-of-distribution（OOD）：測試條件不屬於 training coverage 的統稱。
- Covariate shift：輸入 `p(x)` 改變，例如新的 current profile 或 sensor sampling，但相同輸入與 NEP 的物理關係大致未變。
- Conditional/concept shift：`p(y|x)` 改變，例如不同 chemistry、aging mechanism 或缺少關鍵隱藏變數，使相同可觀測特徵對應不同 NEP。

後者更危險，因為 feature-distance 可能不大，模型卻高信心犯錯。[Ovadia et al.](https://proceedings.neurips.cc/paper_files/paper/2019/hash/8558cb408c1d76621371888657d2eb1d-Abstract.html)顯示，許多 uncertainty 方法在 dataset shift 下 calibration 會惡化，不能只用 in-domain 結果宣稱可靠。

**kNN distance、Mahalanobis distance 與 latent representation**

- k-nearest-neighbor distance：test point 到 training points 中最近幾個鄰居的距離；直觀但受 feature scaling 與高維度影響。
- Mahalanobis distance：以 training covariance 正規化不同方向的尺度與相關性，比單純 Euclidean distance 更能表達資料雲形狀，但 covariance 需 regularization。
- Latent representation：neural network hidden layer 對輸入形成的內部表示。可在 latent space 算距離，但表示是為 prediction loss 學得，不一定天然適合 OOD detection。

**Abstention、fallback 與 fail-safe**

- Abstention：模型明確表示此次 prediction 不足以安全使用。
- Fallback：abstain 後採用的替代控制，例如降到保守 C-rate、暫停、進入 conventional CC-CV，或要求 diagnostic pulse。
- Fail-safe：communication timeout、feature invalid、model crash 或 nonphysical output 時，系統能回到已知安全狀態。

只有 uncertainty score 而沒有 fallback policy，仍不是完整的 trustworthy control system。

### 10.4 評估指標名詞

**Coverage 與 interval width**

Coverage 是 true value 落在 prediction interval 內的比例；width 是區間寬度。高 coverage 可以靠無限寬區間輕易達到，所以研究目標是在指定 coverage 下使 width 足夠窄，或在指定 safety risk 下保留最高 control coverage。

**Risk–coverage curve 與 AURC**

模型依 uncertainty 從高到低逐步 abstain。Coverage 是仍接受的資料比例；risk 是接受部分的 error 或 safety loss。好的 score 應讓 coverage 降低時 risk 快速下降。AURC 是整條曲線的面積，通常越低越好，但必須清楚寫出 risk 定義是 MAE、high-error rate 或 plating false negative。

**AUROC、AUPRC 與 FPR@95TPR**

- AUROC 衡量 score 對 positive/negative event 的整體排序，不依單一 threshold。
- AUPRC 在危險事件稀少時通常更具資訊，baseline 約等於 positive prevalence。
- FPR@95TPR 表示為抓到 95% 危險事件，會誤報多少正常事件。

這些是 detection 指標，不直接告訴我們 charge-time cost，因此仍要回到 controller replay。

**Plating false negative 與 false positive**

- False negative：真實已達 plating-risk／plating event，但系統判安全；這是主要 safety loss。
- False positive：實際安全但系統判危險，造成不必要降電流與充電變慢。

兩者成本高度不對稱，不能只報 accuracy。應用 cost-sensitive threshold 或明確的 safety constraint。

**Point-level 與 event-level metric**

每秒資料高度相關。Point-level sensitivity 可能被一段很長的 event 主導；event-level sensitivity 則問每次獨立 plating episode 是否被偵測，以及第一次偵測距真正 onset 有多久。安全控制至少需同時報 event recall、false alarms per charge 與 time-to-warning。

## 11. Li-plating 補充知識與研究含義

### 11.1 從原因到後果的因果鏈

可將 Li plating 理解成下列鏈條：

```text
低溫／高 C-rate／高 SOC／低 N/P／老化與局部不均
                    ↓
電解液傳輸、界面反應或石墨固相擴散跟不上
                    ↓
負極 polarization 增大、表面 Li concentration 上升
                    ↓
Li metal nucleation 與 surface deposition
                    ↓
部分 stripping/re-intercalation；部分形成新 SEI 與 dead Li
                    ↓
LLI、impedance rise、局部發熱、形貌與機械損傷
                    ↓
更高 plating propensity；嚴重時 internal short／thermal risk
```

這解釋了為何 aging 本身既是 OOD，也是未來 plating risk 的放大器；同一 charging protocol 在 fresh/25 °C cell 安全，不表示在 aged/0 °C cell 仍安全。

### 11.2 不同偵測方法量到的是不同「真相」

| 方法 | 主要訊號 | 優點 | 限制／對本研究的用途 |
|---|---|---|---|
| 3E reference electrode | NEP vs. Li/Li+ | 即時、物理解釋直接 | cell 結構特殊；量到的位置不一定代表全電極局部極值；是 VRE training label |
| Voltage relaxation／dV/dt | 休息時 plated Li stripping/re-intercalation 的 mixed-potential signature | 只需 terminal voltage、容易導入 BMS | 常在充電後確認；較偏向 reversible plated Li；適合獨立 cross-check |
| Differential voltage/current | dV/dQ、dQ/dV 或 CV current feature | 非侵入、成本低 | 對 noise、protocol 與 chemistry 敏感；需要平滑和 threshold calibration |
| Operando EIS | SEI/charge-transfer impedance 變化 | Brown et al. 顯示可偵測很小 plated-Li amount | excitation、時間與硬體複雜度較高；可當實驗 ground-truth proxy |
| Pressure/thickness | plating 與 intercalation 的體積／壓力反應不同 | pouch cell 可即時量測；能提供獨立 modality | 受 fixture、temperature、aging 與 cell mechanics 影響 |
| NMR／XRD／optical／SEM | 直接或近直接辨識 metallic Li／morphology | 科學驗證力高 | 成本高；部分方法非即時或需特殊 cell／post-mortem |
| Chemical titration | 定量 reactive metallic Li | 靈敏且可量化 | destructive；適合驗證 detector sensitivity，不適合 onboard |

[Schindler et al.](https://doi.org/10.1016/j.jpowsour.2015.11.044)展示 voltage relaxation 與 impedance 方法；[Fear et al.](https://doi.org/10.1021/acsami.0c07803)以負極 potential minimum 配合 optical observation 分析 onset；[Brown et al.](https://doi.org/10.1016/j.xcrp.2021.100589)以 operando EIS 並用 chemical titration cross-validation；[Chen et al.](https://doi.org/10.1038/s41467-022-33486-4)用 `dP/dQ` 在 pouch cells 進行早期偵測與動態降電流；[Adam et al.](https://doi.org/10.1016/j.jpowsour.2021.229794)則展示 differential charging voltage 的非侵入 onset detection。

對 Lee-Hsun 最有價值的實驗不是把所有方法都做一遍，而是挑一種**獨立於 NEP 的 secondary label**。例如 VRE lower bound 預警後，以 pressure、relaxation signature 或少量 post-mortem 驗證，可以避免整篇研究只用「VRE 預測 NEP」去證明「VRE 的 plating risk 預測正確」所造成的循環論證。

### 11.3 對 trustworthy VRE 的四個直接研究機會

1. **從 NEP regression 轉成 safety decision。** 同時預測連續 NEP 與 binary/event-level plating risk，但 binary label 應結合獨立 evidence，不只由 `NEP < 0` 人工產生。
2. **把局部性視為 uncertainty source。** 一個 RE 或 VRE 輸出代表有限位置／整體特徵，未必捕捉 electrode edge、temperature hotspot 或 current crowding；這應進入 error taxonomy。
3. **做多訊號交叉驗證。** Pressure、temperature、relaxation 或 impedance 不一定要成為 deployment input，也可只在研究階段驗證 confidence score 是否與真實 plating severity 一致。
4. **把 threshold 寫成 policy parameter。** `0 V` 是物理 risk boundary，`+20 mV` 是原論文採用的工程 margin；未來 margin 應由 calibration level、latency、sensor error、false-negative target 與 charge-time cost 共同決定，不應被當成 universal constant。

## 12. 建議閱讀順序

### A. 先建立 Li-plating 全貌

1. [Lin et al., *Lithium Plating Mechanism, Detection, and Mitigation in Lithium-Ion Batteries* (2021)](https://doi.org/10.1016/j.pecs.2021.100953)：最適合先讀的完整綜述，涵蓋機理、偵測、model 與 charging mitigation。
2. [Liu, Zhu and Cui, *Challenges and opportunities towards fast-charging battery materials* (2019)](https://doi.org/10.1038/s41560-019-0405-3)：從材料與跨尺度角度理解快充瓶頸。
3. [Waldmann et al., *Li plating as unwanted side reaction in commercial Li-ion cells—A review* (2018)](https://doi.org/10.1016/j.jpowsour.2018.02.063)：聚焦商用 cell、操作條件、形貌、老化與安全。

### B. 再比較可作 ground truth／secondary evidence 的方法

4. [Schindler et al., voltage relaxation and impedance (2016)](https://doi.org/10.1016/j.jpowsour.2015.11.044)。
5. [Fear et al., potential minimum and operando onset mapping (2020)](https://doi.org/10.1021/acsami.0c07803)。
6. [Brown et al., operando EIS with titration validation (2021)](https://doi.org/10.1016/j.xcrp.2021.100589)。
7. [Chen et al., onboard differential-pressure detection and mitigation (2022)](https://doi.org/10.1038/s41467-022-33486-4)。
8. [Investigation of the lithium-plating triggering criterion (2024)](https://doi.org/10.1039/D4TA00244J)：理解為何 0 V 是重要風險界線、卻不是完整 onset criterion。

### C. 最後接到你的 trustworthy ML 方法

9. [Lakshminarayanan et al., deep ensembles (2017)](https://proceedings.neurips.cc/paper/2017/hash/9ef2ed4b7fd2c810847ffa5fa85bce38-Abstract.html)。
10. [Ovadia et al., uncertainty under dataset shift (2019)](https://proceedings.neurips.cc/paper_files/paper/2019/hash/8558cb408c1d76621371888657d2eb1d-Abstract.html)。
11. [Angelopoulos and Bates, conformal prediction introduction (2021/2023)](https://arxiv.org/abs/2107.07511)。
12. 回到 [Yu et al., VRE (2026)](https://doi.org/10.1038/s41467-026-76535-y)，逐項標記哪些 uncertainty、OOD 與 secondary validation 尚未完成。

## 13. 資料與參考來源

- Yu, J. et al., “Battery smart sensing via a virtual reference electrode,” *Nature Communications* 17, 8336 (2026), DOI: [10.1038/s41467-026-76535-y](https://doi.org/10.1038/s41467-026-76535-y).
- Paper raw data: [Zenodo 10.5281/zenodo.20937591](https://doi.org/10.5281/zenodo.20937591).
- Paper code: [Zenodo 10.5281/zenodo.21077954](https://doi.org/10.5281/zenodo.21077954).
- Local Supplementary Information: [41467_2026_76535_MOESM1_ESM.pdf](/home/phil30601/BatteryML/TrustworthyTest/ResearchPlan/41467_2026_76535_MOESM1_ESM.pdf).
- Internal plans copied into this folder: assignment summary and the plans for Lee-Hsun, Erina, Haoming, Jiayi, Katie, Thelonius, and Yiping.

補充說明：SI 已納入本分析。其 Table S2、S5–S9、Figures S15–S19 與 Note #3 是 threshold、false-negative、cell variability、protocol generalization 和 NEP–Li-coverage 關係的主要依據。
