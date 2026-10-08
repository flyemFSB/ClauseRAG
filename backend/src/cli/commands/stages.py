"""stages 命令：单阶段离线手动执行与索引重建。"""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING
from uuid import UUID

from cli.output import print_stage_failure, print_stage_outcome
from domain.chunks.errors import ChunkError
from domain.embedding import EmbeddingError, IndexingError
from domain.knowledge import IngestionStage, KnowledgeNotFoundError
from domain.parsing import DocumentParseError

if TYPE_CHECKING:
    from application.ingestion.document_ingestion import StageOutcome
    from composition.cli.runtime import StageRuntime


RUNNABLE_STAGES = (
    IngestionStage.PARSE,
    IngestionStage.CHUNK,
    IngestionStage.EMBED,
    IngestionStage.INDEX,
)


def run_stage(runtime: StageRuntime, stage: IngestionStage, version_id: UUID) -> int:
    """同步执行指定摄取阶段并输出结果。"""
    try:
        outcome = asyncio.run(run_once_async(runtime, stage, version_id))
    except KnowledgeNotFoundError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except (DocumentParseError, ChunkError, EmbeddingError, IndexingError) as error:
        print_stage_failure(version_id, error)
        return 1
    print_stage_outcome(outcome)
    return 0


def reindex(runtime: StageRuntime, version_id: UUID) -> int:
    """重新生成向量嵌入并更新向量索引。"""
    try:
        asyncio.run(reindex_async(runtime, version_id))
    except KnowledgeNotFoundError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except (DocumentParseError, ChunkError, EmbeddingError, IndexingError) as error:
        print_stage_failure(version_id, error)
        return 1
    return 0


async def reindex_async(runtime: StageRuntime, version_id: UUID) -> None:
    """在同一事件循环中执行嵌入与索引阶段。"""
    try:
        print(f"rebuild of document version {version_id}")
        print("stage embed")
        print_stage_outcome(
            await runtime.ingestion.run_once(
                stage=IngestionStage.EMBED,
                document_version_id=version_id,
            )
        )
        print("stage index")
        print_stage_outcome(
            await runtime.ingestion.run_once(
                stage=IngestionStage.INDEX,
                document_version_id=version_id,
            )
        )
    finally:
        await runtime.close()


def parse_version_id(raw: str) -> UUID | None:
    """解析并校验文档版本 UUID。"""
    try:
        return UUID(raw)
    except ValueError:
        print(f"error: {raw} is not a document version identifier", file=sys.stderr)
        return None


async def run_once_async(
    runtime: StageRuntime,
    stage: IngestionStage,
    version_id: UUID,
) -> StageOutcome:
    """执行单阶段任务并释放运行时资源。"""
    try:
        return await runtime.ingestion.run_once(stage=stage, document_version_id=version_id)
    finally:
        await runtime.close()
