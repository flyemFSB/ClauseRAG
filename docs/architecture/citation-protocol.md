# 端到端引用防伪协议规范

## 传输层流式事件 (SSE Events)

客户端与服务端通过标准 Server-Sent Events 通信，单次会话流严格遵循单一终态规约：

```text
run_started       # 推理开始，包含 run_id 与 conversation_id
answer_delta      # 答案增量文本片段
citation          # 经服务端校验通过的权威引用对象
run_completed     # 正常完成终态，输出最终答案聚合与证据状态
run_failed        # 异常失败终态，携带结构化错误归因
run_cancelled     # 客户端主动断开或代际推进触发的取消终态
```

客户端断开连接将触发服务端异步任务取消链与资源释放，杜绝后台无效计算。

---

## 文本输出与引用格式

大模型在流式生成回答时，仅允许输出请求内局部短标识：

```text
根据服务协议第 8.1 条，乙方在任何情况下均不对间接损害承担赔偿责任。[S1]
```

---

## 服务端权威引用载荷 (Citation Payload)

大模型严禁自行输出引用详情。客户端接收到的引用对象完全由后端校验节点回表解析并推送：

```json
{
  "citation_id": "S1",
  "document_id": "11111111-1111-1111-1111-111111111111",
  "document_version_id": "22222222-2222-2222-2222-222222222222",
  "document_name": "Master_Services_Agreement.pdf",
  "parent_id": "33333333-3333-3333-3333-333333333333",
  "child_id": "44444444-4444-4444-4444-444444444444",
  "heading_path": ["Article 8", "8.1 Limitation of Liability"],
  "line_start": 88,
  "line_end": 96,
  "quote": "In no event shall Service Provider be liable for any indirect, incidental, or consequential damages..."
}
```

- `quote` 字段直接取自存储在对象存储/数据库中的真实切片原文，绝不采用大模型复述。
- 若大模型输出了不存在的引用标识，依据配置策略执行剥离（`strip`）或直接拒绝（`reject`），坚决不透传伪造引用。

---

## 引用三层保证模型 (Three-Layer Guarantee)

- **L1：标识合法性（Identity Legitimacy）**：模型输出的每一个 `[Sn]` 必须精确匹配本次门控通过的候选子切片，由后端严格校验拦截。
- **L2：引用充分性（Coverage）**：声明有据可依的回答必须至少包含一个有效引用。若模型未标注任何有效引用，系统将执行状态标记为 `unverified`（未核验），防止无依据答案混充权威结论。
- **L3：语义支撑度（Semantic Support）**：引用条款是否在语义逻辑上充分支撑答复陈述，属于概率性推断问题，由独立的离线评测体系（RAGAS Faithfulness）量化评估，不与 L1/L2 确定性校验混淆。

---

## 数据隔离与提示词注入防护 (ADR-0031 / ADR-0032)

1. **生成与定位分离**：大模型生成上下文读取 Parent 切片聚合文本；权威引用与行号定位指向 Child 切片。二者在数据结构上严格分离，杜绝将整段父文本冒充为条款原文。
2. **提示词上下文隔离**：检索出的合同文本作为独立数据块包裹于 `<evidence>` 与 `</evidence>` 标签内输入，不直接拼入系统提示词。
3. **协议标记过滤**：在构建输入提示词前，服务端对合同正文进行扫描，强制清洗掉其中可能包含的 `[source:Sn]` 或 `[Sn]` 伪造标记，防止对抗性文档实施提示词注入或伪造引用标识。

---

## 真实坐标字段规范 (ADR-0027)

- `line_start` 与 `line_end`：基于制品库中规范化 Markdown（`parse_artifacts.markdown_object_key`）的 1-indexed 绝对物理行号区间。
- 系统以绝对行号和原文切片（`quote`）作为唯一法律溯源坐标，绝不基于字数估算或脑补页码。

---

## 前端工程交互契约

- 遵循类型化 HTTP/SSE 数据结构；
- 将 `[Sn]` 渲染为具有无障碍焦点的交互式引用标签；
- 支持 Popover 悬浮快速预览与右侧抽屉式原文全景检视；
- 完备处理加载中、空状态、错误归因与代际撤销；
- 严禁从前端模型文本中自行正则推测或编造坐标。
