"""CLI 命令标准输出与错误信息格式化。"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from application.ingestion.chunk import ChunkOutcome
from application.ingestion.embed import EmbedOutcome
from application.ingestion.parse import ParseOutcome

if TYPE_CHECKING:
    from uuid import UUID

    from application.ingestion.document_ingestion import StageOutcome
    from domain.chunks.errors import ChunkError
    from domain.chunks.model import ChunkArtifact
    from domain.embedding import EmbeddedVersion, EmbeddingError, IndexedVersion, IndexingError
    from domain.parsing import DocumentParseError, ParseArtifact


def print_stage_outcome(outcome: StageOutcome) -> None:
    """打印阶段执行成功产物摘要。"""
    if isinstance(outcome, ParseOutcome):
        print_parse_artifact(outcome.artifact)
    elif isinstance(outcome, ChunkOutcome):
        print_chunk_artifact(outcome.artifact)
    elif isinstance(outcome, EmbedOutcome):
        print_embedding(outcome.embedded)
    else:
        print_index(outcome.indexed)


def print_stage_failure(
    version_id: UUID,
    error: DocumentParseError | ChunkError | EmbeddingError | IndexingError,
) -> None:
    """将阶段失败详情输出至 stderr：失败后的状态由作业行记录，此处不重复推断。"""
    print(f"error: {type(error).__name__}: {error}", file=sys.stderr)
    print(
        f"version {version_id}: the job row records what this attempt became",
        file=sys.stderr,
    )


def print_parse_artifact(artifact: ParseArtifact) -> None:
    """格式化输出文档解析产物信息。"""
    version_id = artifact.document_version_id
    print(f"version {version_id} status=parsed")
    print(f"artifact {artifact.markdown_object_key}")
    print(f"checksum {artifact.checksum}")
    print(f"size_bytes {artifact.size_bytes}")
    print(f"parser {artifact.parser_name} {artifact.parser_version}")
    # 页数为空时按数据库 NULL 格式打印
    print(f"page_count {artifact.page_count if artifact.page_count is not None else 'NULL'}")
    for warning in artifact.warnings:
        print(f"warning {warning}")


def print_chunk_artifact(artifact: ChunkArtifact) -> None:
    """格式化输出分块产物信息。"""
    print(f"version {artifact.document_version_id} status=chunking")
    print(f"artifact {artifact.object_key}")
    print(f"checksum {artifact.checksum}")
    print(f"size_bytes {artifact.size_bytes}")
    print(f"parents {artifact.parent_count}")
    print(f"children {artifact.child_count}")
    for warning in artifact.warnings:
        print(f"warning {warning}")


def print_embedding(embedded: EmbeddedVersion) -> None:
    """格式化输出向量嵌入结果信息。"""
    print(f"version {embedded.document_version_id} status=embedding")
    print(f"model {embedded.model}")
    print(f"dimension {embedded.dimension}")
    print(f"children {embedded.child_count}")
    print(f"batches {embedded.batch_count}")


def print_index(indexed: IndexedVersion) -> None:
    """格式化输出索引构建结果信息。"""
    print(f"version {indexed.document_version_id} status=ready")
    print(f"points {indexed.point_count}")
    print(f"children {indexed.child_count}")
