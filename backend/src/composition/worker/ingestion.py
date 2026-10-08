"""Worker 摄取流水线装配：按需装配解析、分块、向量化与索引核验阶段。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.ingestion.chunk import ChunkDocumentVersion
from application.ingestion.document_ingestion import DocumentIngestion
from application.ingestion.embed import EmbedDocumentVersion
from application.ingestion.index import IndexDocumentVersion
from application.ingestion.parse import ParseDocumentVersion
from composition.shared.stores import open_ingestion_store
from domain.knowledge import IngestionStage
from infrastructure.parsing.token_counter import TiktokenTokenCounter

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

    from application.ingestion.parsers import DocumentParser
    from application.shared.providers import EmbeddingProvider
    from application.shared.storage import ObjectStorage
    from application.shared.vectors import VectorIndex
    from domain.parsing import ParseRoute
    from infrastructure.config.settings import Settings
    from infrastructure.db.engine import Database

ALL_INGESTION_STAGES: tuple[IngestionStage, ...] = (
    IngestionStage.PARSE,
    IngestionStage.CHUNK,
    IngestionStage.EMBED,
    IngestionStage.INDEX,
)


def open_ingestion(
    settings: Settings,
    *,
    database: Database,
    objects: ObjectStorage | None = None,
    index: VectorIndex | None = None,
    parsers: Mapping[ParseRoute, DocumentParser] | None = None,
    embedding: EmbeddingProvider | None = None,
    stages: Collection[IngestionStage] = ALL_INGESTION_STAGES,
) -> DocumentIngestion:
    """根据指定的 stages 集合装配文档摄取门面服务。"""
    ingestion_store = open_ingestion_store(database, settings)
    parse: ParseDocumentVersion | None = None
    if IngestionStage.PARSE in stages:
        if objects is None or parsers is None:
            raise RuntimeError("装配解析阶段需要提供对象存储与解析器字典")
        parse = ParseDocumentVersion(
            documents=ingestion_store,
            objects=objects,
            parsers=parsers,
            max_parse_bytes=settings.max_upload_bytes,
            parse_timeout_seconds=settings.parse_timeout_seconds,
        )
    chunk: ChunkDocumentVersion | None = None
    if IngestionStage.CHUNK in stages:
        if objects is None:
            raise RuntimeError("装配分块阶段需要提供对象存储")
        chunk = ChunkDocumentVersion(
            documents=ingestion_store,
            objects=objects,
            counter=TiktokenTokenCounter(),
            max_markdown_bytes=settings.max_upload_bytes,
            chunk_timeout_seconds=settings.chunk_timeout_seconds,
        )
    embed: EmbedDocumentVersion | None = None
    if IngestionStage.EMBED in stages:
        if index is None or embedding is None:
            raise RuntimeError("装配向量化阶段需要提供向量索引与向量化模型提供方")
        embed = EmbedDocumentVersion(
            documents=ingestion_store,
            provider=embedding,
            index=index,
            batch_size=settings.embedding_batch_size,
            embed_timeout_seconds=settings.embed_timeout_seconds,
        )
    index_stage: IndexDocumentVersion | None = None
    if IngestionStage.INDEX in stages:
        if index is None:
            raise RuntimeError("装配索引门控阶段需要提供向量索引")
        index_stage = IndexDocumentVersion(
            documents=ingestion_store,
            index=index,
            index_timeout_seconds=settings.index_timeout_seconds,
        )
    return DocumentIngestion(
        parse=parse,
        chunk=chunk,
        embed=embed,
        index=index_stage,
        documents=ingestion_store,
    )
