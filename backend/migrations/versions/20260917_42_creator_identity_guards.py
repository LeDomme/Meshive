"""Guard Creator canonical names and aliases as one global namespace.

Revision ID: 20260917_42
Revises: 20260916_41
"""
from alembic import op

revision = "20260917_42"
down_revision = "20260916_41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite unique indexes cannot span tables. These guards make the
    # application-level validation durable for imports and direct DB writers.
    op.execute("""
        CREATE TRIGGER creator_profiles_identity_insert
        BEFORE INSERT ON creator_profiles
        WHEN EXISTS (SELECT 1 FROM creator_aliases WHERE normalized_alias = NEW.normalized_name)
        BEGIN SELECT RAISE(ABORT, 'creator identity conflicts with alias'); END
    """)
    op.execute("""
        CREATE TRIGGER creator_profiles_identity_update
        BEFORE UPDATE OF normalized_name ON creator_profiles
        WHEN EXISTS (SELECT 1 FROM creator_aliases WHERE normalized_alias = NEW.normalized_name AND creator_profile_id != NEW.id)
        BEGIN SELECT RAISE(ABORT, 'creator identity conflicts with alias'); END
    """)
    op.execute("""
        CREATE TRIGGER creator_aliases_identity_insert
        BEFORE INSERT ON creator_aliases
        WHEN EXISTS (SELECT 1 FROM creator_profiles WHERE normalized_name = NEW.normalized_alias AND id != NEW.creator_profile_id)
        BEGIN SELECT RAISE(ABORT, 'creator alias conflicts with canonical name'); END
    """)
    op.execute("""
        CREATE TRIGGER creator_aliases_identity_update
        BEFORE UPDATE OF normalized_alias, creator_profile_id ON creator_aliases
        WHEN EXISTS (SELECT 1 FROM creator_profiles WHERE normalized_name = NEW.normalized_alias AND id != NEW.creator_profile_id)
        BEGIN SELECT RAISE(ABORT, 'creator alias conflicts with canonical name'); END
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER creator_aliases_identity_update")
    op.execute("DROP TRIGGER creator_aliases_identity_insert")
    op.execute("DROP TRIGGER creator_profiles_identity_update")
    op.execute("DROP TRIGGER creator_profiles_identity_insert")
