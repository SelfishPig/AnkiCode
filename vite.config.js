import { defineConfig } from "vite";
import { resolve } from "node:path";
import { readFileSync } from "node:fs";

function includeMonacoNotices() {
    const monacoRoot = resolve(
        import.meta.dirname,
        "node_modules/monaco-editor",
    );
    return {
        name: "include-monaco-notices",
        buildStart() {
            for (const fileName of ["LICENSE", "ThirdPartyNotices.txt"]) {
                this.emitFile({
                    type: "asset",
                    fileName,
                    source: readFileSync(resolve(monacoRoot, fileName)),
                });
            }
        },
    };
}

function injectCss() {
    return {
        name: "inject-css",
        enforce: "post",
        generateBundle(_options, bundle) {
            const cssAssets = Object.entries(bundle).filter(
                ([fileName, output]) =>
                    fileName.endsWith(".css") && output.type === "asset",
            );
            if (cssAssets.length === 0) return;

            const css = cssAssets
                .map(([, output]) => String(output.source))
                .join("\n");
            const injection = [
                "const style = document.createElement(\"style\");",
                `style.textContent = ${JSON.stringify(css)};`,
                "document.head.appendChild(style);",
            ].join("\n");

            for (const output of Object.values(bundle)) {
                if (output.type === "chunk" && output.isEntry) {
                    output.code = `${injection}\n${output.code}`;
                }
            }
            for (const [fileName] of cssAssets) delete bundle[fileName];
        },
    };
}

export default defineConfig({
    plugins: [includeMonacoNotices(), injectCss()],
    build: {
        cssCodeSplit: false,
        emptyOutDir: true,
        lib: {
            entry: resolve(import.meta.dirname, "editor.js"),
            formats: ["es"],
            fileName: () => "editor.js",
        },
        outDir: "vendor",
        rolldownOptions: {
            output: {
                codeSplitting: false,
            },
        },
        target: "es2020",
    },
});
