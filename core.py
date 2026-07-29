"""Pure helpers for context-aware template completions.

This module deliberately has no Anki or Qt imports, which keeps the completion
logic easy to test and lets the GUI module fail gracefully on unsupported Anki
versions.
"""

from __future__ import annotations

import re
from collections.abc import Iterable


HTML_COMPLETIONS = (
    "a",
    "abbr",
    "audio",
    "b",
    "blockquote",
    "body",
    "br",
    "button",
    "canvas",
    "class",
    "code",
    "data-",
    "details",
    "div",
    "em",
    "for",
    "h1",
    "h2",
    "h3",
    "head",
    "href",
    "hr",
    "html",
    "id",
    "img",
    "input",
    "label",
    "lang",
    "li",
    "link",
    "meta",
    "ol",
    "p",
    "picture",
    "pre",
    "script",
    "small",
    "source",
    "span",
    "src",
    "strong",
    "style",
    "table",
    "tbody",
    "td",
    "template",
    "title",
    "tr",
    "ul",
)

CSS_COMPLETIONS = (
    "align-items",
    "animation",
    "background",
    "background-color",
    "border",
    "border-radius",
    "bottom",
    "box-shadow",
    "box-sizing",
    "color",
    "column-gap",
    "content",
    "cursor",
    "display",
    "filter",
    "flex",
    "flex-direction",
    "flex-wrap",
    "font-family",
    "font-size",
    "font-style",
    "font-weight",
    "gap",
    "grid-template-columns",
    "height",
    "justify-content",
    "left",
    "letter-spacing",
    "line-height",
    "margin",
    "margin-bottom",
    "margin-left",
    "margin-right",
    "margin-top",
    "max-height",
    "max-width",
    "min-height",
    "min-width",
    "object-fit",
    "opacity",
    "overflow",
    "padding",
    "padding-bottom",
    "padding-left",
    "padding-right",
    "padding-top",
    "position",
    "right",
    "row-gap",
    "text-align",
    "text-decoration",
    "text-overflow",
    "text-shadow",
    "text-transform",
    "top",
    "transform",
    "transition",
    "vertical-align",
    "visibility",
    "white-space",
    "width",
    "word-break",
    "z-index",
)

JAVASCRIPT_COMPLETIONS = (
    "addEventListener",
    "Array",
    "async",
    "await",
    "break",
    "case",
    "catch",
    "class",
    "const",
    "continue",
    "document",
    "else",
    "export",
    "false",
    "fetch",
    "finally",
    "for",
    "forEach",
    "function",
    "if",
    "import",
    "JSON",
    "let",
    "localStorage",
    "map",
    "Math",
    "new",
    "null",
    "Object",
    "Promise",
    "querySelector",
    "querySelectorAll",
    "reduce",
    "return",
    "setInterval",
    "setTimeout",
    "String",
    "switch",
    "this",
    "throw",
    "true",
    "try",
    "typeof",
    "undefined",
    "var",
    "while",
    "window",
)

ANKI_SPECIAL_COMPLETIONS = (
    "Card",
    "CardFlag",
    "Deck",
    "FrontSide",
    "Subdeck",
    "Tags",
    "Type",
)


def embedded_language(text_before_cursor: str, editor_mode: str) -> str:
    """Return the language active at the cursor.

    Anki stores the styling field as plain CSS, while front/back templates can
    contain embedded style and script blocks.
    """

    if editor_mode == "css":
        return "css"

    lowered = text_before_cursor.lower()
    script_open = lowered.rfind("<script")
    script_close = lowered.rfind("</script")
    if script_open > script_close:
        return "javascript"

    style_open = lowered.rfind("<style")
    style_close = lowered.rfind("</style")
    if style_open > style_close:
        return "css"

    return "html"


def completion_context(text_before_cursor: str, editor_mode: str) -> tuple[str, str]:
    """Return ``(context, prefix)`` for the completion popup."""

    mustache_open = text_before_cursor.rfind("{{")
    mustache_close = text_before_cursor.rfind("}}")
    if mustache_open > mustache_close:
        prefix = text_before_cursor[mustache_open + 2 :]
        if "\n" not in prefix:
            return "anki", prefix

    language = embedded_language(text_before_cursor, editor_mode)
    if language == "css":
        match = re.search(r"[-_a-zA-Z][\w-]*$", text_before_cursor)
    elif language == "javascript":
        match = re.search(r"[$A-Za-z_][$\w]*$", text_before_cursor)
    else:
        match = re.search(r"[A-Za-z][\w:-]*$", text_before_cursor)

    return language, match.group(0) if match else ""


def completion_items(context: str, field_names: Iterable[str]) -> tuple[str, ...]:
    """Build the sorted completion list for a language/context."""

    if context == "css":
        items = CSS_COMPLETIONS
    elif context == "javascript":
        items = JAVASCRIPT_COMPLETIONS
    elif context == "anki":
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
        items = tuple(variants)
    else:
        items = HTML_COMPLETIONS

    return tuple(sorted(set(items), key=lambda item: item.casefold()))
