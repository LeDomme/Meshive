import pytest

from meshive.services.library_paths import (
    PathPatternError,
    model_pattern_warnings,
    parse_library_path,
    validate_library_root,
)


def test_parses_creator_franchise_and_model_folder_layout() -> None:
    normalized_path, values = parse_library_path(
        directory_pattern="{creator_folder}/{franchise}/{model_folder}",
        model_pattern="{franchise} - {model} - by {creator}",
        relative_path=(
            r"Bulkamancer Sculpts\Bocchi the Rock"
            r"\Bocchi the Rock - Hitori Gotoh - by Bulkamancer"
        ),
    )

    assert normalized_path == (
        "Bulkamancer Sculpts/Bocchi the Rock/"
        "Bocchi the Rock - Hitori Gotoh - by Bulkamancer"
    )
    assert values == {
        "creator_folder": "Bulkamancer Sculpts",
        "franchise": "Bocchi the Rock",
        "model_folder": "Bocchi the Rock - Hitori Gotoh - by Bulkamancer",
        "model": "Hitori Gotoh",
        "creator": "Bulkamancer",
    }


def test_parses_franchise_and_model_folder_layout() -> None:
    _, values = parse_library_path(
        directory_pattern="{franchise}/{model_folder}",
        model_pattern="{franchise} - {model} - by {creator}",
        relative_path="Animal Crossing/Animal Crossing - Ankha - by Rubim",
    )

    assert values["franchise"] == "Animal Crossing"
    assert values["model"] == "Ankha"
    assert values["creator"] == "Rubim"


def test_rejects_conflicting_values_from_directory_and_model_name() -> None:
    with pytest.raises(PathPatternError, match="Conflicting values"):
        parse_library_path(
            directory_pattern="{franchise}/{model_folder}",
            model_pattern="{franchise} - {model} - by {creator}",
            relative_path="Animal Crossing/Zelda - Link - by Example",
        )


def test_tries_model_name_patterns_in_order_and_keeps_broad_franchise() -> None:
    _, values = parse_library_path(
        directory_pattern="{franchise}/{model_folder}",
        model_pattern=(
            "{series} - {model} - by {creator}\n"
            "{series} - {model} - {creator}"
        ),
        relative_path="Marvel/Marvel Rivals - Magik - 3D.moonn",
    )

    assert values["franchise"] == "Marvel"
    assert values["series"] == "Marvel Rivals"
    assert values["model"] == "Magik"
    assert values["creator"] == "3D.moonn"


def test_parses_series_below_a_broad_franchise() -> None:
    _, values = parse_library_path(
        directory_pattern="{franchise}/{model_folder}",
        model_pattern="{series} - {model} - by {creator}",
        relative_path="Disney/Aladdin - Jasmin - by CA3D",
    )

    assert values["franchise"] == "Disney"
    assert values["series"] == "Aladdin"
    assert values["model"] == "Jasmin"


@pytest.mark.parametrize("identifier", ["variant", "Version", "EDITION", "revision"])
def test_parses_free_form_model_variant(identifier: str) -> None:
    _, values = parse_library_path(
        directory_pattern="{franchise}/{model_folder}",
        model_pattern=(
            "{franchise} - {series} - {model} - "
            "{variant_identifier} {variant} - by {creator}\n"
            "{franchise} - {series} - {model} - by {creator}"
        ),
        relative_path=(
            f"Marvel/Marvel - X-Men - Psylocke - {identifier} Chibi - BY E.S Monster"
        ),
    )

    assert values["franchise"] == "Marvel"
    assert values["series"] == "X-Men"
    assert values["model"] == "Psylocke"
    assert values["variant_identifier"] == identifier
    assert values["variant"] == "Chibi"
    assert values["creator"] == "E.S Monster"


def test_warns_about_structurally_ambiguous_variant_patterns() -> None:
    warnings = model_pattern_warnings(
        "{franchise} - {series} - {model} - by {creator}\n"
        "{franchise} - {model} - {variant} - by {creator}"
    )

    assert len(warnings) == 1
    assert "Patterns 1 and 2" in warnings[0]
    assert "{variant_identifier} {variant}" in warnings[0]

    assert model_pattern_warnings(
        "{franchise} - {series} - {model} - by {creator}\n"
        "{franchise} - {model} - {variant_identifier} {variant} - by {creator}"
    ) == []


def test_variant_identifier_requires_variant_value() -> None:
    with pytest.raises(PathPatternError, match="requires"):
        parse_library_path(
            directory_pattern="{franchise}/{model_folder}",
            model_pattern=(
                "{franchise} - {model} - {variant_identifier} - by {creator}"
            ),
            relative_path="Marvel/Marvel - Psylocke - variant - by Example",
        )


def test_tries_deeper_directory_layout_before_standard_layout() -> None:
    _, values = parse_library_path(
        directory_pattern=(
            "{creator_folder}/{franchise}/{series}/{model_folder}\n"
            "{creator_folder}/{franchise}/{model_folder}"
        ),
        model_pattern="{franchise} - {model} - by {creator}\n{model}",
        relative_path=(
            "Bulkamancer Sculpts/League of Legends/League of Legends Arcane/"
            "League of Legends - Jinx - by Bulkamancer"
        ),
    )

    assert values["creator_folder"] == "Bulkamancer Sculpts"
    assert values["franchise"] == "League of Legends"
    assert values["series"] == "League of Legends Arcane"
    assert values["model"] == "Jinx"
    assert values["creator"] == "Bulkamancer"


def test_rejects_parent_path_segments() -> None:
    with pytest.raises(PathPatternError, match="unsafe"):
        parse_library_path(
            directory_pattern="{franchise}/{model}",
            relative_path="../Animal Crossing/Ankha",
        )


def test_library_root_must_stay_inside_allowed_root() -> None:
    assert validate_library_root("/models/bulkamancer", "/models") == "/models/bulkamancer"

    with pytest.raises(PathPatternError, match="inside /models"):
        validate_library_root("/etc", "/models")
