# 消融實驗結果（KG 後端：mini，推理器：rule，top_k=5）

| 系統 | 結論正確率 | 跨文件衝突檢出率 | 條文召回 | 文件召回 | 幻覺率 | 幻覺案例比例 | 平均延遲(s) |
|---|---|---|---|---|---|---|---|
| single-naive | 0.0% | 0.0% | 0.0% | 44.4% | 0.0% | 0.0% | 0.00 |
| single-hybrid | 66.7% | 25.0% | 77.8% | 100.0% | 0.0% | 0.0% | 0.00 |
| a2a-naive | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 0.0% | 0.20 |
| a2a-hybrid | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 0.0% | 0.20 |

## 逐案結果

| 案例 | 預期 | single-naive | single-hybrid | a2a-naive | a2a-hybrid |
|---|---|---|---|---|---|
| T01 | CONDITIONAL | ❌ UNKNOWN | ❌ VIOLATION | ✅ CONDITIONAL | ✅ CONDITIONAL |
| T02 | VIOLATION | ❌ UNKNOWN | ✅ VIOLATION | ✅ VIOLATION | ✅ VIOLATION |
| T03 | VIOLATION | ❌ UNKNOWN | ✅ VIOLATION | ✅ VIOLATION | ✅ VIOLATION |
| T04 | VIOLATION | ❌ UNKNOWN | ❌ COMPLIANT | ✅ VIOLATION | ✅ VIOLATION |
| T05 | VIOLATION | ❌ UNKNOWN | ✅ VIOLATION | ✅ VIOLATION | ✅ VIOLATION |
| T06 | COMPLIANT | ❌ UNKNOWN | ✅ COMPLIANT | ✅ COMPLIANT | ✅ COMPLIANT |

> 註：rule 推理器為確定性規則引擎，幻覺率恆為 0；此模式量測的是「檢索 + 任務拆解」的貢獻。正式論文數據請以 `PCS_REASONER=llm`（本機 Ollama）重跑並設定 --repeats。
