# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React + TypeScript + Vite+ (vp CLI), TanStack Router/Query, Base UI, lucide, Tailwind, motion

## Users

涉美业务企业法务团队、执业律师、商业合同审查人员及合规审计人员，在面对复杂商业协议（MSA、NDA、SaaS 许可、采购供应协议等）的审查、条款比对、风险排查场景下，需要快速获取可信、可追溯至具体合同条款行号的权威解答与风险提示。

## Product Purpose

提供基于 LangGraph 的 Agentic RAG 平台，面向美国商业合同与法律协议文档（MSA/NDA/SOW/SaaS License/Employment Agreement）的解析、条款索引、双通道混合检索与流式问答。核心价值是让法务与商务人员快速获得带条款引用验证的准确答案，确保每一条审查意见都有据可查。

## Positioning

通过**可验证引用**和**多通道混合检索**（dense/keyword）确保合同审查结论的绝对可信度。每个引用都经过后端验证，包含合同名、页码、行号和原文引用，区别于通用 RAG 系统的无法溯源与幻觉编造问题。LangGraph agent 架构支持复杂的多轮法律推理和检索策略。

## Operating Context

- **管理端工作流**：创建法务知识库（如"主服务协议库"、"保密协议模板库"）→ 上传多格式合同文档（PDF/DOCX/TXT/MD/HTML/扫描件）→ 监控摄取任务状态（解析/分块/嵌入/索引）→ 使用检索调试工具验证条款召回质量。
- **对话端工作流**：选择知识库 → 发起自然语言提问 → 实时接收流式答案 → 查看答案中的引用标记 → 点击引用查看原文位置和上下文。
- **技术环境**：后端 FastAPI + LangGraph，PostgreSQL 存储业务数据，Qdrant 向量索引，RabbitMQ 任务队列，SSE 实时推送。

## Capabilities and Constraints

- **支持格式**：PDF, DOCX, PPTX, XLSX, TXT, Markdown, HTML, 图像（OCR）。
- **检索能力**：BGE-M3 dense embeddings, PostgreSQL keyword retrieval, BGE-reranker-v2-m3 reranking, RRF 融合。
- **引用协议**：每个引用包含 `citation_id`, `document_name`, `parent_id`, `child_ids`, `heading_path`, `page_start`, `page_end`, `line_start`, `line_end`, `quote`，后端验证每个引用ID的存在性。
- **约束**：商业合同与法务数据高度保密，需支持用户级与租户级隔离；答案必须附带可验证条款引用，不得编造合同义务；agent 循环必须有界，防止无限推理。
- **术语**：知识库（knowledge base）、文档版本（document version）、摄取任务（ingestion job）、引用（citation）、检索轮次（retrieval rounds）、证据状态（evidence status）。

## Brand Commitments

- **视觉方向**：中性灰白为底色，主色为法务专业蓝 #1677FF（标记与填充；承载正文级文字时用可读变体 #0958D9）；状态色：成功 #52C41A、进行中 #1677FF、告警 #FAAD14、失败 #FF4D4F。深色模式使用材质深灰的四个台阶（桌板 #111216、岛屿/画布 #1A1D24、浮起层 #1F2228、悬停 #282C35）与降饱和白文字（#E6E6E6 / #8C8C8C），不以纯黑纯白强对比阅读。两个工作区的底板不同：聊天 #F4F5F7 / #111216，管理台 #F8F9FA / #14161A。
- **设计规范**：具体 token、组件皮肤与状态词以 `DESIGN.md` 为准；本文件的视觉描述与 `DESIGN.md` 冲突时，以 `DESIGN.md` 为准。
- **组件约束**：仅使用 Base UI 内置组件与 `lucide-react` 字形，不允许自定义组件库。
- **字体**：系统默认字体栈（-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif）。
- **语气**：专业、严谨、客观、可信，严格使用美国商事合同法律术语，避免过度营销化语言；在法律场景下强调责任边界准确性与条款可追溯性。

## Evidence on Hand

- 已有后端 API/SSE 契约（`docs/architecture/frontend-contract.md`）。
- 已有领域模型、数据流、摄取和检索管道规范（`docs/architecture/`）。
- 前端工程层已部署基础设施（TanStack Query, typed API schemas, SSE client）。
- **缺失**：真实涉密合同文档示例、企业律所 logo。原型阶段将使用合成商业合同占位内容，标记为示意数据。

## Product Principles

1. **引用优先（Citation-First）**：每个答案必须附带可验证的引用链条，引用是产品信任的基石，UI 需让引用清晰可见、易于点击查看。
2. **透明的检索过程（Transparent Retrieval）**：管理端提供检索调试工具，暴露 dense/keyword 双通道的原始结果、融合排序、rerank 打分，帮助用户理解答案来源。
3. **渐进式加载（Progressive Disclosure）**：对话界面优先展示答案流式输出，引用以行内标记呈现，点击后展开详情面板；管理界面将复杂的摄取任务、版本历史折叠在需要时展开。
4. **任务状态可见（Visible Task State）**：摄取任务的每个阶段（parse/chunk/embed/index）都有明确状态指示，用户随时知道文档处理进展。
5. **商事合同场景优化（Contract Context Optimized）**：支持复杂长协议（如数十页 MSA/SLA）的多层级条款标题导航（Article / Section / Clause），支持多版本条款对比（Redline / 协议修订版），支持按合同类型筛选（MSA/NDA/SOW/SaaS）。

## Accessibility & Inclusion

- 遵循 WCAG 2.1 AA 标准。
- 流式文本输出需保证屏幕阅读器可访问（使用 `aria-live="polite"`）。
- 引用标记需提供可识别的焦点状态和键盘导航。
- 色彩对比度符合 WCAG 2.1 AA：正文与占位符 ≥4.5:1（主文本 #1D1D1F 对 #FFFFFF 为 16.8:1，正文级次要文本与占位符使用 #6E6E73，对 #FFFFFF 为 5.1:1）；大号文本与控件边界 ≥3:1（#86868B 对 #FFFFFF 为 3.6:1，作控件边界用）。
- 摄取任务状态使用图标+文字双重指示，不依赖颜色单一信息传递。
