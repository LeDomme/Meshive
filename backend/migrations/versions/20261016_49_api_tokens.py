"""Add personal API tokens.

Revision ID: 20261016_49
Revises: 20261015_48
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261016_49"
down_revision: str | None = "20261015_48"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_prefix", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_api_tokens_user_id"), "api_tokens", ["user_id"])
    op.create_index(
        op.f("ix_api_tokens_token_hash"),
        "api_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(op.f("ix_api_tokens_expires_at"), "api_tokens", ["expires_at"])

    connection = op.get_bind()
    administrator_role_id = connection.execute(
        sa.text("SELECT id FROM roles WHERE normalized_name = :name"),
        {"name": "administrator"},
    ).scalar_one_or_none()
    if administrator_role_id is not None:
        connection.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_key) "
                "SELECT :role_id, :permission_key "
                "WHERE NOT EXISTS ("
                "SELECT 1 FROM role_permissions "
                "WHERE role_id = :role_id AND permission_key = :permission_key"
                ")"
            ),
            {
                "role_id": administrator_role_id,
                "permission_key": "api_tokens.manage_own",
            },
        )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_key = 'api_tokens.manage_own'"
        )
    )
    op.drop_index(op.f("ix_api_tokens_expires_at"), table_name="api_tokens")
    op.drop_index(op.f("ix_api_tokens_token_hash"), table_name="api_tokens")
    op.drop_index(op.f("ix_api_tokens_user_id"), table_name="api_tokens")
    op.drop_table("api_tokens")
