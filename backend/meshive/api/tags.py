from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from meshive.auth.dependencies import get_current_user, require_admin
from meshive.database import get_session
from meshive.models.catalog import LibraryModel
from meshive.models.library_source import LibrarySource
from meshive.models.tag import (
    AutomaticTagMatch,
    AutomaticTagRule,
    FolderTagRule,
    ModelTag,
    Tag,
)
from meshive.schemas.tag import (
    AutomaticTagEvaluationRead,
    AutomaticTagRuleCreate,
    AutomaticTagRuleRead,
    FolderRuleCreate,
    FolderRuleRead,
    TagCreate,
    TagRead,
    TagUpdate,
)
from meshive.services.library_paths import PathPatternError, normalize_relative_path
from meshive.services.tags import (
    normalize_automatic_pattern,
    recompute_automatic_tags,
    recompute_inherited_tags,
)

router = APIRouter(prefix="/tags", tags=["tags"], dependencies=[Depends(get_current_user)])
admin_router = APIRouter(
    prefix="/admin", tags=["tag administration"], dependencies=[Depends(require_admin)]
)


@router.get("", response_model=list[TagRead])
def list_tags(session: Session = Depends(get_session)) -> list[Tag]:
    return list(session.scalars(select(Tag).order_by(Tag.name.collate("NOCASE"))))


@admin_router.post("/tags", response_model=TagRead, status_code=201)
def create_tag(payload: TagCreate, session: Session = Depends(get_session)) -> Tag:
    name, description = _tag_values(payload)
    tag = Tag(name=name, color=payload.color, description=description)
    session.add(tag)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="A tag with this name already exists"
        ) from error
    session.refresh(tag)
    return tag


@admin_router.put("/tags/{tag_id}", response_model=TagRead)
def update_tag(
    tag_id: int,
    payload: TagUpdate,
    session: Session = Depends(get_session),
) -> Tag:
    tag = session.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    tag.name, tag.description = _tag_values(payload)
    tag.color = payload.color
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="A tag with this name already exists"
        ) from error
    session.refresh(tag)
    return tag


@admin_router.delete("/tags/{tag_id}", status_code=204)
def delete_tag(tag_id: int, session: Session = Depends(get_session)) -> Response:
    tag = session.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    session.delete(tag)
    session.commit()
    return Response(status_code=204)


@admin_router.put("/models/{model_id}/tags/{tag_id}", status_code=204)
def add_model_tag(model_id: int, tag_id: int, session: Session = Depends(get_session)) -> Response:
    if session.get(LibraryModel, model_id) is None or session.get(Tag, tag_id) is None:
        raise HTTPException(status_code=404, detail="Model or tag not found")
    assignment = session.scalar(
        select(ModelTag).where(ModelTag.model_id == model_id, ModelTag.tag_id == tag_id)
    )
    if assignment is None:
        session.add(
            ModelTag(
                model_id=model_id,
                tag_id=tag_id,
                is_direct=True,
                is_inherited=False,
                is_automatic=False,
            )
        )
    else:
        assignment.is_direct = True
    session.commit()
    return Response(status_code=204)


@admin_router.delete("/models/{model_id}/tags/{tag_id}", status_code=204)
def remove_model_tag(
    model_id: int, tag_id: int, session: Session = Depends(get_session)
) -> Response:
    assignment = session.scalar(
        select(ModelTag).where(ModelTag.model_id == model_id, ModelTag.tag_id == tag_id)
    )
    if assignment is not None:
        assignment.is_direct = False
        if not assignment.is_inherited and not assignment.is_automatic:
            session.delete(assignment)
        session.commit()
    return Response(status_code=204)


@admin_router.get("/folder-tag-rules", response_model=list[FolderRuleRead])
def list_rules(session: Session = Depends(get_session)) -> list[FolderRuleRead]:
    return [
        FolderRuleRead(
            id=rule.id,
            library_source_id=rule.library_source_id,
            relative_path=rule.relative_path,
            tag_id=rule.tag_id,
            recursive=rule.recursive,
            tag_name=name,
        )
        for rule, name in session.execute(
            select(FolderTagRule, Tag.name).join(Tag, Tag.id == FolderTagRule.tag_id)
        )
    ]


@admin_router.post("/folder-tag-rules", response_model=FolderRuleRead, status_code=201)
def create_rule(
    payload: FolderRuleCreate, session: Session = Depends(get_session)
) -> FolderRuleRead:
    source = session.get(LibrarySource, payload.library_source_id)
    tag = session.get(Tag, payload.tag_id)
    if source is None or tag is None:
        raise HTTPException(status_code=404, detail="Source or tag not found")
    try:
        path = normalize_relative_path(payload.relative_path)
    except PathPatternError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    rule = FolderTagRule(
        library_source_id=source.id,
        relative_path=path,
        tag_id=tag.id,
        recursive=payload.recursive,
    )
    session.add(rule)
    try:
        session.flush()
        recompute_inherited_tags(session, source.id)
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="This folder tag rule already exists"
        ) from error
    return FolderRuleRead(
        id=rule.id,
        library_source_id=source.id,
        relative_path=path,
        tag_id=tag.id,
        recursive=rule.recursive,
        tag_name=tag.name,
    )


@admin_router.delete("/folder-tag-rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, session: Session = Depends(get_session)) -> Response:
    rule = session.get(FolderTagRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Folder tag rule not found")
    source_id = rule.library_source_id
    session.delete(rule)
    session.flush()
    recompute_inherited_tags(session, source_id)
    session.commit()
    return Response(status_code=204)


@admin_router.get("/automatic-tag-rules", response_model=list[AutomaticTagRuleRead])
def list_automatic_rules(
    session: Session = Depends(get_session),
) -> list[AutomaticTagRuleRead]:
    return [
        AutomaticTagRuleRead(
            id=rule.id,
            tag_id=rule.tag_id,
            tag_name=tag_name,
            pattern=rule.pattern,
            enabled=rule.enabled,
            match_count=match_count,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
        )
        for rule, tag_name, match_count in session.execute(
            select(
                AutomaticTagRule,
                Tag.name,
                func.count(AutomaticTagMatch.id),
            )
            .join(Tag, Tag.id == AutomaticTagRule.tag_id)
            .outerjoin(
                AutomaticTagMatch,
                AutomaticTagMatch.automatic_tag_rule_id == AutomaticTagRule.id,
            )
            .group_by(AutomaticTagRule.id, Tag.name)
            .order_by(AutomaticTagRule.id)
        )
    ]


@admin_router.post(
    "/automatic-tag-rules",
    response_model=AutomaticTagRuleRead,
    status_code=status.HTTP_201_CREATED,
)
def create_automatic_rule(
    payload: AutomaticTagRuleCreate,
    session: Session = Depends(get_session),
) -> AutomaticTagRuleRead:
    tag = session.get(Tag, payload.tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    pattern, pattern_key = _automatic_pattern(payload.pattern)
    rule = AutomaticTagRule(
        tag_id=tag.id,
        pattern=pattern,
        pattern_key=pattern_key,
        enabled=payload.enabled,
    )
    session.add(rule)
    try:
        session.flush()
        recompute_automatic_tags(session)
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="This automatic tag rule already exists",
        ) from error
    session.refresh(rule)
    return _automatic_rule_read(session, rule, tag.name)


@admin_router.put("/automatic-tag-rules/{rule_id}", response_model=AutomaticTagRuleRead)
def update_automatic_rule(
    rule_id: int,
    payload: AutomaticTagRuleCreate,
    session: Session = Depends(get_session),
) -> AutomaticTagRuleRead:
    rule = session.get(AutomaticTagRule, rule_id)
    tag = session.get(Tag, payload.tag_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Automatic tag rule not found")
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    rule.pattern, rule.pattern_key = _automatic_pattern(payload.pattern)
    rule.tag_id = tag.id
    rule.enabled = payload.enabled
    try:
        session.flush()
        recompute_automatic_tags(session)
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="This automatic tag rule already exists",
        ) from error
    session.refresh(rule)
    return _automatic_rule_read(session, rule, tag.name)


@admin_router.delete("/automatic-tag-rules/{rule_id}", status_code=204)
def delete_automatic_rule(rule_id: int, session: Session = Depends(get_session)) -> Response:
    rule = session.get(AutomaticTagRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Automatic tag rule not found")
    session.delete(rule)
    session.flush()
    recompute_automatic_tags(session)
    session.commit()
    return Response(status_code=204)


@admin_router.post(
    "/automatic-tag-rules/re-evaluate",
    response_model=AutomaticTagEvaluationRead,
)
def reevaluate_automatic_rules(
    session: Session = Depends(get_session),
) -> AutomaticTagEvaluationRead:
    result = recompute_automatic_tags(session)
    session.commit()
    return AutomaticTagEvaluationRead(**result.__dict__)


def _automatic_pattern(value: str) -> tuple[str, str]:
    pattern = value.strip()
    pattern_key = normalize_automatic_pattern(pattern)
    if not pattern_key:
        raise HTTPException(status_code=422, detail="Pattern cannot be empty")
    return pattern, pattern_key


def _tag_values(payload: TagCreate | TagUpdate) -> tuple[str, str | None]:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Tag name cannot be empty")
    description = payload.description.strip() if payload.description else None
    return name, description


def _automatic_rule_read(
    session: Session, rule: AutomaticTagRule, tag_name: str
) -> AutomaticTagRuleRead:
    match_count = (
        session.scalar(
            select(func.count(AutomaticTagMatch.id)).where(
                AutomaticTagMatch.automatic_tag_rule_id == rule.id
            )
        )
        or 0
    )
    return AutomaticTagRuleRead(
        id=rule.id,
        tag_id=rule.tag_id,
        tag_name=tag_name,
        pattern=rule.pattern,
        enabled=rule.enabled,
        match_count=match_count,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )
