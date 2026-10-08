"""解析产物记录管理，维护文档解析成功生成的 Markdown 产物指针及元数据。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert

from infrastructure.db.models.ingestion import ParseArtifactRow

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from domain.parsing import ParseArtifact


async def record_parse_artifact(
    session: AsyncSession,
    artifact: ParseArtifact,
    *,
    at: datetime,
) -> str | None:
    """记录或更新文档版本的解析产物，返回被替换的历史对象键。"""
    previous_key = await session.scalar(
        select(ParseArtifactRow.markdown_object_key).where(
            ParseArtifactRow.document_version_id == artifact.document_version_id
        )
    )
    await session.execute(
        postgres_insert(ParseArtifactRow)
        .values(
            document_version_id=artifact.document_version_id,
            parser_name=artifact.parser_name,
            parser_version=artifact.parser_version,
            markdown_object_key=artifact.markdown_object_key,
            checksum=artifact.checksum,
            size_bytes=artifact.size_bytes,
            page_count=artifact.page_count,
            warnings=list(artifact.warnings) or None,
            created_at=at,
            updated_at=at,
        )
        .on_conflict_do_update(
            index_elements=[ParseArtifactRow.document_version_id],
            set_={
                "parser_name": artifact.parser_name,
                "parser_version": artifact.parser_version,
                "markdown_object_key": artifact.markdown_object_key,
                "checksum": artifact.checksum,
                "size_bytes": artifact.size_bytes,
                "page_count": artifact.page_count,
                "warnings": list(artifact.warnings) or None,
                "updated_at": at,
            },
        )
    )
    return previous_key
