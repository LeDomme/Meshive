from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from meshive.auth.dependencies import get_current_user, require_admin
from meshive.database import get_session
from meshive.models.catalog import LibraryModel
from meshive.models.library_source import LibrarySource
from meshive.models.tag import FolderTagRule, ModelTag, Tag
from meshive.schemas.tag import FolderRuleCreate, FolderRuleRead, TagCreate, TagRead
from meshive.services.library_paths import PathPatternError, normalize_relative_path
from meshive.services.tags import recompute_inherited_tags

router = APIRouter(prefix="/tags", tags=["tags"], dependencies=[Depends(get_current_user)])
admin_router = APIRouter(prefix="/admin", tags=["tag administration"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[TagRead])
def list_tags(session: Session = Depends(get_session)) -> list[Tag]:
    return list(session.scalars(select(Tag).order_by(Tag.name.collate("NOCASE"))))


@admin_router.post("/tags", response_model=TagRead, status_code=201)
def create_tag(payload: TagCreate, session: Session = Depends(get_session)) -> Tag:
    tag = Tag(name=payload.name.strip(), color=payload.color, description=payload.description)
    session.add(tag)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="A tag with this name already exists") from error
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
        session.add(ModelTag(model_id=model_id, tag_id=tag_id, is_direct=True, is_inherited=False))
    else:
        assignment.is_direct = True
    session.commit()
    return Response(status_code=204)


@admin_router.delete("/models/{model_id}/tags/{tag_id}", status_code=204)
def remove_model_tag(model_id: int, tag_id: int, session: Session = Depends(get_session)) -> Response:
    assignment = session.scalar(
        select(ModelTag).where(ModelTag.model_id == model_id, ModelTag.tag_id == tag_id)
    )
    if assignment is not None:
        assignment.is_direct = False
        if not assignment.is_inherited:
            session.delete(assignment)
        session.commit()
    return Response(status_code=204)


@admin_router.get("/folder-tag-rules", response_model=list[FolderRuleRead])
def list_rules(session: Session = Depends(get_session)) -> list[FolderRuleRead]:
    return [
        FolderRuleRead(
            id=rule.id, library_source_id=rule.library_source_id,
            relative_path=rule.relative_path, tag_id=rule.tag_id,
            recursive=rule.recursive, tag_name=name,
        )
        for rule, name in session.execute(
            select(FolderTagRule, Tag.name).join(Tag, Tag.id == FolderTagRule.tag_id)
        )
    ]


@admin_router.post("/folder-tag-rules", response_model=FolderRuleRead, status_code=201)
def create_rule(payload: FolderRuleCreate, session: Session = Depends(get_session)) -> FolderRuleRead:
    source = session.get(LibrarySource, payload.library_source_id)
    tag = session.get(Tag, payload.tag_id)
    if source is None or tag is None:
        raise HTTPException(status_code=404, detail="Source or tag not found")
    try:
        path = normalize_relative_path(payload.relative_path)
    except PathPatternError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    rule = FolderTagRule(
        library_source_id=source.id, relative_path=path,
        tag_id=tag.id, recursive=payload.recursive,
    )
    session.add(rule)
    try:
        session.flush()
        recompute_inherited_tags(session, source.id)
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="This folder tag rule already exists") from error
    return FolderRuleRead(id=rule.id, library_source_id=source.id, relative_path=path, tag_id=tag.id, recursive=rule.recursive, tag_name=tag.name)


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
