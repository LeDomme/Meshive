"""Add canonical tag-assignment rule foundation.

Revision ID: 20260909_37
Revises: 20260906_36

The legacy rule tables remain authoritative in Phase 1.  This migration copies
their configuration (and available automatic-match provenance) into the new
canonical tables without touching ``model_tags``.  Downgrade therefore loses no
legacy or direct-tag data while no Phase-2-only rules have been created.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260909_37"
down_revision: str | Sequence[str] | None = "20260906_36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tag_assignment_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("library_source_id", sa.Integer(), nullable=True),
        sa.Column("match_mode", sa.String(length=32), nullable=False),
        sa.Column("pattern", sa.String(length=255), nullable=True),
        sa.Column("pattern_key", sa.String(length=255), nullable=True),
        sa.Column("path_value", sa.Text(), nullable=True),
        sa.Column("path_relation", sa.String(length=32), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("legacy_kind", sa.String(length=32), nullable=True),
        sa.Column("legacy_rule_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("match_mode IN ('contains', 'regex', 'path_relation')"),
        sa.CheckConstraint(
            "path_relation IS NULL OR path_relation IN "
            "('direct_child', 'self_or_descendant')"
        ),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["library_source_id"], ["library_sources.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("legacy_kind", "legacy_rule_id"),
    )
    op.create_index(
        op.f("ix_tag_assignment_rules_tag_id"), "tag_assignment_rules", ["tag_id"]
    )
    op.create_index(
        op.f("ix_tag_assignment_rules_library_source_id"),
        "tag_assignment_rules",
        ["library_source_id"],
    )
    op.create_index(
        op.f("ix_tag_assignment_rules_enabled"), "tag_assignment_rules", ["enabled"]
    )

    op.create_table(
        "tag_assignment_rule_targets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tag_assignment_rule_id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("folder_segment", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint(
            "target_type IN ('model_relative_path', 'archive_filename', "
            "'archive_entry_path', 'archive_entry_name')"
        ),
        sa.CheckConstraint("folder_segment = 0 OR target_type = 'model_relative_path'"),
        sa.ForeignKeyConstraint(
            ["tag_assignment_rule_id"], ["tag_assignment_rules.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("tag_assignment_rule_id", "target_type", "folder_segment"),
    )
    op.create_index(
        op.f("ix_tag_assignment_rule_targets_tag_assignment_rule_id"),
        "tag_assignment_rule_targets",
        ["tag_assignment_rule_id"],
    )
    op.create_index(
        op.f("ix_tag_assignment_rule_targets_target_type"),
        "tag_assignment_rule_targets",
        ["target_type"],
    )

    op.create_table(
        "tag_assignment_rule_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tag_assignment_rule_id", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["tag_assignment_rule_id"], ["tag_assignment_rules.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["model_id"], ["library_models.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tag_assignment_rule_id", "model_id"),
    )
    op.create_index(
        op.f("ix_tag_assignment_rule_matches_tag_assignment_rule_id"),
        "tag_assignment_rule_matches",
        ["tag_assignment_rule_id"],
    )
    op.create_index(
        op.f("ix_tag_assignment_rule_matches_model_id"),
        "tag_assignment_rule_matches",
        ["model_id"],
    )

    _copy_legacy_rules()


def _copy_legacy_rules() -> None:
    connection = op.get_bind()
    op.execute(
        """
        INSERT INTO tag_assignment_rules
            (tag_id, library_source_id, match_mode, path_value, path_relation, enabled,
             legacy_kind, legacy_rule_id, created_at, updated_at)
        SELECT tag_id, library_source_id, 'path_relation', relative_path,
               CASE WHEN recursive THEN 'self_or_descendant' ELSE 'direct_child' END,
               1, 'folder_tag_rule', id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM folder_tag_rules
        """
    )
    op.execute(
        """
        INSERT INTO tag_assignment_rule_targets
            (tag_assignment_rule_id, target_type, folder_segment)
        SELECT id, 'model_relative_path', 0
        FROM tag_assignment_rules
        WHERE legacy_kind = 'folder_tag_rule'
        """
    )
    op.execute(
        """
        INSERT INTO tag_assignment_rules
            (tag_id, library_source_id, match_mode, pattern, pattern_key, enabled,
             legacy_kind, legacy_rule_id, created_at, updated_at)
        SELECT tag_id, NULL, 'contains', pattern, pattern_key, enabled,
               'automatic_tag_rule', id, created_at, updated_at
        FROM automatic_tag_rules
        """
    )
    for target_type in ("archive_entry_path", "archive_entry_name"):
        connection.execute(
            sa.text(
                """
                INSERT INTO tag_assignment_rule_targets
                    (tag_assignment_rule_id, target_type, folder_segment)
                SELECT id, :target_type, 0
                FROM tag_assignment_rules
                WHERE legacy_kind = 'automatic_tag_rule'
                """
            ),
            {"target_type": target_type},
        )
    op.execute(
        """
        INSERT INTO tag_assignment_rule_matches (tag_assignment_rule_id, model_id, created_at)
        SELECT canonical.id, legacy.model_id, legacy.created_at
        FROM automatic_tag_matches AS legacy
        JOIN tag_assignment_rules AS canonical
          ON canonical.legacy_kind = 'automatic_tag_rule'
         AND canonical.legacy_rule_id = legacy.automatic_tag_rule_id
        """
    )

    # This branch intentionally has no folder-name-regex migration ancestor.  The
    # conditional copy keeps the foundation safe for databases that already contain
    # those tables from an unmerged deployment.
    inspector = sa.inspect(connection)
    if "folder_name_regex_tag_rules" not in inspector.get_table_names():
        return
    op.execute(
        """
        INSERT INTO tag_assignment_rules
            (tag_id, library_source_id, match_mode, pattern, pattern_key, enabled,
             legacy_kind, legacy_rule_id, created_at, updated_at)
        SELECT tag_id, NULL, 'regex', pattern, pattern_key, enabled,
               'folder_name_regex_tag_rule', id, created_at, updated_at
        FROM folder_name_regex_tag_rules
        """
    )
    op.execute(
        """
        INSERT INTO tag_assignment_rule_targets
            (tag_assignment_rule_id, target_type, folder_segment)
        SELECT id, 'model_relative_path', 1
        FROM tag_assignment_rules
        WHERE legacy_kind = 'folder_name_regex_tag_rule'
        """
    )
    if "folder_name_regex_tag_matches" in inspector.get_table_names():
        op.execute(
            """
            INSERT INTO tag_assignment_rule_matches
                (tag_assignment_rule_id, model_id, created_at)
            SELECT canonical.id, legacy.model_id, legacy.created_at
            FROM folder_name_regex_tag_matches AS legacy
            JOIN tag_assignment_rules AS canonical
              ON canonical.legacy_kind = 'folder_name_regex_tag_rule'
             AND canonical.legacy_rule_id = legacy.folder_name_regex_tag_rule_id
            """
        )


def downgrade() -> None:
    # Phase 1 does not expose canonical CRUD and does not alter legacy tables or
    # ModelTag provenance, so dropping only these copied tables is lossless.
    op.drop_table("tag_assignment_rule_matches")
    op.drop_table("tag_assignment_rule_targets")
    op.drop_table("tag_assignment_rules")
