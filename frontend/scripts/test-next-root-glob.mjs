import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import path from "node:path";

const require = createRequire(import.meta.url);
const configRequire = createRequire(require.resolve("eslint-config-next"));
const pluginEntry = configRequire.resolve("@next/eslint-plugin-next");
const pluginRequire = createRequire(pluginEntry);
const { getRootDirs } = pluginRequire(path.join(path.dirname(pluginEntry), "utils/get-root-dirs.js"));
const selectedGlob = pluginRequire("fast-glob");
assert.equal(typeof selectedGlob.globSync, "function");
assert.match(pluginRequire.resolve("fast-glob").replaceAll("\\", "/"), /\/tinyglobby\//);
assert.doesNotMatch(readFileSync(new URL("../pnpm-lock.yaml", import.meta.url), "utf8"), /^ {2}braces@/m);

const temporaryParent = path.resolve(tmpdir());
const fixture = mkdtempSync(path.join(temporaryParent, "angmoo-next-glob-"));
const portable = (value) => path.resolve(value).replaceAll("\\", "/");
const roots = ["alpha", "beta"].map((name) => path.join(fixture, "packages", name));
try {
  for (const root of roots) {
    mkdirSync(path.join(root, "pages"), { recursive: true });
    writeFileSync(path.join(root, "pages", "about.js"), "export default function Page() {}\n");
  }
  mkdirSync(path.join(fixture, "packages", ".hidden"), { recursive: true });
  writeFileSync(path.join(fixture, "packages", "not-a-directory"), "synthetic fixture\n");
  const context = (rootDir) => ({ cwd: fixture, getCwd: () => fixture, settings: { next: { rootDir } } });
  const normalized = (values) => values.map(portable).sort();
  assert.deepEqual(getRootDirs(context(undefined)), [fixture]);
  assert.deepEqual(normalized(getRootDirs(context(path.join(fixture, "packages", "*")))), normalized(roots));
  assert.deepEqual(normalized(getRootDirs(context(path.join(fixture, "packages", "{alpha,beta}")))), normalized(roots));
  assert.deepEqual(normalized(getRootDirs(context(roots))), normalized(roots));
  assert.deepEqual(getRootDirs(context(path.join(fixture, "missing", "*"))), []);

  const { Linter } = require("eslint");
  const plugin = configRequire("@next/eslint-plugin-next");
  const ruleId = "@next/next/no-html-link-for-pages";
  const linter = new Linter();
  const configuration = [{
    languageOptions: { parserOptions: { ecmaFeatures: { jsx: true } } },
    plugins: { "@next/next": plugin },
    settings: { next: { rootDir: path.join(fixture, "packages", "*") } },
    rules: { [ruleId]: "error" },
  }];
  const invalid = linter.verify('const page = <a href="/about">About</a>;', configuration);
  assert.equal(invalid.length, 1);
  assert.equal(invalid[0].ruleId, ruleId);
  assert.equal(invalid[0].fatal, undefined);
  assert.equal(linter.verify('const page = <Link href="/about">About</Link>;', configuration).length, 0);
  assert.equal(linter.verify('const page = <a href="https://example.invalid/about">About</a>;', configuration).length, 0);
  console.log("Pinned Next glob directory discovery and active internal-link rule passed.");
} finally {
  const target = path.resolve(fixture);
  assert.equal(path.dirname(target), temporaryParent);
  assert.ok(path.basename(target).startsWith("angmoo-next-glob-"));
  rmSync(target, { recursive: true, force: true });
}
