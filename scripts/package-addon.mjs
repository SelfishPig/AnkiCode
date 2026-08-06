import { readFile, readdir, writeFile } from "node:fs/promises";
import { basename, dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { zipSync } from "fflate";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const ankiWebBuild = process.argv.includes("--ankiweb");
const runtimeFiles = [
    "__init__.py",
    "editor.py",
    "README.html",
];
if (!ankiWebBuild) runtimeFiles.push("manifest.json");
const generatedAssets = "vendor";

async function readJson(path) {
    return JSON.parse(await readFile(path, "utf8"));
}

async function addDirectory(archive, directory) {
    const entries = await readdir(directory, { withFileTypes: true });
    entries.sort((left, right) => left.name.localeCompare(right.name));

    for (const entry of entries) {
        const path = join(directory, entry.name);
        if (entry.isDirectory()) {
            await addDirectory(archive, path);
        } else if (entry.isFile()) {
            const archivePath = relative(projectRoot, path)
                .split(sep)
                .join("/");
            archive[archivePath] = new Uint8Array(await readFile(path));
        }
    }
}

const [manifest, packageJson, packageLock] = await Promise.all([
    readJson(join(projectRoot, "manifest.json")),
    readJson(join(projectRoot, "package.json")),
    readJson(join(projectRoot, "package-lock.json")),
]);
const versions = [
    manifest.version,
    packageJson.version,
    packageLock.version,
    packageLock.packages[""].version,
];
if (!versions.every((version) => version === manifest.version)) {
    throw new Error(`Version mismatch: ${versions.join(", ")}`);
}

const archive = {};
for (const fileName of runtimeFiles) {
    archive[fileName] = new Uint8Array(
        await readFile(join(projectRoot, fileName)),
    );
}
await addDirectory(archive, join(projectRoot, generatedAssets));

const artifactName = ankiWebBuild
    ? `AnkiCode-v${manifest.version}-ankiweb.ankiaddon`
    : `AnkiCode-v${manifest.version}.ankiaddon`;
const artifactPath = join(projectRoot, artifactName);
const data = zipSync(archive, {
    level: 9,
    mtime: new Date(1980, 0, 1),
});
await writeFile(artifactPath, data);
console.log(`Created ${basename(artifactPath)}`);
