from pathlib import PurePosixPath

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from meshive.models.catalog import LibraryModel
from meshive.models.tag import FolderTagRule, ModelTag


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
            update(ModelTag)
            .where(ModelTag.model_id.in_(model_ids))
            .values(is_inherited=False)
        )
    existing = {
        (item.model_id, item.tag_id): item
        for item in session.scalars(
            select(ModelTag).where(ModelTag.model_id.in_(model_ids))
        )
    } if model_ids else {}

    for model in models:
        model_path = PurePosixPath(model.relative_path)
        for rule in rules:
            rule_path = PurePosixPath(rule.relative_path)
            matches = (
                (rule.recursive and (rule_path == model_path or rule_path in model_path.parents))
                or (not rule.recursive and rule_path == model_path.parent)
            )
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
        )
    )
