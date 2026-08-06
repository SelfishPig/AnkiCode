# Template Code Editor for Anki

This add-on upgrades the text area in **Cards…** with the bundled Monaco editor
for front templates, back templates, and card styling.

Features:

- Monaco syntax highlighting for HTML, embedded CSS/JavaScript, and standalone
  card CSS;
- Monaco's default HTML, CSS, and JavaScript completion support;
- document and selection formatting for HTML, embedded JavaScript, and CSS;
- syntax diagnostics for standalone CSS and JavaScript inside `<script>` tags;
- line numbers, code folding, current-line highlighting, automatic indentation,
  paired brackets/quotes, automatic HTML closing tags, and the rest of Monaco's
  default behavior;
- Monaco's default light and dark themes, selected with Anki's theme;
- no network runtime dependency: Monaco and its styles are compiled into
  `vendor/editor.js`, with its generated language workers under `vendor/assets/`;
- preserves Anki's live preview, search, Add Field, Save, and Cancel behavior.

Use the arrow keys to select a suggestion and press `Tab` or `Enter` to accept
it. `Ctrl+Space` opens completion at any time.

The add-on targets Anki 2.1.50 and newer (including current 25.x/26.x builds).

## Building the editor

Install dependencies with `npm install`, then run `npm run build`. Vite bundles
the `editor.js` source, Monaco, and its CSS into `vendor/editor.js`, and emits
Monaco's language workers under `vendor/assets/`.
