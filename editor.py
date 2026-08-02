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
        return [f"{cls._monaco_base_path()}/loader.js"]

    @classmethod
    def _monaco_base_path(cls) -> str:
        return f"/_addons/{cls._addon_package()}/vendor/monaco/vs"

    def _editor_body(self) -> str:
        options = {
            "monacoBasePath": self._monaco_base_path(),
            "mode": self._mode_provider(),
            "theme": self._theme_name(),
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
</style>
<div id="editor"></div>
<script>
(function () {{
    "use strict";

    const options = {serialized};
    require.config({{ paths: {{ vs: options.monacoBasePath }} }});
    require(["vs/editor/editor.main"], function () {{
        let settingFromPython = false;
        let cursorTimer = null;

        function sendBridge(message) {{
            if (typeof pycmd === "function") {{
                pycmd(JSON.stringify(message));
            }} else {{
                window.setTimeout(function () {{ sendBridge(message); }}, 10);
            }}
        }}

        function modeName(mode) {{
            return mode === "css" ? "css" : "html";
        }}

        const editor = monaco.editor.create(
            document.getElementById("editor"),
            {{ theme: options.theme }}
        );
        const model = editor.getModel();
        monaco.editor.setModelLanguage(model, modeName(options.mode));
        const javascriptModels = [];
        let diagnosticsTimer = null;
        let diagnosticsVersion = 0;

        function scriptBlocks(model) {{
            const text = model.getValue();
            const lowered = text.toLocaleLowerCase();
            const blocks = [];
            let searchFrom = 0;
            while (searchFrom < text.length) {{
                const openingTag = lowered.indexOf("<script", searchFrom);
                if (openingTag < 0) break;
                const tagEnd = text.indexOf(">", openingTag);
                if (tagEnd < 0) break;
                const contentStart = tagEnd + 1;
                const closingTag = lowered.indexOf("</script", contentStart);
                const contentEnd = closingTag < 0 ? text.length : closingTag;
                blocks.push({{
                    content: text.slice(contentStart, contentEnd),
                    contentStart: contentStart,
                    contentEnd: contentEnd
                }});
                if (closingTag < 0) break;
                const closingEnd = text.indexOf(">", closingTag);
                searchFrom = closingEnd < 0 ? text.length : closingEnd + 1;
            }}
            return blocks;
        }}

        function scriptContext(model, position) {{
            const cursor = model.getOffsetAt(position);
            const blocks = scriptBlocks(model);
            for (let index = 0; index < blocks.length; index += 1) {{
                const block = blocks[index];
                if (cursor >= block.contentStart && cursor <= block.contentEnd) {{
                    return Object.assign({{
                        cursor: cursor - block.contentStart,
                        index: index
                    }}, block);
                }}
            }}
            return null;
        }}

        function javascriptModel(index, content) {{
            if (!javascriptModels[index]) {{
                javascriptModels[index] = monaco.editor.createModel(
                    content,
                    "javascript",
                    monaco.Uri.parse(
                        "inmemory://anki-template/script-" + index + ".js"
                    )
                );
            }} else if (javascriptModels[index].getValue() !== content) {{
                javascriptModels[index].setValue(content);
            }}
            return javascriptModels[index];
        }}

        function completionKind(kind) {{
            const kinds = monaco.languages.CompletionItemKind;
            if (kind === "method") return kinds.Method;
            if (kind === "function") return kinds.Function;
            if (kind === "property" || kind === "getter" || kind === "setter") {{
                return kinds.Property;
            }}
            if (kind === "class") return kinds.Class;
            if (kind === "interface" || kind === "type") return kinds.Interface;
            if (kind === "module") return kinds.Module;
            if (kind === "keyword") return kinds.Keyword;
            if (kind === "const") return kinds.Constant;
            return kinds.Variable;
        }}

        const javascriptCompletionProvider =
            monaco.languages.registerCompletionItemProvider("html", {{
                triggerCharacters: [".", "'", String.fromCharCode(34)],
                provideCompletionItems: async function (model, position) {{
                    const context = scriptContext(model, position);
                    if (!context) return {{ suggestions: [] }};

                    const scriptModel = javascriptModel(
                        context.index,
                        context.content
                    );

                    try {{
                        const getWorker =
                            await monaco.languages.typescript.getJavaScriptWorker();
                        const worker = await getWorker(scriptModel.uri);
                        const info = await worker.getCompletionsAtPosition(
                            scriptModel.uri.toString(),
                            context.cursor
                        );
                        if (!info) return {{ suggestions: [] }};

                        const word = model.getWordUntilPosition(position);
                        const defaultRange = new monaco.Range(
                            position.lineNumber,
                            word.startColumn,
                            position.lineNumber,
                            word.endColumn
                        );
                        return {{
                            suggestions: info.entries.map(function (entry) {{
                                let range = defaultRange;
                                const span = entry.replacementSpan ||
                                    info.optionalReplacementSpan;
                                if (span) {{
                                    const start = model.getPositionAt(
                                        context.contentStart + span.start
                                    );
                                    const end = model.getPositionAt(
                                        context.contentStart + span.start + span.length
                                    );
                                    if (start.lineNumber === end.lineNumber) {{
                                        range = new monaco.Range(
                                            start.lineNumber,
                                            start.column,
                                            end.lineNumber,
                                            end.column
                                        );
                                    }}
                                }}
                                const suggestion = {{
                                    filterText: entry.filterText,
                                    insertText: entry.insertText || entry.name,
                                    kind: completionKind(entry.kind),
                                    label: entry.name,
                                    range: range,
                                    sortText: entry.sortText
                                }};
                                if (entry.isSnippet) {{
                                    suggestion.insertTextRules =
                                        monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet;
                                }}
                                return suggestion;
                            }})
                        }};
                    }} catch (_error) {{
                        return {{ suggestions: [] }};
                    }}
                }}
            }});

        function diagnosticMessage(message) {{
            if (typeof message === "string") return message;
            const parts = [message.messageText];
            (message.next || []).forEach(function (next) {{
                parts.push(diagnosticMessage(next));
            }});
            return parts.join("\\n");
        }}

        async function validateJavascript(version) {{
            if (model.getLanguageId() !== "html") {{
                monaco.editor.setModelMarkers(model, "javascript", []);
                return;
            }}

            const blocks = scriptBlocks(model);
            while (javascriptModels.length > blocks.length) {{
                javascriptModels.pop().dispose();
            }}
            if (!blocks.length) {{
                monaco.editor.setModelMarkers(model, "javascript", []);
                return;
            }}

            try {{
                const getWorker =
                    await monaco.languages.typescript.getJavaScriptWorker();
                const markers = [];
                for (let index = 0; index < blocks.length; index += 1) {{
                    const block = blocks[index];
                    const scriptModel = javascriptModel(index, block.content);
                    const worker = await getWorker(scriptModel.uri);
                    const diagnostics = await worker.getSyntacticDiagnostics(
                        scriptModel.uri.toString()
                    );
                    diagnostics.forEach(function (diagnostic) {{
                        const startOffset = block.contentStart +
                            (diagnostic.start || 0);
                        const endOffset = startOffset + (diagnostic.length || 1);
                        const start = model.getPositionAt(startOffset);
                        const end = model.getPositionAt(endOffset);
                        markers.push({{
                            code: String(diagnostic.code),
                            endColumn: end.column,
                            endLineNumber: end.lineNumber,
                            message: diagnosticMessage(diagnostic.messageText),
                            severity: monaco.MarkerSeverity.Error,
                            source: "JavaScript",
                            startColumn: start.column,
                            startLineNumber: start.lineNumber
                        }});
                    }});
                }}
                if (version === diagnosticsVersion) {{
                    monaco.editor.setModelMarkers(model, "javascript", markers);
                }}
            }} catch (_error) {{
                if (version === diagnosticsVersion) {{
                    monaco.editor.setModelMarkers(model, "javascript", []);
                }}
            }}
        }}

        function scheduleDiagnostics() {{
            if (diagnosticsTimer !== null) window.clearTimeout(diagnosticsTimer);
            const version = ++diagnosticsVersion;
            diagnosticsTimer = window.setTimeout(function () {{
                diagnosticsTimer = null;
                validateJavascript(version);
            }}, 250);
        }}

        const voidElements = new Set([
            "area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "param", "source", "track", "wbr"
        ]);

        function closeHtmlTag(change) {{
            const cursorOffset = change.rangeOffset + 1;
            window.setTimeout(function () {{
                if (model.getLanguageId() !== "html") return;
                const position = editor.getPosition();
                if (!position || model.getOffsetAt(position) !== cursorOffset) return;

                const text = model.getValue();
                if (text.charAt(cursorOffset - 1) !== ">") return;
                const tagStart = text.lastIndexOf("<", cursorOffset - 1);
                if (tagStart < 0) return;
                const openingTag = text.slice(tagStart, cursorOffset);
                if (openingTag.startsWith("</") || openingTag.endsWith("/>")) return;

                const match = openingTag.match(
                    /^<([A-Za-z][\\w:-]*)(?:\\s+(?:[^"'<>]|"[^"]*"|'[^']*')*)?>$/
                );
                if (!match) return;
                const tagName = match[1];
                if (voidElements.has(tagName.toLocaleLowerCase())) return;
                const closingTag = "</" + tagName + ">";
                if (text.slice(cursorOffset).toLocaleLowerCase().startsWith(
                    closingTag.toLocaleLowerCase()
                )) return;

                editor.executeEdits("close-html-tag", [{{
                    range: new monaco.Range(
                        position.lineNumber,
                        position.column,
                        position.lineNumber,
                        position.column
                    ),
                    text: closingTag
                }}]);
                editor.setPosition(position);
            }}, 0);
        }}

        model.onDidChangeContent(function (event) {{
            if (settingFromPython) return;
            scheduleDiagnostics();
            if (event.changes.length === 1 && event.changes[0].text === ">") {{
                closeHtmlTag(event.changes[0]);
            }}
            const position = editor.getPosition();
            sendBridge({{
                event: "change",
                text: model.getValue(),
                cursor: position ? model.getOffsetAt(position) : 0
            }});
        }});

        editor.onDidChangeCursorPosition(function () {{
            if (settingFromPython) return;
            if (cursorTimer !== null) window.clearTimeout(cursorTimer);
            cursorTimer = window.setTimeout(function () {{
                cursorTimer = null;
                const position = editor.getPosition();
                sendBridge({{
                    event: "cursor",
                    cursor: position ? model.getOffsetAt(position) : 0
                }});
            }}, 25);
        }});

        window.codeEditorSetValue = function (value) {{
            settingFromPython = true;
            model.setValue(String(value));
            editor.setPosition({{ lineNumber: 1, column: 1 }});
            settingFromPython = false;
            scheduleDiagnostics();
        }};
        window.codeEditorSetMode = function (mode) {{
            options.mode = mode;
            monaco.editor.setModelLanguage(model, modeName(mode));
            scheduleDiagnostics();
        }};
        window.codeEditorSetTheme = function (theme) {{
            options.theme = theme;
            monaco.editor.setTheme(theme);
        }};
        window.codeEditorSelect = function (start, end) {{
            const range = new monaco.Range(
                model.getPositionAt(start).lineNumber,
                model.getPositionAt(start).column,
                model.getPositionAt(end).lineNumber,
                model.getPositionAt(end).column
            );
            editor.setSelection(range);
            editor.revealRangeInCenterIfOutsideViewport(range);
            editor.focus();
        }};
        window.codeEditorDispose = function () {{
            diagnosticsVersion += 1;
            if (diagnosticsTimer !== null) window.clearTimeout(diagnosticsTimer);
            monaco.editor.setModelMarkers(model, "javascript", []);
            javascriptCompletionProvider.dispose();
            javascriptModels.forEach(function (scriptModel) {{
                scriptModel.dispose();
            }});
            editor.dispose();
            model.dispose();
        }};

        sendBridge({{ event: "ready" }});
    }});
}})();
</script>
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
