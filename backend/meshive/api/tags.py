from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from meshive.auth.access import (
    get_access_context,
    get_visible_model_or_404,
    require_access_permission,
    require_any_global_permission,
    require_global_permission,
    visible_model_scope,
)
from meshive.auth.dependencies import get_current_user
from meshive.auth.permissions import CATALOGUE_VIEW, MODELS_TAGS, TAG_RULES_MANAGE, TAGS_MANAGE
from meshive.database import get_session
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
from meshive.schemas.tag import (
    AutomaticTagEvaluationRead,
    AutomaticTagRuleCreate,
    AutomaticTagRuleRead,
    FolderRuleCreate,
    FolderRuleRead,
    TagAssignmentRuleEvaluationRead,
    TagAssignmentRulePreview,
    TagAssignmentRulePreviewRead,
    TagAssignmentRuleRead,
    TagAssignmentRuleWrite,
    TagCreate,
    TagRead,
    TagUpdate,
)
from meshive.services.audit import AuditAction, log_event
from meshive.services.library_paths import PathPatternError, normalize_relative_path
from meshive.services.tag_assignment_rules import (
    MATCH_REGEX,
    compile_case_insensitive_regex,
    evaluate_assignment_rule,
    find_assignment_rule_matches,
    reevaluate_canonical_rules,
    refresh_assignment_rule_tags,
)
from meshive.services.tags import (
    normalize_automatic_pattern,
    recompute_automatic_tags,
    recompute_inherited_tags,
)

router = APIRouter(prefix="/tags", tags=["tags"], dependencies=[Depends(get_current_user)])
admin_router = APIRouter(prefix="/admin", tags=["tag administration"])
model_tag_router = APIRouter(prefix="/admin", tags=["tag administration"])
CurrentUser = Annotated[User, Depends(get_current_user)]
SessionDependency = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[TagRead])
def list_tags(
    current_user: CurrentUser,
    session: SessionDependency,
) -> list[Tag]:
    access = get_access_context(session, current_user)
    require_access_permission(access, CATALOGUE_VIEW)
    scope = visible_model_scope(access)
    statement = (
        select(Tag)
        .join(ModelTag, ModelTag.tag_id == Tag.id)
        .join(LibraryModel, LibraryModel.id == ModelTag.model_id)
        .distinct()
        .order_by(Tag.name.collate("NOCASE"))
    )
    if scope is not None:
        statement = statement.where(scope)
    return list(session.scalars(statement))


@admin_router.get(
    "/tags",
    response_model=list[TagRead],
    dependencies=[Depends(require_any_global_permission({TAGS_MANAGE, TAG_RULES_MANAGE}))],
)
def list_admin_tags(session: SessionDependency) -> list[Tag]:
    return list(session.scalars(select(Tag).order_by(Tag.name.collate("NOCASE"))))


@admin_router.get(
    "/tags/library-sources",
    dependencies=[Depends(require_any_global_permission({TAGS_MANAGE, TAG_RULES_MANAGE}))],
)
def list_tag_rule_sources(session: SessionDependency) -> list[dict[str, object]]:
    return [
        {"id": source.id, "name": source.name}
        for source in session.scalars(select(LibrarySource).order_by(LibrarySource.name))
    ]


@admin_router.post("/tags", response_model=TagRead, status_code=201, dependencies=[Depends(require_global_permission(TAGS_MANAGE))])
def create_tag(
    payload: TagCreate, current_user: CurrentUser, session: SessionDependency
) -> Tag:
    name, description = _tag_values(payload)
    tag = Tag(name=name, color=payload.color, description=description)
    session.add(tag)
    try:
        session.flush()
        log_event(
            session,
            current_user,
            AuditAction.TAG_CREATED,
            "tag",
            tag.name,
            target_id=tag.id,
        )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="A tag with this name already exists"
        ) from error
    session.refresh(tag)
    return tag


@admin_router.put("/tags/{tag_id}", response_model=TagRead, dependencies=[Depends(require_global_permission(TAGS_MANAGE))])
def update_tag(
    tag_id: int,
    payload: TagUpdate,
    current_user: CurrentUser,
    session: SessionDependency,
) -> Tag:
    tag = session.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    previous_name, previous_color = tag.name, tag.color
    tag.name, tag.description = _tag_values(payload)
    tag.color = payload.color
    try:
        changed_categories = []
        if tag.name != previous_name:
            changed_categories.append("name")
        if tag.color != previous_color:
            changed_categories.append("color")
        log_event(
            session,
            current_user,
            AuditAction.TAG_UPDATED,
            "tag",
            tag.name,
            target_id=tag.id,
            details={"changed_categories": changed_categories},
        )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="A tag with this name already exists"
        ) from error
    session.refresh(tag)
    return tag


@admin_router.delete("/tags/{tag_id}", status_code=204, dependencies=[Depends(require_global_permission(TAGS_MANAGE))])
def delete_tag(
    tag_id: int, current_user: CurrentUser, session: SessionDependency
) -> Response:
    tag = session.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    log_event(
        session,
        current_user,
        AuditAction.TAG_DELETED,
        "tag",
        tag.name,
        target_id=tag.id,
    )
    session.delete(tag)
    session.commit()
    return Response(status_code=204)


@model_tag_router.put("/models/{model_id}/tags/{tag_id}", status_code=204)
def add_model_tag(
    model_id: int,
    tag_id: int,
    current_user: CurrentUser,
    session: SessionDependency,
) -> Response:
    access = get_access_context(session, current_user)
    get_visible_model_or_404(session, access, model_id)
    require_access_permission(access, MODELS_TAGS)
    if session.get(Tag, tag_id) is None:
        raise HTTPException(status_code=404, detail="Model or tag not found")
    assignment = session.scalar(
        select(ModelTag).where(ModelTag.model_id == model_id, ModelTag.tag_id == tag_id)
    )
    changed = assignment is None or not assignment.is_direct
    if assignment is None:
        assignment = ModelTag(
                model_id=model_id,
                tag_id=tag_id,
                is_direct=True,
                is_inherited=False,
                is_automatic=False,
            )
        session.add(assignment)
    else:
        assignment.is_direct = True
    if changed:
        session.flush()
        model = session.get(LibraryModel, model_id)
        log_event(
            session,
            current_user,
            AuditAction.MODEL_TAG_ADDED,
            "model_tag",
            "Model tag assignment",
            target_id=assignment.id,
            library_source_id=model.library_source_id if model is not None else None,
        )
    session.commit()
    return Response(status_code=204)


@model_tag_router.delete("/models/{model_id}/tags/{tag_id}", status_code=204)
def remove_model_tag(
    model_id: int,
    tag_id: int,
    current_user: CurrentUser,
    session: SessionDependency,
) -> Response:
    access = get_access_context(session, current_user)
    get_visible_model_or_404(session, access, model_id)
    require_access_permission(access, MODELS_TAGS)
    if session.get(Tag, tag_id) is None:
        raise HTTPException(status_code=404, detail="Model or tag not found")
    assignment = session.scalar(
        select(ModelTag).where(ModelTag.model_id == model_id, ModelTag.tag_id == tag_id)
    )
    if assignment is not None and assignment.is_direct:
        model = session.get(LibraryModel, model_id)
        log_event(
            session,
            current_user,
            AuditAction.MODEL_TAG_REMOVED,
            "model_tag",
            "Model tag assignment",
            target_id=assignment.id,
            library_source_id=model.library_source_id if model is not None else None,
        )
        assignment.is_direct = False
        if (
            not assignment.is_inherited
            and not assignment.is_automatic
            and not assignment.is_assignment_rule
        ):
            session.delete(assignment)
        session.commit()
    return Response(status_code=204)


@admin_router.get("/folder-tag-rules", response_model=list[FolderRuleRead], dependencies=[Depends(require_global_permission(TAGS_MANAGE))])
def list_rules(session: SessionDependency) -> list[FolderRuleRead]:
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


@admin_router.post("/folder-tag-rules", response_model=FolderRuleRead, status_code=201, dependencies=[Depends(require_global_permission(TAGS_MANAGE))])
def create_rule(
    payload: FolderRuleCreate,
    current_user: CurrentUser,
    session: SessionDependency,
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
        log_event(
            session,
            current_user,
            AuditAction.FOLDER_TAG_RULE_CREATED,
            "folder_tag_rule",
            "Folder tag rule",
            target_id=rule.id,
            library_source_id=source.id,
            details={"changed_categories": ["scope"]},
        )
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


@admin_router.put(
    "/folder-tag-rules/{rule_id}",
    response_model=FolderRuleRead,
    dependencies=[Depends(require_global_permission(TAGS_MANAGE))],
)
def update_rule(
    rule_id: int,
    payload: FolderRuleCreate,
    current_user: CurrentUser,
    session: SessionDependency,
) -> FolderRuleRead:
    rule = session.get(FolderTagRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Folder tag rule not found")
    source = session.get(LibrarySource, payload.library_source_id)
    tag = session.get(Tag, payload.tag_id)
    if source is None or tag is None:
        raise HTTPException(status_code=404, detail="Source or tag not found")
    try:
        path = normalize_relative_path(payload.relative_path)
    except PathPatternError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    previous_source_id = rule.library_source_id
    changed_categories = []
    if rule.library_source_id != source.id or rule.tag_id != tag.id:
        changed_categories.append("relation")
    if rule.relative_path != path or rule.recursive != payload.recursive:
        changed_categories.append("scope")
    rule.library_source_id = source.id
    rule.relative_path = path
    rule.tag_id = tag.id
    rule.recursive = payload.recursive
    try:
        session.flush()
        recompute_inherited_tags(session, previous_source_id)
        if source.id != previous_source_id:
            recompute_inherited_tags(session, source.id)
        log_event(
            session,
            current_user,
            AuditAction.FOLDER_TAG_RULE_UPDATED,
            "folder_tag_rule",
            "Folder tag rule",
            target_id=rule.id,
            library_source_id=source.id,
            details={"changed_categories": changed_categories},
        )
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


@admin_router.delete("/folder-tag-rules/{rule_id}", status_code=204, dependencies=[Depends(require_global_permission(TAGS_MANAGE))])
def delete_rule(
    rule_id: int, current_user: CurrentUser, session: SessionDependency
) -> Response:
    rule = session.get(FolderTagRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Folder tag rule not found")
    source_id = rule.library_source_id
    log_event(
        session,
        current_user,
        AuditAction.FOLDER_TAG_RULE_DELETED,
        "folder_tag_rule",
        "Folder tag rule",
        target_id=rule.id,
        library_source_id=source_id,
    )
    session.delete(rule)
    session.flush()
    recompute_inherited_tags(session, source_id)
    session.commit()
    return Response(status_code=204)


@admin_router.get("/automatic-tag-rules", response_model=list[AutomaticTagRuleRead], dependencies=[Depends(require_global_permission(TAG_RULES_MANAGE))])
def list_automatic_rules(
    session: SessionDependency,
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
    dependencies=[Depends(require_global_permission(TAG_RULES_MANAGE))],
)
def create_automatic_rule(
    payload: AutomaticTagRuleCreate,
    current_user: CurrentUser,
    session: SessionDependency,
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
        log_event(
            session,
            current_user,
            AuditAction.AUTOMATIC_TAG_RULE_CREATED,
            "automatic_tag_rule",
            "Automatic tag rule",
            target_id=rule.id,
            details={"changed_categories": ["relation", "scope", "enabled"]},
        )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="This automatic tag rule already exists",
        ) from error
    session.refresh(rule)
    return _automatic_rule_read(session, rule, tag.name)


@admin_router.put("/automatic-tag-rules/{rule_id}", response_model=AutomaticTagRuleRead, dependencies=[Depends(require_global_permission(TAG_RULES_MANAGE))])
def update_automatic_rule(
    rule_id: int,
    payload: AutomaticTagRuleCreate,
    current_user: CurrentUser,
    session: SessionDependency,
) -> AutomaticTagRuleRead:
    rule = session.get(AutomaticTagRule, rule_id)
    tag = session.get(Tag, payload.tag_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Automatic tag rule not found")
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    previous_tag_id = rule.tag_id
    previous_pattern = rule.pattern
    previous_enabled = rule.enabled
    rule.pattern, rule.pattern_key = _automatic_pattern(payload.pattern)
    rule.tag_id = tag.id
    rule.enabled = payload.enabled
    try:
        session.flush()
        recompute_automatic_tags(session)
        changed_categories = []
        if rule.tag_id != previous_tag_id:
            changed_categories.append("relation")
        if rule.pattern != previous_pattern:
            changed_categories.append("scope")
        if rule.enabled != previous_enabled:
            changed_categories.append("enabled")
        log_event(
            session,
            current_user,
            AuditAction.AUTOMATIC_TAG_RULE_UPDATED,
            "automatic_tag_rule",
            "Automatic tag rule",
            target_id=rule.id,
            details={"changed_categories": changed_categories},
        )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="This automatic tag rule already exists",
        ) from error
    session.refresh(rule)
    return _automatic_rule_read(session, rule, tag.name)


@admin_router.delete("/automatic-tag-rules/{rule_id}", status_code=204, dependencies=[Depends(require_global_permission(TAG_RULES_MANAGE))])
def delete_automatic_rule(
    rule_id: int, current_user: CurrentUser, session: SessionDependency
) -> Response:
    rule = session.get(AutomaticTagRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Automatic tag rule not found")
    log_event(
        session,
        current_user,
        AuditAction.AUTOMATIC_TAG_RULE_DELETED,
        "automatic_tag_rule",
        "Automatic tag rule",
        target_id=rule.id,
    )
    session.delete(rule)
    session.flush()
    recompute_automatic_tags(session)
    session.commit()
    return Response(status_code=204)


@admin_router.post(
    "/automatic-tag-rules/re-evaluate",
    response_model=AutomaticTagEvaluationRead,
    dependencies=[Depends(require_global_permission(TAG_RULES_MANAGE))],
)
def reevaluate_automatic_rules(
    session: SessionDependency,
) -> AutomaticTagEvaluationRead:
    result = recompute_automatic_tags(session)
    session.commit()
    return AutomaticTagEvaluationRead(**result.__dict__)


@admin_router.get(
    "/tags/{tag_id}/assignment-rules", response_model=list[TagAssignmentRuleRead]
)
def list_assignment_rules(
    tag_id: int, current_user: CurrentUser, session: SessionDependency
) -> list[TagAssignmentRuleRead]:
    tag = _tag_or_404(session, tag_id)
    _require_assignment_rule_access(session, current_user)
    rules = list(
        session.scalars(
            select(TagAssignmentRule)
            .where(
                TagAssignmentRule.tag_id == tag.id,
                TagAssignmentRule.legacy_kind.is_(None),
            )
            .order_by(TagAssignmentRule.id)
        )
    )
    return [_assignment_rule_read(session, rule, tag.name) for rule in rules]


@admin_router.post(
    "/tags/{tag_id}/assignment-rules",
    response_model=TagAssignmentRuleRead,
    status_code=status.HTTP_201_CREATED,
)
def create_assignment_rule(
    tag_id: int,
    payload: TagAssignmentRuleWrite,
    current_user: CurrentUser,
    session: SessionDependency,
) -> TagAssignmentRuleRead:
    tag = _tag_or_404(session, tag_id)
    _require_assignment_rule_access(session, current_user)
    values = _assignment_rule_values(session, payload)
    rule = TagAssignmentRule(tag_id=tag.id, **values)
    session.add(rule)
    try:
        session.flush()
        _replace_assignment_rule_targets(session, rule, payload)
        affected_model_ids = evaluate_assignment_rule(session, rule)
        refresh_assignment_rule_tags(session, affected_model_ids)
        log_event(
            session,
            current_user,
            AuditAction.TAG_ASSIGNMENT_RULE_CREATED,
            "tag_assignment_rule",
            "Tag assignment rule",
            target_id=rule.id,
            library_source_id=rule.library_source_id,
            details=_assignment_rule_audit_details(rule, payload.targets),
        )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="Tag assignment rule already exists") from error
    session.refresh(rule)
    return _assignment_rule_read(session, rule, tag.name)


@admin_router.post(
    "/tag-assignment-rules/preview", response_model=list[TagAssignmentRulePreviewRead]
)
def preview_assignment_rule(
    payload: TagAssignmentRulePreview,
    current_user: CurrentUser,
    session: SessionDependency,
) -> list[TagAssignmentRulePreviewRead]:
    _require_assignment_rule_access(session, current_user)
    values = _assignment_rule_values(session, payload)
    rule = TagAssignmentRule(tag_id=0, **values)
    targets = [
        TagAssignmentRuleTarget(
            target_type=target.target_type, folder_segment=target.folder_segment
        )
        for target in payload.targets
    ]
    models, matched_model_ids = find_assignment_rule_matches(session, rule, targets)
    return [
        TagAssignmentRulePreviewRead(model_name=model.name, relative_path=model.relative_path)
        for model in models
        if model.id in matched_model_ids
    ][: payload.limit]


@admin_router.post(
    "/tag-assignment-rules/re-evaluate", response_model=TagAssignmentRuleEvaluationRead
)
def reevaluate_all_assignment_rules(
    current_user: CurrentUser, session: SessionDependency
) -> TagAssignmentRuleEvaluationRead:
    _require_assignment_rule_access(session, current_user)
    models_evaluated, matches, added, removed = reevaluate_canonical_rules(session)
    log_event(
        session,
        current_user,
        AuditAction.TAG_ASSIGNMENT_RULE_RE_EVALUATED,
        "tag_assignment_rule",
        "Tag assignment rules",
        details={"scope": "all", "models_evaluated": models_evaluated, "matches": matches},
    )
    session.commit()
    return TagAssignmentRuleEvaluationRead(
        models_evaluated=models_evaluated,
        matches=matches,
        assignments_added=added,
        assignments_removed=removed,
    )


@admin_router.put(
    "/tag-assignment-rules/{rule_id}", response_model=TagAssignmentRuleRead
)
def update_assignment_rule(
    rule_id: int,
    payload: TagAssignmentRuleWrite,
    current_user: CurrentUser,
    session: SessionDependency,
) -> TagAssignmentRuleRead:
    rule = _assignment_rule_or_404(session, rule_id)
    _require_assignment_rule_access(session, current_user)
    values = _assignment_rule_values(session, payload)
    previous_model_ids = set(
        session.scalars(
            select(TagAssignmentRuleMatch.model_id).where(
                TagAssignmentRuleMatch.tag_assignment_rule_id == rule.id
            )
        )
    )
    for name, value in values.items():
        setattr(rule, name, value)
    try:
        _replace_assignment_rule_targets(session, rule, payload)
        session.flush()
        affected_model_ids = previous_model_ids | evaluate_assignment_rule(session, rule)
        refresh_assignment_rule_tags(session, affected_model_ids)
        log_event(
            session,
            current_user,
            AuditAction.TAG_ASSIGNMENT_RULE_UPDATED,
            "tag_assignment_rule",
            "Tag assignment rule",
            target_id=rule.id,
            library_source_id=rule.library_source_id,
            details=_assignment_rule_audit_details(rule, payload.targets),
        )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="Tag assignment rule already exists") from error
    session.refresh(rule)
    return _assignment_rule_read(session, rule, _tag_or_404(session, rule.tag_id).name)


@admin_router.delete("/tag-assignment-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assignment_rule(
    rule_id: int, current_user: CurrentUser, session: SessionDependency
) -> Response:
    rule = _assignment_rule_or_404(session, rule_id)
    _require_assignment_rule_access(session, current_user)
    affected_model_ids = set(
        session.scalars(
            select(TagAssignmentRuleMatch.model_id).where(
                TagAssignmentRuleMatch.tag_assignment_rule_id == rule.id
            )
        )
    )
    source_id = rule.library_source_id
    rule_id = rule.id
    session.execute(
        delete(TagAssignmentRuleMatch).where(
            TagAssignmentRuleMatch.tag_assignment_rule_id == rule_id
        )
    )
    session.execute(
        delete(TagAssignmentRuleTarget).where(
            TagAssignmentRuleTarget.tag_assignment_rule_id == rule_id
        )
    )
    session.delete(rule)
    session.flush()
    refresh_assignment_rule_tags(session, affected_model_ids)
    log_event(
        session,
        current_user,
        AuditAction.TAG_ASSIGNMENT_RULE_DELETED,
        "tag_assignment_rule",
        "Tag assignment rule",
        target_id=rule_id,
        library_source_id=source_id,
        details={"scope": "source" if source_id is not None else "all_sources"},
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_router.post(
    "/tag-assignment-rules/{rule_id}/re-evaluate",
    response_model=TagAssignmentRuleEvaluationRead,
)
def reevaluate_assignment_rule_endpoint(
    rule_id: int, current_user: CurrentUser, session: SessionDependency
) -> TagAssignmentRuleEvaluationRead:
    rule = _assignment_rule_or_404(session, rule_id)
    _require_assignment_rule_access(session, current_user)
    affected_model_ids = evaluate_assignment_rule(session, rule)
    added, removed = refresh_assignment_rule_tags(session, affected_model_ids)
    matches = session.scalar(
        select(func.count(TagAssignmentRuleMatch.id)).where(
            TagAssignmentRuleMatch.tag_assignment_rule_id == rule.id
        )
    ) or 0
    log_event(
        session,
        current_user,
        AuditAction.TAG_ASSIGNMENT_RULE_RE_EVALUATED,
        "tag_assignment_rule",
        "Tag assignment rule",
        target_id=rule.id,
        library_source_id=rule.library_source_id,
        details={"models_evaluated": len(affected_model_ids), "matches": matches},
    )
    session.commit()
    return TagAssignmentRuleEvaluationRead(
        models_evaluated=len(affected_model_ids),
        matches=matches,
        assignments_added=added,
        assignments_removed=removed,
    )


def _require_assignment_rule_access(session: Session, current_user: User) -> None:
    access = get_access_context(session, current_user)
    require_access_permission(access, TAG_RULES_MANAGE)
    if not access.all_sources:
        raise HTTPException(status_code=403, detail="All sources access is required")


def _tag_or_404(session: Session, tag_id: int) -> Tag:
    tag = session.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag


def _assignment_rule_or_404(session: Session, rule_id: int) -> TagAssignmentRule:
    rule = session.get(TagAssignmentRule, rule_id)
    if rule is None or rule.legacy_kind is not None:
        raise HTTPException(status_code=404, detail="Tag assignment rule not found")
    return rule


def _assignment_rule_values(
    session: Session, payload: TagAssignmentRuleWrite
) -> dict[str, object]:
    if payload.library_source_id is not None and session.get(
        LibrarySource, payload.library_source_id
    ) is None:
        raise HTTPException(status_code=404, detail="Library source not found")
    if payload.match_mode == MATCH_REGEX:
        try:
            pattern, pattern_key, _ = compile_case_insensitive_regex(payload.pattern or "")
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {
            "library_source_id": payload.library_source_id,
            "match_mode": payload.match_mode,
            "pattern": pattern,
            "pattern_key": pattern_key,
            "path_value": None,
            "path_relation": None,
            "enabled": payload.enabled,
            "legacy_kind": None,
            "legacy_rule_id": None,
        }
    if payload.match_mode == "path_relation":
        try:
            path_value = normalize_relative_path(payload.path_value or "")
        except PathPatternError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {
            "library_source_id": payload.library_source_id,
            "match_mode": payload.match_mode,
            "pattern": None,
            "pattern_key": None,
            "path_value": path_value,
            "path_relation": payload.path_relation,
            "enabled": payload.enabled,
            "legacy_kind": None,
            "legacy_rule_id": None,
        }
    pattern = (payload.pattern or "").strip()
    if not pattern:
        raise HTTPException(status_code=422, detail="Pattern cannot be empty")
    return {
        "library_source_id": payload.library_source_id,
        "match_mode": payload.match_mode,
        "pattern": pattern,
        "pattern_key": pattern.casefold(),
        "path_value": None,
        "path_relation": None,
        "enabled": payload.enabled,
        "legacy_kind": None,
        "legacy_rule_id": None,
    }


def _replace_assignment_rule_targets(
    session: Session, rule: TagAssignmentRule, payload: TagAssignmentRuleWrite
) -> None:
    session.execute(
        delete(TagAssignmentRuleTarget).where(
            TagAssignmentRuleTarget.tag_assignment_rule_id == rule.id
        )
    )
    session.add_all(
        TagAssignmentRuleTarget(
            tag_assignment_rule_id=rule.id,
            target_type=target.target_type,
            folder_segment=target.folder_segment,
        )
        for target in payload.targets
    )
    session.flush()


def _assignment_rule_read(
    session: Session, rule: TagAssignmentRule, tag_name: str
) -> TagAssignmentRuleRead:
    targets = list(
        session.scalars(
            select(TagAssignmentRuleTarget)
            .where(TagAssignmentRuleTarget.tag_assignment_rule_id == rule.id)
            .order_by(TagAssignmentRuleTarget.id)
        )
    )
    match_count = session.scalar(
        select(func.count(TagAssignmentRuleMatch.id)).where(
            TagAssignmentRuleMatch.tag_assignment_rule_id == rule.id
        )
    ) or 0
    return TagAssignmentRuleRead(
        id=rule.id,
        tag_id=rule.tag_id,
        tag_name=tag_name,
        library_source_id=rule.library_source_id,
        match_mode=rule.match_mode,
        pattern=rule.pattern,
        path_value=rule.path_value,
        path_relation=rule.path_relation,
        enabled=rule.enabled,
        targets=targets,
        match_count=match_count,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def _assignment_rule_audit_details(
    rule: TagAssignmentRule, targets: list[TagAssignmentRuleTarget]
) -> dict[str, object]:
    return {
        "targets": [target.target_type for target in targets],
        "match_mode": rule.match_mode,
        "scope": "source" if rule.library_source_id is not None else "all_sources",
        "enabled": rule.enabled,
    }


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
