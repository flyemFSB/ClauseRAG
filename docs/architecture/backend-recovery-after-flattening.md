# 后端扁平化重构恢复备忘录

> **说明**：本文件记录了移除外层 `rag_platform/` 冗余包目录后的结构恢复方案与证据映射。当前系统已全面完成扁平化并稳定运行。

---

## 恢复目标与规范目录

系统确立了扁平化后的单一源代码根目录规范（`backend/src/`），严禁回退至旧版 `rag_platform` 嵌套结构：

```text
backend/src/
├── agent_runtime/    # LangGraph 有界图推理引擎与状态机定义
├── api/              # FastAPI 路由接入层、HTTP 异常映射与认证依赖
├── application/      # 业务用例服务（按业务领域内聚）
├── cli/              # 命令行运维管理工具集
├── composition/      # 各进程独立依赖注入组装与生命周期管理
├── domain/           # 纯粹领域实体模型、事件与业务规则
├── infrastructure/   # 外部依赖适配器（数据库、Qdrant、RabbitMQ、S3、模型客户端）
└── worker/           # Taskiq 异步流水线任务消费循环与调度
```

代码内部所有导入统一使用扁平化顶级包路径，例如：
```python
from application.retrieval import RetrievalService
from composition.api import build_api_runtime
from infrastructure.db import Base
```

---

## 核心架构原则与设计落地

系统在扁平化重构中贯彻了如下核心契约：
1. **进程独立依赖注入**：废弃全局通用单例容器，改为按进程隔离的装配工厂（`composition/api/`、`composition/agent/`、`composition/worker/`、`composition/cli/`）。
2. **高内聚业务门面**：
   - `DocumentCatalog`：统一接管文档上传、哈希校验、版本管理与软删除；
   - `DocumentIngestion`：统一接管异步摄取任务的分发、租约认领与阶段推进；
   - `RetrievalService`：对外暴露统一检索接口，收敛双通道召回、RRF 融合与重排逻辑；
   - `ConversationAgent`：统一对外提供流式 Agent 执行接口。
3. **分用例持久化端口**：废弃单体仓储，拆分为按用例内聚的 Store（`DocumentStore`、`IngestionStore`、`ChunkStore`、`ConversationStore`、`CleanupStore`）。
4. **异步清理意图机制**：删除文档时原子提交物理清理意图（`cleanup_intents`），由后台 Worker 异步幂等执行 S3 对象与向量索引删除。
5. **作业行驱动的任务调度**：依据 ADR-0030，PostgreSQL 作业行为单一调度契约，RabbitMQ 仅负责轻量唤醒。
