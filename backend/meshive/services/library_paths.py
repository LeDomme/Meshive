import re
from pathlib import PurePosixPath

ALLOWED_VARIABLES = frozenset(
    {
        "category",
        "collection",
        "creator",
        "creator_folder",
        "folder",
        "franchise",
        "model",
        "model_folder",
        "series",
        "variant",
    }
)
VARIABLE_PATTERN = re.compile(r"\{([a-z][a-z0-9_]*)\}")


class PathPatternError(ValueError):
    pass


def normalize_relative_path(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not normalized:
        raise PathPatternError("The test path must be relative to the library source")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise PathPatternError("The path contains an unsafe segment")
    return path.as_posix()


def normalize_library_root(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    path = PurePosixPath(normalized)
    if not path.is_absolute():
        raise PathPatternError("The library root must be an absolute container path")
    if any(part in {".", ".."} for part in path.parts):
        raise PathPatternError("The library root contains an unsafe segment")
    return path.as_posix()


def validate_library_root(value: str, allowed_root: str) -> str:
    root = PurePosixPath(normalize_library_root(value))
    allowed = PurePosixPath(normalize_library_root(allowed_root))
    if root != allowed and allowed not in root.parents:
        raise PathPatternError(f"The library root must be inside {allowed.as_posix()}")
    return root.as_posix()


def validate_directory_pattern(value: str) -> str:
    patterns = []
    for line in value.splitlines():
        if not line.strip():
            continue
        pattern = _normalize_pattern(line)
        variables = set(VARIABLE_PATTERN.findall(pattern))
        if not {"model", "model_folder"} & variables:
            raise PathPatternError(
                "Each directory pattern must contain {model} or {model_folder}"
            )
        _compile_pattern(pattern)
        patterns.append(pattern)
    if not patterns:
        raise PathPatternError("A directory pattern is required")
    return "\n".join(patterns)


def validate_model_pattern(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    patterns = []
    for line in value.splitlines():
        if not line.strip():
            continue
        pattern = _normalize_pattern(line)
        if "/" in pattern:
            raise PathPatternError("Model-name patterns cannot contain path separators")
        _compile_pattern(pattern)
        patterns.append(pattern)
    return "\n".join(patterns)


def model_pattern_warnings(value: str | None) -> list[str]:
    normalized = validate_model_pattern(value)
    if not normalized:
        return []

    patterns = normalized.splitlines()
    warnings: list[str] = []
    for left_index, left in enumerate(patterns):
        left_variables = set(VARIABLE_PATTERN.findall(left))
        for right_index in range(left_index + 1, len(patterns)):
            right = patterns[right_index]
            right_variables = set(VARIABLE_PATTERN.findall(right))
            if ("variant" in left_variables) == ("variant" in right_variables):
                continue
            if _pattern_signature(left) != _pattern_signature(right):
                continue
            warnings.append(
                f"Patterns {left_index + 1} and {right_index + 1} are structurally "
                "ambiguous around {variant}; the first matching pattern wins. "
                "Add a literal marker such as variant {variant} if both layouts occur."
            )
    return warnings


def parse_library_path(
    *,
    directory_pattern: str,
    relative_path: str,
    model_pattern: str | None = None,
    defaults: dict[str, str | None] | None = None,
) -> tuple[str, dict[str, str]]:
    directory_pattern = validate_directory_pattern(directory_pattern)
    model_pattern = validate_model_pattern(model_pattern)
    normalized_path = normalize_relative_path(relative_path)

    values = {}
    for pattern in directory_pattern.splitlines():
        match = _compile_pattern(pattern).fullmatch(normalized_path)
        if match is not None:
            values = {
                key: value.strip()
                for key, value in match.groupdict().items()
                if value
            }
            break
    else:
        raise PathPatternError("The path does not match any directory pattern")

    if model_pattern:
        model_folder = values.get("model_folder")
        if not model_folder:
            raise PathPatternError(
                "A model-name pattern requires {model_folder} in the directory pattern"
            )
        pattern_errors: list[PathPatternError] = []
        for pattern in model_pattern.splitlines():
            name_match = _compile_pattern(pattern).fullmatch(model_folder)
            if name_match is None:
                continue
            candidate = values.copy()
            try:
                _merge_values(candidate, name_match.groupdict())
            except PathPatternError as error:
                pattern_errors.append(error)
                continue
            values = candidate
            break
        else:
            if pattern_errors:
                raise pattern_errors[0]
            raise PathPatternError(
                "The model folder does not match any model-name pattern"
            )
    elif "model" not in values and "model_folder" in values:
        values["model"] = values["model_folder"]

    for key, value in (defaults or {}).items():
        if value and key not in values:
            values[key] = value.strip()

    if not values.get("model"):
        raise PathPatternError("No model name could be resolved")

    return normalized_path, values


def _normalize_pattern(value: str) -> str:
    pattern = value.strip().replace("\\", "/").strip("/")
    if not pattern:
        raise PathPatternError("A path pattern is required")
    variables = VARIABLE_PATTERN.findall(pattern)
    unknown = sorted(set(variables) - ALLOWED_VARIABLES)
    if unknown:
        raise PathPatternError(f"Unknown variables: {', '.join(unknown)}")
    without_variables = VARIABLE_PATTERN.sub("", pattern)
    if "{" in without_variables or "}" in without_variables:
        raise PathPatternError("The pattern contains an invalid variable")
    return pattern


def _pattern_signature(pattern: str) -> str:
    return VARIABLE_PATTERN.sub("{value}", pattern).casefold()


def _compile_pattern(pattern: str) -> re.Pattern[str]:
    chunks: list[str] = []
    position = 0
    seen: set[str] = set()
    for match in VARIABLE_PATTERN.finditer(pattern):
        chunks.append(re.escape(pattern[position : match.start()]))
        name = match.group(1)
        if name in seen:
            chunks.append(f"(?P={name})")
        else:
            chunks.append(f"(?P<{name}>[^/]+?)")
            seen.add(name)
        position = match.end()
    chunks.append(re.escape(pattern[position:]))
    return re.compile("".join(chunks))


def _merge_values(target: dict[str, str], incoming: dict[str, str | None]) -> None:
    for key, raw_value in incoming.items():
        if raw_value is None:
            continue
        value = raw_value.strip()
        if key in target and target[key].casefold() != value.casefold():
            raise PathPatternError(f"Conflicting values were found for {key}")
        target[key] = value
