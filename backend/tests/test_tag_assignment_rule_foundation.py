from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from meshive.auth.access import require_tag_assignment_rules_manage
from meshive.auth.permissions import TAG_RULES_MANAGE
from meshive.config import get_settings
from meshive.database import Base
from meshive.models.authorization import Role, RolePermission
from meshive.models.catalog import LibraryModel
from meshive.models.library_source import LibrarySource
from meshive.models.tag import (
    AutomaticTagMatch,
    AutomaticTagRule,
    FolderTagRule,
    ModelTag,
    Tag,
    TagAssignmentRule,
    TagAssignmentRuleMatch,
    TagAssignmentRuleTarget,
)
from meshive.models.user import User
from meshive.services.tag_assignment_rules import (
    PATH_DIRECT_CHILD,
    PATH_SELF_OR_DESCENDANT,
    compile_case_insensitive_regex,
    matches_legacy_folder_path,
)


def test_assignment_rule_migration_copies_legacy_rules_without_touching_tags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "tag-assignment-rules.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("MESHIVE_DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config("backend/alembic.ini")
    try:
        command.upgrade(config, "20260906_36")
        engine = create_engine(database_url)
        with Session(engine) as session:
            source = LibrarySource(
                name="Library",
                root_path="/private/library",
                directory_pattern="{model_folder}",
                archive_formats=["zip"],
                image_formats=["jpg"],
                is_active=True,
                scan_enabled=True,
            )
            folder_tag = Tag(name="Folder tag")
            automatic_tag = Tag(name="Automatic tag")
            direct_tag = Tag(name="Direct tag")
            session.add_all([source, folder_tag, automatic_tag, direct_tag])
            session.flush()
            model = LibraryModel(
                library_source_id=source.id,
                relative_path="Series/Model",
                name="Model",
                status="available",
            )
            session.add(model)
            session.flush()
            folder_rule = FolderTagRule(
                library_source_id=source.id,
                relative_path="Series",
                tag_id=folder_tag.id,
                recursive=True,
            )
            automatic_rule = AutomaticTagRule(
                tag_id=automatic_tag.id,
                pattern="private-pattern",
                pattern_key="private-pattern",
                enabled=True,
            )
            session.add_all([folder_rule, automatic_rule])
            session.flush()
            session.add(AutomaticTagMatch(automatic_tag_rule_id=automatic_rule.id, model_id=model.id, matched_path="private/path"))
            # This fixture intentionally exercises the pre-provenance schema.
            session.execute(
                text(
                    "INSERT INTO model_tags (model_id, tag_id, is_direct, is_inherited, is_automatic) "
                    "VALUES (:model_id, :tag_id, 1, 0, 0)"
                ),
                {"model_id": model.id, "tag_id": direct_tag.id},
            )
            session.commit()
            legacy_ids = (folder_rule.id, automatic_rule.id, model.id, direct_tag.id)
            automatic_tag_id = automatic_tag.id

        # This branch does not have the unmerged FolderNameRegex migration as an
        # ancestor.  Model its tables explicitly to prove the defensive copy path.
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE folder_name_regex_tag_rules "
                    "(id INTEGER PRIMARY KEY, tag_id INTEGER NOT NULL, pattern TEXT NOT NULL, "
                    "pattern_key TEXT NOT NULL, enabled BOOLEAN NOT NULL, "
                    "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE folder_name_regex_tag_matches "
                    "(id INTEGER PRIMARY KEY, folder_name_regex_tag_rule_id INTEGER NOT NULL, "
                    "model_id INTEGER NOT NULL, created_at DATETIME NOT NULL)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO folder_name_regex_tag_rules "
                    "(id, tag_id, pattern, pattern_key, enabled, created_at, updated_at) "
                    "VALUES (9, :tag_id, '_p[12]$', '_p[12]$', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"tag_id": automatic_tag_id},
            )
            connection.execute(
                text(
                    "INSERT INTO folder_name_regex_tag_matches "
                    "(id, folder_name_regex_tag_rule_id, model_id, created_at) "
                    "VALUES (9, 9, :model_id, CURRENT_TIMESTAMP)"
                ),
                {"model_id": model.id},
            )

        command.upgrade(config, "head")
        with Session(engine) as session:
            copied = list(session.scalars(select(TagAssignmentRule).order_by(TagAssignmentRule.id)))
            assert len(copied) == 3
            folder = next(rule for rule in copied if rule.legacy_kind == "folder_tag_rule")
            automatic = next(rule for rule in copied if rule.legacy_kind == "automatic_tag_rule")
            folder_regex = next(
                rule for rule in copied if rule.legacy_kind == "folder_name_regex_tag_rule"
            )
            assert folder.legacy_rule_id == legacy_ids[0]
            assert folder.match_mode == "path_relation"
            assert folder.library_source_id is not None
            assert folder.path_value == "Series"
            assert folder.path_relation == PATH_SELF_OR_DESCENDANT
            assert automatic.legacy_rule_id == legacy_ids[1]
            assert automatic.match_mode == "contains"
            assert automatic.pattern == "private-pattern"
            assert folder_regex.match_mode == "regex"
            assert folder_regex.pattern == "_p[12]$"
            targets = list(session.scalars(select(TagAssignmentRuleTarget)))
            assert {(target.tag_assignment_rule_id, target.target_type, target.folder_segment) for target in targets} == {
                (folder.id, "model_relative_path", False),
                (automatic.id, "archive_entry_path", False),
                (automatic.id, "archive_entry_name", False),
                (folder_regex.id, "model_relative_path", True),
            }
            matches = list(session.scalars(select(TagAssignmentRuleMatch)))
            assert len(matches) == 2
            assert {match.model_id for match in matches} == {legacy_ids[2]}
            direct = session.scalar(select(ModelTag).where(ModelTag.tag_id == legacy_ids[3]))
            assert direct is not None and direct.is_direct is True

        inspector = inspect(engine)
        assert {"tag_assignment_rules", "tag_assignment_rule_targets", "tag_assignment_rule_matches"} <= set(inspector.get_table_names())
        assert {"ix_tag_assignment_rules_tag_id", "ix_tag_assignment_rules_library_source_id", "ix_tag_assignment_rules_enabled"} <= {index["name"] for index in inspector.get_indexes("tag_assignment_rules")}
        assert {"ix_tag_assignment_rule_matches_tag_assignment_rule_id", "ix_tag_assignment_rule_matches_model_id"} <= {index["name"] for index in inspector.get_indexes("tag_assignment_rule_matches")}

        command.downgrade(config, "20260906_36")
        inspector = inspect(engine)
        assert "tag_assignment_rules" not in inspector.get_table_names()
        with Session(engine) as session:
            assert session.get(FolderTagRule, legacy_ids[0]) is not None
            assert session.get(AutomaticTagRule, legacy_ids[1]) is not None
            assert session.scalar(
                text("SELECT id FROM model_tags WHERE tag_id = :tag_id"),
                {"tag_id": legacy_ids[3]},
            ) is not None

        command.upgrade(config, "head")
        with Session(engine) as session:
            assert len(list(session.scalars(select(TagAssignmentRule)))) == 3
        engine.dispose()
    finally:
        get_settings.cache_clear()


def test_assignment_rule_foundation_preserves_legacy_path_and_safe_regex_semantics() -> None:
    assert matches_legacy_folder_path("Series/Model", "Series", PATH_DIRECT_CHILD)
    assert not matches_legacy_folder_path("Series/Sub/Model", "Series", PATH_DIRECT_CHILD)
    assert matches_legacy_folder_path("Series/Model", "Series", PATH_SELF_OR_DESCENDANT)
    assert matches_legacy_folder_path("Series/Sub/Model", "Series", PATH_SELF_OR_DESCENDANT)
    pattern, key, compiled = compile_case_insensitive_regex("_p[12]$")
    assert pattern == "_p[12]$"
    assert key == "_p[12]$"
    assert compiled.search("PSUP_P2")
    assert compiled.search("foo_p10") is None
    with pytest.raises(ValueError, match="Invalid RE2 pattern"):
        compile_case_insensitive_regex("(")


def test_assignment_rule_management_requires_tag_rules_and_all_sources() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as session:
            manager_role = Role(name="Rule manager", normalized_name="rule manager")
            forbidden_role = Role(name="Forbidden", normalized_name="forbidden")
            session.add_all([manager_role, forbidden_role])
            session.flush()
            session.add(RolePermission(role_id=manager_role.id, permission_key=TAG_RULES_MANAGE))
            manager = User(
                username="Manager", normalized_username="manager", password_hash="unused",
                role="user", role_definition=manager_role, all_sources=True, is_active=True,
            )
            scoped_manager = User(
                username="Scoped", normalized_username="scoped", password_hash="unused",
                role="user", role_definition=manager_role, all_sources=False, is_active=True,
            )
            forbidden = User(
                username="Forbidden", normalized_username="forbidden", password_hash="unused",
                role="user", role_definition=forbidden_role, all_sources=True, is_active=True,
            )
            session.add_all([manager, scoped_manager, forbidden])
            session.commit()
            dependency = require_tag_assignment_rules_manage()
            assert dependency(manager, session).all_sources
            with pytest.raises(HTTPException) as scoped_error:
                dependency(scoped_manager, session)
            assert scoped_error.value.status_code == 403
            with pytest.raises(HTTPException) as forbidden_error:
                dependency(forbidden, session)
            assert forbidden_error.value.status_code == 403
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
