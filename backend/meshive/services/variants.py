import unicodedata
from collections.abc import Iterable

from meshive.models.catalog import LibraryModel, ModelVariant


def normalize_variant(value: str) -> tuple[str, str] | None:
    display_value = unicodedata.normalize("NFKC", value).strip()
    if not display_value:
        return None
    return display_value, display_value.casefold()


def normalize_variant_values(values: Iterable[str]) -> list[tuple[str, str]]:
    normalized_values: list[tuple[str, str]] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_variant(value)
        if normalized is not None and normalized[1] not in seen:
            normalized_values.append(normalized)
            seen.add(normalized[1])
    return normalized_values


def parse_source_variants(value: str | None) -> list[str]:
    if value is None:
        return []
    return [display_value for display_value, _ in normalize_variant_values(value.split(","))]


def replace_model_variants(model: LibraryModel, values: list[str] | None) -> None:
    normalized_values = normalize_variant_values(values or [])
    existing_by_normalized_value = {
        variant.normalized_value: variant for variant in model.variants
    }
    variants: list[ModelVariant] = []
    for position, (value, normalized_value) in enumerate(normalized_values):
        variant = existing_by_normalized_value.pop(normalized_value, None)
        if variant is None:
            variant = ModelVariant(
                value=value,
                normalized_value=normalized_value,
                position=position,
            )
        else:
            variant.value = value
            variant.position = position
        variants.append(variant)
    model.variants = variants
