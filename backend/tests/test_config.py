import pytest
from pydantic import ValidationError

from meshive.config import Settings


@pytest.mark.parametrize(
    "override",
    [
        {"environment": "staging"},
        {"session_lifetime_days": 0},
        {"archive_timeout_seconds": 0},
        {"archive_max_entries": 0},
        {"thumbnail_size": 32},
        {"thumbnail_quality": 101},
    ],
)
def test_invalid_runtime_limits_are_rejected(override: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **override)
