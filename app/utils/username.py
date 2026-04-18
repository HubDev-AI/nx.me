"""Username normalization helper.

NFKC + ASCII-fold + lowercase produces a homograph-safe canonical form
used at every username write/compare site (registration, availability
check, reservation insert). Both app-side and DB-side (CHECK constraint
in migration 0044) enforce lowercase — the two together are what
prevents Cyrillic/fullwidth/diacritic bypass of the 180-day reservation.
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
