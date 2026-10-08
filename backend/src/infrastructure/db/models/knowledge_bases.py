"""知识库目录数据模型。"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.db.base import NAME_LENGTH, Base, DomainUuid


class KnowledgeBaseRow(Base):
    """知识库表数据模型。"""

    __tablename__ = "knowledge_bases"

    id: Mapped[uuid.UUID] = mapped_column(DomainUuid(), primary_key=True)
    # 无外键约束：系统已剥离独立账户表（ADR-0033）。保留该列用于联合唯一键、
    # 索引构建以及校验会话所有权关联（fk_conversations_owner_matches_kb）。
    owner_id: Mapped[uuid.UUID] = mapped_column(DomainUuid(), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(NAME_LENGTH), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text())
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)

    __table_args__ = (
        sa.UniqueConstraint("owner_id", "name", name="uq_knowledge_bases_owner_id_name"),
        sa.UniqueConstraint("id", "owner_id", name="uq_knowledge_bases_id_owner"),
        sa.Index(
            "ix_knowledge_bases_owner_created_id",
            "owner_id",
            sa.text("created_at DESC"),
            "id",
        ),
    )
