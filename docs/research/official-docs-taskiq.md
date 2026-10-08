# 官方文档结论：Taskiq 与 `taskiq-aio-pika`

日期：2026-10-02 · 依据版本：`taskiq 0.13.0`、`taskiq-aio-pika 0.6.1`、`aio-pika 10.1.0`（`uv.lock` 锁定值）
用途：Phase 2 后半段（解析阶段接入唯一业务队列）的 API 依据。**实现里只使用本文列出的官方 API。**

## 链接

| 主题 | 官方链接 |
| --- | --- |
| Getting started（broker 声明、`startup()`、`kiq`、worker 启动） | <https://taskiq-python.github.io/guide/getting-started.html> |
| Architecture overview（`kick`/`listen`、kicker、labels、worker CLI） | <https://taskiq-python.github.io/guide/architecture-overview.html> |
| CLI（`taskiq worker`、ack 类型、`--max-async-tasks`、优雅退出） | <https://taskiq-python.github.io/guide/cli.html> |
| State and Dependencies（`TaskiqDepends`、`Context`） | <https://taskiq-python.github.io/guide/state-and-deps.html> |
| Available middlewares（`SimpleRetryMiddleware`、`SmartRetryMiddleware`、`types_of_exceptions`） | <https://taskiq-python.github.io/available-components/middlewares.html> |
| `taskiq-aio-pika` 官方说明（delay queue、优先级、自定义 Queue/Exchange） | <https://pypi.org/project/taskiq-aio-pika/>（该包主页即 README） |
| 源码依据（本机 `.venv`，与上列文档一致） | `taskiq/middlewares/{simple,smart}_retry_middleware.py`、`taskiq_aio_pika/broker.py`、`taskiq/receiver/receiver.py` |

## 1. Broker 构造与启动

- RabbitMQ 的 broker **不在 taskiq 核心里**：`taskiq.brokers` 只有 `inmemory` / `shared` / `zeromq`；RabbitMQ 来自独立包 `taskiq-aio-pika`（`AioPikaBroker`）。官方 Getting started 明确：安装 `taskiq-aio-pika` 后用
  `broker = AioPikaBroker("amqp://guest:guest@localhost:5672")`。
- **必须在发任务前调用 `await broker.startup()`**（官方原文："Never forget to call startup in the beginning" / "the AioPika broker requires calling startup before using it"）。
  实测 `AioPikaBroker.startup()` 会：连接（`is_worker_process=True` 时另开读连接）、声明 exchange、声明 task 队列、**并声明死信队列**（`_declare_queues()` → `_declare_dead_letter_queue()`）。
- 对应 `await broker.shutdown()` 关闭连接；官方 CLI 在子进程结束时调用它（`taskiq/cli/worker/run.py` 的 `shutdown_broker`）。
- 本项目的取舍：worker 进程由适配器在 `listen()` 前调用 `startup()`；API 进程**在第一次投递时才 `startup()`**（一次，带锁），理由是 RabbitMQ 不可用时 API 仍要能起来并把依赖健康报成 503，而不是崩溃重启。投递失败按端口错误处理（见 ADR-0017）。

## 2. 任务声明与注册

- 官方写法：`@broker.task` / `@broker.task(task_name="my_tasks.add_one", label1=1)`；装饰后得到 `AsyncTaskiqDecoratedTask`，同时注册进 broker 的任务表（`find_task(name)` / `get_all_tasks()`）。
- 任务参数按类型注解做“宽松转换”（`taskiq/receiver/params_parser.py`，可用 `--no-parse` 关闭）；类型转换失败不报错，只保留原值。本项目因此**显式传字符串 ID 并在任务体内构造 `UUID`**，不依赖隐式转换。
- 依赖注入：`Annotated[SomeType, TaskiqDepends()]` 按**类型**解析，取自 `broker.custom_dependency_context`（`add_dependency_context({Type: instance})`）；`Context` / `TaskiqState` 由 receiver 自动注入。实测：注入类型若是自定义类，`taskiq_dependencies` 会 `get_type_hints(Cls.__init__)`，注解里出现只在 `TYPE_CHECKING` 下导入的名字会触发 `RuntimeWarning`（功能仍可用）。
- 本项目结论：**不使用 DI 注入应用服务**（避免上述告警与 `TC001/TC002` 冲突），改为在 broker 工厂里闭包捕获 `RunParseJob` 并把任务对象交给适配器持有；任务体只做 `runner.run(ids)`。

## 3. 投递 API

- `await my_task.kiq(*args)`（等价 `my_task.kicker().kiq(...)`）；kicker 可 `with_task_id()` / `with_labels()` / `with_broker()`。
- 消息只带 `task_name`、`task_id`、`args`/`kwargs` 与 labels。`AioPikaBroker.kick()` 的 routing key：只有一个 task 队列时用该队列的 `routing_key`（未设则用队列名，本项目即 `taskiq`）；多个队列时用 `label_for_routing`（默认 label 名 `queue_name`）并从任务 label 里取。labels 一并放进 AMQP headers。官方消息格式与实测一致：body 为 `{"task_id","task_name","labels","labels_types","args","kwargs"}`。
- 队列参数：`AioPikaBroker(url, task_queues=[Queue(...)], dead_letter_queue=Queue(...), delay_queue=Queue(...), qos=N)`；`Queue` 默认 `type=QueueType.QUORUM`、`durable=True`、`name="taskiq"`，死信队列默认名 `taskiq.dead_letter`，exchange 默认 `Exchange(name="taskiq", type=TOPIC, durable=True)`。
- 实测拓扑（本机 rabbitmq 4.3.6）：`taskiq` durable+quorum，参数 `x-dead-letter-exchange=""`、`x-dead-letter-routing-key="taskiq.dead_letter"`、`x-queue-type=quorum`；`taskiq.dead_letter` durable+quorum；exchange `taskiq`（topic、durable，由 broker 声明）。

## 4. 官方重试机制在哪里、怎么配置

**位置：中间件**（`taskiq.middlewares`），不是 broker 或任务参数。

- `SimpleRetryMiddleware(default_retry_count=3, default_retry_label=False, no_result_on_retry=True, types_of_exceptions=None)`：失败后**立即**重发同一条消息（同 `task_id`、同 args）。
- `SmartRetryMiddleware(default_retry_count=5, default_retry_label=False, default_delay=5, use_jitter=False, use_delay_exponent=False, max_delay_exponent=60, schedule_source=None, types_of_exceptions=None)`：失败后按 delay/抖动/指数退避重发。
- 启用方式（两种，可叠加）：middleware 参数（broker 级默认）+ 任务 label：`@broker.task(retry_on_error=True, max_retries=10, delay=15, types_of_exceptions=(...))`。
- **计数语义（源码实测）**：`retries = labels["_retries"] + 1`，仅在 `retries < max_retries` 时重发；`max_retries` 缺省取 middleware 的 `default_retry_count`。因此 **`max_retries = 总投递次数**（首次 + 重试）。实测 `default_retry_count=3` → 恰好 3 次投递、2 次重发。
- **只重试指定异常**：`types_of_exceptions`（broker 级或任务 label，label 优先）——不在元组里的异常**不重试**。实测 `types_of_exceptions=(ValueError,)` 时 `KeyError` 只投递 1 次。
- 延迟如何实现：`on_send()` 把 `delay` label 交给 kicker；`AioPikaBroker.kick()` 在有 `delay_queue` 时把消息发到 delay 队列并设 per-message `expiration`，到期后由死信机制回到 task 队列（或使用 `delayed_message_exchange_plugin`，需 RabbitMQ 插件）。
  **注意**：quorum 队列不支持 per-message TTL，所以 delay 队列必须是 `QueueType.CLASSIC`（实测：classic + durable 的 delay 队列工作正常，参数 `x-dead-letter-exchange="taskiq"`、`x-dead-letter-routing-key=<task queue>`）。
- 本项目的配置（见 ADR-0017）：`SmartRetryMiddleware(default_retry_count=RAG_PARSE_MAX_ATTEMPTS, default_delay=RAG_PARSE_RETRY_DELAY_SECONDS, use_jitter=True, use_delay_exponent=True, max_delay_exponent=RAG_PARSE_RETRY_MAX_DELAY_SECONDS, types_of_exceptions=(TransientParseError,))`，任务 label 只声明 `retry_on_error=True` 与同一 `types_of_exceptions`；**不把 `max_retries`/`delay` 写进 label**，让 worker 进程的 settings 成为 middleware 与业务 attempt 预算的唯一来源。

## 5. worker 的官方启动方式

- 官方 CLI：`taskiq worker mybroker:broker_var my_project.module1 ...`（另有 `--tasks-pattern` / `-fsd` 自动发现；`--max-async-tasks`、`--ack-type`、`--shutdown-timeout`、`--wait-tasks-timeout`、`--hardkill-count` 等参数）。
- 官方 CLI 内部做的事（`taskiq/cli/worker/run.py`，可复用）：`broker.is_worker_process = True` → 导入任务模块 → `Receiver(broker=..., executor=..., max_async_tasks=..., propagate_exceptions=True, ack_type=...)` → `loop.run_until_complete(receiver.listen(shutdown_event))` → `broker.shutdown()`。
- `AsyncBroker.listen()` 是 broker 的官方消费接口；`Receiver.listen(event)` 内部会 `await broker.startup()`（`run_startup=True` 时）。
- 本项目选择**进程内 Receiver**（官方公开类 `taskiq.receiver.Receiver`，与 CLI 同一实现）：worker 自己的事件循环里同时持有 container（DB 连接池、S3 客户端）与 broker，`run_startup=False` 因为适配器已 `startup()`；停止信号走 `Receiver.listen(finish_event)` 的官方事件语义（停止拉取 → 等在跑的任务 → 关闭 broker）。这样避免 `taskiq worker` 在 Windows 上通过 `ProcessManager` 再 spawn 一层子进程，也不需要模块级 broker 全局变量。
- ack：官方四种（`when_received` / `when_executed` / `when_saved`（默认）/ `manual`），可用任务 label `ack_type` 覆盖；只有 broker 产出 `AckableMessage` 时才可 ack（aio-pika broker 是）。本项目用默认 `when_saved`：业务状态写入成功后才 ack（对应 backend-guidelines「RabbitMQ 确认晚于持久副作用与业务状态更新」）。

## 6. 队列 / DLQ 的声明方式与命名

- 声明由 `startup()` 完成，名字来自 `Queue`/`Exchange` 数据类：task 队列默认 `taskiq`，死信队列默认 `taskiq.dead_letter`，exchange 默认 `taskiq`（topic、durable）。
- **RabbitMQ 不会自己创建死信目标队列**：`x-dead-letter-routing-key` 指向不存在的队列时消息被静默丢弃（ADR-0009）。taskiq-aio-pika 的 `startup()` 会声明 `taskiq.dead_letter`，因此部署必须让至少一个进程（worker 或 API）启动过 broker。
- `taskiq` 不能以 classic 重复声明（实测 `PRECONDITION_FAILED - inequivalent arg 'x-queue-type'`），所以本项目不再自行声明这两个队列，只用库默认。
- 本项目额外声明的只有 delay 队列 `taskiq.delay_queue`（classic、durable），命名沿用官方 README 示例。

## 7. 与本文档不一致 / 未决

- 官方文档没有描述 `Receiver` 的直接用法（只在 CLI 实现里使用）；`listen()` 与 `Receiver` 都是公开 API，但“进程内 worker”属于文档未展开的用法，本文记录为本项目的选择而非官方推荐路径。
- 官方未给出 `qos`（prefetch）与 `Receiver.max_async_tasks` 的配套建议；本项目用同一个 setting 同时设置两者（未确认消息数不超过可并发执行数）。
- `SmartRetryMiddleware` 的退避是「线性 × 次数再截断」（`min(delay * retries, max_delay_exponent)`），不是标准的 2^n 退避；文档称其为 exponential backoff。本项目按源码语义描述（第 2 次等待 base、第 3 次等待 2×base，截断到 max）。


## 增补（2026-10-03）：任务体的依赖注入，与 Phase 3 的构造环

抓取方式：context7 REST API（本机未配置 context7 MCP），库 ID `/websites/taskiq-python_github_io`，
主题 "kick task by name"、"task registration and declaration"、"publishing tasks from another
process"、"SmartRetryMiddleware exceptions"、"receiver listen startup shutdown"；
原始文本存于 `.probe/c7/taskiq-11..15.txt`（`.probe/` 已 gitignore）。
凡文档没写的，以下写明"文档未给"，并以本机安装的 `taskiq 0.13.0` 源码为依据标注来源。

### 8. `kiq` 需要本进程注册过该任务；不存在"按任务名投递"的高层 API

- 投递路径是 `AsyncTaskiqDecoratedTask.kiq()` → `AsyncKicker.kiq` → broker（`taskiq/kicker.py:114`）。
- `AsyncBroker.kick(message: BrokerMessage)`（`taskiq/abc/broker.py:224`）是**低层**抽象方法：参数已经是
  序列化好的 `BrokerMessage`，官方 docstring 写的是 "You don't need to send broker message. It's helper
  for brokers, please send only bytes from message.message."。因此**没有**"给一个任务名就直接投递"的
  高层 API；发布方进程必须持有那个被装饰的任务对象（`broker.task(...)` / `register_task(...)` 都会登记
  任务名），`broker.find_task(name)`（`taskiq/abc/broker.py:122`）只用于按名查找已登记的任务。
  - 结论：**发布方必须声明任务**；文档未给任何绕过它的官方写法。

### 9. 任务体依赖由 broker 的进程级依赖上下文解析

- `taskiq/__init__.py:5`：`from taskiq_dependencies import Depends as TaskiqDepends`，即 `TaskiqDepends`
  是 taskiq 重新导出、且 `taskiq-dependencies`（本机 `1.5.7`）是 taskiq 自身的依赖，不需要新增依赖。
- `AsyncBroker.add_dependency_context(new_ctx)`（`taskiq/abc/broker.py:157`）把键值并入
  `self.custom_dependency_context`（同文件 `:115`）。
- receiver 在每个交付执行前把这个 dict 作为依赖解析上下文，并按类型补入 `Context` 与 `TaskiqState`：
  ```python
  broker_ctx = self.broker.custom_dependency_context
  broker_ctx.update({Context: Context(message, self.broker, ack_controller), TaskiqState: ...})
  dep_ctx = dependency_graph.async_ctx(broker_ctx, self.broker.dependency_overrides or None)
  ```
  —— `taskiq/receiver/receiver.py:294`（**源码依据**：官方 state-and-deps 页描述 `TaskiqDepends`/`Context`
  的用法，但未描述 broker 级 dict 的注入路径）。
- 因此 `Annotated[DocumentIngestion, TaskiqDepends()]` 形式的参数由框架按**注解类型**解析，而不是由闭包
  捕获。官方示例统一使用该 `Annotated` 形式；默认值形式（`= TaskiqDepends()`）文档未给，本项目不用。

### 10. 对 Phase 3 的结论：构造环由框架的依赖上下文打破

Phase 3 把 by-hand 重试的投递放进 `DocumentIngestion` 之后，出现一个真实的构造环：队列适配器需要一个
`DocumentIngestion` 作为任务体，而 `DocumentIngestion` 需要队列适配器作为其 dispatcher（手工重试没有自己的
消息可搭）。按官方能力，环由一个框架原生机制打破，而不是靠可变状态或回调 hack：

| 计划动作 | 官方/源码依据 | 结论 |
| --- | --- | --- |
| 任务体用 `Annotated[DocumentIngestion, TaskiqDepends()]` 取依赖 | 第 9 节（官方 `TaskiqDepends` + receiver 源码） | 采用过，后来被取代（见修订） |
| 发布方（API/CLI）声明任务名即可投递，不构造 ingestion | 第 8 节（`kiq` 需要任务对象；`kick` 是低层） | 采用：任务在队列适配器构造时声明 |
| 工作进程用 `add_dependency_context({DocumentIngestion: ingestion})` 提供实现 | 第 9 节 | 采用过，后来被取代（见修订） |
| 用 `broker.kick(BrokerMessage(...))` 手工序列化投递 | 第 8 节（低层 API，需自行构造消息） | 不使用：等于重写 Kicker 的序列化 |
| 新增 taskiq 生态依赖（如 `taskiq-fastapi`） | 第 9 节（`taskiq-dependencies` 已随 taskiq 安装） | 不新增 |

未验证项（留待 task-8 的真容器运行）：`taskiq` worker 在依赖上下文中解析 `DocumentIngestion` 的实际行为、
`ingestion.attempt_started` 与 `ingestion.<stage>` trace 名称保持不变，以及重试端点仍投递同一条消息。

### 10.1 修订（2026-10-03，H3）：依赖上下文改为进程注入的可调用对象

第 10 节的构造环后来不复存在：by-hand 重试移到了 `DocumentCatalog`（H2），`DocumentIngestion` 不再需要
队列作为 dispatcher，而 H3 要求传输适配器不导入应用模块。现在的做法是：适配器只声明任务、拓扑、发布与
重试策略，工作进程在装配时把一个接受三个线标识（stage、document version、job）的可调用对象交给它
（`IngestionJobQueue.supply_stage_runner`）。

- **不再使用的官方机制**：`TaskiqDepends` / `add_dependency_context`。它们能跑通（task-8 已验证），但会
  让 `infrastructure/job_queue.py` 依赖 `application.document_ingestion` 这个具体类型 —— 传输层因此知道
  了工作进程的应用实现。
- **仍然不变**：消息形状（三个字符串）、任务名、`SmartRetryMiddleware` 的有限重试与 transient 异常集合、
  trace 名称与字段、以及“只有已提交的 job 才被发布”的规则。
- **回退路径**：官方机制随时可复原；本次选择的是更小的依赖面，而不是对框架能力的重新取舍。
