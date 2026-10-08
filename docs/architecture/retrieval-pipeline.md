# 检索流水线与有界 Agent 状态图规范

## LangGraph 拓扑结构

系统基于 LangGraph 构建确定性有界状态机，单次问答最多允许执行 2 轮检索改写：

```text
load_context（加载上下文）
  → understand_query（意图与查询分析）
  → route_query（查询路由）
     ├─ direct_response ───────► END（通用问答/打招呼直接作答）
     ├─ ask_clarification ─────► END（信息严重缺失主动反问）
     └─ plan_retrieval（规划检索）
          → retrieve（统一检索节点：并发双通道召回、RRF 融合、重排、证据门控与上下文组装）
             ├─ sufficient / degraded ──► generate ──► validate_citations ──► END
             ├─ insufficient（未达 2 轮上限）──► rewrite_query ──► plan_retrieval
             └─ insufficient（已达 2 轮上限）──► abstain_response ────────► END
```

---

## 双通道召回契约与超时隔离

检索服务层并发发起双通道检索，各通道严格设置超时（默认 30 秒）：
1. **Dense 密集向量通道**：基于 Qdrant 向量数据库，通过 SiliconFlow `BAAI/bge-m3` 向量匹配，召回 Top 30 候选切片。
2. **Keyword 关键词通道**：基于 PostgreSQL `pg_trgm` 扩展，执行子块正文字符倒排模糊匹配，召回 Top 30 候选切片。
3. **故障隔离**：单通道超时或异常不中断整体流程；系统记录明确的通道错误类型并在终态予以标记，避免静默降级。

---

## 应用层 RRF 融合与重排 (RRF & Rerank)

### 1. 倒数排名融合 (Reciprocal Rank Fusion)
消除不同数据库原生分数的量纲差异：
$$\text{RRF}(d) = \sum_{c \in \{\text{dense}, \text{keyword}\}} \frac{w_c}{60 + r_c(d)}$$
默认权重均为 $1.0$，取融合排名前 50 条候选切片进入重排阶段。

### 2. 交叉注意力二次重排 (Reranking)
将候选切片输入 SiliconFlow `BAAI/bge-reranker-v2-m3` 模型，计算与用户问题的交叉注意力相似度得分 $\in [0, 1]$。若重排服务暂时不可用，系统显式标注降级（`degraded`）并沿用 RRF 融合顺序，绝不伪造重排分值。

---

## 上下文预算与 Parent-Child 映射 (ADR-0031)

- **配额基准**：
  - `dense_top_k` = 30
  - `keyword_top_k` = 30
  - `fusion_limit` = 50
  - `rerank_limit` = 50
  - `final_parent_limit` = 8
  - `max_context_tokens` = 6000
- **装配策略**：
  - 先按重排分筛选 Top 子切片，再依据所属父切片进行分组聚合；
  - 提示词注入的上下文正文采用 Parent 切片完整段落；
  - 预算计算严格覆盖最终渲染后的所有标识字符与段落文字；若首个子块无法放入剩余 Token 预算，则整组安全跳过，防止段落语义被半路截断。

---

## 证据门控标准 (Evidence Gating)

召回不等于证据。只有通过质量判定的候选集合才能驱动生成：
- **`sufficient`（充分）**：Top 1 重排得分达到阈值（默认 $\ge 0.2$）且具有充足的上下文覆盖，允许调用大模型生成答案。
- **`degraded`（降级）**：部分通道网络异常，但剩余通道证据仍能支撑最小作答依据，带降级标记输出。
- **`insufficient`（不足）**：所有候选得分均低于阈值或召回为空。耗尽重试预算后执行**主动弃答（Abstain）**，输出标准提示，坚决不臆测生成。
- **`unverified`（未核验）**：模型生成的答复未能提供任何可被服务端解析的合法引用，系统标记为未核验，杜绝混淆为权威回答（ADR-0032）。

---

## 状态机瘦身规范

LangGraph Checkpoint 仅保留会话轮次流转必需的轻量状态：
- 提问文本、改写历史、意图分类与当前检索轮次；
- 最终组装的上下文切片指引与生成答复；
- **禁止在图状态中大面积保存全量候选原始文本**，重型明细仅在当前请求诊断中透传，避免数据库检查点表无谓膨胀。
