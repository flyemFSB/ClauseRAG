"""Qdrant 业务稠密向量索引适配器实现。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from qdrant_client import AsyncQdrantClient, models

from application.shared.vectors import VectorIndexError, VectorIndexRejectedError
from domain.embedding import INDEXED_PAYLOAD_FIELDS
from domain.retrieval import ChannelMatch

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain.embedding import VectorPoint

log = structlog.get_logger(__name__)

_UUID_PAYLOAD_FIELDS = frozenset(
    {"knowledge_base_id", "document_version_id", "document_id", "parent_id"}
)
_REJECTED_STATUSES = frozenset({400, 401, 403, 404, 409, 422})


class QdrantChildChunkIndex:
    """管理文档切片向量点在 Qdrant 中的集合创建、索引构建、插入与检索。"""

    def __init__(
        self,
        *,
        url: str,
        api_key: str | None,
        collection: str,
        dimension: int,
        timeout_seconds: int,
    ) -> None:
        self._url = url
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._collection = collection
        self._dimension = dimension
        self._lock = asyncio.Lock()
        self._client: AsyncQdrantClient | None = None

    @property
    def collection(self) -> str:
        return self._collection

    async def _connection(self) -> AsyncQdrantClient:
        async with self._lock:
            if self._client is None:
                self._client = AsyncQdrantClient(
                    url=self._url,
                    api_key=self._api_key,
                    timeout=self._timeout_seconds,
                )
            return self._client

    async def ensure_ready(self) -> None:
        """确保存储集合与关键载荷字段索引已创建，并验证向量维度一致性。"""
        try:
            client = await self._connection()
            exists = await client.collection_exists(self._collection)
            if not exists:
                await client.create_collection(
                    collection_name=self._collection,
                    vectors_config=models.VectorParams(
                        size=self._dimension,
                        distance=models.Distance.COSINE,
                    ),
                )
                log.info(
                    "向量索引集合创建成功",
                    collection=self._collection,
                    dimension=self._dimension,
                )
            indexed, size = await self._existing_layout(client)
        except Exception as error:
            raise self._failure(error, "检查或初始化集合就绪状态") from error
        if size is not None and size != self._dimension:
            raise VectorIndexRejectedError(
                f"集合 {self._collection} 的向量维度为 {size}，"
                f"与当前部署要求的 {self._dimension} 维度不一致；"
                "禁止向不同维度的旧集合写入数据"
            )
        for field in INDEXED_PAYLOAD_FIELDS:
            if field in indexed:
                continue
            try:
                await client.create_payload_index(
                    collection_name=self._collection,
                    field_name=field,
                    field_schema=self._schema_for(field),
                )
            except Exception as error:
                raise self._failure(error, f"为载荷字段 {field} 创建索引") from error
            log.info("向量索引载荷字段索引创建成功", collection=self._collection, field=field)

    async def upsert(self, points: Sequence[VectorPoint]) -> None:
        """批量写入或更新向量点数据。"""
        if not points:
            return
        structures = [
            models.PointStruct(
                id=str(point.point_id),
                vector=list(point.vector),
                payload=dict(point.payload),
            )
            for point in points
        ]
        try:
            client = await self._connection()
            await client.upsert(
                collection_name=self._collection,
                points=structures,
                wait=True,
            )
        except Exception as error:
            raise self._failure(error, f"写入 {len(structures)} 个向量点") from error

    async def search_dense(
        self,
        *,
        vector: Sequence[float],
        knowledge_base_id: UUID,
        limit: int,
    ) -> Sequence[ChannelMatch]:
        """按知识库 ID 范围检索最相似的切片点。"""
        if limit <= 0:
            return ()
        try:
            client = await self._connection()
            if not await client.collection_exists(self._collection):
                return ()
            response = await client.query_points(
                collection_name=self._collection,
                query=list(vector),
                query_filter=self._filter("knowledge_base_id", str(knowledge_base_id)),
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as error:
            raise self._failure(error, f"在知识库中检索前 {limit} 个向量点") from error
        return tuple(self._match(point) for point in response.points)

    async def count_for_version(self, document_version_id: UUID) -> int:
        """精确统计指定文档版本的向量点数量。"""
        count_filter = self._filter("document_version_id", str(document_version_id))
        try:
            client = await self._connection()
            result = await client.count(
                collection_name=self._collection,
                count_filter=count_filter,
                exact=True,
            )
        except Exception as error:
            raise self._failure(error, "统计单文档版本的向量点数量") from error
        return result.count

    async def delete_versions(self, document_version_ids: Sequence[UUID]) -> None:
        """删除指定文档版本对应的全部向量点。"""
        if not document_version_ids:
            return
        try:
            client = await self._connection()
            if not await client.collection_exists(self._collection):
                return
            await client.delete(
                collection_name=self._collection,
                points_selector=models.FilterSelector(
                    filter=self._filter(
                        "document_version_id",
                        [str(version_id) for version_id in document_version_ids],
                    )
                ),
                wait=True,
            )
        except Exception as error:
            raise self._failure(error, "删除指定文档版本的向量点") from error

    async def delete_knowledge_base(self, knowledge_base_id: UUID) -> None:
        """删除指定知识库下的全部向量点。"""
        try:
            client = await self._connection()
            if not await client.collection_exists(self._collection):
                return
            await client.delete(
                collection_name=self._collection,
                points_selector=models.FilterSelector(
                    filter=self._filter("knowledge_base_id", str(knowledge_base_id))
                ),
                wait=True,
            )
        except Exception as error:
            raise self._failure(error, "删除指定知识库下的向量点") from error

    async def close(self) -> None:
        async with self._lock:
            client, self._client = self._client, None
        if client is not None:
            await client.close()

    async def _existing_layout(
        self,
        client: AsyncQdrantClient,
    ) -> tuple[frozenset[str], int | None]:
        info = await client.get_collection(self._collection)
        vectors = info.config.params.vectors
        size = None if vectors is None or isinstance(vectors, dict) else vectors.size
        return frozenset(info.payload_schema or {}), size

    @staticmethod
    def _match(point: models.ScoredPoint) -> ChannelMatch:
        payload = point.payload or {}
        try:
            child_id = UUID(str(payload["child_id"]))
            parent_id = UUID(str(payload["parent_id"]))
            document_version_id = UUID(str(payload["document_version_id"]))
        except (KeyError, ValueError) as error:
            raise VectorIndexRejectedError(
                f"集合中向量点 {point.id} 缺少召回协议所需的主键标识 "
                "(child_id/parent_id/document_version_id)"
            ) from error
        return ChannelMatch(
            child_id=child_id,
            parent_id=parent_id,
            document_version_id=document_version_id,
            score=float(point.score),
        )

    @staticmethod
    def _schema_for(field: str) -> models.PayloadSchemaType:
        if field in _UUID_PAYLOAD_FIELDS:
            return models.PayloadSchemaType.UUID
        return models.PayloadSchemaType.KEYWORD

    @staticmethod
    def _filter(key: str, value: str | list[str]) -> models.Filter:
        match: models.Match = (
            models.MatchValue(value=value) if isinstance(value, str) else models.MatchAny(any=value)
        )
        return models.Filter(must=[models.FieldCondition(key=key, match=match)])

    def _failure(self, error: Exception, what: str) -> VectorIndexError:
        status = getattr(error, "status_code", None)
        detail = f"{type(error).__name__}" + (f" HTTP {status}" if status else "")
        message = f"向量索引集合 {self._collection} 执行「{what}」失败: {detail}"
        if status in _REJECTED_STATUSES:
            return VectorIndexRejectedError(message)
        return VectorIndexError(message)
