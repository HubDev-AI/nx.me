"""Shared auth helpers that both the API layer and repositories import.

Kept in its own module so `user_repo.py` can import without pulling the
full FastAPI router tree from `auth.py`.
"""

from __future__ import annotations

import unicodedata

from unidecode import unidecode


def normalize_username(username: str) -> str:
    """NFKC + ASCII-fold lowercase — homograph-safe availability key.

    Applied at registration, availability check, and reservation insert so
    Cyrillic 'а', fullwidth 'ａ', and diacritic variants ('café') all
    collide with their ASCII base forms.
    """
    return unidecode(unicodedata.normalize("NFKC", username)).lower()
