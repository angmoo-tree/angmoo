import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(fileURLToPath(new URL("..", import.meta.url)));
const outputRoot = join(frontendRoot, "out");
const portIndex = process.argv.indexOf("--port");
const port = Number(portIndex >= 0 ? process.argv[portIndex + 1] : "3200");
if (!Number.isInteger(port) || port < 1 || port > 65535) {
  throw new Error("Static preview port must be between 1 and 65535.");
}
if (!existsSync(join(outputRoot, "index.html"))) {
  throw new Error("Run pnpm build:static before starting the static preview.");
}

const contentTypes = new Map([
  [".css", "text/css; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".ico", "image/x-icon"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".png", "image/png"],
  [".svg", "image/svg+xml"],
  [".txt", "text/plain; charset=utf-8"],
]);

createServer((request, response) => {
  let pathname;
  try {
    pathname = decodeURIComponent(
      new URL(request.url ?? "/", "http://127.0.0.1").pathname,
    );
  } catch {
    response.writeHead(400).end("invalid path");
    return;
  }
  const relative = normalize(pathname).replace(/^[/\\]+/, "");
  let target = resolve(outputRoot, relative || "index.html");
  if (
    !target.startsWith(`${resolve(outputRoot)}${sep}`) &&
    target !== resolve(outputRoot)
  ) {
    response.writeHead(400).end("invalid path");
    return;
  }
  if (existsSync(target) && statSync(target).isDirectory()) {
    target = join(target, "index.html");
  }
  if (!existsSync(target) || !statSync(target).isFile()) {
    target = join(outputRoot, "404.html");
  }
  response.setHeader("Cache-Control", "no-store");
  response.setHeader(
    "Content-Type",
    contentTypes.get(extname(target)) ?? "application/octet-stream",
  );
  createReadStream(target).pipe(response);
}).listen(port, "127.0.0.1", () => {
  console.log(`Angmoo static preview listening on http://127.0.0.1:${port}`);
});
