"""基于环境变量的系统运行时配置解析与强类型校验。"""

from __future__ import annotations

from typing import Literal, Self
from urllib.parse import urlparse

from pydantic import (
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLACEHOLDER_CREDENTIAL = "replace-me"


class ConfigurationError(RuntimeError):
    """环境配置不满足系统要求时抛出的异常。"""


class Settings(BaseSettings):
    """系统全局运行时配置模型。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    log_level: str = "INFO"

    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)

    health_probe_timeout_seconds: int = Field(default=3, gt=0, le=30)
    database_timeout_seconds: int = Field(default=5, gt=0, le=60)

    # 数据库连接池配额
    api_database_pool_size: int = Field(default=8, ge=1, le=100)
    agent_database_pool_size: int = Field(default=8, ge=1, le=100)
    worker_database_pool_size: int = Field(default=8, ge=1, le=100)
    database_max_overflow: int = Field(default=4, ge=0, le=100)

    max_upload_bytes: int = Field(default=100 * 1024 * 1024, gt=0)
    parse_timeout_seconds: int = Field(default=900, gt=0, le=7200)
    chunk_timeout_seconds: int = Field(default=600, gt=0, le=7200)

    job_max_attempts: int = Field(default=3, ge=1, le=10)
    job_retry_delay_seconds: float = Field(default=30, ge=0, le=600)
    job_retry_max_delay_seconds: float = Field(default=300, ge=0, le=3600)
    job_stale_after_seconds: int = Field(default=1800, gt=0, le=86400)
    job_dispatch_interval_seconds: float = Field(default=2, gt=0, le=60)
    job_republish_seconds: float = Field(default=30, ge=0, le=600)

    cleanup_retry_delay_seconds: float = Field(default=30, ge=0, le=3600)
    cleanup_lease_seconds: float = Field(default=3600, gt=0, le=86400)

    worker_max_async_tasks: int = Field(default=4, ge=1, le=64)
    job_dispatch_timeout_seconds: int = Field(default=10, gt=0, le=60)
    storage_timeout_seconds: int = Field(default=300, gt=0, le=3600)

    database_url: SecretStr
    rabbitmq_url: SecretStr

    # 业务 Redis 派生能力配置（限流、检索调试缓存与并发锁）
    redis_enabled: bool = False
    redis_url: SecretStr | None = None
    redis_key_prefix: str = Field(default="clauserag", min_length=1, max_length=64)
    redis_connect_timeout_seconds: float = Field(default=1, gt=0, le=30)
    redis_socket_timeout_seconds: float = Field(default=1, gt=0, le=30)
    redis_health_timeout_seconds: float = Field(default=1, gt=0, le=30)
    redis_max_connections: int = Field(default=32, ge=1, le=1000)
    redis_rate_limit_enabled: bool = False
    redis_cache_enabled: bool = False
    redis_cache_ttl_seconds: int = Field(default=60, ge=1, le=3600)
    redis_cache_ttl_jitter_seconds: int = Field(default=10, ge=0, le=600)
    redis_cache_lock_blocking_timeout_seconds: float = Field(default=0.15, ge=0, le=5)
    redis_cache_lock_timeout_seconds: int = Field(default=30, ge=1, le=300)
    redis_max_cache_value_bytes: int = Field(default=1048576, ge=1024, le=16777216)

    @model_validator(mode="after")
    def _keep_the_business_redis_isolated(self) -> Self:
        """校验业务 Redis 配置有效性，确保不与 Langfuse 冲突。"""
        if self.redis_enabled and self.redis_url is None:
            raise ValueError("REDIS_ENABLED 为真时必须配置 REDIS_URL")
        if self.redis_url is not None:
            database = urlparse(self.redis_url.get_secret_value()).path.strip("/")
            if database == "1":
                raise ValueError(
                    "业务 Redis 不得使用 Langfuse 所在的库 1；请改用独立实例或独立库（如库 0）"
                )
        return self

    s3_endpoint_url: str = "http://127.0.0.1:9000"
    s3_region: str = "us-east-1"
    s3_bucket: str = "rag-documents"
    s3_access_key: SecretStr
    s3_secret_key: SecretStr

    # PaddleOCR 配置
    paddleocr_api_key: SecretStr
    paddleocr_base_url: str = "https://paddleocr.aistudio-app.com"
    paddleocr_model: str = "PaddleOCR-VL"
    paddleocr_request_timeout_seconds: int = Field(default=60, gt=0, le=600)
    paddleocr_poll_interval_seconds: float = Field(default=2, gt=0, le=60)
    paddleocr_poll_timeout_seconds: int = Field(default=300, gt=0, le=3600)

    @field_validator("paddleocr_api_key")
    @classmethod
    def _require_usable_ocr_credential(cls, value: SecretStr) -> SecretStr:
        credential = value.get_secret_value().strip()
        if not credential:
            raise ValueError(
                "PaddleOCR-VL 访问凭据为空；请将 PADDLEOCR_API_KEY 配置为有效的 API 密钥"
            )
        if credential == _PLACEHOLDER_CREDENTIAL:
            raise ValueError(
                f"PaddleOCR-VL 访问凭据仍为 .env.example 中的占位符 {_PLACEHOLDER_CREDENTIAL}；"
                "请将 PADDLEOCR_API_KEY 配置为有效的 API 密钥"
            )
        return value

    # SiliconFlow 外部模型服务配置
    siliconflow_api_key: SecretStr
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    provider_max_connections: int = Field(default=16, ge=1, le=200)

    # pgvector HNSW 检索超参数：候选池大小、扩扫模式与单轮最大扫描行数。
    hnsw_ef_search: int = Field(default=100, gt=0, le=1000)
    hnsw_iterative_scan: Literal["off", "relaxed_order", "strict_order"] = "strict_order"
    hnsw_max_scan_tuples: int = Field(default=20000, gt=0, le=1000000)

    # 嵌入模型与维度部署契约，需与表结构定义一致。
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = Field(default=1024, gt=0, le=8192)
    embedding_batch_size: int = Field(default=16, ge=1, le=512)
    embedding_timeout_seconds: int = Field(default=120, gt=0, le=600)
    embed_timeout_seconds: int = Field(default=900, gt=0, le=7200)
    index_timeout_seconds: int = Field(default=120, gt=0, le=3600)

    # Langfuse 可观测性配置
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str = "http://127.0.0.1:3000"
    langfuse_database: str = "langfuse"
    langfuse_bucket: str = "rag-langfuse"

    @field_validator("siliconflow_api_key")
    @classmethod
    def _require_usable_embedding_credential(cls, value: SecretStr) -> SecretStr:
        credential = value.get_secret_value().strip()
        if not credential:
            raise ValueError(
                "SiliconFlow 访问凭据为空；请将 SILICONFLOW_API_KEY 配置为有效的 API 密钥"
            )
        if credential == _PLACEHOLDER_CREDENTIAL:
            raise ValueError(
                f"SiliconFlow 访问凭据仍为 .env.example 中的占位符 {_PLACEHOLDER_CREDENTIAL}；"
                "请将 SILICONFLOW_API_KEY 配置为有效的 API 密钥"
            )
        return value

    # Chat 与意图识别模型配置
    chat_model: str = "Qwen/Qwen2.5-7B-Instruct"
    # 对话模型独立端点与鉴权密钥；未指定时沿用 SiliconFlow 配置。
    chat_base_url: str | None = None
    chat_api_key: SecretStr | None = None

    @model_validator(mode="after")
    def _keep_the_chat_endpoint_whole(self) -> Self:
        """校验 CHAT_BASE_URL 与 CHAT_API_KEY 必须成对配置。"""
        if (self.chat_base_url is None) != (self.chat_api_key is None):
            raise ValueError(
                "CHAT_BASE_URL 与 CHAT_API_KEY 必须同时配置："
                "模型名称绑定特定服务商端点，不完整的配置会导致端点解析异常"
            )
        return self

    chat_timeout_seconds: int = Field(default=120, gt=0, le=600)
    chat_max_tokens: int = Field(default=1024, ge=1, le=8192)
    chat_temperature: float = Field(default=0.2, ge=0, le=2)
    chat_history_messages: int = Field(default=6, ge=0, le=50)
    query_understanding_max_tokens: int = Field(default=256, ge=1, le=2048)
    chat_context_window: int = Field(default=32768, ge=1024, le=1048576)
    chat_prompt_reserve_tokens: int = Field(default=4000, ge=0, le=65536)

    # 重排模型与召回配额
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_timeout_seconds: int = Field(default=60, gt=0, le=600)

    dense_top_k: int = Field(default=30, ge=1, le=200)
    keyword_top_k: int = Field(default=30, ge=1, le=200)
    fusion_limit: int = Field(default=50, ge=1, le=500)
    rerank_limit: int = Field(default=50, ge=1, le=200)
    final_parent_limit: int = Field(default=8, ge=1, le=50)
    max_context_tokens: int = Field(default=6000, ge=256, le=64000)
    max_retrieval_rounds: int = Field(default=2, ge=1, le=5)

    rrf_rank_constant: int = Field(default=60, ge=1, le=1000)
    dense_channel_weight: float = Field(default=1.0, ge=0, le=10)
    keyword_channel_weight: float = Field(default=1.0, ge=0, le=10)
    retrieval_channel_timeout_seconds: int = Field(default=30, gt=0, le=300)

    @model_validator(mode="after")
    def _keep_the_prompt_budget_inside_the_window(self) -> Self:
        """校验提示词预算总和不超出模型上下文窗口。"""
        total = self.max_context_tokens + self.chat_max_tokens + self.chat_prompt_reserve_tokens
        if total > self.chat_context_window:
            raise ValueError(
                f"提示词预算总和 ({total} tokens: 上下文 {self.max_context_tokens} "
                f"+ 回答 {self.chat_max_tokens} + 预留 {self.chat_prompt_reserve_tokens}) "
                f"超出模型上下文窗口上限 ({self.chat_context_window} tokens)"
            )
        return self

    min_rerank_score: float = Field(default=0.2, ge=0, le=1)

    citation_quote_chars: int = Field(default=600, ge=64, le=4000)
    citation_invalid_id_policy: Literal["strip", "reject"] = "strip"

    # Agent 运行时配置
    agent_runtime_host: str = "127.0.0.1"
    agent_runtime_port: int = Field(default=8001, ge=1, le=65535)
    checkpoint_pool_size: int = Field(default=4, ge=1, le=32)
    answer_timeout_seconds: int = Field(default=300, gt=0, le=3600)
    rerank_max_documents: int = Field(default=50, ge=1, le=200)

    # RAGAS 评测配置：只有评测依赖组（uv run --group eval）读取，业务进程不读。
    # 专用 judge 凭据缺失时回落到 SiliconFlow 的 OpenAI-compatible endpoint，
    # 避免为了打分再要求一套 key；模型和 base_url 必须支持结构化输出。
    eval_judge_api_key: SecretStr | None = None
    eval_judge_base_url: str | None = None
    eval_judge_model: str | None = None
    eval_embedding_model: str | None = None
    # 并发与重试由 RAGAS 之外的这一层控制：不能让 RAGAS 默认 16 workers / 10 retries 直冲供应商。
    eval_max_concurrency: int = Field(default=2, ge=1, le=16)
    eval_timeout_seconds: int = Field(default=120, gt=0, le=600)
    eval_max_retries: int = Field(default=2, ge=0, le=10)
    eval_cache_dir: str = "dist/eval-cache"
    # AnswerRelevancy 每个回答生成多少个问题；基线先用 1，发布评测再升为 RAGAS 默认的 3。
    eval_answer_relevancy_strictness: int = Field(default=1, ge=1, le=5)


def load_settings() -> Settings:
    """读取并校验环境变量配置。"""
    try:
        return Settings()  # pyright: ignore[reportCallIssue]
    except ValidationError as error:
        raise ConfigurationError(str(error)) from error


def libpq_dsn(database_url: str) -> str:
    """将 SQLAlchemy 数据库连接串转换为 libpq 协议格式。"""
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
