from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from meshive.api.tags import (
    create_assignment_rule,
    delete_assignment_rule,
    list_assignment_rules,
    preview_assignment_rule,
    update_assignment_rule,
)
from meshive.database import Base
from meshive.models.audit import AuditEvent
from meshive.models.authorization import Role, RolePermission
from meshive.models.catalog import Archive, ArchiveEntry, LibraryModel
from meshive.models.library_source import LibrarySource
from meshive.models.tag import ModelTag, Tag, TagAssignmentRule, TagAssignmentRuleMatch
from meshive.models.user import User
from meshive.schemas.tag import TagAssignmentRulePreview, TagAssignmentRuleWrite


def test_assignment_rule_api_evaluates_targets_and_preserves_other_provenance() -> None:
    engine, sessions, actor, tag_ids, model_ids = _rule_test_database()
    try:
        with sessions() as session:
            rule = create_assignment_rule(
                tag_ids["canonical"],
                TagAssignmentRuleWrite(match_mode="regex", pattern=r"(_P|P\.)[2-9]", targets=[
                        {"target_type": "archive_entry_path"},
                        {"target_type": "archive_entry_name"},
                    ]),
                actor["value"],
                session,
            )
            assert rule.match_count == 2
            preview = preview_assignment_rule(
                TagAssignmentRulePreview(match_mode="contains", pattern="A2_P2", targets=[{"target_type": "archive_entry_path"}], limit=50),
                actor["value"],
                session,
            )
            assert [item.model_dump() for item in preview] == [
                {"model_name": "A2", "relative_path": "Series/A2"}
            ]

            path_rule = create_assignment_rule(
                tag_ids["path"],
                TagAssignmentRuleWrite(library_source_id=1, match_mode="path_relation", path_value="Series", path_relation="self_or_descendant", targets=[{"target_type": "model_relative_path"}]),
                actor["value"],
                session,
            )
            assert path_rule.match_count == 2

            disabled = update_assignment_rule(
                rule.id,
                TagAssignmentRuleWrite(match_mode="regex", pattern=r"(_P|P\.)[2-9]", enabled=False, targets=[{"target_type": "archive_entry_name"}]),
                actor["value"],
                session,
            )
            assert disabled.match_count == 0
            assert delete_assignment_rule(path_rule.id, actor["value"], session).status_code == 204

        with sessions() as session:
            # Canonical provenance was removed, but direct and Legacy flags survive.
            assignments = list(session.scalars(select(ModelTag).order_by(ModelTag.model_id)))
            assert {(item.model_id, item.tag_id) for item in assignments} == {
                (model_ids["a2"], tag_ids["direct"]),
                (model_ids["a2"], tag_ids["legacy"]),
            }
            assert all(not item.is_assignment_rule for item in assignments)
            assert session.scalar(select(TagAssignmentRuleMatch)) is None
            audit_events = list(session.scalars(select(AuditEvent)))
            assert {event.action for event in audit_events} >= {
                "tag_assignment_rule.created",
                "tag_assignment_rule.updated",
                "tag_assignment_rule.deleted",
            }
            serialized = " ".join(str(event.details) for event in audit_events)
            assert "(_P|P" not in serialized
            assert "Series/A2" not in serialized
    finally:
        _teardown_rule_test_database(engine, actor)


def test_assignment_rule_api_preview_permissions_scope_and_no_persistence() -> None:
    engine, sessions, actor, tag_ids, _ = _rule_test_database()
    try:
        with sessions() as session:
            preview = {
                "match_mode": "contains",
                "pattern": "P.2",
                "targets": [{"target_type": "archive_entry_path"}],
            }
            assert preview_assignment_rule(
                TagAssignmentRulePreview(**preview), actor["value"], session
            )
            with pytest.raises(HTTPException, match="Invalid RE2 pattern") as invalid:
                create_assignment_rule(
                    tag_ids["canonical"],
                    TagAssignmentRuleWrite(**{**preview, "match_mode": "regex", "pattern": "("}),
                    actor["value"],
                    session,
                )
            assert invalid.value.status_code == 422

            actor["value"] = SimpleNamespace(
                id=actor["id"], username="Scoped", role_id=actor["role_id"],
                role_definition=SimpleNamespace(is_superuser=False), all_sources=False,
            )
            with pytest.raises(HTTPException) as scoped_error:
                preview_assignment_rule(TagAssignmentRulePreview(**preview), actor["value"], session)
            assert scoped_error.value.status_code == 403
            with pytest.raises(HTTPException) as list_error:
                list_assignment_rules(tag_ids["canonical"], actor["value"], session)
            assert list_error.value.status_code == 403

            actor["value"] = SimpleNamespace(
                id=actor["id"], username="Denied", role_id=None,
                role_definition=SimpleNamespace(is_superuser=False), all_sources=True,
            )
            with pytest.raises(HTTPException) as forbidden_error:
                list_assignment_rules(tag_ids["canonical"], actor["value"], session)
            assert forbidden_error.value.status_code == 403
            # Identifiable missing resources remain hidden even from forbidden users.
            with pytest.raises(HTTPException) as missing_error:
                list_assignment_rules(9999, actor["value"], session)
            assert missing_error.value.status_code == 404

        with sessions() as session:
            assert session.scalar(select(TagAssignmentRule)) is None
            assert session.scalar(select(TagAssignmentRuleMatch)) is None
            assert session.scalar(select(ModelTag).where(ModelTag.is_assignment_rule.is_(True))) is None
            assert session.scalar(select(AuditEvent)) is None
    finally:
        _teardown_rule_test_database(engine, actor)


def _rule_test_database() -> tuple[object, sessionmaker[Session], dict[str, object], dict[str, int], dict[str, int]]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as session:
        role = Role(name="Rule manager", normalized_name="rule manager")
        session.add(role)
        session.flush()
        session.add(RolePermission(role_id=role.id, permission_key="tag_rules.manage"))
        user = User(
            username="Manager", normalized_username="manager", password_hash="unused",
            role="user", role_id=role.id, all_sources=True, is_active=True,
        )
        source = LibrarySource(
            name="Library", root_path="/not/exposed", directory_pattern="{model_folder}",
            archive_formats=["zip"], image_formats=["jpg"], is_active=True, scan_enabled=True,
        )
        tags = [Tag(name=name) for name in ("Canonical", "Path", "Direct", "Legacy")]
        session.add_all([user, source, *tags])
        session.flush()
        a2 = _model_with_archive(session, source.id, "A2", "Series/A2", "A2_P2.stl")
        other = _model_with_archive(session, source.id, "Other", "Series/Other", "P.2 - A2.stl")
        session.add_all(
            [
                ModelTag(model_id=a2.id, tag_id=tags[2].id, is_direct=True),
                ModelTag(model_id=a2.id, tag_id=tags[3].id, is_automatic=True),
            ]
        )
        session.commit()
        actor: dict[str, object] = {
            "id": user.id,
            "role_id": role.id,
            "value": SimpleNamespace(
                id=user.id, username=user.username, role_id=role.id,
                role_definition=SimpleNamespace(is_superuser=False), all_sources=True,
            ),
        }
        tag_ids = {"canonical": tags[0].id, "path": tags[1].id, "direct": tags[2].id, "legacy": tags[3].id}
        model_ids = {"a2": a2.id, "other": other.id}
    return engine, sessions, actor, tag_ids, model_ids


def _model_with_archive(
    session: Session, source_id: int, name: str, relative_path: str, entry_path: str
) -> LibraryModel:
    model = LibraryModel(
        library_source_id=source_id, relative_path=relative_path, name=name, status="available"
    )
    session.add(model)
    session.flush()
    archive = Archive(
        model_id=model.id, filename=f"{name}.zip", relative_path=f"{relative_path}/{name}.zip",
        format="zip", size_bytes=1, modified_ns=1, status="ready",
    )
    session.add(archive)
    session.flush()
    session.add(ArchiveEntry(archive_id=archive.id, path=entry_path, name=entry_path.rsplit("/", 1)[-1]))
    return model


def _teardown_rule_test_database(
    engine: object, actor: dict[str, object] | None = None
) -> None:
    Base.metadata.drop_all(engine)  # type: ignore[arg-type]
    engine.dispose()  # type: ignore[union-attr]
