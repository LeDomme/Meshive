"""Persist reversible Creator merge history.

Revision ID: 20260917_43
Revises: 20260917_42
"""

import sqlalchemy as sa
from alembic import op

revision = "20260917_43"
down_revision = "20260917_42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite cannot rename a rebuilt table while dependent triggers exist.
    op.execute("DROP TRIGGER creator_aliases_identity_update")
    op.execute("DROP TRIGGER creator_aliases_identity_insert")
    op.execute("DROP TRIGGER creator_profiles_identity_update")
    op.execute("DROP TRIGGER creator_profiles_identity_insert")
    with op.batch_alter_table("creator_profiles") as batch:
        batch.add_column(sa.Column("merged_into_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_creator_profiles_merged_into",
            "creator_profiles",
            ["merged_into_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_creator_profiles_merged_into_id", ["merged_into_id"])
    # batch_alter_table rebuilds SQLite tables and therefore drops their triggers.
    op.execute(
        "CREATE TRIGGER creator_profiles_identity_insert BEFORE INSERT ON creator_profiles WHEN EXISTS (SELECT 1 FROM creator_aliases WHERE normalized_alias = NEW.normalized_name) BEGIN SELECT RAISE(ABORT, 'creator identity conflicts with alias'); END"
    )
    op.execute(
        "CREATE TRIGGER creator_profiles_identity_update BEFORE UPDATE OF normalized_name ON creator_profiles WHEN EXISTS (SELECT 1 FROM creator_aliases WHERE normalized_alias = NEW.normalized_name AND creator_profile_id != NEW.id) BEGIN SELECT RAISE(ABORT, 'creator identity conflicts with alias'); END"
    )
    op.execute(
        "CREATE TRIGGER creator_aliases_identity_insert BEFORE INSERT ON creator_aliases WHEN EXISTS (SELECT 1 FROM creator_profiles WHERE normalized_name = NEW.normalized_alias AND id != NEW.creator_profile_id) BEGIN SELECT RAISE(ABORT, 'creator alias conflicts with canonical name'); END"
    )
    op.execute(
        "CREATE TRIGGER creator_aliases_identity_update BEFORE UPDATE OF normalized_alias, creator_profile_id ON creator_aliases WHEN EXISTS (SELECT 1 FROM creator_profiles WHERE normalized_name = NEW.normalized_alias AND id != NEW.creator_profile_id) BEGIN SELECT RAISE(ABORT, 'creator alias conflicts with canonical name'); END"
    )
    op.create_table(
        "creator_merges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "target_profile_id", sa.Integer(), sa.ForeignKey("creator_profiles.id"), nullable=False
        ),
        sa.Column(
            "source_profile_id", sa.Integer(), sa.ForeignKey("creator_profiles.id"), nullable=False
        ),
        sa.Column("snapshot", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_creator_merges_target_profile_id", "creator_merges", ["target_profile_id"])
    op.create_index("ix_creator_merges_source_profile_id", "creator_merges", ["source_profile_id"])


def downgrade() -> None:
    op.execute("DROP TRIGGER creator_aliases_identity_update")
    op.execute("DROP TRIGGER creator_aliases_identity_insert")
    op.execute("DROP TRIGGER creator_profiles_identity_update")
    op.execute("DROP TRIGGER creator_profiles_identity_insert")
    op.drop_table("creator_merges")
    with op.batch_alter_table("creator_profiles") as batch:
        batch.drop_index("ix_creator_profiles_merged_into_id")
        batch.drop_constraint("fk_creator_profiles_merged_into", type_="foreignkey")
        batch.drop_column("merged_into_id")
    op.execute(
        "CREATE TRIGGER creator_profiles_identity_insert BEFORE INSERT ON creator_profiles WHEN EXISTS (SELECT 1 FROM creator_aliases WHERE normalized_alias = NEW.normalized_name) BEGIN SELECT RAISE(ABORT, 'creator identity conflicts with alias'); END"
    )
    op.execute(
        "CREATE TRIGGER creator_profiles_identity_update BEFORE UPDATE OF normalized_name ON creator_profiles WHEN EXISTS (SELECT 1 FROM creator_aliases WHERE normalized_alias = NEW.normalized_name AND creator_profile_id != NEW.id) BEGIN SELECT RAISE(ABORT, 'creator identity conflicts with alias'); END"
    )
    op.execute(
        "CREATE TRIGGER creator_aliases_identity_insert BEFORE INSERT ON creator_aliases WHEN EXISTS (SELECT 1 FROM creator_profiles WHERE normalized_name = NEW.normalized_alias AND id != NEW.creator_profile_id) BEGIN SELECT RAISE(ABORT, 'creator alias conflicts with canonical name'); END"
    )
    op.execute(
        "CREATE TRIGGER creator_aliases_identity_update BEFORE UPDATE OF normalized_alias, creator_profile_id ON creator_aliases WHEN EXISTS (SELECT 1 FROM creator_profiles WHERE normalized_name = NEW.normalized_alias AND id != NEW.creator_profile_id) BEGIN SELECT RAISE(ABORT, 'creator alias conflicts with canonical name'); END"
    )
