import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const shellRoot = join(frontendRoot, "static-shell");
const shellOutput = join(shellRoot, "out");
const productOutput = join(frontendRoot, "out");
const nextCli = join(frontendRoot, "node_modules", "next", "dist", "bin", "next");

const build = spawnSync(process.execPath, [nextCli, "build", shellRoot], {
  cwd: frontendRoot,
  env: {
    ...process.env,
    NEXT_PUBLIC_ANGMOO_FRONTEND_PROFILE: "tauri-static",
  },
  stdio: "inherit",
});
if (build.status !== 0) process.exit(build.status ?? 1);
if (!existsSync(shellOutput)) throw new Error("Next static shell output was not created.");

rmSync(productOutput, { force: true, recursive: true });
mkdirSync(productOutput, { recursive: true });
cpSync(shellOutput, productOutput, { recursive: true });

// The Tauri asset protocol and static preview server both use this document
// when a dynamic product URL has no physical HTML file. The client router then
// resolves the real World, Character, or Post identifier from location.pathname.
cpSync(join(productOutput, "index.html"), join(productOutput, "404.html"));

const publicRoot = join(frontendRoot, "public");
for (const asset of [
  "favicon.ico",
  "openapi.json",
  "pwa-icon-192.png",
  "pwa-icon-512.png",
  "pwa-maskable-512.png",
]) {
  cpSync(join(publicRoot, asset), join(productOutput, asset));
}
cpSync(join(frontendRoot, "src", "app", "icon.svg"), join(productOutput, "icon.svg"));

console.log(`Angmoo Tauri static shell exported to ${productOutput}`);
