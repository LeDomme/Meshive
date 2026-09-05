"""Add audit event source reference."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260906_36"
down_revision: str | Sequence[str] | None = "20260905_35"
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.batch_alter_table("audit_events") as batch:
        batch.add_column(sa.Column("library_source_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_audit_events_library_source_id", "library_sources", ["library_source_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_audit_events_library_source_id", ["library_source_id"])

def downgrade() -> None:
    with op.batch_alter_table("audit_events") as batch:
        batch.drop_index("ix_audit_events_library_source_id")
        batch.drop_constraint("fk_audit_events_library_source_id", type_="foreignkey")
        batch.drop_column("library_source_id")
