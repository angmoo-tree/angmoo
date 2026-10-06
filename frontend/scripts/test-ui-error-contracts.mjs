// Exercise shipped adapters and rendered fields, with synthetic responses only.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const root = fileURLToPath(new URL("../src/", import.meta.url));
const nativeRequire = createRequire(import.meta.url);
const { I18nextProvider } = nativeRequire("react-i18next");
let calls = 0, readFails = false;
let runtimeFetch = async () => new Response("{}", { status: 200 });
class SyntheticFileReader {
  readAsDataURL() {
    if (readFails) this.onerror();
    else { this.result = "data:image/png;base64,c3ludGhldGlj"; this.onload(); }
  }
}
const context = vm.createContext({ console, process, FormData, File, Headers, Response, URL, Date, Intl,
  AbortController, FileReader: SyntheticFileReader, crypto: { randomUUID: () => "synthetic-only" } });
const modules = new Map();
function load(filename) {
  if (modules.has(filename)) return modules.get(filename).exports;
  const loaded = { exports: {} }; modules.set(filename, loaded);
  if (filename.endsWith(".json")) { loaded.exports = JSON.parse(fs.readFileSync(filename, "utf8")); return loaded.exports; }
  if (filename.endsWith(".css")) { loaded.exports = new Proxy({}, { get: (_target, key) => String(key) }); return loaded.exports; }
  const code = ts.transpileModule(fs.readFileSync(filename, "utf8"), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
  } }).outputText;
  const require = spec => {
    if (spec === "@/lib/runtime/runtime-config") return { runtimeFetch: (...args) => { calls++; return runtimeFetch(...args); } };
    if (!spec.startsWith("@/") && !spec.startsWith(".")) return nativeRequire(spec);
    const base = spec.startsWith("@/") ? path.join(root, spec.slice(2)) : path.resolve(path.dirname(filename), spec);
    const resolved = [base, base + ".ts", base + ".tsx", base + ".json"].find(file => fs.existsSync(file) && fs.statSync(file).isFile());
    assert.ok(resolved, spec); return load(resolved);
  };
  vm.runInContext(`(function(module,exports,require){${code}\n})`, context, { filename })(loaded, loaded.exports, require);
  return loaded.exports;
}
const source = name => load(path.join(root, name));
const { createUiI18n } = source("lib/i18n/instance.ts");
const { uiResources } = source("composition/providers/ui-resources.ts");
const { ApiRequestError } = source("lib/http/error-contract.ts");
const { personaLengthError, personaTextLength } = source("features/characters/utils/persona-limits.ts");
const { PersonaField } = source("features/characters/components/persona-field.tsx");
const { uploadImage, ImageUploadInputError } = source("features/media/api/media-client.ts");
const { stageWorldPackageImport, WorldPackageApiError } = source("features/world-packages/api/world-package-client.ts");
const { formatWorldPackageFailure } = source("features/world-packages/utils/error-presentation.ts");
let passed = 0;
const check = async (name, action) => { await action(); passed++; console.log(`PASS ${name}`); };

await check("Unicode limits use NFC codepoints, never truncate original input", () => {
  assert.equal(personaTextLength("e\u0301😀"), 2);
  assert.equal(personaLengthError("e\u0301😀", 2), undefined);
  const error = personaLengthError("e\u0301😀A", 2);
  assert.equal(error.code, "persona_length_exceeded"); assert.equal(error.limit, 2); assert.equal(error.excess, 1);
});

for (const language of ["ko", "en"]) {
  const i18n = createUiI18n(uiResources, language);
  const text = ns => (key, params = {}) => {
    assert.ok(i18n.exists(key, { ns: [ns, "shell"] }), `missing ${language}:${ns}:${key}`);
    return String(i18n.t(key, { ...params, ns: [ns, "shell"] }));
  };
  const number = new Intl.NumberFormat(language).format;
  await check(`${language}: rendered PersonaField alert, ARIA association and exact excess`, () => {
    const html = renderToStaticMarkup(React.createElement(I18nextProvider, { i18n },
      React.createElement(PersonaField, { label: "Original 原文", value: "😀".repeat(1001), limit: 1000 })));
    assert.ok(html.includes('aria-invalid="true"') && html.includes('role="alert"') && html.includes("1,001"));
    assert.ok(html.includes(language === "en" ? "You are 1 over the limit." : "현재 1자 초과했습니다."));
    if (language === "en") assert.ok(!/[가-힣]/.test(html));
    assert.ok(html.includes("Original 原文"));
  });
  const cases = [
    ["handle", "string_pattern_mismatch", "handle_format_invalid", {}],
    ["activity_interval_minutes", "greater_than_equal", "activity_interval_too_small", { minimum: 30 }],
    ["activity_interval_minutes", "less_than_equal", "activity_interval_too_large", { maximum: 1440 }],
    ["activity_interval_minutes", "int_parsing", "activity_interval_invalid", {}],
    ["max_comments_per_day", "less_than_equal", "reply_limit_invalid", { minimum: 0, maximum: 60 }],
    ["max_posts_per_day", "less_than_equal", "post_limit_invalid", { minimum: 0, maximum: 30 }],
  ];
  for (const feature of ["identity", "characters", "social"]) {
    const { apiRequest } = source(`features/${feature}/api/request.ts`);
    for (const [field, type, code, params] of cases) await check(`${language}:${feature}:${code}`, async () => {
      runtimeFetch = async () => new Response(JSON.stringify({ detail: [{ loc: ["body", field], type,
        msg: "PRIVATE uploaded text", input: "PRIVATE credential" }] }), { status: 422, headers: { "Retry-After": "60" } });
      await assert.rejects(apiRequest("/synthetic"), error => {
        assert.ok(error instanceof ApiRequestError); assert.equal(error.status, 422); assert.equal(error.code, code);
        assert.equal(error.retryAfter, "60"); assert.equal(JSON.stringify(error.params), JSON.stringify(params));
        const display = text(feature)(error.message);
        assert.ok(!display.includes("PRIVATE")); assert.ok(language === "en" ? !/[가-힣]/.test(display) : /[가-힣]/.test(display));
        return true;
      });
    });
  }
  for (const [file, code] of [[new File(["x"], "unsupported.gif", { type: "image/gif" }), "image_file_unsupported"],
    [new File([new Uint8Array(10 * 1024 * 1024 + 1)], "large.png", { type: "image/png" }), "image_file_unsupported"],
    [new File(["x"], "read-error.png", { type: "image/png" }), "image_file_read_failed"]]) {
    await check(`${language}: image preflight ${file.name} sends no request`, async () => {
      const before = calls; readFails = code === "image_file_read_failed";
      await assert.rejects(uploadImage(file, "world", "synthetic"), error => {
        assert.ok(error instanceof ImageUploadInputError); assert.equal(error.code, code);
        const display = text("media")(error.message);
        assert.ok(language === "en" ? !/[가-힣]/.test(display) : /[가-힣]/.test(display)); return true;
      });
      assert.equal(calls, before); readFails = false;
    });
  }
  await check(`${language}: World Package retains status/code/lengths, strips private fields`, async () => {
    runtimeFetch = async () => new Response(JSON.stringify({ detail: { code: "world_package_persona_invalid", raw: "PRIVATE",
      fields: [{ field: "personality", actual: 6001, limit: 6000, input: "PRIVATE" },
        { field: "secret", actual: 99, limit: 1 }, { field: "speech_style", actual: -1, limit: 6000 }] } }), { status: 422 });
    await assert.rejects(stageWorldPackageImport(new File(["synthetic"], "fixture.angmoo-world")), error => {
      assert.ok(error instanceof WorldPackageApiError); assert.equal(error.status, 422); assert.equal(error.code, "world_package_persona_invalid");
      assert.equal(error.fields.length, 1); assert.ok(!JSON.stringify(error).includes("PRIVATE"));
      const display = formatWorldPackageFailure({ kind: "request", reason: error }, "import", text("world-packages"), number);
      assert.ok(display.includes("6,001 / 6,000")); assert.ok(!display.includes("world_package_") && !display.includes("PRIVATE"));
      assert.ok(display.includes(language === "en" ? "Personality" : "성격")); return true;
    });
  });
  const backendCodes = fs.readFileSync(new URL("../../backend/app/domains/world_packages/exceptions.py", import.meta.url), "utf8")
    .match(/world_package_[a-z_]+/g);
  await check(`${language}: all backend reason codes have explanations`, () => {
    for (const code of new Set(backendCodes)) {
      const display = formatWorldPackageFailure({ kind: "request", reason: new WorldPackageApiError(422, { code }) }, "import", text("world-packages"), number);
      assert.ok(!display.includes("world_package_") && !display.includes("could not be imported"));
      assert.ok(language === "en" ? !/[가-힣]/.test(display) : /[가-힣]/.test(display));
    }
    const fields = ["one_liner", "personality", "speech_style", "worldview", "character_background", "topic_preferences", "safety_rules", "persona_summary"];
    const reason = new WorldPackageApiError(422, { code: "world_package_persona_invalid",
      fields: fields.map(field => ({field, limit: 8000, actual: 8001})) });
    assert.equal(reason.fields.length, fields.length);
    const display = formatWorldPackageFailure({kind: "request", reason}, "import", text("world-packages"), number);
    assert.ok(display.includes(language === "en" ? "Character background / worldview" : "캐릭터 배경·세계관"));
  });
  for (const operation of ["import", "export"]) await check(`${language}: safe ${operation} fallback and server errors`, () => {
    for (const reason of [new Error("PRIVATE credential"), new WorldPackageApiError(422, "PRIVATE credential"),
      new WorldPackageApiError(503, { code: "world_package_preparation_failed", text: "PRIVATE credential" })]) {
      const display = formatWorldPackageFailure({ kind: "request", reason }, operation, text("world-packages"), number);
      assert.ok(!display.includes("PRIVATE") && !display.includes("world_package_"));
      if (language === "en") { assert.ok(!/[가-힣]/.test(display)); assert.ok(display.includes(operation)); }
      else assert.ok(display.includes(operation === "import" ? "가져오" : "내보내"));
    }
  });
}
console.log(`UI error contracts PASS: ${passed} checks; rendered fields, typed feature validation, image preflight and World Package messages in both languages. No external calls.`);
