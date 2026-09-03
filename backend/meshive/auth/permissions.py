import unicodedata
from dataclasses import dataclass

CATALOGUE_VIEW = "catalogue.view"
CATALOGUE_VIEW_MAINTENANCE = "catalogue.view_maintenance"
ARCHIVES_VIEW_ENTRIES = "archives.view_entries"
ARCHIVES_DOWNLOAD = "archives.download"
FAVORITES_MANAGE = "favorites.manage"
MODELS_PRIMARY_IMAGE = "models.primary_image"
MODELS_TAGS = "models.tags"
MODELS_RESCAN = "models.rescan"
MODELS_REBUILD_IMAGES = "models.rebuild_images"
MODELS_RESET_IMAGES = "models.reset_images"
MODELS_DELETE_MISSING = "models.delete_missing"
SCANS_VIEW = "scans.view"
SCANS_START = "scans.start"
SCANS_CONTROL = "scans.control"
METADATA_MANAGE = "metadata.manage"
TAGS_MANAGE = "tags.manage"
TAG_RULES_MANAGE = "tag_rules.manage"
SOURCES_MANAGE = "sources.manage"
DIAGNOSTICS_VIEW = "diagnostics.view"
BACKUPS_MANAGE = "backups.manage"
USERS_MANAGE = "users.manage"
ROLES_MANAGE = "roles.manage"
AUDIT_VIEW = "audit.view"

ALL_PERMISSION_KEYS = frozenset(
    {
        CATALOGUE_VIEW,
        CATALOGUE_VIEW_MAINTENANCE,
        ARCHIVES_VIEW_ENTRIES,
        ARCHIVES_DOWNLOAD,
        FAVORITES_MANAGE,
        MODELS_PRIMARY_IMAGE,
        MODELS_TAGS,
        MODELS_RESCAN,
        MODELS_REBUILD_IMAGES,
        MODELS_RESET_IMAGES,
        MODELS_DELETE_MISSING,
        SCANS_VIEW,
        SCANS_START,
        SCANS_CONTROL,
        METADATA_MANAGE,
        TAGS_MANAGE,
        TAG_RULES_MANAGE,
        SOURCES_MANAGE,
        DIAGNOSTICS_VIEW,
        BACKUPS_MANAGE,
        USERS_MANAGE,
        ROLES_MANAGE,
        AUDIT_VIEW,
    }
)


@dataclass(frozen=True)
class SystemRoleDefinition:
    name: str
    description: str
    permission_keys: frozenset[str]
    is_superuser: bool = False


def normalize_role_name(name: str) -> str:
    return unicodedata.normalize("NFKC", name).strip().casefold()


VIEWER_PERMISSIONS = frozenset({CATALOGUE_VIEW, ARCHIVES_VIEW_ENTRIES, FAVORITES_MANAGE})
MEMBER_PERMISSIONS = VIEWER_PERMISSIONS | frozenset({ARCHIVES_DOWNLOAD})
CURATOR_PERMISSIONS = MEMBER_PERMISSIONS | frozenset(
    {MODELS_PRIMARY_IMAGE, MODELS_TAGS, METADATA_MANAGE, TAGS_MANAGE, TAG_RULES_MANAGE}
)
OPERATOR_PERMISSIONS = MEMBER_PERMISSIONS | frozenset(
    {
        CATALOGUE_VIEW_MAINTENANCE,
        MODELS_RESCAN,
        MODELS_REBUILD_IMAGES,
        MODELS_RESET_IMAGES,
        MODELS_DELETE_MISSING,
        SCANS_VIEW,
        SCANS_START,
        SCANS_CONTROL,
        DIAGNOSTICS_VIEW,
    }
)

SYSTEM_ROLE_DEFINITIONS = (
    SystemRoleDefinition("Viewer", "View the catalogue without downloads.", VIEWER_PERMISSIONS),
    SystemRoleDefinition("Member", "View and download accessible library content.", MEMBER_PERMISSIONS),
    SystemRoleDefinition("Curator", "Maintain visible catalogue metadata.", CURATOR_PERMISSIONS),
    SystemRoleDefinition("Operator", "Operate scans and diagnostics.", OPERATOR_PERMISSIONS),
    SystemRoleDefinition(
        "Administrator",
        "Full system administration.",
        ALL_PERMISSION_KEYS,
        is_superuser=True,
    ),
)


def system_role_name_for_legacy_role(legacy_role: str) -> str:
    return "Administrator" if legacy_role == "admin" else "Member"
