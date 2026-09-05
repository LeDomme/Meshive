"""Add audit events."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260905_35"
down_revision: str | Sequence[str] | None = "20260903_34"
branch_labels = None
depends_on = None
def upgrade() -> None:
    op.create_table("audit_events", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")), sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True), sa.Column("actor_username", sa.String(120), nullable=False), sa.Column("action", sa.String(100), nullable=False), sa.Column("target_type", sa.String(60), nullable=False), sa.Column("target_id", sa.Integer(), nullable=True), sa.Column("target_label", sa.String(255), nullable=False), sa.Column("details", sa.JSON(), nullable=True))
    for key in ("created_at", "action", "actor_user_id"): op.create_index(f"ix_audit_events_{key}", "audit_events", [key])
def downgrade() -> None:
    op.drop_table("audit_events")
