import pytest

from meshive.services.variants import parse_source_variants


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, []),
        ("Neon", ["Neon"]),
        ("Neon, sexy, chibi", ["Neon", "sexy", "chibi"]),
        (" Neon , sexy ,  chibi ", ["Neon", "sexy", "chibi"]),
        ("Neon,, sexy, ", ["Neon", "sexy"]),
        ("Neon, neon, CHIBI, chibi", ["Neon", "CHIBI"]),
        ("b, a, c", ["b", "a", "c"]),
    ],
)
def test_parse_source_variants(value: str | None, expected: list[str]) -> None:
    assert parse_source_variants(value) == expected
