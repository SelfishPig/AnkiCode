"""Pure helpers for Anki template completions.

This module deliberately has no Anki or Qt imports, which keeps the completion
logic easy to test and lets the GUI module fail gracefully on unsupported Anki
versions.
"""

from __future__ import annotations

from collections.abc import Iterable


ANKI_SPECIAL_COMPLETIONS = (
    "Card",
    "CardFlag",
    "Deck",
    "FrontSide",
    "Subdeck",
    "Tags",
    "Type",
)


def anki_completion_items(field_names: Iterable[str]) -> tuple[str, ...]:
    """Build the sorted completion list for Anki fields and special values."""

    fields = tuple(name for name in field_names if name)
    variants: list[str] = list(ANKI_SPECIAL_COMPLETIONS)
    for name in fields:
        variants.extend(
            (
                name,
                f"#{name}",
                f"/{name}",
                f"^{name}",
                f"cloze:{name}",
                f"hint:{name}",
                f"type:{name}",
            )
        )

    return tuple(sorted(set(variants), key=str.casefold))
