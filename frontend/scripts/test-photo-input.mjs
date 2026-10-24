import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const root = fileURLToPath(new URL("../src/", import.meta.url));
const modules = new Map();
let decode = async blob => ({ width: 10, height: 10, close() {}, blob });
const context = vm.createContext({ console, ArrayBuffer, Uint8Array, Blob, File, DOMException,
  AbortController, performance, setTimeout, clearTimeout, btoa,
  createImageBitmap: (...args) => decode(...args) });
function load(relative) {
  const filename = path.resolve(root, relative);
  if (modules.has(filename)) return modules.get(filename).exports;
  const loaded = { exports: {} }; modules.set(filename, loaded);
  const code = ts.transpileModule(fs.readFileSync(filename, "utf8"), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  }}).outputText;
  const require = spec => load((spec.startsWith("@/") ? spec.slice(2) : path.relative(root, path.resolve(path.dirname(filename), spec))) + ".ts");
  vm.runInContext(`(function(module,exports,require){${code}\n})`, context, { filename })(loaded, loaded.exports, require);
  return loaded.exports;
}
const { readFileInput, withFileInputDeadline, FileInputError } = load("lib/media/read-file-input.ts");
function input(chunks, { type = "image/png", readError, cancelError = false, hang = false } = {}) {
  const state = { reads: 0, streams: 0, cancelled: 0, released: 0, ended: false };
  const file = {
    get size() { throw Error("External size accessed"); },
    get lastModified() { throw Error("External timestamp accessed"); },
    get name() { assert.ok(state.ended); return "original.png"; },
    get type() { assert.ok(state.ended); return type; },
    arrayBuffer() { throw Error("Unbounded external read"); },
    slice() { throw Error("External slice"); },
    stream() { state.streams++; return { getReader() { return {
      async read() {
        state.reads++;
        if (hang) return new Promise(() => {});
        if (readError) throw readError;
        if (chunks.length) return { value: chunks.shift(), done: false };
        state.ended = true; return { done: true };
      },
      cancel() { state.cancelled++; return cancelError ? Promise.reject(Error("cleanup")) : Promise.resolve(); },
      releaseLock() { state.released++; },
    }; } }; },
  };
  return { file, state };
}
const read = (file, max, signal = new AbortController().signal, timeout = 1000) =>
  withFileInputDeadline(signal, timeout, scope => readFileInput(file, max, scope));
const isCode = code => error => error instanceof FileInputError && error.code === code;
let cases = 0;
for (const max of [5 * 1048576, 10 * 1048576, 20 * 1048576, 6_000_000]) {
  for (const delta of [-1, 0, 1]) {
    const bytes = new Uint8Array(max + delta).fill(91);
    const {file, state} = input(Array.from({length: Math.ceil(bytes.length / 65536)}, (_, i) => bytes.subarray(i * 65536, (i + 1) * 65536)));
    if (delta > 0) { await assert.rejects(read(file, max), isCode("size")); assert.equal(state.cancelled, 1); }
    else { const actual = new Uint8Array(await read(file, max)); assert.deepEqual(actual, bytes); assert.equal(state.cancelled, 0); }
    assert.equal(state.streams, 1); assert.ok(state.released); cases++;
  }
}
const tiny = input(Array.from({ length: 4097 }, (_, i) => new Uint8Array([i % 256])));
assert.deepEqual(new Uint8Array(await read(tiny.file, 5000)), Uint8Array.from({length:4097}, (_, i) => i % 256)); cases++;
const empty = input([]); assert.equal((await read(empty.file, 100)).byteLength, 0); cases++;
const failed = input([], { readError: new DOMException("changed", "NotReadableError"), cancelError: true });
await assert.rejects(read(failed.file, 100), isCode("read")); assert.equal(failed.state.cancelled, 1); cases++;
const stalled = input([], { hang: true, cancelError: true });
await assert.rejects(read(stalled.file, 100, undefined, 10), isCode("timeout")); assert.equal(stalled.state.cancelled, 1); cases++;
const aborted = new AbortController(); aborted.abort(); const untouched = input([]);
await assert.rejects(read(untouched.file, 100, aborted.signal), { name: "AbortError" }); assert.equal(untouched.state.streams, 0); cases++;
const cancel = new AbortController(), waiting = input([], { hang: true });
const pending = read(waiting.file, 100, cancel.signal); cancel.abort();
await assert.rejects(pending, { name: "AbortError" }); assert.equal(waiting.state.cancelled, 1); cases++;
let closeCount = 0;
await assert.rejects(withFileInputDeadline(new AbortController().signal, 5, scope => scope.wait(
  new Promise(resolve => setTimeout(() => resolve({ close() { closeCount++; } }), 20)), image => image.close())), isCode("timeout"));
await new Promise(resolve => setTimeout(resolve, 25)); assert.equal(closeCount, 1); cases++;
// Reading does not grant a second deadline to decoding.
await assert.rejects(withFileInputDeadline(new AbortController().signal, 25, async scope => {
  await scope.wait(new Promise(resolve => setTimeout(resolve, 18)));
  await scope.wait(new Promise(resolve => setTimeout(resolve, 18)));
}), isCode("timeout")); cases++;
for (const [source, exported] of [["characters/controllers/prepare-profile-media", "prepareProfileMedia"], ["worlds/controllers/prepare-world-image", "prepareWorldImage"]]) {
  const prepare = load(`features/${source}.ts`)[exported];
  const selected = input([Uint8Array.of(1,2,3)]);
  decode = async blob => { assert.ok(blob instanceof Blob); assert.equal(blob.size, 3); return { close() {} }; };
  const bitmap = await prepare(selected.file, new AbortController().signal); bitmap.close(); assert.equal(selected.state.streams, 1);
  await assert.rejects(prepare(input([Uint8Array.of(1)], {type:"image/heic"}).file, new AbortController().signal), e => e.code === "format");
  let release; let closed = 0; decode = () => new Promise(resolve => { release = () => resolve({ close() { closed++; } }); });
  const controller = new AbortController(); const preparing = prepare(input([Uint8Array.of(1)]).file, controller.signal);
  while (!release) await new Promise(resolve => setTimeout(resolve, 0)); controller.abort();
  await assert.rejects(preparing, { name: "AbortError" }); release(); await new Promise(resolve => setTimeout(resolve, 0)); assert.equal(closed, 1); cases += 3;
}
const {prepareCardInput} = load("features/characters/controllers/prepare-card-input.ts");
for (const bytes of [Buffer.from('PNG\x00chara\x00unchanged-metadata'), Buffer.from('{"name":"原文","data":{}}')]) {
  const selected = input([new Uint8Array(bytes)]);
  assert.deepEqual(Buffer.from(await prepareCardInput(selected.file, new AbortController().signal), "base64"), bytes); assert.equal(selected.state.streams, 1); cases++;
}
const {prepareSeedImage} = load("features/characters/controllers/prepare-seed-image.ts");
const seed = input([Uint8Array.of(4,5,6)]); const payload = await prepareSeedImage(seed.file, new AbortController().signal);
assert.equal(payload.data_base64, "BAUG"); assert.equal(payload.filename, "original.png"); cases++;
console.log(`PASS ${cases} bounded input, deadline, cleanup, owned decoding and raw transport cases`);
