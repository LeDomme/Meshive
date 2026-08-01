"""Add recovery email addresses and one-time action tokens.

Revision ID: 20260802_16
Revises: 20260802_15
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260802_16"
down_revision: str | Sequence[str] | None = "20260802_15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("email", sa.String(320), nullable=True))
        batch_op.add_column(
            sa.Column("normalized_email", sa.String(320), nullable=True)
        )
        batch_op.add_column(
            sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_index(
            op.f("ix_users_normalized_email"),
            ["normalized_email"],
            unique=True,
        )

    op.create_table(
        "user_action_tokens",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        op.f("ix_user_action_tokens_user_id"),
        "user_action_tokens",
        ["user_id"],
    )
    op.create_index(
        op.f("ix_user_action_tokens_purpose"),
        "user_action_tokens",
        ["purpose"],
    )
    op.create_index(
        op.f("ix_user_action_tokens_expires_at"),
        "user_action_tokens",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_table("user_action_tokens")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index(op.f("ix_users_normalized_email"))
        batch_op.drop_column("email_verified_at")
        batch_op.drop_column("normalized_email")
        batch_op.drop_column("email")
