import { readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const version = (process.argv[2] || "").replace(/^v/, "");
if (!/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(version)) {
    throw new Error(`Invalid release version: ${process.argv[2] || "(empty)"}`);
}

async function readJson(fileName) {
    return JSON.parse(await readFile(join(projectRoot, fileName), "utf8"));
}

async function writeJson(fileName, value, spaces) {
    await writeFile(
        join(projectRoot, fileName),
        `${JSON.stringify(value, null, spaces)}\n`,
    );
}

const [manifest, packageJson, packageLock] = await Promise.all([
    readJson("manifest.json"),
    readJson("package.json"),
    readJson("package-lock.json"),
]);
manifest.version = version;
packageJson.version = version;
packageLock.version = version;
packageLock.packages[""].version = version;

await Promise.all([
    writeJson("manifest.json", manifest, 4),
    writeJson("package.json", packageJson, 2),
    writeJson("package-lock.json", packageLock, 2),
]);
console.log(`Set release version to ${version}`);
