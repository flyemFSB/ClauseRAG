"""pgvector 业务稠密向量索引适配器实现（原生 HNSW cosine）。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Literal, cast

import sqlalchemy as sa
import structlog
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError

from application.shared.vectors import VectorIndexError, VectorIndexRejectedError
from domain.knowledge import DocumentVersionStatus, IngestionJobStatus, IngestionStage
from domain.retrieval import ChannelMatch
from infrastructure.db.models.chunks import (
    EMBEDDINGS_HNSW_INDEX,
    EMBEDDINGS_TABLE,
    ChildChunkEmbeddingRow,
    ChildChunkRow,
)
from infrastructure.db.models.documents import DocumentRow, DocumentVersionRow
from infrastructure.db.models.ingestion import IngestionJobRow

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Sequence
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from domain.embedding import EmbeddingWriteGuard, VectorPoint

log = structlog.get_logger(__name__)

# 常见瞬态连接与事务异常类型。
_TRANSIENT_ERRORS = (OperationalError, InterfaceError)
# 允许重试的 SQLSTATE 类别（连接、事务回滚、资源不足、运维干预）。
_RETRYABLE_SQLSTATE_CLASSES = frozenset({"08", "40", "53", "57"})

IterativeScan = Literal["off", "relaxed_order", "strict_order"]


def _is_transient(error: Exception) -> bool:
    """判断数据库异常是否属于可重试的瞬态失败。"""
    if isinstance(error, _TRANSIENT_ERRORS):
        return True
    sqlstate = getattr(getattr(error, "orig", None), "sqlstate", None)
    return isinstance(sqlstate, str) and sqlstate[:2] in _RETRYABLE_SQLSTATE_CLASSES


class PgVectorChildChunkIndex:
    """基于 PostgreSQL vector 列与 HNSW cosine 索引的稠密向量检索适配器。"""

    def __init__(
        self,
        *,
        sessions: async_sessionmaker[AsyncSession],
        dimension: int,
        model: str,
        ef_search: int,
        iterative_scan: IterativeScan,
        max_scan_tuples: int,
    ) -> None:
        self._sessions = sessions
        self._dimension = dimension
        self._model = model
        self._ef_search = ef_search
        self._iterative_scan = iterative_scan
        self._max_scan_tuples = max_scan_tuples

    async def ensure_ready(self) -> None:
        """只读校验 vector 扩展、向量维度契约与 HNSW 索引就绪状态。"""
        async with self._sessions() as session:
            row = (
                await session.execute(
                    sa.text(
                        """
                        SELECT
                            (SELECT extversion FROM pg_extension WHERE extname = 'vector')
                                AS extension_version,
                            (SELECT a.atttypmod FROM pg_attribute a
                              WHERE a.attrelid = to_regclass(:embeddings_table)
                                AND a.attname = 'embedding' AND a.attnum > 0)
                                AS declared_dimension,
                            (SELECT i.indisvalid AND i.indisready FROM pg_index i
                              WHERE i.indexrelid = to_regclass(:index_name))
                                AS hnsw_ready
                        """
                    ),
                    {"index_name": EMBEDDINGS_HNSW_INDEX, "embeddings_table": EMBEDDINGS_TABLE},
                )
            ).one()
        if row.extension_version is None or row.declared_dimension is None:
            raise VectorIndexRejectedError(
                f"数据库缺少 vector 扩展或 {EMBEDDINGS_TABLE} 表；"
                "请先执行 schema-init 初始化数据库表结构"
            )
        if int(row.declared_dimension) != self._dimension:
            raise VectorIndexRejectedError(
                f"{EMBEDDINGS_TABLE}.embedding 的宽度为 {row.declared_dimension}，"
                f"与当前部署要求的 {self._dimension} 不一致；"
                "换向量模型要重建整个语料，不能直接往不同宽度的列里写"
            )
        if row.hnsw_ready is not True:
            raise VectorIndexRejectedError(
                f"近似最近邻索引 {EMBEDDINGS_HNSW_INDEX} 不存在或不可用；"
                "请执行 schema-init 初始化结构，或修复后以 CONCURRENTLY 方式重建"
            )

    async def upsert(self, points: Sequence[VectorPoint], *, guard: EmbeddingWriteGuard) -> None:
        """在写入门控仍有效时批量插入或更新子块向量。"""
        if not points:
            return
        statement = _upsert_statement(points, dimension=self._dimension, model=self._model)
        async with (
            _classified(f"写入 {len(points)} 条子块向量"),
            self._sessions() as session,
            session.begin(),
        ):
            await session.execute(
                statement,
                {
                    "version_id": guard.document_version_id,
                    "job_id": guard.job_id,
                    "attempt": guard.attempt,
                    "stage": IngestionStage.EMBED.value,
                    "job_status": IngestionJobStatus.RUNNING.value,
                },
            )

    async def search_dense(
        self,
        *,
        vector: Sequence[float],
        knowledge_base_id: UUID,
        limit: int,
    ) -> Sequence[ChannelMatch]:
        """按知识库与就绪状态过滤检索最近邻子块。"""
        if limit <= 0:
            return ()
        distance = ChildChunkEmbeddingRow.embedding.cosine_distance(list(vector))
        statement = (
            sa.select(
                ChildChunkRow.child_id,
                ChildChunkRow.parent_id,
                ChildChunkRow.document_version_id,
                (sa.literal(1.0) - distance).label("score"),
            )
            .join(
                ChildChunkRow,
                ChildChunkRow.child_id == ChildChunkEmbeddingRow.child_id,
            )
            .join(
                DocumentVersionRow,
                DocumentVersionRow.id == ChildChunkRow.document_version_id,
            )
            .join(DocumentRow, DocumentRow.id == DocumentVersionRow.document_id)
            .where(
                ChildChunkEmbeddingRow.knowledge_base_id == knowledge_base_id,
                DocumentRow.knowledge_base_id == knowledge_base_id,
                DocumentVersionRow.status == DocumentVersionStatus.READY.value,
                ChildChunkEmbeddingRow.embedding_model == self._model,
            )
            .order_by(distance)
            .limit(limit)
        )
        async with (
            _classified(f"在知识库中检索前 {limit} 条近邻"),
            self._sessions() as session,
            session.begin(),
        ):
            await self._apply_ann_settings(session)
            rows = (await session.execute(statement)).all()
        return tuple(
            ChannelMatch(
                child_id=row.child_id,
                parent_id=row.parent_id,
                document_version_id=row.document_version_id,
                score=float(row.score),
            )
            for row in rows
        )

    async def count_for_version(self, document_version_id: UUID) -> int:
        """统计指定文档版本当前模型下的有效向量数。"""
        statement = (
            sa.select(sa.func.count())
            .select_from(ChildChunkEmbeddingRow)
            .join(ChildChunkRow, ChildChunkRow.child_id == ChildChunkEmbeddingRow.child_id)
            .where(
                ChildChunkRow.document_version_id == document_version_id,
                ChildChunkEmbeddingRow.embedding_model == self._model,
            )
        )
        async with _classified("统计文档版本的向量条数"), self._sessions() as session:
            count = await session.scalar(statement)
        return int(count or 0)

    async def delete_versions(self, document_version_ids: Sequence[UUID]) -> None:
        """删除指定文档版本的全部向量记录。"""
        if not document_version_ids:
            return
        statement = sa.delete(ChildChunkEmbeddingRow).where(
            ChildChunkEmbeddingRow.child_id.in_(
                sa.select(ChildChunkRow.child_id).where(
                    ChildChunkRow.document_version_id.in_(list(document_version_ids))
                )
            )
        )
        await self._delete(statement, f"删除 {len(document_version_ids)} 个文档版本的向量")

    async def delete_knowledge_base(self, knowledge_base_id: UUID) -> None:
        """删除指定知识库的全部向量。"""
        statement = sa.delete(ChildChunkEmbeddingRow).where(
            ChildChunkEmbeddingRow.knowledge_base_id == knowledge_base_id
        )
        await self._delete(statement, "删除知识库的向量")

    async def _delete(self, statement: sa.Delete, what: str) -> None:
        async with _classified(what), self._sessions() as session, session.begin():
            await session.execute(statement)

    async def _apply_ann_settings(self, session: AsyncSession) -> None:
        """在当前事务内局部设置 HNSW 检索参数。"""
        settings = (
            f"SET LOCAL hnsw.ef_search = {int(self._ef_search)}",
            f"SET LOCAL hnsw.iterative_scan = {self._iterative_scan}",
        )
        for statement in settings:
            await session.execute(sa.text(statement))
        if self._iterative_scan != "off":
            await session.execute(
                sa.text(f"SET LOCAL hnsw.max_scan_tuples = {int(self._max_scan_tuples)}")
            )


@asynccontextmanager
async def _classified(what: str) -> AsyncGenerator[None]:
    """将底层数据库异常分类转换为向量索引业务异常。"""
    try:
        yield
    except TimeoutError as error:
        raise VectorIndexError(f"{what}时数据库连接超时: {type(error).__name__}") from error
    except DBAPIError as error:
        if _is_transient(error):
            raise VectorIndexError(f"{what}时数据库暂时不可用: {type(error).__name__}") from error
        raise VectorIndexRejectedError(f"{what}被数据库拒绝: {type(error).__name__}") from error


def _upsert_statement(
    points: Sequence[VectorPoint],
    *,
    dimension: int,
    model: str,
) -> sa.Insert:
    """构造带写入门控与权威归属推导的批量落库语句。"""
    # 显式转换 VECTOR 类型以避免 VALUES 列表被误推断为文本。
    incoming = sa.values(
        sa.column("child_id", sa.Uuid),
        sa.column("embedding", VECTOR(dimension)),
        name="incoming",
    ).data([(point.child_id, list(point.vector)) for point in points])
    eligible = (
        sa.select(sa.literal(1))
        .select_from(IngestionJobRow)
        .where(
            IngestionJobRow.id == sa.bindparam("job_id"),
            IngestionJobRow.document_version_id == sa.bindparam("version_id"),
            IngestionJobRow.stage == sa.bindparam("stage"),
            IngestionJobRow.status == sa.bindparam("job_status"),
            IngestionJobRow.attempt == sa.bindparam("attempt"),
            IngestionJobRow.lease_expires_at > sa.func.now(),
        )
        .exists()
    )
    staged = (
        sa.select(
            ChildChunkRow.child_id,
            DocumentRow.knowledge_base_id,
            sa.literal(model),
            sa.cast(incoming.c.embedding, VECTOR(dimension)),
        )
        .select_from(incoming)
        .join(ChildChunkRow, ChildChunkRow.child_id == incoming.c.child_id)
        .join(
            DocumentVersionRow,
            DocumentVersionRow.id == ChildChunkRow.document_version_id,
        )
        .join(DocumentRow, DocumentRow.id == DocumentVersionRow.document_id)
        .where(eligible)
    )
    # 使用 Core Table 避免 ORM 批量插入路径解析 from_select 失败。
    table = cast("sa.Table", ChildChunkEmbeddingRow.__table__)
    statement = postgres_insert(table).from_select(
        ["child_id", "knowledge_base_id", "embedding_model", "embedding"],
        staged,
    )
    # 冲突时仅更新向量值与模型名，保持归属字段不可篡改。
    return statement.on_conflict_do_update(
        index_elements=[table.c.child_id],
        set_={
            "embedding": statement.excluded.embedding,
            "embedding_model": statement.excluded.embedding_model,
        },
    )
