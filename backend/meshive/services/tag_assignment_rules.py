"""Shared validation and legacy-path semantics for assignment-rule phases."""

from pathlib import PurePosixPath

import re2
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from meshive.models.catalog import Archive, ArchiveEntry, LibraryModel
from meshive.models.tag import (
    AutomaticTagMatch,
    FolderTagRule,
    ModelTag,
    TagAssignmentRule,
    TagAssignmentRuleMatch,
    TagAssignmentRuleTarget,
)


def legacy_rule_preflight(session: Session, limit: int = 5) -> list[dict[str, object]]:
    """Compare persisted legacy provenance with a read-only canonical calculation."""
    results: list[dict[str, object]] = []
    rules = session.scalars(
        select(TagAssignmentRule).where(TagAssignmentRule.legacy_kind.is_not(None))
    )
    for rule in rules:
        expected = _legacy_match_ids(session, rule)
        _, calculated = find_assignment_rule_matches(session, rule)
        only_legacy = expected - calculated
        only_canonical = calculated - expected
        results.append({
            "rule_id": rule.id,
            "tag_id": rule.tag_id,
            "legacy_kind": rule.legacy_kind,
            "legacy_matches": len(expected),
            "canonical_matches": len(calculated),
            "only_legacy": len(only_legacy),
            "only_canonical": len(only_canonical),
            "only_legacy_models": _diagnostic_models(session, only_legacy, limit),
            "only_canonical_models": _diagnostic_models(session, only_canonical, limit),
        })
    return results


def _legacy_match_ids(session: Session, rule: TagAssignmentRule) -> set[int]:
    if rule.legacy_kind == "automatic_tag_rule":
        return set(session.scalars(select(AutomaticTagMatch.model_id).where(
            AutomaticTagMatch.automatic_tag_rule_id == rule.legacy_rule_id
        )))
    if rule.legacy_kind == "folder_tag_rule":
        legacy = session.get(FolderTagRule, rule.legacy_rule_id)
        if legacy is None:
            return set()
        return {model.id for model in session.scalars(select(LibraryModel).where(
            LibraryModel.library_source_id == legacy.library_source_id
        )) if matches_legacy_folder_path(model.relative_path, legacy.relative_path,
                                         PATH_SELF_OR_DESCENDANT if legacy.recursive else PATH_DIRECT_CHILD)}
    return set(session.scalars(select(TagAssignmentRuleMatch.model_id).where(
        TagAssignmentRuleMatch.tag_assignment_rule_id == rule.id
    )))


def _diagnostic_models(session: Session, model_ids: set[int], limit: int) -> list[dict[str, object]]:
    if not model_ids:
        return []
    return [{"id": model.id, "name": model.name} for model in session.scalars(
        select(LibraryModel).where(LibraryModel.id.in_(model_ids)).order_by(LibraryModel.id).limit(limit)
    )]

MAX_PATTERN_LENGTH = 255
MATCH_CONTAINS = "contains"
MATCH_REGEX = "regex"
MATCH_PATH_RELATION = "path_relation"
PATH_DIRECT_CHILD = "direct_child"
PATH_SELF_OR_DESCENDANT = "self_or_descendant"
TARGET_MODEL_RELATIVE_PATH = "model_relative_path"
TARGET_ARCHIVE_FILENAME = "archive_filename"
TARGET_ARCHIVE_ENTRY_PATH = "archive_entry_path"
TARGET_ARCHIVE_ENTRY_NAME = "archive_entry_name"


def compile_case_insensitive_regex(value: str) -> tuple[str, str, re2._Regexp]:
    pattern = value.strip()
    if not pattern:
        raise ValueError("Pattern cannot be empty")
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise ValueError(f"Pattern must not exceed {MAX_PATTERN_LENGTH} characters")
    options = re2.Options()
    options.case_sensitive = False
    try:
        compiled = re2.compile(pattern, options=options)
    except re2.error as error:
        raise ValueError(f"Invalid RE2 pattern: {error}") from error
    return pattern, pattern.casefold(), compiled


def matches_legacy_folder_path(
    model_relative_path: str,
    rule_relative_path: str,
    path_relation: str,
) -> bool:
    """Preserve the exact FolderTagRule recursive/non-recursive behavior."""
    model_path = PurePosixPath(model_relative_path)
    rule_path = PurePosixPath(rule_relative_path)
    if path_relation == PATH_SELF_OR_DESCENDANT:
        return rule_path == model_path or rule_path in model_path.parents
    if path_relation == PATH_DIRECT_CHILD:
        return rule_path == model_path.parent
    raise ValueError(f"Unsupported path relation: {path_relation}")


def evaluate_assignment_rule(session: Session, rule: TagAssignmentRule) -> set[int]:
    """Evaluate one new canonical rule and update only its match provenance."""
    models, matched_model_ids = find_assignment_rule_matches(session, rule, targets=None)
    model_ids = [model.id for model in models]
    session.execute(
        delete(TagAssignmentRuleMatch).where(
            TagAssignmentRuleMatch.tag_assignment_rule_id == rule.id
        )
    )
    if not rule.enabled or not models:
        return set(model_ids)
    session.add_all(
        TagAssignmentRuleMatch(tag_assignment_rule_id=rule.id, model_id=model_id)
        for model_id in matched_model_ids
    )
    return set(model_ids)


def find_assignment_rule_matches(
    session: Session,
    rule: TagAssignmentRule,
    targets: list[TagAssignmentRuleTarget] | None = None,
) -> tuple[list[LibraryModel], set[int]]:
    selected_models = select(LibraryModel)
    if rule.library_source_id is not None:
        selected_models = selected_models.where(
            LibraryModel.library_source_id == rule.library_source_id
        )
    models = list(session.scalars(selected_models))
    model_ids = [model.id for model in models]
    if not rule.enabled or not models:
        return models, set()
    if targets is None:
        targets = list(
            session.scalars(
                select(TagAssignmentRuleTarget).where(
                    TagAssignmentRuleTarget.tag_assignment_rule_id == rule.id
                )
            )
        )
    compiled = (
        compile_case_insensitive_regex(rule.pattern or "")[2]
        if rule.match_mode == MATCH_REGEX
        else None
    )
    archive_values: dict[int, list[tuple[str, str | None, str | None]]] = {
        model_id: [] for model_id in model_ids
    }
    if any(target.target_type != TARGET_MODEL_RELATIVE_PATH for target in targets):
        rows = session.execute(
            select(Archive.model_id, Archive.filename, ArchiveEntry.path, ArchiveEntry.name)
            .outerjoin(ArchiveEntry, ArchiveEntry.archive_id == Archive.id)
            .where(Archive.model_id.in_(model_ids), Archive.status == "ready")
        )
        for model_id, filename, entry_path, entry_name in rows:
            archive_values[model_id].append((filename, entry_path, entry_name))

    matched_model_ids: set[int] = set()
    for model in models:
        if _matches_rule(rule, targets, model.relative_path, archive_values[model.id], compiled):
            matched_model_ids.add(model.id)
    return models, matched_model_ids


def reevaluate_canonical_rules(
    session: Session, rule_ids: list[int] | None = None
) -> tuple[int, int, int, int]:
    statement = select(TagAssignmentRule).where(TagAssignmentRule.legacy_kind.is_(None))
    if rule_ids is not None:
        statement = statement.where(TagAssignmentRule.id.in_(rule_ids))
    rules = list(session.scalars(statement))
    affected_model_ids: set[int] = set()
    for rule in rules:
        affected_model_ids.update(evaluate_assignment_rule(session, rule))
    added, removed = refresh_assignment_rule_tags(session, affected_model_ids)
    return len(affected_model_ids), _match_count(session, rules), added, removed


def refresh_assignment_rule_tags(session: Session, model_ids: set[int]) -> tuple[int, int]:
    if not model_ids:
        return 0, 0
    desired = {model_id: set() for model_id in model_ids}
    for model_id, tag_id in session.execute(
        select(TagAssignmentRuleMatch.model_id, TagAssignmentRule.tag_id)
        .join(TagAssignmentRule, TagAssignmentRule.id == TagAssignmentRuleMatch.tag_assignment_rule_id)
        .where(
            TagAssignmentRuleMatch.model_id.in_(model_ids),
            TagAssignmentRule.legacy_kind.is_(None),
            TagAssignmentRule.enabled.is_(True),
        )
    ):
        desired[model_id].add(tag_id)
    assignments = {
        (item.model_id, item.tag_id): item
        for item in session.scalars(select(ModelTag).where(ModelTag.model_id.in_(model_ids)))
    }
    added = removed = 0
    for model_id, tag_ids in desired.items():
        for tag_id in tag_ids:
            assignment = assignments.get((model_id, tag_id))
            if assignment is None:
                session.add(
                    ModelTag(model_id=model_id, tag_id=tag_id, is_assignment_rule=True)
                )
                added += 1
            elif not assignment.is_assignment_rule:
                assignment.is_assignment_rule = True
                added += 1
    for (model_id, tag_id), assignment in assignments.items():
        if not assignment.is_assignment_rule or tag_id in desired[model_id]:
            continue
        assignment.is_assignment_rule = False
        removed += 1
        if not assignment.is_direct and not assignment.is_inherited and not assignment.is_automatic:
            session.delete(assignment)
    return added, removed


def _matches_rule(
    rule: TagAssignmentRule,
    targets: list[TagAssignmentRuleTarget],
    relative_path: str,
    archive_values: list[tuple[str, str | None, str | None]],
    compiled: re2._Regexp | None,
) -> bool:
    for target in targets:
        if target.target_type == TARGET_MODEL_RELATIVE_PATH:
            values = PurePosixPath(relative_path).parts if target.folder_segment else (relative_path,)
        elif target.target_type == TARGET_ARCHIVE_FILENAME:
            values = (item[0] for item in archive_values)
        elif target.target_type == TARGET_ARCHIVE_ENTRY_PATH:
            values = (item[1] for item in archive_values if item[1] is not None)
        else:
            values = (item[2] for item in archive_values if item[2] is not None)
        for value in values:
            if rule.match_mode == MATCH_PATH_RELATION:
                if target.target_type == TARGET_MODEL_RELATIVE_PATH and matches_legacy_folder_path(
                    relative_path, rule.path_value or "", rule.path_relation or ""
                ):
                    return True
            elif (
                rule.match_mode == MATCH_CONTAINS
                and (rule.pattern or "").casefold() in value.casefold()
            ) or (
                rule.match_mode == MATCH_REGEX
                and compiled is not None
                and compiled.search(value)
            ):
                return True
    return False


def _match_count(session: Session, rules: list[TagAssignmentRule]) -> int:
    rule_ids = [rule.id for rule in rules]
    if not rule_ids:
        return 0
    return len(
        list(
            session.scalars(
                select(TagAssignmentRuleMatch.id).where(
                    TagAssignmentRuleMatch.tag_assignment_rule_id.in_(rule_ids)
                )
            )
        )
    )
