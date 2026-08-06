import "monaco-editor/languages/definitions/register.all";
import "monaco-editor/languages/features/register.all";
import * as monaco from "monaco-editor";

(function () {
    "use strict";

    const options = window.codeEditorOptions;
    let settingFromPython = false;
    let cursorTimer = null;

    function sendBridge(message) {
        if (typeof pycmd === "function") {
            pycmd(JSON.stringify(message));
        } else {
            window.setTimeout(function () {
                sendBridge(message);
            }, 10);
        }
    }

    function modeName(mode) {
        return mode === "css" ? "css" : "html";
    }

    const editor = monaco.editor.create(document.getElementById("editor"), {
        automaticLayout: true,
        theme: options.theme,
    });
    const model = editor.getModel();
    monaco.editor.setModelLanguage(model, modeName(options.mode));
    const javascriptModels = [];
    let diagnosticsTimer = null;
    let diagnosticsVersion = 0;

    function scriptBlocks(sourceModel) {
        const text = sourceModel.getValue();
        const lowered = text.toLocaleLowerCase();
        const blocks = [];
        let searchFrom = 0;
        while (searchFrom < text.length) {
            const openingTag = lowered.indexOf("<script", searchFrom);
            if (openingTag < 0) break;
            const tagEnd = text.indexOf(">", openingTag);
            if (tagEnd < 0) break;
            const contentStart = tagEnd + 1;
            const closingTag = lowered.indexOf("</script", contentStart);
            const contentEnd = closingTag < 0 ? text.length : closingTag;
            blocks.push({
                content: text.slice(contentStart, contentEnd),
                contentStart,
                contentEnd,
            });
            if (closingTag < 0) break;
            const closingEnd = text.indexOf(">", closingTag);
            searchFrom = closingEnd < 0 ? text.length : closingEnd + 1;
        }
        return blocks;
    }

    function scriptContext(sourceModel, position) {
        const cursor = sourceModel.getOffsetAt(position);
        const blocks = scriptBlocks(sourceModel);
        for (let index = 0; index < blocks.length; index += 1) {
            const block = blocks[index];
            if (cursor >= block.contentStart && cursor <= block.contentEnd) {
                return Object.assign(
                    {
                        cursor: cursor - block.contentStart,
                        index,
                    },
                    block,
                );
            }
        }
        return null;
    }

    function javascriptModel(index, content) {
        if (!javascriptModels[index]) {
            javascriptModels[index] = monaco.editor.createModel(
                content,
                "javascript",
                monaco.Uri.parse(
                    `inmemory://anki-template/script-${index}.js`,
                ),
            );
        } else if (javascriptModels[index].getValue() !== content) {
            javascriptModels[index].setValue(content);
        }
        return javascriptModels[index];
    }

    function completionKind(kind) {
        const kinds = monaco.languages.CompletionItemKind;
        if (kind === "method") return kinds.Method;
        if (kind === "function") return kinds.Function;
        if (kind === "property" || kind === "getter" || kind === "setter") {
            return kinds.Property;
        }
        if (kind === "class") return kinds.Class;
        if (kind === "interface" || kind === "type") return kinds.Interface;
        if (kind === "module") return kinds.Module;
        if (kind === "keyword") return kinds.Keyword;
        if (kind === "const") return kinds.Constant;
        return kinds.Variable;
    }

    const javascriptCompletionProvider =
        monaco.languages.registerCompletionItemProvider("html", {
            triggerCharacters: [".", "'", String.fromCharCode(34)],
            async provideCompletionItems(sourceModel, position) {
                const context = scriptContext(sourceModel, position);
                if (!context) return { suggestions: [] };

                const scriptModel = javascriptModel(
                    context.index,
                    context.content,
                );

                try {
                    const getWorker =
                        await monaco.languages.typescript.getJavaScriptWorker();
                    const worker = await getWorker(scriptModel.uri);
                    const info = await worker.getCompletionsAtPosition(
                        scriptModel.uri.toString(),
                        context.cursor,
                    );
                    if (!info) return { suggestions: [] };

                    const word = sourceModel.getWordUntilPosition(position);
                    const defaultRange = new monaco.Range(
                        position.lineNumber,
                        word.startColumn,
                        position.lineNumber,
                        word.endColumn,
                    );
                    return {
                        suggestions: info.entries.map(function (entry) {
                            let range = defaultRange;
                            const span =
                                entry.replacementSpan ||
                                info.optionalReplacementSpan;
                            if (span) {
                                const start = sourceModel.getPositionAt(
                                    context.contentStart + span.start,
                                );
                                const end = sourceModel.getPositionAt(
                                    context.contentStart +
                                        span.start +
                                        span.length,
                                );
                                if (start.lineNumber === end.lineNumber) {
                                    range = new monaco.Range(
                                        start.lineNumber,
                                        start.column,
                                        end.lineNumber,
                                        end.column,
                                    );
                                }
                            }
                            const suggestion = {
                                filterText: entry.filterText,
                                insertText: entry.insertText || entry.name,
                                kind: completionKind(entry.kind),
                                label: entry.name,
                                range,
                                sortText: entry.sortText,
                            };
                            if (entry.isSnippet) {
                                suggestion.insertTextRules =
                                    monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet;
                            }
                            return suggestion;
                        }),
                    };
                } catch (_error) {
                    return { suggestions: [] };
                }
            },
        });

    function diagnosticMessage(message) {
        if (typeof message === "string") return message;
        const parts = [message.messageText];
        (message.next || []).forEach(function (next) {
            parts.push(diagnosticMessage(next));
        });
        return parts.join("\n");
    }

    async function validateJavascript(version) {
        if (model.getLanguageId() !== "html") {
            monaco.editor.setModelMarkers(model, "javascript", []);
            return;
        }

        const blocks = scriptBlocks(model);
        while (javascriptModels.length > blocks.length) {
            javascriptModels.pop().dispose();
        }
        if (!blocks.length) {
            monaco.editor.setModelMarkers(model, "javascript", []);
            return;
        }

        try {
            const getWorker =
                await monaco.languages.typescript.getJavaScriptWorker();
            const markers = [];
            for (let index = 0; index < blocks.length; index += 1) {
                const block = blocks[index];
                const scriptModel = javascriptModel(index, block.content);
                const worker = await getWorker(scriptModel.uri);
                const diagnostics = await worker.getSyntacticDiagnostics(
                    scriptModel.uri.toString(),
                );
                diagnostics.forEach(function (diagnostic) {
                    const startOffset =
                        block.contentStart + (diagnostic.start || 0);
                    const endOffset =
                        startOffset + (diagnostic.length || 1);
                    const start = model.getPositionAt(startOffset);
                    const end = model.getPositionAt(endOffset);
                    markers.push({
                        code: String(diagnostic.code),
                        endColumn: end.column,
                        endLineNumber: end.lineNumber,
                        message: diagnosticMessage(diagnostic.messageText),
                        severity: monaco.MarkerSeverity.Error,
                        source: "JavaScript",
                        startColumn: start.column,
                        startLineNumber: start.lineNumber,
                    });
                });
            }
            if (version === diagnosticsVersion) {
                monaco.editor.setModelMarkers(model, "javascript", markers);
            }
        } catch (_error) {
            if (version === diagnosticsVersion) {
                monaco.editor.setModelMarkers(model, "javascript", []);
            }
        }
    }

    function scheduleDiagnostics() {
        if (diagnosticsTimer !== null) {
            window.clearTimeout(diagnosticsTimer);
        }
        const version = ++diagnosticsVersion;
        diagnosticsTimer = window.setTimeout(function () {
            diagnosticsTimer = null;
            validateJavascript(version);
        }, 250);
    }

    const voidElements = new Set([
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    ]);

    function closeHtmlTag(change) {
        const cursorOffset = change.rangeOffset + 1;
        window.setTimeout(function () {
            if (model.getLanguageId() !== "html") return;
            const position = editor.getPosition();
            if (
                !position ||
                model.getOffsetAt(position) !== cursorOffset
            ) {
                return;
            }

            const text = model.getValue();
            if (text.charAt(cursorOffset - 1) !== ">") return;
            const tagStart = text.lastIndexOf("<", cursorOffset - 1);
            if (tagStart < 0) return;
            const openingTag = text.slice(tagStart, cursorOffset);
            if (openingTag.startsWith("</") || openingTag.endsWith("/>")) {
                return;
            }

            const match = openingTag.match(
                /^<([A-Za-z][\w:-]*)(?:\s+(?:[^"'<>]|"[^"]*"|'[^']*')*)?>$/,
            );
            if (!match) return;
            const tagName = match[1];
            if (voidElements.has(tagName.toLocaleLowerCase())) return;
            const closingTag = `</${tagName}>`;
            if (
                text
                    .slice(cursorOffset)
                    .toLocaleLowerCase()
                    .startsWith(closingTag.toLocaleLowerCase())
            ) {
                return;
            }

            editor.executeEdits("close-html-tag", [
                {
                    range: new monaco.Range(
                        position.lineNumber,
                        position.column,
                        position.lineNumber,
                        position.column,
                    ),
                    text: closingTag,
                },
            ]);
            editor.setPosition(position);
        }, 0);
    }

    model.onDidChangeContent(function (event) {
        if (settingFromPython) return;
        scheduleDiagnostics();
        if (event.changes.length === 1 && event.changes[0].text === ">") {
            closeHtmlTag(event.changes[0]);
        }
        const position = editor.getPosition();
        sendBridge({
            event: "change",
            text: model.getValue(),
            cursor: position ? model.getOffsetAt(position) : 0,
        });
    });

    editor.onDidChangeCursorPosition(function () {
        if (settingFromPython) return;
        if (cursorTimer !== null) window.clearTimeout(cursorTimer);
        cursorTimer = window.setTimeout(function () {
            cursorTimer = null;
            const position = editor.getPosition();
            sendBridge({
                event: "cursor",
                cursor: position ? model.getOffsetAt(position) : 0,
            });
        }, 25);
    });

    window.codeEditorSetValue = function (value) {
        settingFromPython = true;
        model.setValue(String(value));
        editor.setPosition({ lineNumber: 1, column: 1 });
        settingFromPython = false;
        scheduleDiagnostics();
    };
    window.codeEditorSetMode = function (mode) {
        options.mode = mode;
        monaco.editor.setModelLanguage(model, modeName(mode));
        scheduleDiagnostics();
    };
    window.codeEditorSetTheme = function (theme) {
        options.theme = theme;
        monaco.editor.setTheme(theme);
    };
    window.codeEditorSelect = function (start, end) {
        const startPosition = model.getPositionAt(start);
        const endPosition = model.getPositionAt(end);
        const range = new monaco.Range(
            startPosition.lineNumber,
            startPosition.column,
            endPosition.lineNumber,
            endPosition.column,
        );
        editor.setSelection(range);
        editor.revealRangeInCenterIfOutsideViewport(range);
        editor.focus();
    };
    window.codeEditorDispose = function () {
        diagnosticsVersion += 1;
        if (diagnosticsTimer !== null) {
            window.clearTimeout(diagnosticsTimer);
        }
        monaco.editor.setModelMarkers(model, "javascript", []);
        javascriptCompletionProvider.dispose();
        javascriptModels.forEach(function (scriptModel) {
            scriptModel.dispose();
        });
        editor.dispose();
        model.dispose();
    };

    sendBridge({ event: "ready" });
})();
