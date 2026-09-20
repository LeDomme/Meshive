import unicodedata

from meshive.models.catalog import LibraryModel, ModelVariant


def normalize_variant(value: str) -> tuple[str, str] | None:
    display_value = unicodedata.normalize("NFKC", value).strip()
    if not display_value:
        return None
    return display_value, display_value.casefold()


def replace_model_variants(model: LibraryModel, values: list[str] | None) -> None:
    normalized_values: list[tuple[str, str]] = []
    seen: set[str] = set()
    for value in values or []:
        normalized = normalize_variant(value)
        if normalized is not None and normalized[1] not in seen:
            normalized_values.append(normalized)
            seen.add(normalized[1])
    model.variants = [
        ModelVariant(value=value, normalized_value=normalized_value, position=position)
        for position, (value, normalized_value) in enumerate(normalized_values)
    ]


def add_scanned_variant(model: LibraryModel, value: str | None) -> None:
    if value is None:
        return
    normalized = normalize_variant(value)
    if normalized is None:
        return
    display_value, normalized_value = normalized
    if any(item.normalized_value == normalized_value for item in model.variants):
        return
    model.variants.append(
        ModelVariant(
            value=display_value,
            normalized_value=normalized_value,
            position=len(model.variants),
        )
    )
