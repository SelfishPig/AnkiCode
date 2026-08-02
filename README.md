# Template Code Editor for Anki

This add-on upgrades the text area in **Cards…** with the bundled Ace web editor
for front templates, back templates, and card styling.

Features:

- Ace syntax highlighting for HTML, embedded CSS/JavaScript, standalone card
  CSS, and Anki `{{field}}` tags;
- live completion suggestions for HTML, CSS, JavaScript, Anki special fields,
  and every field in the current note type;
- line numbers, code folding, current-line highlighting, automatic indentation,
  paired brackets/quotes, and configurable spaces for Tab;
- GitHub Light Default and GitHub Dark themes, selected with Anki's theme;
- no network runtime dependency: Ace and its modes are loaded from `vendor/`;
- preserves Anki's live preview, search, Add Field, Save, and Cancel behavior.

Live completion appears after two characters by default. Use the arrow keys to
select a suggestion and press `Tab` or `Enter` to accept it. `Ctrl+Space` opens
completion at any time. Settings are available from Anki's add-on configuration
dialog.

The add-on targets Anki 2.1.50 and newer (including current 25.x/26.x builds).
