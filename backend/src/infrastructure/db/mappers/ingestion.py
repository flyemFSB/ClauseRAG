"""摄取流水线数据行到领域实体的转换映射。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.chunks.model import BlockType, ChildChunk
from domain.knowledge import IngestionJob, IngestionJobStatus, IngestionStage
from domain.parsing import ParseArtifact

if TYPE_CHECKING:
    from infrastructure.db.models.chunks import ChildChunkRow
    from infrastructure.db.models.ingestion import IngestionJobRow, ParseArtifactRow


def to_ingestion_job(row: IngestionJobRow) -> IngestionJob:
    """将摄取作业数据库行转换为领域作业实体。"""
    return IngestionJob(
        id=row.id,
        document_version_id=row.document_version_id,
        stage=IngestionStage(row.stage),
        status=IngestionJobStatus(row.status),
        revision=row.revision,
        attempt=row.attempt,
        error_class=row.error_class,
        error_message=row.error_message,
        created_at=row.created_at,
        updated_at=row.updated_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


def to_child_chunk(row: ChildChunkRow) -> ChildChunk:
    """将子分块数据库行转换为领域子分块实体。"""
    return ChildChunk(
        child_id=row.child_id,
        parent_id=row.parent_id,
        document_version_id=row.document_version_id,
        heading_path=tuple(row.heading_path),
        block_type=BlockType(row.block_type),
        ordinal=row.ordinal,
        line_start=row.line_start,
        line_end=row.line_end,
        content=row.content,
        token_count=row.token_count,
    )


def to_parse_artifact(row: ParseArtifactRow) -> ParseArtifact:
    """将解析产物数据库行转换为领域解析产物实体。"""
    return ParseArtifact(
        document_version_id=row.document_version_id,
        parser_name=row.parser_name,
        parser_version=row.parser_version,
        markdown_object_key=row.markdown_object_key,
        checksum=row.checksum,
        size_bytes=row.size_bytes,
        page_count=row.page_count,
        warnings=tuple(row.warnings or []),
    )
