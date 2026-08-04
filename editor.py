"""Monaco-based code editor used in Anki's card-template dialog."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from aqt import mw
from aqt.qt import QTextCursor, QWidget, pyqtSignal
from aqt.theme import theme_manager
from aqt.webview import AnkiWebView, AnkiWebViewKind


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
    """A Monaco editor with the QTextEdit API required by Anki's Cards dialog."""

    textChanged = pyqtSignal()

    def __init__(
        self,
        parent: QWidget,
        mode_provider: Callable[[], str],
    ) -> None:
        super().__init__(parent, kind=AnkiWebViewKind.CARD_LAYOUT)
        self._mode_provider = mode_provider
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
        # AnkiWebView normally maps Escape to closing its parent dialog. Monaco
        # uses Escape to dismiss suggestions, so leave the key with Monaco.
        pass

    @staticmethod
    def _addon_package() -> str:
        assert mw is not None
        return mw.addonManager.addonFromModule(__name__)

    @classmethod
    def _asset_paths(cls) -> list[str]:
        return []

    def _editor_body(self) -> str:
        options = {
            "mode": self._mode_provider(),
            "theme": self._theme_name(),
        }
        serialized = json.dumps(options).replace("</", "<\\/")
        editor_script = f"/_addons/{self._addon_package()}/vendor/editor.js"
        return f"""
<style>
html, body, #editor {{
    height: 100%;
    margin: 0;
    overflow: hidden;
    padding: 0;
    width: 100%;
}}
</style>
<div id="editor"></div>
<script>window.codeEditorOptions = {serialized};</script>
<script type="module" src="{editor_script}"></script>
"""

    @staticmethod
    def _theme_name() -> str:
        return "vs-dark" if theme_manager.night_mode else "vs"

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
        if self._ready:
            self.eval("window.codeEditorDispose();")
        super().cleanup()
