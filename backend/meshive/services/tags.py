from dataclasses import dataclass
from pathlib import PurePosixPath

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from meshive.models.catalog import Archive, ArchiveEntry, LibraryModel
from meshive.models.tag import (
    AutomaticTagMatch,
    AutomaticTagRule,
    FolderTagRule,
    ModelTag,
)


@dataclass(frozen=True)
class AutomaticTagEvaluation:
    models_evaluated: int = 0
    matches: int = 0
    assignments_added: int = 0
    assignments_removed: int = 0


def normalize_automatic_pattern(value: str) -> str:
    return value.strip().casefold()


def recompute_inherited_tags(session: Session, source_id: int) -> None:
    models = session.scalars(
        select(LibraryModel).where(LibraryModel.library_source_id == source_id)
    ).all()
    rules = session.scalars(
        select(FolderTagRule).where(FolderTagRule.library_source_id == source_id)
    ).all()
    model_ids = [model.id for model in models]
    if model_ids:
        session.execute(
            update(ModelTag).where(ModelTag.model_id.in_(model_ids)).values(is_inherited=False)
        )
    existing = (
        {
            (item.model_id, item.tag_id): item
            for item in session.scalars(select(ModelTag).where(ModelTag.model_id.in_(model_ids)))
        }
        if model_ids
        else {}
    )

    for model in models:
        model_path = PurePosixPath(model.relative_path)
        for rule in rules:
            rule_path = PurePosixPath(rule.relative_path)
            matches = (
                rule.recursive and (rule_path == model_path or rule_path in model_path.parents)
            ) or (not rule.recursive and rule_path == model_path.parent)
            if not matches:
                continue
            assignment = existing.get((model.id, rule.tag_id))
            if assignment is None:
                assignment = ModelTag(
                    model_id=model.id,
                    tag_id=rule.tag_id,
                    is_direct=False,
                    is_inherited=True,
                )
                session.add(assignment)
                existing[(model.id, rule.tag_id)] = assignment
            else:
                assignment.is_inherited = True

    session.flush()
    session.execute(
        delete(ModelTag).where(
            ModelTag.model_id.in_(model_ids),
            ModelTag.is_direct.is_(False),
            ModelTag.is_inherited.is_(False),
            ModelTag.is_automatic.is_(False),
        )
    )


def recompute_automatic_tags(
    session: Session, model_ids: list[int] | None = None
) -> AutomaticTagEvaluation:
    if model_ids is None:
        selected_model_ids = list(session.scalars(select(LibraryModel.id)))
    else:
        selected_model_ids = list(dict.fromkeys(model_ids))
    if not selected_model_ids:
        return AutomaticTagEvaluation()

    rules = list(
        session.scalars(
            select(AutomaticTagRule)
            .where(AutomaticTagRule.enabled.is_(True))
            .order_by(AutomaticTagRule.id)
        )
    )
    rule_needles = {rule.id: normalize_automatic_pattern(rule.pattern) for rule in rules}
    matched_paths: dict[tuple[int, int], str] = {}
    if rules:
        rows = session.execute(
            select(Archive.model_id, ArchiveEntry.path, ArchiveEntry.name)
            .join(ArchiveEntry, ArchiveEntry.archive_id == Archive.id)
            .where(
                Archive.model_id.in_(selected_model_ids),
                Archive.status == "ready",
            )
            .order_by(Archive.model_id, Archive.id, ArchiveEntry.id)
        ).yield_per(1000)
        for model_id, path, name in rows:
            folded_path = path.casefold()
            folded_name = name.casefold()
            for rule in rules:
                match_key = (model_id, rule.id)
                if match_key in matched_paths:
                    continue
                needle = rule_needles[rule.id]
                if needle in folded_path or needle in folded_name:
                    matched_paths[match_key] = path

    session.execute(
        delete(AutomaticTagMatch).where(AutomaticTagMatch.model_id.in_(selected_model_ids))
    )
    session.add_all(
        AutomaticTagMatch(
            automatic_tag_rule_id=rule_id,
            model_id=model_id,
            matched_path=matched_path,
        )
        for (model_id, rule_id), matched_path in matched_paths.items()
    )

    rule_tags = {rule.id: rule.tag_id for rule in rules}
    desired_tags: dict[int, set[int]] = {model_id: set() for model_id in selected_model_ids}
    for model_id, rule_id in matched_paths:
        desired_tags[model_id].add(rule_tags[rule_id])

    assignments = {
        (assignment.model_id, assignment.tag_id): assignment
        for assignment in session.scalars(
            select(ModelTag).where(ModelTag.model_id.in_(selected_model_ids))
        )
    }
    added = 0
    removed = 0
    for model_id, tag_ids in desired_tags.items():
        for tag_id in tag_ids:
            assignment = assignments.get((model_id, tag_id))
            if assignment is None:
                assignment = ModelTag(
                    model_id=model_id,
                    tag_id=tag_id,
                    is_direct=False,
                    is_inherited=False,
                    is_automatic=True,
                )
                session.add(assignment)
                assignments[(model_id, tag_id)] = assignment
                added += 1
            elif not assignment.is_automatic:
                assignment.is_automatic = True
                added += 1

    for (model_id, tag_id), assignment in assignments.items():
        if not assignment.is_automatic or tag_id in desired_tags[model_id]:
            continue
        assignment.is_automatic = False
        removed += 1
        if not assignment.is_direct and not assignment.is_inherited:
            session.delete(assignment)

    session.flush()
    return AutomaticTagEvaluation(
        models_evaluated=len(selected_model_ids),
        matches=len(matched_paths),
        assignments_added=added,
        assignments_removed=removed,
    )
