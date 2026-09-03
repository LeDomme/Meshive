"""Add roles, permissions, and source grants.

Revision ID: 20260903_34
Revises: 20260901_33
Create Date: 2026-09-03

Downgrading removes role assignments and source grants. Restore a database
backup before downgrading if those assignments must be retained.
"""

import unicodedata
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_34"
down_revision: str | Sequence[str] | None = "20260901_33"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _normalize_role_name(name: str) -> str:
    return unicodedata.normalize("NFKC", name).strip().casefold()


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("normalized_name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_name"),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_key", sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_key"),
    )
    op.create_table(
        "user_library_sources",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("library_source_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["library_source_id"], ["library_sources.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "library_source_id"),
    )

    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("role_id", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column(
                "all_sources",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    roles = (
        ("Viewer", "View the catalogue without downloads.", False),
        ("Member", "View and download accessible library content.", False),
        ("Curator", "Maintain visible catalogue metadata.", False),
        ("Operator", "Operate scans and diagnostics.", False),
        ("Administrator", "Full system administration.", True),
    )
    roles_table = sa.table(
        "roles",
        sa.column("name", sa.String),
        sa.column("normalized_name", sa.String),
        sa.column("description", sa.Text),
        sa.column("is_system", sa.Boolean),
        sa.column("is_superuser", sa.Boolean),
    )
    op.bulk_insert(
        roles_table,
        [
            {
                "name": name,
                "normalized_name": _normalize_role_name(name),
                "description": description,
                "is_system": True,
                "is_superuser": is_superuser,
            }
            for name, description, is_superuser in roles
        ],
    )

    viewer_permissions = {
        "catalogue.view",
        "archives.view_entries",
        "favorites.manage",
    }
    member_permissions = viewer_permissions | {"archives.download"}
    curator_permissions = member_permissions | {
        "models.primary_image",
        "models.tags",
        "metadata.manage",
        "tags.manage",
        "tag_rules.manage",
    }
    operator_permissions = member_permissions | {
        "catalogue.view_maintenance",
        "models.rescan",
        "models.rebuild_images",
        "models.reset_images",
        "models.delete_missing",
        "scans.view",
        "scans.start",
        "scans.control",
        "diagnostics.view",
    }
    all_permissions = curator_permissions | operator_permissions | {
        "sources.manage",
        "backups.manage",
        "users.manage",
        "roles.manage",
        "audit.view",
    }
    permissions_by_role = {
        "Viewer": viewer_permissions,
        "Member": member_permissions,
        "Curator": curator_permissions,
        "Operator": operator_permissions,
        "Administrator": all_permissions,
    }
    connection = op.get_bind()
    role_ids = dict(
        connection.execute(sa.text("SELECT normalized_name, id FROM roles")).all()
    )
    role_permissions_table = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Integer),
        sa.column("permission_key", sa.String),
    )
    op.bulk_insert(
        role_permissions_table,
        [
            {"role_id": role_ids[_normalize_role_name(name)], "permission_key": key}
            for name, keys in permissions_by_role.items()
            for key in sorted(keys)
        ],
    )

    unknown_roles = connection.scalar(
        sa.text(
            "SELECT COUNT(*) FROM users "
            "WHERE role IS NULL OR role NOT IN ('admin', 'user')"
        )
    )
    if unknown_roles:
        raise RuntimeError("Cannot migrate users with an unknown legacy role")
    connection.execute(
        sa.text("UPDATE users SET role_id = :role_id, all_sources = 1 WHERE role = 'admin'"),
        {"role_id": role_ids[_normalize_role_name("Administrator")]},
    )
    connection.execute(
        sa.text("UPDATE users SET role_id = :role_id, all_sources = 1 WHERE role = 'user'"),
        {"role_id": role_ids[_normalize_role_name("Member")]},
    )
    missing_assignments = connection.scalar(
        sa.text("SELECT COUNT(*) FROM users WHERE role_id IS NULL")
    )
    if missing_assignments:
        raise RuntimeError("Cannot complete role migration with unassigned users")

    with op.batch_alter_table("users") as batch:
        batch.create_foreign_key("fk_users_role_id_roles", "roles", ["role_id"], ["id"], ondelete="RESTRICT")
        batch.create_index("ix_users_role_id", ["role_id"])


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_role_id")
        batch.drop_constraint("fk_users_role_id_roles", type_="foreignkey")
        batch.drop_column("all_sources")
        batch.drop_column("role_id")
    op.drop_table("user_library_sources")
    op.drop_table("role_permissions")
    op.drop_table("roles")
