import { cpSync, existsSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const standaloneRoot = join(frontendRoot, ".next", "standalone");
const server = join(standaloneRoot, "server.js");
const sourceStatic = join(frontendRoot, ".next", "static");
const targetStatic = join(standaloneRoot, ".next", "static");
const sourcePublic = join(frontendRoot, "public");
const targetPublic = join(standaloneRoot, "public");
const portIndex = process.argv.indexOf("--port");
const port = Number(portIndex >= 0 ? process.argv[portIndex + 1] : "3300");

if (!Number.isInteger(port) || port < 1 || port > 65535) {
  throw new Error("Production preview port must be between 1 and 65535.");
}
if (!existsSync(server) || !existsSync(sourceStatic)) {
  throw new Error("Run pnpm build before starting the production preview.");
}

const isWindows = process.platform === "win32";
if (!isWindows) {
  rmSync(targetStatic, { force: true, recursive: true });
  cpSync(sourceStatic, targetStatic, { recursive: true });
  rmSync(targetPublic, { force: true, recursive: true });
  cpSync(sourcePublic, targetPublic, { recursive: true });
  cpSync(join(frontendRoot, "src", "app", "icon.svg"), join(targetPublic, "icon.svg"));
}

// Next's traced standalone tree contains POSIX symlinks that cannot always be
// dereferenced from a Windows checkout. Canonical Ubuntu visual runs use the
// standalone server; Windows developer runs use the same production build via
// `next start` as a platform-only launcher fallback.
const nextCli = join(frontendRoot, "node_modules", "next", "dist", "bin", "next");
const child = spawn(
  process.execPath,
  isWindows ? [nextCli, "start", "--hostname", "127.0.0.1", "--port", String(port)] : [server],
  {
  cwd: isWindows ? frontendRoot : standaloneRoot,
  env: {
    ...process.env,
    HOSTNAME: "127.0.0.1",
    PORT: String(port),
  },
  stdio: "inherit",
  },
);

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => child.kill(signal));
}

child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 1);
});
