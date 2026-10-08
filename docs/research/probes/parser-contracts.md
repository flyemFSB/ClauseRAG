# 实证探针：解析路由与规范化 Markdown 契约（Parser contracts）

> **后续变更（ADR-0029）**：本文记录的样本正文中包含“图谱召回”条目，该文案已随图谱通道一并从
> `scripts/probes/parsing_samples.py` 删除（现为“重排：基于 BGE-Reranker-v2-M3”）。文中的样本片段是
> 当时的输出快照，保留原样。

日期：2026-10-02 · 环境：Windows PowerShell 7 · CPython 3.12.14 · uv 0.12.13 · cwd `D:\YZB\RAG`
凭证来源：仓库根 `.env` 的 `PADDLEOCR_API_KEY`（本文件一律写 `<token>`，绝不回显）。
原始输出保存在 `.probe\parser\out-*.txt`、样本在 `.probe\samples\`（`.probe/` 已 gitignore）。
本文件内所有命令与数字均为本轮**实际执行**所得；凡属推断一律显式标注「**推断**」。

探针 venv（全部隔离，未污染项目 `.venv`）：
`.probe\venv-parser`（anydoc）、`.probe\venv-samples`（样本生成 + HTML 转换库）、
`.probe\venv-docling`、`.probe\venv-unstructured`、`.probe\venv-markitdown`、`.probe\venv-native`、`.probe\venv-stack`。

---

## 状态：VERIFIED

一句话结论：**首版解析栈 = `firecrawl-anydoc`（Office/PDF）+ `html-to-markdown`（HTML）+ `PaddleOCR-VL` 异步 API（图片/扫描件），共 2 个 Python 包、0 个外部二进制、0 个传递依赖**；
三者均已用真实文件跑通；`anydoc` 对全部 4 种二进制格式**输出确定性**（3 次转换 SHA-256 完全一致）；
PaddleOCR-VL 用仓库 `.env` 的 key 真实调用成功（`PaddleOCR-VL` 模型），返回的 Markdown 亦确定性。
唯一未决项是 PaddleOCR-VL 的**限流/并发数值**与部分错误码（见 C 的 UNVERIFIED 清单）。

---

## A. 本地多格式解析库的身份与选型

### A1. 名字查证：`anydoc` 这个名字下面有三个不同的东西

| 候选名 | PyPI 实况 | 判定 |
|---|---|---|
| `anydoc` | **0.0.0**，summary = 「🔌 Turn your GitHub Markdown documentation into a Q&A bot for Slack」，`requires-python <3.11,>=3.8`，仅 1 个 release，上传于 2023-04-27，仓库 `alvarobartt/anydoc` | **否决**：是 Slack 问答机器人，不是文档解析器，且不支持 3.12 |
| `anydoc-py` | `https://pypi.org/pypi/anydoc-py/json` → **HTTP 404，包不存在** | 不存在 |
| **`firecrawl-anydoc`** | **0.2.4**，`requires-python >=3.10`，MIT，**无 Requires-Dist**，cp310-abi3 预编译 wheel（含 `win_amd64`），仓库 `github.com/firecrawl/anydoc` | **采用**：文档里写的「AnyDoc 适配器」指的就是它（`pip install firecrawl-anydoc`，`import anydoc`） |

查询命令（可复跑）：

```powershell
foreach ($n in @('anydoc','anydoc-py','firecrawl-anydoc')) {
  try { $r = Invoke-RestMethod "https://pypi.org/pypi/$n/json" -SkipHttpErrorCheck
        "$n -> $($r.info.name) $($r.info.version) py=$($r.info.requires_python)" }
  catch { "$n -> 404" }
}
```

实测输出：

```
anydoc -> anydoc 0.0.0 py=<3.11,>=3.8
anydoc-py -> 404
firecrawl-anydoc -> firecrawl-anydoc 0.2.4 py=>=3.10
```

`firecrawl-anydoc` 官方身份（GitHub API 实测）：

```
full_name=firecrawl/anydoc
desc=Convert Word, PowerPoint, Excel, OpenDocument, RTF, EPUB, CSV, and PDF to clean Markdown. Built in Rust, with Node.js and Python bindings.
license=MIT   stars=22396   forks=1415
created=2026-08-03   pushed=2026-08-28   open_issues=103   archived=False
```

安装与元数据实测（`uv pip install --python .probe\venv-parser\Scripts\python.exe firecrawl-anydoc`）：

```
Resolved 1 package in 232ms
Installed 1 package in 36ms
 + firecrawl-anydoc==0.2.4

Requires-Python: >=3.10
Requires-Dist  : None                     <- 零传递依赖
License        : MIT
Classifiers    : ['Programming Language :: Rust', 'Typing :: Typed', ...]
file kinds     : 1×.pyd(原生扩展) 1×.pyi(类型桩) 1×.py 1×.typed
installed      : 8.3 MB
```

**不需要任何外部二进制**：只有 1 个 `.pyd`（Rust 静态编译进 wheel），无 LibreOffice / poppler / tesseract 调用。
实测「把 socket 禁掉再转换」仍成功，证明**完全离线、无模型下载**：

```
### offline behaviour (socket disabled)
  anydoc offline docx: OK len=366 (no network needed)
  anydoc offline pdf : OK len=346
```

### A2. 覆盖范围、source location、确定性

公开 API（`inspect.signature` 实测）：

```python
anydoc.to_markdown(path, *, ocr='reject'|'hosted', api_key=None, api_url=None) -> str
anydoc.to_markdown_bytes(data, format=None, *, ocr=..., ...) -> str
anydoc.to_document(data, format=None) -> Document          # 注意：PDF 不支持
anydoc.format_from_bytes(b) / format_from_extension('.docx') / format_from_path(p)
```

- **格式覆盖（实测 `format_from_extension`）**：`.doc .docx .docm → doc/docx`、`.ppt .pptx → ppt/pptx`、`.xls .xlsx → xlsx`、`.csv .rtf .epub .odt .ods .odp → 对应`；
  `.html .htm .txt .md .markdown .png .jpg` **全部返回 `None`**（不支持的输入，正合我们需要自己路由的格式）。
  → 覆盖 PDF/DOCX/PPTX/XLSX **全部 4 种首版二进制格式**。
- **source location：没有页/行定位**。文档模型 `Document{blocks, assets, notes}` → `Block{kind, level, anchor, content, list, table, blocks}`。
  实测 `Block.anchor` 在 docx/xlsx 为 `None`，在 pptx 是**标题文本**（用于文内锚点），**不是页码也不是行号**；
  PDF 输出 Markdown **不含任何分页标记**（无 `\x0c`），2 页 PDF 输出长度 346 字符、`formfeed=False`。
  → `page_start/page_end` **无法**从 anydoc 得到；`line_start/line_end` 只能由规范化后的 Markdown 行偏移自行计算。
  这是本方案唯一的真实缺口，见「未决项」。
- **确定性：成立**。同一输入连续 3 次 `to_markdown`，SHA-256 完全一致（见 B 表）。输出**不含时间戳、不含随机 id**。
- **PDF 的标题级别是启发式推断**（按字号）：`multipage.pdf`（14pt 标题 + 11pt 正文）里正文被判成 `##`，说明字号推断会把正文误判为标题。这是**保真度风险**，规范化阶段应保留但可复核。

### A3. 被否决候选与理由（全部真实安装/运行过）

| 候选 | 实测依赖足迹 | 实测转换结果 | 否决理由 |
|---|---|---|---|
| **docling 2.132.0** | **107 包 / 1026 MB**（含 torch 2.14.0、torchvision、transformers、opencv、rapidocr） | docx/pptx/xlsx/html/txt/md 保真度最好（`#`→`##`→`###` 层级正确）；**PDF 与 PNG 失败** | PDF 路径必须下载 HF 布局模型，本机 `huggingface.co` **不可达**（12s 超时，WinError 10060）；加 `HF_ENDPOINT=https://hf-mirror.com` 后仍被 Xet CAS `401 Unauthorized` 拦住，再加 `HF_HUB_DISABLE_XET=1` 才跑通，**2 页 PDF 耗时 36.5 s**（anydoc 1.5 ms），且 PDF 标题层级被压平成全 `##`、表格被压平成一行。1026 MB + torch + 依赖第三方镜像 → 不适合首版 |
| **unstructured 0.27.10** | 基础 73 包；加 `[docx,pptx,xlsx,pdf,md]` 后 **132 包 / 1356 MB** | docx 耗时 **89.9 s**；pptx/xlsx/pdf 有 `page_number`；**PNG 路径失败**（要下 HF `yolox_l0.05.onnx`） | 体积最大、最慢、PNG/OCR 路径被 HF 阻断；而且**根本没有 Markdown 序列化器**（只给 element 列表，Markdown 得自己写），违背 `ingestion-pipeline.md`「parser internals are not reimplemented」 |
| **markitdown**（基础） | 26 包，但**无 Office/PDF 能力**：4 种格式全部 `MissingDependencyException` | — | 基础包不可用 |
| **markitdown + `[docx,pptx,xlsx,pdf]`** | 43 包（+17） | docx/pptx/xlsx/pdf 成功且确定性 | ①**PNG 静默返回空串**（`len=0`，不抛错）——正是 `backend-guidelines.md` 禁止的「degraded result as empty success」；②xlsx 输出 `NaN` / `Unnamed: 1`（pandas 残留）；③docx 丢了标题层级（Title 变成普通文本）；④PDF 输出**没有任何标题**（结构全丢）；⑤pptx 插入 `<!-- Slide number: N -->` 注释噪音 |
| **原生库组合**（`pypdf 6.19.0` + `pymupdf 1.28.2` + `python-docx 1.2.0` + `python-pptx 1.0.2` + `openpyxl 3.1.5`） | **11 包 / 77 MB**，无外部二进制 | pypdf 能按页取文本（`pages=2`）；pymupdf 能取字号（`[10.0,12.0,13.0,16.0]`）但 **`find_tables()` 找到 0 个表**；python-docx 能取样式名（`Title`/`Heading 1`/`List Bullet`） | **没有 Markdown 序列化器**。要用它就得自己写并长期维护「多格式 → 规范化 Markdown」转换器（标题级别、列表、表格、合并单元格、脚注、嵌套……），与 `ingestion-pipeline.md` 的「适配器是自定义代码，但 parser 内部不重写」直接冲突。且它是 5 个库而非 1 个 |

**选型结论**：`firecrawl-anydoc` 一个库覆盖 PDF/DOCX/PPTX/XLSX，1 个包、无外部二进制、离线、确定性、MIT；
并且它内置的 `NeedsOcrError.pages` 恰好就是「扫描件 → 交给 PaddleOCR-VL」的路由信号（见 C）。
HTML 另用 `html-to-markdown`（见 D）。**不需要 docling/unstructured/markitdown，也不需要手写原生适配器。**

---

## B. 逐格式实测

样本由本地库生成（`.probe\parser\gen_samples.py`，不下任何文件）：中文正文 + 三级标题 + 项目符号列表 + 一个 3 列 4 行表格。

```powershell
uv venv .probe\venv-samples --python 3.12
uv pip install --python .probe\venv-samples\Scripts\python.exe python-docx python-pptx openpyxl reportlab pillow
& .probe\venv-samples\Scripts\python.exe -u .probe\parser\gen_samples.py
```

```
sample.docx    37325 bytes    sample.pptx    30854 bytes    sample.xlsx     5511 bytes
sample.pdf     25025 bytes    sample.html     1103 bytes    sample.md        770 bytes
sample.txt       545 bytes    sample_cn.png  42903 bytes
```

转换命令：

```powershell
& .probe\venv-parser\Scripts\python.exe -u .probe\parser\anydoc_probe.py   # -> .probe\parser\out-anydoc.txt
```

### B1. 逐格式结果

| 格式 | 成功 | 耗时 (ms) 首次/连跑 3 次 | 结构保真度 | page/line 定位 | 错误 |
|---|---|---|---|---|---|
| `.docx` | ✅ | 23.8 / 14.5 / 16.5 / 11.9 | 标题 ✅（但 **Title 与 Heading1 都塌成 `#`**，Heading2→`##`）、列表 `-` ✅、表格 ✅ 且带表头行 | ❌ 无 | — |
| `.pptx` | ✅ | 2.0 / 1.4 / 1.2 / 1.1 | 标题 ✅（标题占位符→`##`）、表格 ✅；**文本框内的项目符号退化为普通段落** | ❌ 无（`Block.anchor` 只是标题文本） | — |
| `.xlsx` | ✅ | 1.2 / 0.5 / 0.6 / 0.5 | 整张表 → 一个 3 列 14 行 Markdown 表；`header_rows=0`（**未识别表头**，尽管 A1 是加粗） | ❌ 无 | — |
| `.pdf` | ✅ | 18.7 / 1.6 / 1.4 / 1.5 | 标题按字号推断 ✅（`#`/`##`/`###`）、`-` 列表 ✅；**第 2 页的表格被压成一行普通文本**；无分页标记 | ❌ 无 | — |
| `.html` | ❌ | — | — | — | `UnsupportedError: unsupported input: unrecognized file content and extension` |
| `.txt` | ❌ | — | — | — | 同上（由 passthrough 分支处理） |
| `.md` | ❌ | — | — | — | 同上（直接校验规范化） |
| `.png` | ❌ | — | — | — | `UnsupportedError`（→ 路由到 PaddleOCR-VL） |
| `scan_only.pdf`（纯图） | ❌ | — | — | — | **`NeedsOcrError pages=[1]`，`page_count=1`，`str(e)="page 1 of 1 needs OCR"`** |
| `encrypted.pdf` | ❌ | — | — | — | `EncryptedError: document is encrypted` |
| 空字节 / 乱码 / 截断 docx | ❌ | — | — | — | `UnsupportedError: unrecognized file content: name the format explicitly` |
| `to_document(pdf)` | ❌ | — | — | — | `UnsupportedError: PDF converts directly to Markdown; use to_markdown or to_markdown_bytes` |
| 非法 format 名 | ❌ | — | — | — | `ValueError: unknown format "nope"; expected one of doc, docx, odt, pdf, ppt, pptx, rtf, epub, xlsx, ods, odp, csv` |

真实 Markdown 片段（裁剪）：

`.docx`：
```markdown
# 知识库检索增强生成系统设计说明

# 一、系统概述

本系统面向企业内部知识管理场景，提供文档解析、向量检索与答案生成能力。

## 1.1 检索通道

检索通道包括稠密向量召回、关键词召回与图谱召回三路，结果通过应用层 RRF 融合。

- 稠密召回：基于 BGE-M3 向量
- 关键词召回：基于 PostgreSQL pg_trgm
- 图谱召回：基于 LightRAG

## 1.2 父子块模型

子块作为检索与引用锚点，父块为答案提供完整语义上下文。

| 阶段 | 负责组件 | 产物 |
| --- | --- | --- |
| 解析 | 解析路由适配器 | document.md |
| 切分 | 父子块切分器 | chunks.jsonl |
| 索引 | 向量与关键词索引 | Qdrant 点集 |
```

`.pdf`（注意第 2 页表格被压平）：
```markdown
### 1.1 检索通道

检索通道包括稠密向量召回、关键词召回与图谱召回三路，结果通过应用层 RRF 融合。

- 稠密召回：基于 BGE-M3 向量
- 关键词召回：基于 PostgreSQL pg_trgm
- 图谱召回：基于 LightRAG
### 1.2 父子块模型          <- 注意：`###` 前缺空行

## 1.3 处理阶段表

阶段 | 负责组件 | 产物 解析 | 解析路由适配器 | document.md 切分 | 父子块切分器 | chunks.jsonl 索引 | 向量与关键词索引 | Qdrant 点集
```

### B2. 确定性（关键）

同一文件连续 `to_markdown` **3 次**，比较输出 Markdown 的 SHA-256：

```
FILE sample.docx  DETERMINISTIC=True  sha256 run1=7440bf24d04280af run2=7440bf24d04280af run3=7440bf24d04280af
FILE sample.pptx  DETERMINISTIC=True  sha256 run1=1223e4e2f69857d7 run2=1223e4e2f69857d7 run3=1223e4e2f69857d7
FILE sample.xlsx  DETERMINISTIC=True  sha256 run1=0cd1222da105a855 run2=0cd1222da105a855 run3=0cd1222da105a855
FILE sample.pdf   DETERMINISTIC=True  sha256 run1=cb51832274d222b7 run2=cb51832274d222b7 run3=cb51832274d222b7
```

**4/4 格式完全一致，无时间戳、无随机 id、无差异来源。**
（对照：`markitdown` 4 种格式亦 `det=True`；`unstructured` 亦 `det=True`；docling 亦 `det=True`。
PaddleOCR-VL 见 C。所以「确定性」不是选型差异点，但 anydoc 的确定性是**纯本地、无网络**的确定性。）

### B3. 依赖足迹（`uv pip install` 前后包数差，实测）

| 组合 | 包数（净） | 安装体积 | 外部二进制 | 备注 |
|---|---|---|---|---|
| **`firecrawl-anydoc` 0.2.4** | **1** | 8.3 MB | 无 | 0 传递依赖；离线可用 |
| **`firecrawl-anydoc` + `html-to-markdown`** | **2** | 25.2 MB | 无 | 推荐栈（`.probe\venv-stack` 实测） |
| `docling` 2.132.0 | 107 | 1026 MB | 需 HF 布局模型 | PDF 需镜像绕过 |
| `unstructured` 0.27.10 + extras | 73 → **132**（+59） | 1356 MB | 需 HF yolox | PNG/OCR 需 HF |
| `markitdown` + `[docx,pptx,xlsx,pdf]` | 26 → **43**（+17） | — | 无 | 基础包无 Office/PDF 能力 |
| 原生库组合（5 库） | 11 | 77 MB | 无 | 无 Markdown 序列化器 |
| `markdownify`（对照） | +4（bs4, soupsieve, six, typing-extensions） | 0.09 MB | 无 | Setext 标题，见 D |

---

## C. PaddleOCR-VL 真机契约

**状态：VERIFIED（真实调用成功）**，但有若干与文档不一致之处，逐条列出。

### C0. 官方文档（已确证来源）

| 文档 | URL | 更新时间 |
|---|---|---|
| 异步 API 使用文档 | `https://ai.baidu.com/ai-doc/AISTUDIO/fml7mozw5` | 2026-02-04 |
| PaddleOCR-VL_API（同步） | `https://ai.baidu.com/ai-doc/AISTUDIO/2mh4okm66` | — |
| PaddleOCR-VL-1.5_API（同步） | `https://ai.baidu.com/ai-doc/AISTUDIO/Cmkz2m0ma` | 2026-06-16 |
| API 配额规则和错误码说明 | `https://ai.baidu.com/ai-doc/AISTUDIO/Xmjclapam` | 2026-09-08 |

（这些页面是 Gatsby SPA，正文内联在 HTML 里；用 `Invoke-WebRequest` 取回后正则抽取即可，无需登录。）

### C1. 调用方式（已确证）

```
Base URL : https://paddleocr.aistudio-app.com/
提交任务 : POST /api/v2/ocr/jobs
查询任务 : GET  /api/v2/ocr/jobs/{jobId}
批量查询 : GET  /api/v2/ocr/jobs/batch/{batchId}
鉴权头   : Authorization: Bearer {access_token}
```

- 传**本地文件**：`Content-Type: multipart/form-data`，字段 `file`(bytes) + `model` + `optionalPayload`(JSON 字符串)
- 传**文件链接**：`Content-Type: application/json`，`{"fileUrl": "...", "model": "...", "optionalPayload": {...}}`
- `model` 必填，可选 `PaddleOCR-VL-1.5` / `PaddleOCR-VL` / `PP-StructureV3` / `PP-OCRv5`
- 可选 `pageRanges`（如 `"2,4-6"`、`"2--2"`）、`batchId`

> **重要差异**：同步 API 文档用的鉴权头是 `Authorization: token {TOKEN}`，
> 而异步 API 文档（上面这套、也是本次实测成功的）用的是 `Authorization: Bearer {TOKEN}`。
> 两者不通用。且同步文档明确写「API_URL 及 TOKEN 请访问 `https://aistudio.baidu.com/paddleocr/task` 在 API 调用示例中获取」——
> **同步 API 的 URL 是按用户/模型分配的**，所以 `.env` 里空的 `PADDLEOCR_BASE_URL` 无法靠猜路径补齐（实测 `https://paddleocr.aistudio-app.com/api/v1/ocr` 恒为 404）。
> 异步 API 的 Base URL 是固定的，这才是仓库该用的那一个。

### C2. 真实调用（本仓库 `.env` 的 key，模型 `PaddleOCR-VL`）

命令（key 只从 `.env` 读入环境变量，绝不回显）：

```powershell
$k=$null; Get-Content .env | ForEach-Object { if ($_ -match '^\s*PADDLEOCR_API_KEY\s*=\s*(.+)$') { $k=$Matches[1].Trim() } }
$env:PD_KEY=$k
& .probe\venv-parser\Scripts\python.exe -u .probe\parser\paddleocr_full.py
```

实测输出（裁剪）：

```
A. DETERMINISM: same PNG submitted 3 times
  run0: poll_s=0.2 pages=1 sha=eee662321b420bbe len=64
    md='知识库检索增强生成系统\n\n稠密向量召回与关键词召回并行执行\n\n结果通过应用层 RRF 融合后再重排\n\nOCR 探针样本 2026'
  run1: ... sha=eee662321b420bbe len=64   (同上)
  run2: ... sha=eee662321b420bbe len=64   (同上)
  DETERMINISTIC=True

B. SCANNED PDF (image-only)
  state=done poll_s=44.4 progress={'totalPages': 1, 'extractedPages': 1}
  markdown.text='## 知识库检索增强生成系统\n\n稠密向量召回与关键词召回并行执行\n\n结果通过应用层 RRF 融合后再重排\n\nOCR 探针样本 2026'
  page_count=1 width=1191 height=1684
  parsing_res_list labels=['paragraph_title', 'text', 'text', 'text']
  first bbox=[43, 350, 559, 412]

C. TEXT PDF (sample.pdf, 2 pages)
  state=done poll_s=57.2 progress={'totalPages': 2, 'extractedPages': 2}
  markdown.text:
## 知识库检索增强生成系统设计说明

## 一、 系统概述

本系统面向企业内部知识管理场景，提供文档解析、向量检索与答案生成能力。

### 1.1 检索通道

检索通道包括稠密向量召回、关键词召回与图谱召回三路，结果通过应用层 RRF 融合。

- 稠密召回：基于 BGE-M3 向量

- 关键词召回：基于 PostgreSQL pg trgm

- 图谱召回：基于 LightRAG

### 1.2 父子块模型

子块作为检索与引用锚点，父块为答案提供完整语义上下文。
  layoutParsingResults=2 (每页一个)
    page[0] page_count=2 labels=['paragraph_title','paragraph_title','text','paragraph_title','text','text','text','text','paragraph_title','text']
    page[1] page_count=2 labels=['paragraph_title','content']
```

**响应结构（真实、完整）**：

```json
{
  "logId": "<uuid>",
  "result": {
    "layoutParsingResults": [
      {
        "prunedResult": {
          "page_count": null, "width": 1000, "height": 320,
          "model_settings": { "use_doc_preprocessor": true, "use_layout_detection": true,
            "use_chart_recognition": false, "use_seal_recognition": false,
            "use_ocr_for_image_block": false, "format_block_content": false,
            "merge_layout_blocks": true,
            "markdown_ignore_labels": ["number","footnote","header","header_image","footer","footer_image","aside_text"],
            "return_layout_polygon_points": true },
          "parsing_res_list": [
            { "block_label": "text",
              "block_content": "知识库检索增强生成系统\n稠密向量召回与关键词召回并行执行\n...",
              "block_bbox": [1, 11, 517, 296], "block_id": 0, "block_order": 1, "group_id": 0 }
          ],
          "doc_preprocessor_res": { "model_settings": {...}, "angle": 0 },
          "layout_det_res": { "boxes": [
            { "cls_id": 17, "label": "paragraph_title", "score": 0.451, "coordinate": [0,12,519,72], "order": 1 },
            { "cls_id": 22, "label": "text", "score": 0.429, "coordinate": [1,11,517,296], "order": 2 } ] }
        },
        "markdown": { "text": "<Markdown 文本>", "images": {} },
        "outputImages": { "layout_det_res": "https://...jpg?authorization=..." },
        "inputImage": "https://...jpg?authorization=..."
      }
    ],
    "dataInfo": { "width": 1000, "height": 320, "type": "image" },
    "preprocessedImages": ["https://...jpg?authorization=..."]
  },
  "errorCode": 0, "errorMsg": "Success"
}
```

**Markdown 文本字段名 = `result.layoutParsingResults[i].markdown.text`**（已确证）。
`layoutParsingResults` **每页一个元素**，所以**页码 = 数组下标**（这是 anydoc 给不了的定位信息）。
`prunedResult.parsing_res_list[].block_bbox` 给元素级 bbox。

任务状态响应（`GET /api/v2/ocr/jobs/{jobId}`，真实）：

```json
{"traceId":"...","code":0,"msg":"Success",
 "data":{"jobId":"99432287566266368","state":"done",
   "extractProgress":{"startTime":"2026-10-02 17:08:25","endTime":"2026-10-02 17:08:28",
                      "totalPages":1,"extractedPages":1},
   "resultUrl":{"jsonUrl":"https://paddleocr-store-5.bj.bcebos.com/...json?authorization=bce-auth-v1%2F..."}}}
```

- `state` 取值实测到 `running` / `done`（文档另列 `pending` / `failed`）。
- 耗时：PNG 单页 **0.2 s**（命中缓存/极快），`scan_only.pdf` **44.4 s**，`sample.pdf` 2 页 **57.2 s**（≈28 s/页，异步轮询口径）。
- **与文档不一致**：文档说 `resultUrl` 同时给 `jsonUrl` 与 `markdownUrl`；本轮 **4 次成功任务全部只有 `jsonUrl`**，
  Markdown 必须从 `jsonUrl` 里的 `result.layoutParsingResults[i].markdown.text` 取。

### C3. 失败路径（全部真实）

| 场景 | HTTP | 响应体（全文） |
|---|---|---|
| 不带鉴权头 | **401** | `{"traceId":"...","code":401,"msg":"Unauthorized"}` |
| 错误 token（40 个 0） | **401** | `{"traceId":"...","code":401,"msg":"Unauthorized"}` |
| 错误模型名 `NoSuchModel-v9` | **400** | `{"traceId":"...","code":10007,"msg":"模型传参错误"}` |
| 空文件 | **400** | `{"traceId":"...","code":10004,"msg":"文件格式不支持"}` |
| `.html` 当图片传 | **400** | `{"traceId":"...","code":10004,"msg":"文件格式不支持"}` |
| `pageRanges="abc"` | **400** | `{"traceId":"...","code":10008,"msg":"请求参数错误，请检查 pageRanges 参数格式或内容"}` |
| 不存在的 jobId | **404** | `{"traceId":"...","code":11001,"msg":"jobId 不存在"}` |
| 队列满（VL-1.5，重试 8 次 ~80 s 仍如此） | **400** | `{"traceId":"...","code":10010,"msg":"任务提交队列已满，请稍后重试"}` |
| **`optionalPayload` 里塞未定义键 `noSuchParam`** | **200** | `{"code":0,"msg":"Success","data":{"jobId":"99432884059201536"}}` |

两条**与文档不一致、且对错误映射设计有直接影响**的观测：

1. **空文件实测是 `10004 文件格式不支持`，不是文档写的 `10001 空文件`。**
2. **未定义的 `optionalPayload` 键被静默忽略并返回 200**，不是文档写的 `10008 请求参数错误`。
   → 客户端**不能**靠服务端校验来发现自己写错的参数名；适配器必须自己校验参数白名单。

另：`PaddleOCR-VL-1.5` 队列连续 8 次 `10010`，而 `PaddleOCR-VL` 立即 200 —— 说明 `10010` 是**按模型排队**的瞬时状态，必须走有限重试。

**作业级失败的分类（2026-10-07 实测补全）。** 轮询响应里 `code`/`msg` 描述的是这次查询本身（
查询成功时恒为 `0`/`Success`），**作业为什么失败在 `data.errorMsg` 里**（官方轮询示例读的就是它）。
实测一次两页扫描件在提交后约 1 s 就被供应商置为 `state="failed"`，响应仍是 `code=0,
msg="Success"`：旧代码拿信封的 code 当作业失败理由，于是把它归为确定性的 `OcrProviderError`，
版本被写成 `parse_failed` + 人工重试。正确分类是：**提交已被接受后的作业级失败是瞬态**，
由作业的尝试预算封顶，`data.errorMsg` 记入 `error_message`；确定性状态留给供应商明确给出的
文档/凭据类信号（`_UNREADABLE_CODES`、401/403、`_OPERATIONAL_CODES` 等）。
该行为由 `scripts/probes/parsing.ps1` 的第 9 步断言（`TransientParseError`、作业回到 `pending`
且 `not_before` 未到、版本仍在其运行态）。

### C4. 限流与大小限制（文档值 vs 实测）

| 项 | 值 | 来源 |
|---|---|---|
| 每日配额 | **20000 页 / 用户 / 模型**；超出 → 429 | 文档 Xmjclapam（2026-09-08） |
| 单次请求页数 | ≤ **1000** 页 PDF | 异步文档 fml7mozw5 |
| 单文件（链接） | ≤ **200 MB** | 异步文档 |
| 单文件（本地上传） | ≤ **50 MB** | 异步文档 |
| `batchId` 任务数 | ≤ 100 条 | 错误码 10009 |
| 同步接口默认页数 | 默认只处理前 **100** 页（除非 serving 配置 `max_num_input_imgs: null`） | 同步文档 Cmkz2m0ma —— **与异步文档的 1000 页口径不一致** |
| 并发/RPM 上限 | **未证实**：文档只给「12002 请求频率过高 → 429」「10010 队列已满」，**没有给出具体 RPM/TPM 数值** | — |
| 单图像素上限 | 仅有 `minPixels` / `maxPixels` **可调参数**，未给硬上限 | 同步文档 |

### C5. 判定：能否作为「图片 / 扫描件 / 复杂版式」的路由目标

**能。** 三条实证支持：
1. `scan_only.pdf`（纯图 PDF，anydoc 直接 `NeedsOcrError`）经 PaddleOCR-VL 恢复出正确中文并带 `##` 标题，且给 bbox；
2. 2 页文本 PDF 的标题层级（`##`/`###`）被恢复，`layoutParsingResults` 每页一个元素 → 可直接填 `page_start/page_end`；
3. 同一输入 3 次结果 SHA-256 一致 → 确定性。

**但必须显式建模的降级点**（`backend-guidelines.md` 要求显式，不得静默）：
- 文本保真度损失：`pg_trgm` → **`pg trgm`**（下划线被吞），`一、系统概述` → `一、 系统概述`（多一个空格）。
  → 引用校验时不能拿 OCR 结果做精确字符串匹配；citation 的权威引文应回到该页的原文/规范化文本。
- **扫描页的几何失真会被读错**：把 1191×400 的扫描图拉满 A4 页（`/MediaBox [0 0 595 842]`，图像被横向压缩、纵向拉伸）后，本轮实测 `稠密向量召回与关键词召回并行执行` 回读为 `解密向量召回与关键词召回并行执行`；同一图片按原始宽高成页则回读完全正确（同一文件两次提交 SHA-256 相同，且与直接上传该 PNG 的结果逐字节一致）。
  → 送检的页几何不要做非等比重排；这也再次说明「OCR 文本 ≠ 原文字符」。
- 无 `markdownUrl`（只有 `jsonUrl`）→ 适配器必须解析 JSON 再取 `markdown.text`。
- 参数名写错**不会被发现** → 适配器自己做白名单校验。
- `10010` 队列满 → 必须有限重试（本环境 VL-1.5 长时间不可用）。
- 延迟高（≈28 s/页，异步轮询）→ 需要显式 stage timeout，不能按同步短调用设计。

---

## D. HTML → Markdown 的最小选择

### D1. `html-to-markdown` 真实存在

| 项 | 值（实测） |
|---|---|
| 版本 | **3.15.1** |
| License | **MIT** |
| Requires-Python | `>=3.10` |
| Requires-Dist | **None（0 传递依赖）** |
| 形态 | 原生 Rust 扩展（`.pyd`），安装体积 16.79 MB |
| 仓库 | `https://github.com/xberg-io/html-to-markdown`（881 stars，pushed **2026-10-02**，MIT，未归档） |

API（实测）：

```python
import html_to_markdown as m
r = m.convert(html, options=None, visitor=None)   # -> ConversionResult
r.content     # Markdown 字符串
r.document    # 文档模型
r.metadata    # HtmlMetadata
r.tables      # 结构化表格
r.warnings    # 处理告警
m.options.ConversionOptions(heading_style='atx', extract_metadata=True, escape_underscores=False, ...)
```

### D2. 与 `markdownify` 对比（同一 `sample.html`，实测）

| 维度 | `html-to-markdown` 3.15.1 | `markdownify` 1.2.3 |
|---|---|---|
| 依赖包 | **0**（净 1 包） | 2 直接 → **净 4 包**（beautifulsoup4, soupsieve, six, typing-extensions） |
| 耗时 | **0.54 ms** | 2.63 ms |
| 标题风格 | **ATX `#`/`##`/`###`**（`heading_style='atx'` 默认） | **Setext `===`/`---`**（h1/h2） |
| 表格 | ✅ 保留；无 `thead` 时首行正确当表头 | ✅ 保留；**无 `thead` 时先补一行空表头** |
| 嵌套列表 | `- a` / `  * a1` / `- b` | `* a` / `  + a1` / `* b` |
| 下划线转义 | **不转义**：`pg_trgm` | **转义**：`pg\_trgm`（污染正文，破坏精确关键词匹配） |
| 代码块/行内码/图片/实体 | ✅ | ✅ |
| 重复 `<title>` | 不会（只在 frontmatter 里出现一次） | **会**（正文开头多一份 title 文本） |
| 确定性 | ✅ 3 次 SHA-256 一致 | ✅ 3 次 SHA-256 一致 |

### D3. 决策：**只用 `html-to-markdown`**

理由（按重要性）：
1. **标题风格是硬约束**：`data-flow.md` 要求「Prefer Markdown heading … boundaries over character-only splitting」，
   而 `markdownify` 对 h1/h2 产出 **Setext** 下划线式标题，基于 `#` 的标题解析器会漏掉它们。`html-to-markdown` 默认 ATX。
2. **不转义 `_`**：中文语料里 `pg_trgm`、`document_version_id` 这类标识符很常见；`markdownify` 会写成 `pg\_trgm`，
   直接破坏 PostgreSQL 关键词召回与 citation 精确匹配。
3. 依赖 0 vs 4，速度 5×。
4. 名字与 `ingestion-pipeline.md` 已写的 `html-to-markdown` 一致，无需改文档。

**必须注意的一个默认值**：`extract_metadata=True` 会在输出**最前面加 YAML frontmatter**：

```
---
title: 知识库检索增强生成系统设计说明
---

# 知识库检索增强生成系统设计说明
```

规范化阶段必须显式传 `ConversionOptions(extract_metadata=False)`（实测可完全去掉），
否则开头的 `---` 可能被下游当成水平线或 Setext 下划线。这是本次实测发现的唯一坑。

---

## E. 路由表建议

| 扩展名 | MIME | 适配器 | 依据 |
|---|---|---|---|
| `.pdf` | `application/pdf` | `anydoc` → 若 `NeedsOcrError` 则 `paddleocr-vl` | **实测**：anydoc 转换成功、确定性；纯图 PDF 实测抛 `NeedsOcrError pages=[1]` |
| `.docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | `anydoc` | **实测** |
| `.pptx` | `application/vnd.openxmlformats-officedocument.presentationml.presentation` | `anydoc` | **实测** |
| `.xlsx` | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` | `anydoc` | **实测** |
| `.txt` | `text/plain` | 直读解码 → 规范化（不经解析库） | **实测**：anydoc 对它抛 `UnsupportedError`，需自己的分支 |
| `.md` | `text/markdown` | 校验 + 直接规范化 | 文档规定；**实测** anydoc 抛 `UnsupportedError` |
| `.markdown` | `text/markdown` | 同 `.md` | **推断**（纯扩展名别名；`mimetypes` 实测两者都映射到 `text/markdown`） |
| `.html` | `text/html` | `html-to-markdown`，`extract_metadata=False` | **实测** |
| `.htm` | `text/html` | 同 `.html` | **推断**（`mimetypes` 实测映射一致） |
| `.png` | `image/png` | `paddleocr-vl` | **实测** |
| `.jpg` | `image/jpeg` | `paddleocr-vl` | **推断**（与 `.png` 同一分支；`.jpg` 未单独跑） |
| `.jpeg` | `image/jpeg` | `paddleocr-vl` | **推断** |
| `.webp` | `image/webp` | `paddleocr-vl` | **推断**；⚠ **`mimetypes.guess_type('.webp')` 在 Windows CPython 3.12 实测返回 `None`** → 必须显式映射，不能依赖 stdlib |
| `.bmp` | `image/bmp` | `paddleocr-vl` | **推断** |
| `.tif` | `image/tiff` | `paddleocr-vl` | **推断**（文档明确支持 TIFF，多页按页处理） |
| `.tiff` | `image/tiff` | `paddleocr-vl` | **推断** |

MIME 实测对照命令与结果：

```powershell
& .probe\venv-parser\Scripts\python.exe -u .probe\parser\final_checks.py
```

```
    .pdf       guessed='application/pdf'                                          match=True
    .docx      guessed='application/vnd.openxmlformats-officedocument.wordprocessingml.document' match=True
    .pptx      guessed='application/vnd.openxmlformats-officedocument.presentationml.presentation' match=True
    .xlsx      guessed='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' match=True
    .txt       guessed='text/plain'          match=True
    .md        guessed='text/markdown'       match=True
    .markdown  guessed='text/markdown'       match=True
    .html      guessed='text/html'           match=True
    .htm       guessed='text/html'           match=True
    .png       guessed='image/png'           match=True
    .jpg       guessed='image/jpeg'          match=True
    .jpeg      guessed='image/jpeg'          match=True
    .webp      guessed=None                  match=False   <- 必须显式映射
    .bmp       guessed='image/bmp'           match=True
    .tif       guessed='image/tiff'          match=True
    .tiff      guessed='image/tiff'          match=True
```

**本次实测覆盖到的分支**：`.pdf`、`.docx`、`.pptx`、`.xlsx`、`.html`、`.txt`、`.md`、`.png`，以及 `.pdf` 的 `NeedsOcrError → PaddleOCR-VL` 升级路径。
**仅为文档/推断的分支**：`.markdown`、`.htm`、`.jpg`、`.jpeg`、`.webp`、`.bmp`、`.tif`、`.tiff`（都归入「图片 → PaddleOCR-VL」或「HTML/TXT/MD 别名」两条已实测的同构分支，风险低）。

**不在首版 Scope、应落 `manual_retry_required`**：`.doc .docm .ppt .pptm .xls .xlsm .xlsb .odt .ods .odp .rtf .epub .csv`
（anydoc 实测**能**转这些，但 `system-overview.md` 首版 Scope 不含它们 → 先显式拒绝，不要静默接受）。

### E2. 错误分类（供 retry / terminal 状态映射）

分类口径（ADR-0016 修订）：**只有「文档本身读不出来」才落 `manual_retry_required`**；
**与文档无关的运维/集成故障落 `parse_failed`**（可人工重试，error_class 为 `OcrProviderError`）；
**只有瞬时状态才自动重试**。下表左列是实测/文档依据，右列是本轮**修订后**的映射；
标「实测」的报文均来自 §C3 的真实调用，未改写成推断值。

| 错误 | 分类 | 依据 |
|---|---|---|
| `anydoc.UnsupportedError`（未知格式/内容） | **terminal → `manual_retry_required`** | 实测报文「unrecognized file content and extension」 |
| `anydoc.EncryptedError` | **terminal → `manual_retry_required`** | 实测「document is encrypted」 |
| `anydoc.MalformedError` / `MissingPartError` / `ResourceLimitError` | **terminal → `manual_retry_required`** | 文档列明，均继承 `ConvertError` |
| `anydoc.NeedsOcrError` | **不是失败** → 改派 `paddleocr-vl` | 实测 `pages=[1]`、`page_count` |
| `anydoc.OSError` | **transient → 可重试**（IO） | 文档 |
| PaddleOCR **10004**（文件格式不支持） | **terminal → `manual_retry_required`** | **实测**：空文件与 `.html` 当图片传均回 10004；同一份字节能读与否只取决于文件本身 |
| PaddleOCR **10010**（提交队列满）、12002（429）、500/503/504、网络超时 | **transient → 有限重试** | **实测** 10010（连续 8 次、~80 s 仍如此）；12002/5xx 为文档 |
| PaddleOCR **401 / 403 / 12001 / 10007 / 10008 / 11001** | **operational → `parse_failed`（`OcrProviderError`）** | **实测** 401（无鉴权头、错误 token）、10007（`NoSuchModel-v9`）、10008（`pageRanges` 格式错）、403/12001 为文档；**这些是凭证/配额/参数/集成问题，不是文档属性**：错误 token 下同一张图照样能跑通（§C3），所以不得落 `manual_retry_required` |
| PaddleOCR **未定义/未知 code** 与 base URL 打错导致的 **400/404** | **operational → `parse_failed`（`OcrProviderError`）** | 未映射的 code 不构成「文档读不出来」的证据，不得据此把版本挂在 `manual_retry_required`；400/404 是端点配错 |
| PaddleOCR **11003**（job 解析失败，HTTP 200！） | **terminal → `manual_retry_required`**，且**注意 HTTP 是 200** | 文档；必须按 `code`/`state` 判断，不能只看 HTTP 状态 |
| PaddleOCR 启动时**缺 key / 空 key / 仍是 `replace-me` 占位** | **启动即失败**（`ConfigurationError`，错误信息不回显密钥值） | 首版接受图片输入，没有可用凭证就是环境配错；这类故障不得等到处理文档时才暴露 |

配套决定（ADR-0017）：OCR 适配器内部**不再有第二层 3×2 s 提交重试**，瞬时提交失败只由队列那一层重试，
所以一次 delivery 就是一次 provider 调用，次数与退避都记在 job 行里。

---

## 未决项与再验证命令

### 未决项

| # | 未决项 | 状态 |
|---|---|---|
| U1 | PaddleOCR-VL 的**具体并发/RPM/TPM 上限** | **UNVERIFIED**（文档只给 12002 429 与 10010 队列满，无数值） |
| U2 | `code=12002`（请求频率过高）的真实响应体 | **UNVERIFIED**（无安全触发手段，且会烧配额） |
| U3 | `code=12001`（403 每日 20000 页上限）的真实响应体 | **UNVERIFIED** |
| U4 | `code=10001/10003/10005/10006/11002/11003/500` 的真实响应体 | **UNVERIFIED**（10001 已被证伪为空文件码，见 C3） |
| U5 | `resultUrl.markdownUrl` 是否在任何模型/场景下出现 | **UNVERIFIED**（4 次成功任务均只有 `jsonUrl`） |
| U6 | `PP-OCRv5` / `PP-StructureV3` 的返回字段形状 | **UNVERIFIED**（本轮只跑通 `PaddleOCR-VL`） |
| U7 | 单图**像素/边长硬上限** | **UNVERIFIED**（只有 `minPixels`/`maxPixels` 可调参数） |
| U8 | 同步 API（`Authorization: token`，按用户分配的 URL）是否可用 | **UNVERIFIED**（URL 需登录 `https://aistudio.baidu.com/paddleocr/task` 获取；`.env` 的 `PADDLEOCR_BASE_URL` 为空） |
| U9 | anydoc 的 `page_start/page_end` 从何而来 | **已定为事实边界（ADR-0016）**：anydoc 不提供页码，故文本型 PDF 走 anydoc 时 `page_start/page_end` 记 null；页码只来自 `page_spans`（PDF 走 PaddleOCR-VL 时 = `layoutParsingResults` 下标），或由规范化 Markdown 的行号推导 |
| U10 | `.jpg/.jpeg/.webp/.bmp/.tif/.tiff` 经 PaddleOCR-VL 的逐格式实测 | **未实测**（本轮只测 `.png` 与 `.pdf`） |
| U11 | anydoc 对**混合页** PDF（部分文本 + 部分扫描）是否只对扫描页抛 `NeedsOcrError` | **未实测**（本轮只测了「整页纯图」） |

### 再验证命令（一键复跑）

```powershell
# 0. 前置：3 个探针 venv（隔离，不碰项目 .venv）
uv venv .probe\venv-parser  --python 3.12
uv venv .probe\venv-samples --python 3.12
uv pip install --python .probe\venv-parser\Scripts\python.exe  firecrawl-anydoc html-to-markdown
uv pip install --python .probe\venv-samples\Scripts\python.exe python-docx python-pptx openpyxl reportlab pillow

# 1. 生成样本
$env:PYTHONUTF8=1; [Console]::OutputEncoding=[System.Text.Encoding]::UTF8
& .probe\venv-samples\Scripts\python.exe -u .probe\parser\gen_samples.py
& .probe\venv-samples\Scripts\python.exe -u .probe\parser\gen_extra.py   # scan_only.pdf / encrypted.pdf / multipage.pdf

# 2. anydoc：逐格式转换 + 确定性
& .probe\venv-parser\Scripts\python.exe -u .probe\parser\anydoc_probe.py        # -> out-anydoc.txt
& .probe\venv-parser\Scripts\python.exe -u .probe\parser\anydoc_error_probe.py  # -> out-anydoc-error.txt
& .probe\venv-parser\Scripts\python.exe -u .probe\parser\anydoc_model_probe.py  # -> out-anydoc-model.txt
& .probe\venv-parser\Scripts\python.exe -u .probe\parser\final_checks.py        # -> out-final.txt

# 3. HTML 决策
& .probe\venv-samples\Scripts\python.exe -u .probe\parser\html_probe.py          # -> out-html.txt

# 4. 候选库对照（可选，很重：docling ~1 GB / unstructured ~1.4 GB）
& .probe\venv-docling\Scripts\python.exe      -u .probe\parser\docling_probe.py        # -> out-docling.txt
& .probe\venv-unstructured\Scripts\python.exe -u .probe\parser\unstructured_probe.py   # -> out-unstructured.txt
& .probe\venv-native\Scripts\python.exe       -u .probe\parser\native_probe.py         # -> out-native.txt

# 5. PaddleOCR-VL 真机（key 只从 .env 读，不回显）
$k=$null; Get-Content .env | ForEach-Object { if ($_ -match '^\s*PADDLEOCR_API_KEY\s*=\s*(.+)$') { $k=$Matches[1].Trim() } }
$env:PD_KEY=$k
& .probe\venv-parser\Scripts\python.exe -u .probe\parser\paddleocr_live.py     # 端点发现 + 成功路径
& .probe\venv-parser\Scripts\python.exe -u .probe\parser\paddleocr_full.py     # 确定性 + 扫描件 + 错误路径 -> out-paddleocr-full.txt
```

> PaddleOCR-VL 的 `10010 任务提交队列已满` 是瞬时状态；`paddleocr_full.py` 内建最多 20 次提交重试。
> 若 `PaddleOCR-VL` 也不可用，可把 `run_job(model=...)` 换成 `PaddleOCR-VL-1.5` / `PP-StructureV3`。
