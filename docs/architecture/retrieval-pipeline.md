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
             ├─ sufficient ──► generate ──► validate_citations ──► END
             ├─ insufficient（未达 2 轮上限）──► rewrite_query ──► plan_retrieval
             ├─ degraded（重排不可用）──► abstain_response ────────► END
             └─ insufficient（已达 2 轮上限）──► abstain_response ──► END
```

---

## 双通道召回契约与超时隔离

检索服务层并发发起双通道检索，各通道严格设置超时（默认 30 秒）：
1. **Dense 密集向量通道**：基于 pgvector 原生 HNSW cosine 索引，通过 SiliconFlow `BAAI/bge-m3` 向量匹配，召回 Top 30 候选切片。内层排序是裸的距离表达式（`ORDER BY embedding <=> :query`），加函数包装会让计划退化为排序全表。
2. **Keyword 关键词通道**：基于 ParadeDB `pg_search` BM25 索引，对子块正文执行词项匹配（`content ||| :query`）并按 `pdb.score()` 排序，召回 Top 30 候选切片。默认 `unicode_words` 分词器按 CJK 单字切分，因此定义词、条款编号与中英混排均能命中。
3. **过滤先于截断**：两条 SQL 都把授权知识库与 `status = 'ready'` 写在同一条语句的 LIMIT 之前；严禁先取全库 Top-K 再在应用层筛掉越权命中。
4. **近似检索的召回缺口是已知的**：pgvector 的 ANN 先扫索引再过滤，候选被滤光时可能拿不满 K 条。`HNSW_EF_SEARCH` 决定初始候选池，`HNSW_ITERATIVE_SCAN` + `HNSW_MAX_SCAN_TUPLES` 在被滤光后继续扩大扫描且保持有界；分区是更大规模才引入的下一步，不预设。
5. **故障隔离**：单通道超时或异常不中断整体流程；系统记录明确的通道错误类型并在终态予以标记，避免静默降级。

---

## 应用层 RRF 融合与重排 (RRF & Rerank)

### 1. 查询内倒数排名融合 (Query-level RRF)
意图分析最多产生 2 个查询变体（`MAX_REWRITTEN_QUERIES`）。每个查询在同一渠道内**独立排名**，
再按查询级 RRF 融合为该渠道的统一排名，最后才进入通道间融合：
$$\text{RRF}_q(d) = \sum_{q \in Q} \frac{1}{60 + r_q(d)}$$
两级倒排都不可省：把多个查询的召回直接拼接再统一排名，会让第二个查询的第一名落到第 $K+1$ 名，
在后续通道间 RRF 中被错误降权。同一候选被多个查询命中会累加分数，因此查询级 RRF 同时表达
"某个查询非常相关"与"多个查询都支持该候选"，而 `min(rank)` 会丢掉后一半信息。同一候选的
`raw_score` 只在各查询之间取最大值，绝不跨候选相加，也不把缺失分数写作 0。
查询变体在进入检索前先做轻量规范化：trim、丢弃空查询、保持顺序去重；全部为空时回退到原始问题，
避免模型生成两个相同查询时重复打到供应商。

### 2. 通道间倒数排名融合 (Channel-level RRF)
消除不同索引原生分数的量纲差异（pgvector 为余弦相似度，pg_search 为 BM25 相关性分）：
$$\text{RRF}(d) = \sum_{c \in \{\text{dense}, \text{keyword}\}} \frac{w_c}{60 + r_c(d)}$$
默认权重均为 $1.0$，取融合排名前 50 条候选切片进入重排阶段。

### 3. 交叉注意力二次重排 (Reranking)
将候选切片输入 SiliconFlow `BAAI/bge-reranker-v2-m3` 模型，计算与用户问题的交叉注意力相似度得分 $\in [0, 1]$。若重排服务不可用（超时或 HTTP 错误），系统在诊断中显式标注降级（`degraded`）并保留 RRF 顺序**仅供诊断**：候选不进入上下文、不产生引用，该轮直接拒答（fail-closed）。Dense 余弦分与 BM25 分和重排阈值不同量纲，未经真实数据标定不得互相替代。

---

## 上下文预算与 Parent-Child 映射 (ADR-0031)

- **配额基准**：
  - `dense_top_k` = 30
  - `keyword_top_k` = 30
  - `fusion_limit` = 50
  - `rerank_limit` = 50（送进重排的候选上限）
  - `rerank_max_documents` = 8（重排 `top_n`：只取回分数最高的 8 条，其余候选拿不到重排分、不能进入证据集）
  - `final_parent_limit` = 8
  - `max_context_tokens` = 6000
- **装配策略**：
  - 先把融合前 50 条送进交叉重排、只取回分数最高的 8 条，再依据所属父切片进行分组聚合；
  - 提示词注入的上下文正文采用 Parent 切片完整段落；
  - 预算计算严格覆盖最终渲染后的所有标识字符与段落文字；若首个子块无法放入剩余 Token 预算，则整组安全跳过，防止段落语义被半路截断。

---

## 证据门控标准 (Evidence Gating)

召回不等于证据。只有通过质量判定的候选集合才能驱动生成：
- **`sufficient`（充分）**：至少一个候选内容完整且重排得分达到阈值（默认 $\ge 0.2$），允许调用大模型生成答案。
- **`degraded`（降级）**：重排服务不可用，证据质量无法核验。该状态保留在诊断与 UI 中，但 `accepted` 恒为空：不组装上下文、不生成结论、不产生引用，直接弃答并提示「当前检索结果无法完成可靠的条款相关性核验，因此暂不生成审查结论。请稍后重试。」。重排故障 ≠ 知识库无内容，两者原因不同，不得共用同一句提示。
- **`insufficient`（不足）**：所有候选得分均低于阈值或召回为空。未耗尽重试预算时允许一次查询改写；耗尽后执行**主动弃答（Abstain）**，输出标准提示，坚决不臆测生成。
- **`unverified`（未核验）**：模型生成的答复未能提供任何可被服务端解析的合法引用，系统标记为未核验，杜绝混淆为权威回答（ADR-0032）。

门控闭合规则 `EvidenceStatus.grounded` 只承认 `sufficient`：`degraded` 与 `unverified` 都不构成可生成结论的依据。路由上只有 `insufficient` 会触发查询改写，`degraded` 直接弃答，避免重排供应商故障时连续发出两轮完全相同的重排请求（ADR-0036）。

---

## 状态机瘦身规范

LangGraph Checkpoint 仅保留会话轮次流转必需的轻量状态：
- 提问文本、改写历史、意图分类与当前检索轮次；
- 最终组装的上下文切片指引与生成答复；
- **禁止在图状态中大面积保存全量候选原始文本**，重型明细仅在当前请求诊断中透传，避免数据库检查点表无谓膨胀。
