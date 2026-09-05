"""Shared validation and legacy-path semantics for assignment-rule phases."""

from pathlib import PurePosixPath

import re2

MAX_PATTERN_LENGTH = 255
MATCH_CONTAINS = "contains"
MATCH_REGEX = "regex"
MATCH_PATH_RELATION = "path_relation"
PATH_DIRECT_CHILD = "direct_child"
PATH_SELF_OR_DESCENDANT = "self_or_descendant"


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
