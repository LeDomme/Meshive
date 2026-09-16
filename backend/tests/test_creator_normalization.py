import pytest

from meshive.creators import normalize_creator_name


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Example Creator", "example creator"),
        ("EXAMPLE CREATOR", "example creator"),
        ("  Example Creator\t", "example creator"),
        ("Élodie", "élodie"),
        ("Ａｒｔｉｓｔ", "artist"),
        ("Straße", "strasse"),
    ],
)
def test_normalize_creator_name(value: str, expected: str) -> None:
    assert normalize_creator_name(value) == expected


def test_normalize_creator_name_collides_only_for_equal_normalized_values() -> None:
    assert normalize_creator_name("SomeCreator") == normalize_creator_name("somecreator")
    assert normalize_creator_name("Some Creator") != normalize_creator_name("SomeCreator")
