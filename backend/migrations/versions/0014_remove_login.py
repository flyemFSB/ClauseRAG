"""Login is removed: the deployment has one principal, and the account tables go with it.

The platform ships as a demonstration surface (ADR-0033): there is no sign-in, no session cookie and
no per-request identity. Every row that used to belong to an account therefore belongs to the
platform principal, whose identifier is ``PLATFORM_OWNER_ID`` in ``domain.identity`` — spelled out
here rather than imported, because a migration records the schema as it was written.

``owner_id`` stays on ``knowledge_bases`` and ``conversations``. It is not dead weight: the unique
key ``uq_knowledge_bases_owner_id_name``, the conversation index and the
``fk_conversations_owner_matches_kb`` constraint — the one that keeps a conversation in its own
knowledge base — are all built on it, and dropping the column would be a schema rewrite with no
demonstration value. What goes away is the account it pointed at: ownership is re-keyed to the
platform principal first, so the data the accounts used to own stays visible, and only then are
``users`` and ``sessions`` dropped.

The re-key needs ``fk_conversations_owner_matches_kb`` out of the way: it is checked at the end of
each statement, so the knowledge base cannot move to the new owner while its conversations still
name the old one. It is put back unchanged once both tables are on the platform principal.

Revision ID: 0014_remove_login
Revises: 0013_drop_normalize_stage
Create Date: 2026-10-07

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0014_remove_login"
down_revision: str | None = "0013_drop_normalize_stage"
branch_labels: str | None = None
depends_on: str | None = None

# ``domain.identity.PLATFORM_OWNER_ID``, frozen at this revision's date.
_PLATFORM_OWNER_ID = "00000000-0000-0000-0000-000000000001"

# The one canonical-email rule 0007 added, recreated by the downgrade.
_EMAIL_CANONICAL_CHECK = "email = lower(email) AND email = btrim(email)"


def upgrade() -> None:
    # The server-side half of the cookie: nothing reads it once there is no login.
    op.drop_table("sessions")

    op.drop_constraint("fk_conversations_owner_matches_kb", "conversations", type_="foreignkey")
    op.drop_constraint("fk_knowledge_bases_owner_id_users", "knowledge_bases", type_="foreignkey")
    op.drop_constraint("fk_conversations_owner_id_users", "conversations", type_="foreignkey")

    # ``uq_knowledge_bases_owner_id_name`` is the bound on this re-key: two accounts that named a
    # knowledge base identically collide once they share a principal, and the migration fails loudly
    # rather than renaming somebody's knowledge base behind their back.
    op.execute(f"UPDATE knowledge_bases SET owner_id = '{_PLATFORM_OWNER_ID}'")
    op.execute(f"UPDATE conversations SET owner_id = '{_PLATFORM_OWNER_ID}'")

    op.create_foreign_key(
        "fk_conversations_owner_matches_kb",
        "conversations",
        "knowledge_bases",
        ["knowledge_base_id", "owner_id"],
        ["id", "owner_id"],
        ondelete="CASCADE",
    )
    op.drop_table("users")


def downgrade() -> None:
    """The account tables come back empty of meaning; the accounts themselves do not.

    Passwords were hashes of credentials nobody is left to present, so restoring the rows would only
    restore a login nothing can pass. What the downgrade restores is the shape: ``users`` and
    ``sessions`` as 0007 left them, plus the platform principal as the account every re-keyed row
    already points at — without that row the restored foreign key would have no target. ``sessions``
    stays empty, which is what its rows were worth after the upgrade.
    """
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(_EMAIL_CANONICAL_CHECK, name="ck_users_email_canonical"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    # A hash no Argon2id verification can ever match: the account exists to own rows, not to log in.
    op.execute(
        "INSERT INTO users (id, email, password_hash, display_name, is_active, created_at, "
        f"updated_at) VALUES ('{_PLATFORM_OWNER_ID}', 'platform@local', '!no-login', "
        "'ClauseRAG', false, now(), now())"
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_sessions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_foreign_key(
        "fk_knowledge_bases_owner_id_users",
        "knowledge_bases",
        "users",
        ["owner_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_conversations_owner_id_users",
        "conversations",
        "users",
        ["owner_id"],
        ["id"],
    )
