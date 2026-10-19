import { createServer } from "node:http";
import { createReadStream, existsSync } from "node:fs";
import { resolve, extname, sep } from "node:path";
const root = resolve("../frontend/static-shell/out");
const mime = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml" };
createServer((req, res) => {
  const path = resolve(root, "." + new URL(req.url, "http://localhost").pathname);
  if (path !== root && !path.startsWith(root + sep)) return res.writeHead(400).end();
  const file = extname(path) && existsSync(path) ? path : resolve(root, "index.html");
  res.setHeader("Content-Type", mime[extname(file)] ?? "application/octet-stream");
  res.setHeader("Cache-Control", "no-store");
  createReadStream(file).pipe(res);
}).listen(3491, "127.0.0.1");
