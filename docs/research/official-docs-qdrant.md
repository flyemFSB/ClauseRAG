# 官方文档核对：Qdrant（Official docs cross-check）

日期：2026-10-02 · 抓取方式：`Invoke-WebRequest`（PowerShell 7），原始 HTML/文本存于 `.probe/qd/docs/`
（`.probe/` 已 gitignore）。本文件只记录**官方文档声明**与**本机实测**；凡文档没写的，一律写明“文档未给”，
绝不用推测值填空。本文件服务于 ADR-0019（业务稠密索引）的实现依据。

抓取到的页面（全部 HTTP 200）：

| 主题 | URL（抓取时的实际地址） | 说明 |
|---|---|---|
| Collections | <https://qdrant.tech/documentation/manage-data/collections/>（`/concepts/collections/` 302 到此处） | 建集合、向量配置、距离、命名向量、集合信息 |
| Points | <https://qdrant.tech/documentation/manage-data/points/>（`/concepts/points/` 302 到此处） | point ID 格式、批量 upsert、按 ID/按过滤删除 |
| Indexing | <https://qdrant.tech/documentation/manage-data/indexing/> | payload 索引的字段类型与创建方式 |
| Filtering | <https://qdrant.tech/documentation/search/filtering/> | 过滤子句、`must`、`match` |
| Search / Query API | <https://qdrant.tech/documentation/search/search/> | `query_points` 的当前形状与返回结构 |
| Administration | <https://qdrant.tech/documentation/ops-configuration/administration/> | strict mode、`upsert_max_batchsize` |

注意：`www.qdrant.tech/documentation/concepts/*` 这一组旧路径现在返回 302，落到 `manage-data/*` 与
`search/*`。本次实现前先抓了一次旧路径，发现 `points`、`search` 两个地址只回了 315/300 字节的跳转页
（`<meta http-equiv=refresh>`），改用新路径后才拿到正文。这是本次调研踩到的一个坑，记在这里备用。

---

## 1. Collection 创建：单向量 vs 命名向量、维度与距离

官方原文要点（Collections 页）：

- 一个集合里的点可以带**一个**同维度、同度量的向量，也可以带多个**命名向量**（named vectors），每个命名向量各自有自己的维度和度量：
  > “...same dimensionality and be compared by a single metric. Named vectors can be used to have multiple vectors in a single point, each of which can have their own dimensionality and metric requirements.”
- 支持的距离：`Dot`、`Cosine`、`Euclid`、`Manhattan`。
  > “Cosine similarity is implemented as dot-product over normalized vectors. Vectors are automatically normalized during upload”
  → **余弦下写入的向量会被服务端归一化**，所以检索返回的向量与写入的不是逐位相同（本机实测里也复现了：probe 中 `vector` 返回的是归一化后的值）。这不影响 payload 与业务字段。
- 单向量创建（官方 Python 示例）：
  ```python
  client.create_collection(
      collection_name="{collection_name}",
      vectors_config=models.VectorParams(size=100, distance=models.Distance.COSINE),
  )
  ```
  REST：`PUT /collections/{collection_name}`，body `{"vectors": {"size": 100, "distance": "Cosine"}}`。
  `size` 是必给的：Qdrant 无法从第一批写入推断维度，所以维度必须由配置在创建时固定。

**本机实测**（`qdrant-client 1.19.1` / server `1.19.1`）：`AsyncQdrantClient.create_collection(collection_name, vectors_config=models.VectorParams(size=1024, distance=models.Distance.COSINE))`
建出的集合，`get_collection()` 回报：

```
{"vectors": {"single": {"size": 1024, "distance": "COSINE"}},
 "payload_schema": {"document_id": "uuid", "knowledge_base_id": "uuid", "parent_id": "uuid",
                    "block_type": "keyword", "document_version_id": "uuid"}}
```

（`single` 是本 probe 的 helper 对“未命名单向量”的呈现名；`CollectionParams.vectors` 此时是
`VectorParams`，不是 dict。）

**判定**：本项目的业务集合用**单 dense 向量**（不命名），维度取配置（默认 1024），距离 Cosine。
理由：业务子块只有一路稠密向量；命名向量是给“一个点多种嵌入”用的，用了它反而给检索加一层
`using=` 名字。这一条写进 ADR-0019。

---

## 2. payload 索引：字段类型与创建方式

官方原文要点（Indexing 页）：

- payload 索引是**按字段+类型**建的：
  > “This index is built for a specific field and type, and is used for quick point requests by the corresponding filtering condition. The index is also used to accurately estimate the filter cardinality, which helps the query planning choose a search strategy.”
- 可索引类型（逐条原文）：
  - `keyword` — “for keyword payload, affects Match filtering conditions. Can optionally enable prefix matching.”
  - `integer` — “affects Match and Range filtering conditions.”
  - `float` — “affects Range filtering conditions.”
  - `bool` — “affects Match filtering conditions (available as of v1.4.0).”
  - `geo`、`datetime`（Range）、`text`（full-text）
  - `uuid` — “a special type of index, similar to `keyword`, but optimized for UUID values. Affects Match filtering conditions. **(available as of v1.11.0)**”
- 建议只为会用于过滤的字段建索引：
  > “Payload indexes occupy additional memory and disk space, so it is recommended to only apply payload indexes for those fields that are used in filtering conditions.”
- 创建方式：
  REST `PUT /collections/{collection_name}/index`，body `{"field_name": "...", "field_schema": "keyword"}`；
  Python：`client.create_payload_index(collection_name=..., field_name=..., field_schema=models.PayloadSchemaType.KEYWORD)`。
- **建索引最好在写入数据之前**：
  > “For performant filtering, create payload indexes for the fields you plan to filter on. For best results, create payload indexes before ingesting data.”

**本机实测**：`models.PayloadSchemaType` 的成员为
`KEYWORD, INTEGER, FLOAT, GEO, TEXT, BOOL, DATETIME, UUID`（`UUID.value == "uuid"`，1.19.1 可用）。
`create_payload_index(..., field_schema=models.PayloadSchemaType.UUID)` 对五个字段全部成功，
`get_collection().payload_schema` 回报的 `data_type` 与创建时一致（见 §1 的实测输出）。

**判定**：为 `knowledge_base_id`、`document_version_id`、`document_id`、`parent_id` 建 `uuid` 索引，
为 `block_type` 建 `keyword` 索引；**在创建集合后、写入点之前**建（本实现里 `ensure_ready()` 同时做这两件事
且幂等）。

---

## 3. 过滤语法

官方原文要点（Filtering 页）：

- 过滤加在搜索/检索/删除/滚动上：
  > “With Qdrant, you can set conditions when searching or retrieving points.”
- `must` = AND：
  > “When using `must`, the clause becomes true only if every condition listed inside `must` is satisfied. In this sense, `must` is equivalent to the operator AND.”
- `Match` 条件（官方 Python 示例）：
  ```python
  models.FieldCondition(key="city", match=models.MatchValue(value="London"))
  ```
  REST：`{"key": "city", "match": {"value": "London"}}`。

**本机实测**：`must=[FieldCondition(key="document_version_id", match=MatchValue(value=<uuid 字符串>))]`
与 `must=[FieldCondition(key="knowledge_base_id", match=MatchValue(...))]` 均按预期过滤；
`MatchAny(any=[...])`（多值任一）用于一次删除一个文档的多个版本，实测有效（删除后该版本点数 0）。
配合 `uuid` 类型索引，值是 UUID **字符串**。

**判定**：业务过滤一律用 `must` + `Match`；版本隔离用 `document_version_id`，知识库范围用
`knowledge_base_id`，一次删多版本用 `MatchAny`。

---

## 4. 批量 upsert：官方给出的“推荐批量”与限制

官方原文要点（Points 页）：

- 支持批量写入，两种等价形状（record-oriented / column-oriented）：
  > “To optimize performance, Qdrant supports batch loading of points. This means you can load several points into the service in one API call. Batching allows you to minimize the overhead of creating a network connection.”
  REST：`PUT /collections/{collection_name}/points`，body 可以是 `{"batch": {"ids": ..., "payloads": ..., "vectors": ...}}`
  或 `{"points": [{"id": ..., "payload": ..., "vector": ...}]}`；Python：`client.upsert(collection_name, points=[PointStruct(...)])` 或 `points=models.Batch(...)`。

官方原文要点（Administration 页，strict mode）：

- 官方给的不是“推荐条数”，而是一个**上限开关**：
  > “Sending very large batch upserts can create internal congestion. Setting `upsert_max_batchsize` caps the maximum size in bytes of a batch during vector upserts.”
  （注意：`upsert_max_batchsize` 是**字节数**上限，且只在 strict mode 打开时生效。）

**文档缺口（如实记录）**：官方文档**没有给出任何“推荐批量条数”或“最大条数”**，也没有把批量上限与
向量维度、payload 体积绑成一个公式。可查到的量化约束只有两条：
① strict mode 的 `upsert_max_batchsize`（默认关闭，单位字节）；② 请求整体大小由部署侧参数决定
（本次抓到的页面未给出该类参数的具体默认值，故不写推测数字）。

**本机实测**：单次 `upsert` 写入 3 个 1024 维点、以及 1 个点，均返回 `status=completed`（`wait=True`）；
probe 的默认样本集里一个版本 4 个点，一次性写入。

**判定**：批量大小由本部署的配置决定——`RAG_EMBEDDING_BATCH_SIZE` 同时约束“一次 provider 请求的文本数”
与“一次 upsert 的点数”，默认 16 是**保守选择而非官方常量**，并且明确记录在 ADR-0019 里：一旦某个部署
写入较大的子块文本，就应该降低这个值或改用 Qdrant 的 strict-mode 上限来兜底。这是“文档未给 → 保守配置 +
显式记录”的一次落地。

---

## 5. 删除：按点 ID 与按过滤

官方原文要点（Points 页）：

- 按 ID：`POST /collections/{collection_name}/points/delete`，body `{"points": [0, 3, 100]}`；
  Python：`client.delete(collection_name, points_selector=models.PointIdsList(points=[...]))`。
- 按过滤：
  > “An alternative way to specify which points to remove is to use a filter.”
  REST body `{"filter": {"must": [...]}}`；
  Python：`client.delete(collection_name, points_selector=models.FilterSelector(filter=models.Filter(must=[...])))`。
- 写操作是异步的两阶段（WAL 先落盘）：
  > “At the first stage, the operation is written to the Write-ahead-log. After this moment, the service will not lose the data, even if the machine loses power supply.”
  → 用 `wait=True` 让调用返回时写入已完成。

**本机实测**：`FilterSelector(filter=Filter(must=[FieldCondition(key="document_version_id", match=MatchAny(any=[...]))]))`
删除后用精确计数校验为 0；对**不存在**的集合做删除不在本次实测范围内（本实现改为先 `collection_exists`
再删，避免把 404 当成删除失败）。

**判定**：删除一律用 `FilterSelector` + `must`；`wait=True`；删前先确认集合存在。

---

## 6. `query_points`：当前 API 形状与返回结构

官方原文要点（Search / Query API 页）：

- Query API “Available as of v1.10.0”，是“a single interface for all kinds of search and exploration requests”。
- 最近邻检索：
  REST `POST /collections/{collection_name}/points/query`，body `{"query": [0.2, 0.1, 0.9, 0.7]}`；
  Python：`client.query_points(collection_name=..., query=[...], query_filter=models.Filter(must=[...]), search_params=models.SearchParams(hnsw_ef=128, exact=False), limit=3)`。
- 过滤后只在这些点中检索：
  > “Since the `filter` parameter is specified, the search is performed only among those points that satisfy the filter condition.”
- 返回结构与排序：
  > “The result contains ordered by score list of found point ids.”
  官方返回示例：
  ```json
  {"result": [{"id": 10, "score": 0.81}, {"id": 14, "score": 0.75}, {"id": 11, "score": 0.73}],
   "status": "ok", "time": 0.001}
  ```
- 默认不返回 payload/vector：
  > “By default, retrieval methods do not return any stored information such as payload and vectors.”（用 `with_payload` / `with_vectors` 打开）
- 多向量集合必须给 `using`：`{"query": [...], "using": "image", "limit": 3}`。

**本机实测（1.19.1，client 与 server 同版本）**：`client.search()` **不存在**（`AttributeError: 'QdrantClient' object has no attribute 'search'`，前一轮 Phase 0 探针已记录，本次复核仍如此）；
`query_points(...)` 的签名与文档一致，返回 `QueryResponse`，其真实类型是
`qdrant_client.http.models.models.QueryResponse`（字段只有 `points`），**不是** `qdrant_client.models.QueryResponse`
（后者是 `fastembed_common` 里的同名类型，字段为 `id/embedding/sparse_embedding/metadata/document/score`）。
本 probe 用 `with_payload=True` 拿到 `payload`、用 `score` 拿到相似度，实测输出形如
`score=1.0 / 0.676278 / 0.611127 ...`（第一条就是查询向量的来源点）。

**判定**：检索入口用 `query_points`（Phase 4 的 dense 通道亦然）；注解必须写
`qdrant_client.http.models.models.QueryResponse`；本阶段**不**实现检索通道，隔离性验证由 probe 直接用官方
client 调用 `query_points` 完成，避免提前造 Phase 4 的 API 面。

---

## 7. point ID 允许的格式

官方原文要点（Points 页）：

- > “Qdrant supports using both 64-bit unsigned integers and UUID as identifiers for points.”
- UUID 支持的字符串写法：simple（`936DA01F9ABD4d9d80C702AF85C822A8`）、hyphenated（`550e8400-e29b-41d4-a716-446655440000`）、urn（`urn:uuid:...`）。
- > “That means that in every request a UUID string can be used instead of a numeric ID.”
- 官方 Python 示例直接把字符串塞进 `PointStruct(id="5c56c793-69f3-4fbf-87e6-c4bf54c28c26", ...)`。

**本机实测**：写入时 `id=str(child_id)`（hyphenated UUID5 字符串），随后 `scroll` 取回的 id 是同一个
UUID（本 probe 断言“点的 id 集合恰好等于 child_id 集合”，实测通过）。

**判定**：point ID = `child_id`（版本+层级+序号的 UUID5，ADR-0018），因此 upsert 天然幂等：重建同一版本
写回同一批 id，不会产生第二套点。

---

## 8. 集合信息：怎么从服务端读回配置

官方原文要点（Collections 页 “Collection Info”）：

- `GET /collections/{collection_name}`；Python `client.get_collection(collection_name=...)`。
- 返回里含 `config`（`params.vectors`、`params.{hnsw,optimizer,wal}_config` 等）与 `payload_schema`：
  > “Qdrant allows determining the configuration parameters of an existing collection to better understand how the points are distributed and indexed.”
- `status` 有 green/yellow/grey/red 四种：
  > “🟡 yellow: collection is optimizing”“🔴 red: …”

**本机实测**：`CollectionInfo` 字段为
`status, optimizer_status, warnings, indexed_vectors_count, points_count, segments_count, config, payload_schema, update_queue`；
`CollectionParams` 字段含 `vectors, sparse_vectors, on_disk_payload, ...`；
`CollectionInfo.payload_schema` 的键是字段名、值是带 `data_type` 的 schema。
本 probe 的“集合真实存在且维度/距离/索引正确”这一条（第 2 项证据）就是读这些字段得到的，而不是读代码常量。

**判定**：`ensure_ready()` 用 `get_collection()` 读回 payload 索引集合与向量宽度；
发现已存在集合的向量宽度与配置不一致时**显式失败**（拒绝向不同宽度的集合写入），这既是本实现的行为，
也在 probe 的“维度守卫”里被真实触发过。

---

## 汇总：本实现用到的官方 API 一览（全部有文档出处）

| 用途 | 官方 API（Python / REST） | 出处 |
|---|---|---|
| 集合存在性 | `AsyncQdrantClient.collection_exists(name)` / `GET /collections/{n}/exists` | Collections |
| 建集合 | `create_collection(name, vectors_config=VectorParams(size=, distance=COSINE))` / `PUT /collections/{n}` | Collections |
| 读集合 | `get_collection(name)` / `GET /collections/{n}` | Collections |
| payload 索引 | `create_payload_index(name, field_name=, field_schema=PayloadSchemaType.UUID/KEYWORD)` / `PUT /collections/{n}/index` | Indexing |
| 批量写入 | `upsert(name, points=[PointStruct(id=uuid_str, vector=[...], payload={...})], wait=True)` / `PUT /collections/{n}/points` | Points |
| 过滤 | `Filter(must=[FieldCondition(key=, match=MatchValue/MatchAny)])` | Filtering |
| 精确计数 | `count(name, count_filter=Filter(...), exact=True)` → `CountResult.count` | Search / Filtering |
| 过滤删除 | `delete(name, points_selector=FilterSelector(filter=...), wait=True)` / `POST /collections/{n}/points/delete` | Points |
| 过滤检索（仅 probe 用） | `query_points(name, query=[...], query_filter=Filter(...), limit=, with_payload=True)` / `POST /collections/{n}/points/query` | Search |

**未使用 / 明确不引入**：命名向量、`sparse_vectors_config`（BGE-M3 走 dense-only，ADR-0003/0008）、
量化、`on_disk`、strict mode（本实现不靠 strict mode 限流，而是自己限制批量）。
