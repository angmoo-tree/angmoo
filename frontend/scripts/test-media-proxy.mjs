import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";
import { createServer } from "node:http";
import { once } from "node:events";

const context = vm.createContext({process, fetch, Request, Response, Headers, URL, Error, Set});
function load(file, require = () => { throw new Error("unexpected import"); }) {
  const source = fs.readFileSync(new URL(file, import.meta.url), "utf8");
  const code = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText;
  const loaded = {exports: {}};
  vm.runInContext(`(function(module,exports,require){${code}\n})`, context)(loaded, loaded.exports, require);
  return loaded.exports;
}
const backend = load("../src/lib/server/backend.ts");
const {proxyMedia} = load("../src/lib/server/media.ts", name => {
  assert.equal(name, "./backend"); return backend;
});
const seen = [];
let aborted = false;
const servers = await Promise.all([1, 2].map(async id => {
  const server = createServer((request, response) => {
    seen.push({id, path:request.url, method:request.method, headers:request.headers});
    if (request.url.includes("stream")) {
      response.writeHead(200, {"content-type":"image/png"});
      response.write("start");
      request.on("close", () => { aborted = true; });
      return;
    }
    if (request.url.includes("redirect")) {
      response.writeHead(302, {location:"https://example.invalid/private"}); response.end(); return;
    }
    response.writeHead(request.url.includes("missing") ? 404 : request.headers.range ? 206 : 200,
      {"content-type":"image/png", "content-range":"bytes 0-2/6", "accept-ranges":"bytes", "cache-control":"private, no-store", "x-private-info":"hidden", "set-cookie":"secret=hidden; HttpOnly; Secure; SameSite=Strict"});
    response.end(`id${id}`);
  });
  server.listen(0, "127.0.0.1"); await once(server,"listening"); return server;
}));
const original = process.env.ANGMOO_API_BASE_URL;
try {
  // The same loaded modules must use each runtime upstream without rebuilding.
  for (const [i, server] of servers.entries()) {
    process.env.ANGMOO_API_BASE_URL = `http://127.0.0.1:${server.address().port}`;
    const response = await proxyMedia(new Request("http://localhost/media/worlds/a/banner/x.png?size=1", {
      headers: {cookie:"unrelated=secret; angmoo_browser_session=session", authorization:"secret", range:"bytes=0-2", "x-world-package-download-token":"secret"}
    }), ["worlds","a","banner","x.png"]);
    assert.equal(response.status,206); assert.equal(await response.text(),`id${i+1}`);
    assert.equal(response.headers.get("cache-control"),"private, no-store");
    assert.equal(response.headers.get("content-range"),"bytes 0-2/6");
    assert.equal(response.headers.get("set-cookie"),null); assert.equal(response.headers.get("x-private-info"),null);
    const last = seen.at(-1);
    assert.equal(last.headers.cookie,"angmoo_browser_session=session"); assert.equal(last.headers.authorization,undefined);
    assert.equal(last.headers["x-world-package-download-token"],undefined);
    assert.equal(last.path,"/media/worlds/a/banner/x.png?size=1");
  }
  for (const path of [[".."], ["%2e%2e"], ["a/b"], ["a\\b"], [""], []]) {
    const count = seen.length;
    assert.equal((await proxyMedia(new Request("http://localhost/media/x"),path)).status,400);
    assert.equal(seen.length,count);
  }
  assert.equal((await proxyMedia(new Request("http://localhost/media/missing"),["missing"])).status,404);
  assert.equal((await proxyMedia(new Request("http://localhost/media/redirect"),["redirect"])).status,502);
  const head = await proxyMedia(new Request("http://localhost/media/image",{method:"HEAD"}),["image"]);
  assert.equal(head.body,null); assert.equal(seen.at(-1).method,"HEAD");
  const controller = new AbortController();
  const stream = await proxyMedia(new Request("http://localhost/media/stream",{signal:controller.signal}),["stream"]);
  const reader = stream.body.getReader(); await reader.read(); controller.abort();
  await assert.rejects(reader.read());
  for (let n=0;n<20 && !aborted;n++) await new Promise(r=>setTimeout(r,25));
  assert.ok(aborted);
  for (const url of ["file:///etc", "http://user:pass@localhost", "http://localhost/private", "http://localhost?url=evil"]) {
    process.env.ANGMOO_API_BASE_URL=url; assert.throws(()=>backend.getBackendBaseUrl(),/backend_upstream_invalid/);
  }
  console.log("Runtime media: two upstreams, private cookies, Range/HEAD/404, path refusal and abort passed.");
} finally {
  if (original === undefined) delete process.env.ANGMOO_API_BASE_URL; else process.env.ANGMOO_API_BASE_URL=original;
  await Promise.all(servers.map(server=>new Promise(resolve=>{ server.close(resolve); server.closeAllConnections(); })));
}
