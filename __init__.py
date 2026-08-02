"""Enhanced code editor for Anki card templates."""

from __future__ import annotations

import traceback
from typing import Any

from aqt import gui_hooks, mw
from aqt.qt import QTimer, qconnect

from .editor import TemplateCodeEditor


if mw is not None:
    mw.addonManager.setWebExports(__name__, r"vendor/monaco/.*")


def _install_editor(dialog: Any) -> None:
    """Replace Anki's template QTextEdit after the dialog is constructed."""

    try:
        old_editor = dialog.tform.edit_area
        parent = old_editor.parentWidget()
        layout = parent.layout() if parent else None
        if parent is None or layout is None:
            return

        mode_provider = lambda: (
            "css" if getattr(dialog, "current_editor_index", 0) == 2 else "html"
        )
        editor = TemplateCodeEditor(parent, mode_provider)
        editor.setObjectName(old_editor.objectName())
        editor.setSizePolicy(old_editor.sizePolicy())
        editor.setMinimumSize(old_editor.minimumSize())
        editor.setMaximumSize(old_editor.maximumSize())

        # Preserve text in case a future Anki version fills the widget before
        # firing card_layout_will_show.
        editor.blockSignals(True)
        editor.setPlainText(old_editor.toPlainText())
        editor.blockSignals(False)

        layout.replaceWidget(old_editor, editor)
        old_editor.blockSignals(True)
        old_editor.hide()
        old_editor.setParent(None)
        old_editor.deleteLater()

        dialog.tform.edit_area = editor
        qconnect(editor.textChanged, dialog.write_edits_to_template_and_redraw)

        # Anki updates current_editor_index in its own clicked handler. Queue
        # re-highlighting so it runs after that handler has finished.
        def refresh_after_toggle(_checked: bool = False) -> None:
            QTimer.singleShot(0, editor.refresh_mode)

        for button in (
            dialog.tform.front_button,
            dialog.tform.back_button,
            dialog.tform.style_button,
        ):
            qconnect(button.clicked, refresh_after_toggle)

        # Anki explicitly cleans up its preview webview, but does not know this
        # replacement is also a webview.
        qconnect(dialog.finished, lambda _result: editor.cleanup())

    except Exception:
        # An add-on must never make the Cards dialog unusable. Anki captures
        # stderr in its debug console, where this remains actionable.
        traceback.print_exc()


gui_hooks.card_layout_will_show.append(_install_editor)
