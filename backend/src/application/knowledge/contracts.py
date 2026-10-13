"""文档目录与重试存储持久化接口协议。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence
    from datetime import datetime, timedelta
    from uuid import UUID

    from domain.knowledge import (
        DocumentDetail,
        DocumentSummary,
        DocumentUpload,
        DocumentVersion,
        DocumentVersionStatus,
        IngestionJob,
    )
    from domain.parsing import ParseArtifact, ParseRetry


class ParseRetryStore(Protocol):
    """解析重试状态修改与查询接口协议"""

    async def start_parse_retry(
        self,
        owner_id: UUID,
        version_id: UUID,
        *,
        retryable_statuses: Collection[DocumentVersionStatus],
        stale_after: timedelta,
        at: datetime,
    ) -> ParseRetry | None:
        """重置文档版本解析状态并派发新修订任务"""
        ...


class CorpusRevision(Protocol):
    """知识库可检索语料版本标识接口协议。"""

    async def revision_for_knowledge_base(self, knowledge_base_id: UUID) -> str:
        """返回语料版本标识，内容变更时返回新标识。"""
        ...


class DocumentStore(Protocol):
    """文档、版本与摄取任务存储接口协议"""

    async def add_version(
        self,
        *,
        owner_id: UUID,
        knowledge_base_id: UUID,
        document_id: UUID | None,
        title: str,
        version_id: UUID,
        source_object_key: str,
        mime_type: str,
        checksum: str,
        size_bytes: int,
        at: datetime,
    ) -> DocumentUpload | None:
        """创建逻辑文档（若未指定）并追加新物理版本与初始解析任务"""
        ...

    async def list_summaries(
        self,
        owner_id: UUID,
        knowledge_base_id: UUID,
    ) -> Sequence[DocumentSummary] | None:
        """获取知识库下的文档摘要列表（附带最新版本）"""
        ...

    async def find_detail(self, owner_id: UUID, document_id: UUID) -> DocumentDetail | None:
        """获取文档详情及其完整版本历史"""
        ...

    async def find_version(
        self,
        owner_id: UUID,
        version_id: UUID,
    ) -> DocumentVersion | None:
        """查询指定文档版本"""
        ...

    async def find_parse_artifact(
        self,
        owner_id: UUID,
        version_id: UUID,
    ) -> ParseArtifact | None:
        """查询文档版本的最新解析产物元数据"""
        ...

    async def list_jobs_for_version(
        self,
        owner_id: UUID,
        version_id: UUID,
    ) -> Sequence[IngestionJob] | None:
        """查询文档版本关联的所有摄取阶段任务"""
        ...

    async def find_job(self, owner_id: UUID, job_id: UUID) -> IngestionJob | None:
        """查询指定摄取任务详情"""
        ...

    async def delete(self, owner_id: UUID, document_id: UUID) -> bool:
        """删除文档及其所有版本、任务，并在事务中记录异步清理意图"""
        ...
