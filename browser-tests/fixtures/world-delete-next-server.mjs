// Run the actual compiled standalone server in a fresh, owned browser fixture.
// Windows traces can contain file-typed directory links, so this source-level
// UI test uses the checkout's real dependencies. This is not a packaging test.
import { cpSync, copyFileSync, existsSync, mkdirSync, readdirSync, symlinkSync } from "node:fs";
import { randomUUID } from "node:crypto";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const repo = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const frontend = join(repo, "frontend");
const distName = ".next-world-delete-dialog-prod";
const dist = join(frontend, distName);
const standaloneServer = join(dist, "standalone", "frontend", "server.js");
if (!existsSync(standaloneServer)) throw new Error("Build the isolated World deletion Next fixture first.");
const destination = join(repo, "artifacts", "world-delete-dialog-20261013", `next-runtime-${randomUUID()}`);
const product = join(destination, "frontend");
const output = join(product, distName);
mkdirSync(output, { recursive: true });
copyFileSync(standaloneServer, join(product, "server.js"));
for (const directory of ["server", "static"]) cpSync(join(dist, directory), join(output, directory), { recursive: true });
for (const file of readdirSync(dist, { withFileTypes: true })) {
  if (file.isFile()) copyFileSync(join(dist, file.name), join(output, file.name));
}
cpSync(join(frontend, "public"), join(product, "public"), { recursive: true });
mkdirSync(join(destination, "docs"));
for (const file of ["agent_guide.md", "agent_guide.en.md"]) copyFileSync(join(repo, "docs", file), join(destination, "docs", file));
symlinkSync(join(frontend, "node_modules"), join(product, "node_modules"), process.platform === "win32" ? "junction" : "dir");
await import(pathToFileURL(join(product, "server.js")).href);
