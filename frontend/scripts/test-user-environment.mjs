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
const {I18nextProvider} = nativeRequire("react-i18next");
const storage = () => {
  const values = new Map();
  return { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, String(value)), removeItem: key => values.delete(key) };
};
const events = [];
const browser = { sessionStorage: storage(), localStorage: storage(), dispatchEvent: event => events.push(event.type) };
let runtimeFetch = async () => new Response("{}", {status: 200});
const context = vm.createContext({ console, window: browser, Event, FormData, File, Headers, Response, URL,
  Date, AbortController, navigator: { languages: ["ja-JP"], language: "ja-JP" }, Intl, process });
const modules = new Map();
function load(filename) {
  if (modules.has(filename)) return modules.get(filename).exports;
  const loaded = {exports: {}}; modules.set(filename, loaded);
  if (filename.endsWith(".json")) { loaded.exports = JSON.parse(fs.readFileSync(filename, "utf8")); return loaded.exports; }
  const code = ts.transpileModule(fs.readFileSync(filename, "utf8"), {compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
  }}).outputText;
  const require = spec => {
    if (spec === "@/lib/runtime/runtime-config") return {runtimeFetch: (...args) => runtimeFetch(...args)};
    if (!spec.startsWith("@/") && !spec.startsWith(".")) return nativeRequire(spec);
    const base = spec.startsWith("@/") ? path.join(root, spec.slice(2)) : path.resolve(path.dirname(filename), spec);
    const resolved = [base, base + ".ts", base + ".tsx", base + ".json"].find(value => fs.existsSync(value) && fs.statSync(value).isFile());
    assert.ok(resolved, spec); return load(resolved);
  };
  vm.runInContext(`(function(module,exports,require){${code}\n})`, context, {filename})(loaded, loaded.exports, require);
  return loaded.exports;
}
const source = name => load(path.join(root, name));
const {createUiI18n, resolveUiLanguage} = source("lib/i18n/instance.ts");
const {uiResources} = source("composition/providers/ui-resources.ts");
const {useUiText} = source("hooks/use-ui-text.ts");
const {formatDate, parseApiInstant} = source("utils/profile-presentation.ts");

for (const [saved, detected, expected] of [["ko","ar-AE","ko"],["en","ko-KR","en"],[null,"ko-KR","ko"],[null,"ja-JP","en"],[null,undefined,"en"]]) {
  assert.equal(resolveUiLanguage(saved, detected), expected);
}
const ko = createUiI18n(uiResources, "ko"), en = createUiI18n(uiResources, "en");
assert.notEqual(ko, en);
assert.equal(en.t("홈", {ns: "shell"}), "Home");
assert.equal(ko.t("홈", {ns: "shell"}), "홈");
await ko.changeLanguage("en"); assert.equal(en.language, "en");
await ko.changeLanguage("ko"); assert.equal(en.language, "en");
assert.equal(en.t("근거 {{count}}개 보기", {ns: "chat", count: 1}), "View 1 evidence item");
assert.equal(en.t("근거 {{count}}개 보기", {ns: "chat", count: 2}), "View 2 evidence items");
assert.equal(ko.t("근거 {{count}}개 보기", {ns: "chat", count: 2}), "근거 2개 보기");
assert.equal(en.t("{{name}}(으)로 대화", {ns: "chat", name: "原文 A-17"}), "Chatting as 原文 A-17");
assert.equal(en.t("{{name}}에게 보낼 메시지", {ns: "chat", name: "原文 A-17"}), "Message to 原文 A-17");
function Message() { const text = useUiText("characters"); return React.createElement("p", null, text("휴식 · {{time}}", {time: "<script>原文 A-17</script>"})); }
const rendered = renderToStaticMarkup(React.createElement(I18nextProvider, {i18n: en}, React.createElement(Message)));
assert.ok(rendered.includes("&lt;script&gt;原文 A-17&lt;/script&gt;")); assert.ok(!rendered.includes("<script>"));
for (const zone of ["Asia/Seoul","America/New_York","Europe/London","Asia/Tokyo"]) {
  for (const locale of ["ko","en"]) {
    const utc = "2026-03-08T07:00:00Z";
    const expected = new Intl.DateTimeFormat(locale, {timeZone: zone, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23"}).format(new Date(utc));
    assert.equal(formatDate(utc, zone, locale), expected);
    assert.equal(formatDate(utc.slice(0,-1), zone, locale), expected);
    assert.equal(parseApiInstant(utc).toISOString(), utc.replace("Z", ".000Z"));
  }
}
const detect = source("lib/i18n/detection.ts").detectUserEnvironment;
assert.equal(detect().preferred_language, "ja-JP");
context.navigator = new Proxy({}, {get() {throw new Error("detector unavailable");}});
context.Intl = {DateTimeFormat() {throw new Error("zone unavailable");}};
assert.equal(detect().preferred_language, null); assert.equal(detect().timezone, null);
context.Intl = Intl;

const auth = source("lib/auth/browser-session.ts"), {apiRequest} = source("lib/http/api-request.ts");
const {ApiRequestError} = source("lib/http/error-contract.ts");
const {requestSocialApi} = source("lib/http/social-request.ts");
const {apiRequest: requestCommunity} = source("lib/http/community-request.ts");
const {formatUiRequestFailure} = source("lib/http/error-presentation.ts");
for (const language of ["ko","en"]) for (const zone of ["UTC","Asia/Seoul","America/New_York","Europe/London"]) {
  const instance = language === "ko" ? ko : en;
  const text = (message, values = {}) => String(instance.t(message,{...values,ns:"shell",defaultValue:message}));
  const date = value => formatDate(value, zone, language);
  const utc = "2026-10-04T00:00:00Z";
  const error = new ApiRequestError("PRIVATE provider data",429,"quota_exceeded",{allowance_at:utc},"60");
  const display = formatUiRequestFailure(error,"The request could not be completed. Please try again.",text,date,Date.parse("2026-10-03T15:00:00Z"));
  assert.ok(display.includes(date(utc)) && display.includes(date("2026-10-03T15:01:00Z")));
  assert.ok(!display.includes("PRIVATE")); assert.equal(error.params.allowance_at,utc);
}
const user = id => ({id, display_name: "Original 原文 A-17", email: null, profile_setup_completed: true, feed_content_filter: "all", is_admin: false});
auth.storeAuth({user: user("owner-a")});
for (const status of [403,409,422,429,503]) {
  runtimeFetch = async () => new Response(JSON.stringify({detail: {code: "fixture_failed", params: {limit: 3, allowance_at: "2026-10-04T00:00:00Z", raw: "private"}}}), {status, headers: {"Retry-After": "60"}});
  await assert.rejects(apiRequest("/fixture"), error => error.status === status && error.code === "fixture_failed" && error.params.limit === 3 && error.params.allowance_at === "2026-10-04T00:00:00Z" && error.retryAfter === "60" && !JSON.stringify(error.params).includes("private"));
  assert.equal(auth.getStoredUser().id, "owner-a");
}
for (const body of ["<html>private provider data</html>", JSON.stringify({detail: "private-provider-data"})]) {
  runtimeFetch = async () => new Response(body, {status: 409});
  await assert.rejects(apiRequest("/fixture"), error => error.status === 409 && !error.message.includes("private"));
}
for (const request of [requestSocialApi, requestCommunity]) {
  auth.storeAuth({user: user("owner-a")});
  runtimeFetch = async () => new Response('{"detail":"private-provider-data"}', {status: 503});
  await assert.rejects(request("/fixture"), error => error instanceof ApiRequestError
    && error.status === 503 && !error.message.includes("private"));
  runtimeFetch = async () => new Response("invalid-success-json", {status: 200});
  await assert.rejects(request("/fixture"));
  runtimeFetch = async () => new Response('{"detail":"not_authenticated"}', {status: 401});
  await assert.rejects(request("/fixture"), error => error.status === 401);
  assert.equal(auth.getStoredUser().id, "owner-a");
}
const authenticatedSocial = (path, options) => requestSocialApi(path, {...options, clearAuthOnUnauthorized: true});
for (const request of [apiRequest, auth.authRequest, authenticatedSocial]) {
  for (const transition of ["new-owner", "same-owner-new-session", "runtime-replaced", "aborted"]) {
    auth.storeAuth({user: user("owner-a")});
    browser.__ANGMOO_RUNTIME_CONFIG__ = {apiBaseUrl: "http://127.0.0.1:12345", launchToken: "old-in-memory"};
    let respond; runtimeFetch = () => new Promise(resolve => {respond = resolve;});
    const controller = new AbortController();
    const pending = request("/fixture", {signal: controller.signal});
    if (transition === "new-owner") auth.storeAuth({user: user("owner-b")});
    if (transition === "same-owner-new-session") auth.storeAuth({user: user("owner-a")});
    if (transition === "runtime-replaced") browser.__ANGMOO_RUNTIME_CONFIG__ = {apiBaseUrl: "http://127.0.0.1:12346", launchToken: "new-in-memory"};
    if (transition === "aborted") controller.abort();
    respond(new Response('{"detail":"not_authenticated"}', {status: 401}));
    await assert.rejects(pending, error => error.status === 401);
    assert.equal(auth.getStoredUser().id, transition === "new-owner" ? "owner-b" : "owner-a");
  }
  runtimeFetch = async () => new Response('{"detail":"not_authenticated"}', {status: 401});
  await assert.rejects(request("/fixture"), error => error.status === 401);
  assert.equal(auth.getStoredUser(), null);
}
console.log("User environment contracts PASS: isolated i18next/SSR, interpolation escaping, detectors, UTC display, typed HTTP errors across shared transports and 12 late-response session transitions.");
