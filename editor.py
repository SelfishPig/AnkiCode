"""Ace-based code editor used in Anki's card-template dialog."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from typing import Any

from aqt import mw
from aqt.qt import QTextCursor, QWidget, pyqtSignal
from aqt.theme import theme_manager
from aqt.webview import AnkiWebView, AnkiWebViewKind

from .core import completion_items


DEFAULT_CONFIG: dict[str, Any] = {
    "autocomplete": True,
    "autocomplete_min_chars": 2,
    "auto_close_pairs": True,
    "font_size": 13,
    "line_wrap": False,
    "tab_size": 2,
}


def normalized_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    config = DEFAULT_CONFIG.copy()
    if isinstance(raw, dict):
        config.update(raw)

    def bounded_int(name: str, minimum: int, maximum: int) -> int:
        try:
            value = int(config[name])
        except (TypeError, ValueError):
            value = int(DEFAULT_CONFIG[name])
        return max(minimum, min(maximum, value))

    config["font_size"] = bounded_int("font_size", 8, 32)
    config["tab_size"] = bounded_int("tab_size", 1, 8)
    config["autocomplete_min_chars"] = bounded_int(
        "autocomplete_min_chars", 1, 8
    )
    config["autocomplete"] = bool(config["autocomplete"])
    config["auto_close_pairs"] = bool(config["auto_close_pairs"])
    config["line_wrap"] = bool(config["line_wrap"])
    return config


class _TemplateCursor:
    """The small QTextCursor subset used by Anki's template search."""

    def __init__(self, editor: "TemplateCodeEditor") -> None:
        self._editor = editor

    def movePosition(  # noqa: N802 - Qt-compatible API
        self,
        operation: QTextCursor.MoveOperation,
        _mode: QTextCursor.MoveMode = QTextCursor.MoveMode.MoveAnchor,
        _count: int = 1,
    ) -> bool:
        if operation == QTextCursor.MoveOperation.Start:
            self._editor._cursor_offset = 0
            return True
        return False


class TemplateCodeEditor(AnkiWebView):
    """An Ace editor with the QTextEdit API required by Anki's Cards dialog."""

    textChanged = pyqtSignal()

    def __init__(
        self,
        parent: QWidget,
        mode_provider: Callable[[], str],
        field_names: Iterable[str],
        config: dict[str, Any] | None,
    ) -> None:
        super().__init__(parent, kind=AnkiWebViewKind.CARD_LAYOUT)
        self._mode_provider = mode_provider
        self._field_names = tuple(name for name in field_names if name)
        self.config = normalized_config(config)
        self._text = ""
        self._cursor_offset = 0
        self._ready = False
        self._cleaned_up = False

        self.set_bridge_command(self._on_editor_bridge_command, self)
        self.disable_zoom()
        self.stdHtml(
            self._editor_body(),
            js=self._asset_paths(),
            context=parent.window(),
            default_css=False,
        )

    def _on_load_finished(self) -> None:
        # AnkiWebView normally maps Escape to closing its parent dialog. Ace
        # uses Escape to dismiss inline completion, so leave the key with Ace.
        pass

    @staticmethod
    def _addon_package() -> str:
        assert mw is not None
        return mw.addonManager.addonFromModule(__name__)

    @classmethod
    def _asset_paths(cls) -> list[str]:
        root = f"/_addons/{cls._addon_package()}/vendor"
        return [
            f"{root}/ace.js",
            f"{root}/ext-inline_autocomplete.js",
            f"{root}/mode-html.js",
            f"{root}/mode-css.js",
            f"{root}/mode-javascript.js",
            f"{root}/theme-github_dark.js",
            f"{root}/theme-github_light_default.js",
        ]

    @classmethod
    def _ace_base_path(cls) -> str:
        return f"/_addons/{cls._addon_package()}/vendor"

    def _editor_body(self) -> str:
        options = {
            "aceBasePath": self._ace_base_path(),
            "anki": completion_items("anki", self._field_names),
            "autocomplete": self.config["autocomplete"],
            "autocompleteMinChars": self.config["autocomplete_min_chars"],
            "autoClosePairs": self.config["auto_close_pairs"],
            "css": completion_items("css", self._field_names),
            "fields": self._field_names,
            "fontSize": self.config["font_size"],
            "html": completion_items("html", self._field_names),
            "javascript": completion_items("javascript", self._field_names),
            "mode": self._mode_provider(),
            "tabSize": self.config["tab_size"],
            "theme": self._theme_name(),
            "wrap": self.config["line_wrap"],
        }
        serialized = json.dumps(options).replace("</", "<\\/")
        return f"""
<style>
html, body, #editor {{
    height: 100%;
    margin: 0;
    overflow: hidden;
    padding: 0;
    width: 100%;
}}
#editor {{
    font-variant-ligatures: none;
}}
</style>
<div id="editor"></div>
<script>
(function () {{
    "use strict";

    const options = {serialized};
    ace.config.set("basePath", options.aceBasePath);

    const editor = ace.edit("editor");
    const languageTools = ace.require("ace/ext/language_tools");
    const autocompleteUtil = ace.require("ace/autocomplete/util");
    const Range = ace.require("ace/range").Range;
    let settingFromPython = false;
    let cursorTimer = null;
    let inlineTimer = null;

    function sendBridge(message) {{
        if (typeof pycmd === "function") {{
            pycmd(JSON.stringify(message));
        }} else {{
            window.setTimeout(function () {{ sendBridge(message); }}, 10);
        }}
    }}

    function modeName(mode) {{
        return mode === "css" ? "ace/mode/css" : "ace/mode/html";
    }}

    function textBeforeCursor(session, pos) {{
        const lines = session.getLines(0, pos.row);
        if (!lines.length) return "";
        lines[lines.length - 1] = lines[lines.length - 1].slice(0, pos.column);
        return lines.join("\\n");
    }}

    function activeLanguage(session, pos) {{
        if (session.$mode.$id === "ace/mode/css") return "css";
        const before = textBeforeCursor(session, pos).toLowerCase();
        const scriptOpen = before.lastIndexOf("<script");
        const scriptClose = before.lastIndexOf("</script");
        if (scriptOpen > scriptClose) return "javascript";
        const styleOpen = before.lastIndexOf("<style");
        const styleClose = before.lastIndexOf("</style");
        if (styleOpen > styleClose) return "css";
        return "html";
    }}

    function completionContext(session, pos) {{
        const before = textBeforeCursor(session, pos);
        if (before.lastIndexOf("{{{{") > before.lastIndexOf("}}}}")) return "anki";
        return activeLanguage(session, pos);
    }}

    const templateCompleter = {{
        identifierRegexps: [/[a-zA-Z_0-9$\\-]/],
        getCompletions: function (_editor, session, pos, prefix, callback) {{
            const context = completionContext(session, pos);
            let values = options[context] || [];
            if (context === "anki") {{
                const before = textBeforeCursor(session, pos);
                const tail = before.slice(before.lastIndexOf("{{{{") + 2);
                const modifier = tail.match(/^(?:[#/^]|(?:cloze|hint|type):)/i);
                const typed = modifier ? tail.slice(modifier[0].length) : tail;
                const candidates = modifier ? options.fields : values;
                const matches = candidates
                    .filter(function (value) {{
                        return value.startsWith(typed);
                    }})
                    .map(function (value) {{
                        // Ace replaces only its identifier prefix. Returning
                        // the remaining field-name fragment also supports
                        // names containing spaces (for example "My Field").
                        const insertion = value.slice(
                            Math.max(0, typed.length - prefix.length)
                        );
                        return {{
                            caption: insertion,
                            value: insertion,
                            meta: "anki: " + value,
                            score: 1100
                        }};
                    }});
                callback(null, matches);
                return;
            }}
            callback(null, values
                .filter(function (value) {{
                    return value.startsWith(prefix);
                }})
                .map(function (value) {{
                    return {{
                        caption: value,
                        value: value,
                        meta: context,
                        score: 1000
                    }};
                }}));
        }},
        id: "ankiTemplateCompleter"
    }};

    editor.completers = [
        templateCompleter,
        languageTools.keyWordCompleter,
        languageTools.snippetCompleter
    ];
    editor.setOptions({{
        behavioursEnabled: options.autoClosePairs,
        displayIndentGuides: true,
        enableBasicAutocompletion: false,
        enableInlineAutocompletion: options.autocomplete,
        enableLiveAutocompletion: false,
        enableSnippets: false,
        fontSize: options.fontSize + "pt",
        highlightActiveLine: true,
        highlightSelectedWord: true,
        mode: modeName(options.mode),
        navigateWithinSoftTabs: true,
        showFoldWidgets: true,
        showGutter: true,
        tabSize: options.tabSize,
        theme: options.theme,
        useSoftTabs: true,
        wrap: options.wrap
    }});
    editor.session.setUseWorker(false);

    function startInlineCompletion(forced) {{
        if (!options.autocomplete) return;
        const prefix = autocompleteUtil.getCompletionPrefix(editor);
        if (!forced && prefix.length < options.autocompleteMinChars) return;
        if (editor.completer && editor.completer.activated) return;
        editor.execCommand("startInlineAutocomplete");
    }}

    editor.commands.addCommand({{
        name: "showTemplateInlineCompletion",
        bindKey: {{ win: "Ctrl-Space", mac: "Ctrl-Space" }},
        exec: function () {{ startInlineCompletion(true); }}
    }});

    editor.commands.on("afterExec", function (event) {{
        if (!options.autocomplete || settingFromPython) return;
        if (
            event.command.name !== "insertstring"
            && event.command.name !== "backspace"
        ) return;
        if (inlineTimer !== null) window.clearTimeout(inlineTimer);
        inlineTimer = window.setTimeout(function () {{
            inlineTimer = null;
            startInlineCompletion(false);
        }}, 0);
    }});

    editor.session.on("change", function () {{
        if (settingFromPython) return;
        const pos = editor.getCursorPosition();
        sendBridge({{
            event: "change",
            text: editor.getValue(),
            cursor: editor.session.doc.positionToIndex(pos, 0)
        }});
    }});

    editor.selection.on("changeCursor", function () {{
        if (settingFromPython) return;
        if (cursorTimer !== null) window.clearTimeout(cursorTimer);
        cursorTimer = window.setTimeout(function () {{
            cursorTimer = null;
            const pos = editor.getCursorPosition();
            sendBridge({{
                event: "cursor",
                cursor: editor.session.doc.positionToIndex(pos, 0)
            }});
        }}, 25);
    }});

    window.codeEditorSetValue = function (value) {{
        settingFromPython = true;
        editor.setValue(value, -1);
        settingFromPython = false;
    }};
    window.codeEditorSetMode = function (mode) {{
        options.mode = mode;
        editor.session.setMode(modeName(mode));
    }};
    window.codeEditorSetTheme = function (theme) {{
        options.theme = theme;
        editor.setTheme(theme);
    }};
    window.codeEditorSelect = function (start, end) {{
        const doc = editor.session.doc;
        editor.selection.setRange(new Range(
            doc.indexToPosition(start, 0).row,
            doc.indexToPosition(start, 0).column,
            doc.indexToPosition(end, 0).row,
            doc.indexToPosition(end, 0).column
        ));
        editor.scrollToLine(doc.indexToPosition(start, 0).row, true, true);
        editor.focus();
    }};

    editor.resize(true);
    sendBridge({{ event: "ready" }});
}})();
</script>
"""

    @staticmethod
    def _theme_name() -> str:
        return (
            "ace/theme/github_dark"
            if theme_manager.night_mode
            else "ace/theme/github_light_default"
        )

    def _on_editor_bridge_command(self, command: str) -> None:
        try:
            message = json.loads(command)
        except (TypeError, json.JSONDecodeError):
            return
        if not isinstance(message, dict):
            return

        event = message.get("event")
        if event == "ready":
            self._ready = True
            self._set_javascript_value()
            self.refresh_mode()
            self.eval(
                f"window.codeEditorSetTheme({json.dumps(self._theme_name())});"
            )
        elif event == "change" and isinstance(message.get("text"), str):
            self._text = message["text"]
            self._cursor_offset = self._valid_cursor(message.get("cursor"))
            self.textChanged.emit()
        elif event == "cursor":
            self._cursor_offset = self._valid_cursor(message.get("cursor"))

    def _valid_cursor(self, cursor: Any) -> int:
        try:
            offset = int(cursor)
        except (TypeError, ValueError):
            return self._cursor_offset
        return max(0, min(len(self._text), offset))

    def _set_javascript_value(self) -> None:
        if self._ready:
            self.eval(f"window.codeEditorSetValue({json.dumps(self._text)});")

    def setPlainText(self, text: str) -> None:  # noqa: N802 - Qt API
        self._text = str(text)
        self._cursor_offset = 0
        self._set_javascript_value()
        self.textChanged.emit()

    def toPlainText(self) -> str:  # noqa: N802 - Qt API
        return self._text

    def refresh_mode(self) -> None:
        mode = self._mode_provider()
        if self._ready:
            self.eval(f"window.codeEditorSetMode({json.dumps(mode)});")

    def find(self, text: str, *_args: Any) -> bool:
        if not text:
            return False
        index = self._text.find(text, self._cursor_offset)
        if index < 0:
            return False
        end = index + len(text)
        self._cursor_offset = end
        if self._ready:
            self.eval(f"window.codeEditorSelect({index}, {end});")
        return True

    def textCursor(self) -> _TemplateCursor:  # noqa: N802 - Qt API
        return _TemplateCursor(self)

    def setTextCursor(self, _cursor: _TemplateCursor) -> None:  # noqa: N802
        if self._ready:
            offset = self._cursor_offset
            self.eval(f"window.codeEditorSelect({offset}, {offset});")

    def on_theme_did_change(self) -> None:
        super().on_theme_did_change()
        if self._ready:
            self.eval(
                f"window.codeEditorSetTheme({json.dumps(self._theme_name())});"
            )

    def cleanup(self) -> None:
        if self._cleaned_up:
            return
        self._cleaned_up = True
        super().cleanup()
