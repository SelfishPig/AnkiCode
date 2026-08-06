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

## Building the add-on

Install dependencies with `npm install`, then run `npm run build`. The command:

1. bundles the editor, Monaco, Prettier, and their styles into the ignored
   `vendor/` directory; and
2. creates `AnkiCode-v<version>.ankiaddon` in the project root.

The package contains only the add-on's Python modules, manifest, and generated
web assets. Both `vendor/` and `*.ankiaddon` are build outputs and are excluded
from Git.

## Publishing a release

Development can happen directly on `main`; ordinary pushes do not publish a
release. To publish one, open **Actions → Publish release → Run workflow** on
GitHub and enter the new version number, such as `2.3.4`.

The workflow validates the version, updates `manifest.json`, `package.json`, and
`package-lock.json`, and commits the version bump directly to `main`. It then
rebuilds the ignored vendor assets, creates the `.ankiaddon` package, atomically
pushes the commit and matching `v<version>` tag, and publishes a GitHub Release
with generated release notes and the package attached.

The release fails without changing `main` if the version is invalid, its tag
belongs to another commit, the build fails, or `main` moves while the workflow
is running. Rerunning a partially completed release with the same version safely
reuses its tag and replaces the attached package.
