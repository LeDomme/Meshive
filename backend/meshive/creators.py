"""Shared Creator Profile helpers.

The raw ``LibraryModel.creator`` value remains scan-owned.  This module only
defines the stable identity key used by Creator Profile records and aliases.
"""

import unicodedata


def normalize_creator_name(value: str) -> str:
    """Return Meshive's Unicode-aware stable key for a Creator name."""
    return unicodedata.normalize("NFKC", value).strip().casefold()
