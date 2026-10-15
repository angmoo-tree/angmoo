import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { runInNewContext } from "node:vm";
import assert from "node:assert/strict";
import test from "node:test";
import ts from "typescript";

// Execute the actual controller with deterministic I/O/lifecycle boundaries.
// Browser/HTTP suites separately validate the real transport and React views.
const source = readFileSync(new URL("../../src/features/social/hooks/world-notification-controller.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
const scope = { world_id: "world-a", recipient_world_character_id: "owner-a" };
function harness() {
  const storage = new Map(), intervals = new Set(), timeouts = new Set();
  const counters = { reads: 0, writes: 0, count: 6, command: null };
  const api = {
    getWorldNotifications: async current => { counters.reads++; return { scope: current, unread_count: current.world_id === "world-a" ? counters.count : 3, items: [], next_cursor: null }; },
    getWorldNotificationCount: async current => ({ scope: current, unread_count: counters.count }),
    notificationSnapshotRejected: () => false,
    markAllWorldNotificationsRead: async current => {
      counters.writes++;
      if (counters.command) return counters.command(current);
      const marked = counters.count; counters.count = 0;
      return { scope: current, marked_count: marked, read_at: "2026-10-15T04:00:00Z", through_notification_id: 6, unread_count: 0 };
    },
  };
  const exports = {};
  const require = createRequire(import.meta.url);
  runInNewContext(compiled, {
    exports, AbortController, performance: { now: () => 0 }, queueMicrotask,
    setInterval: fn => { intervals.add(fn); return fn; }, clearInterval: fn => intervals.delete(fn),
    setTimeout: fn => { timeouts.add(fn); return fn; }, clearTimeout: fn => timeouts.delete(fn),
    document: { visibilityState: "visible", addEventListener() {}, removeEventListener() {} },
    window: { addEventListener() {}, removeEventListener() {} },
    sessionStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) },
    require: id => id === "@/lib/auth/browser-session" ? { captureAuthRequestScope: () => ({}), isCurrentAuthRequestScope: () => true }
      : id === "../api/world-notifications" ? api : id === "@/lib/http/error-contract" ? { ApiRequestError: class extends Error {} } : require(id),
  });
  return { controller: exports.createWorldNotificationController("local-user", 1), counters, intervals, timeouts, storage };
}

test("development setup/cleanup/setup keeps one usable owner and never writes on mount", async () => {
  const { controller, counters, intervals } = harness();
  const first = controller.connect(); controller.activate(scope, "list"); await flush();
  controller.deactivate(); first();
  controller.activate(scope, "list"); const second = controller.connect(); await flush();
  assert.equal(counters.writes, 0); assert.equal(intervals.size, 1);
  await controller.markAllRead(); await flush();
  assert.equal(counters.writes, 1); assert.equal(controller.getSnapshot().unreadCount, 0);
  controller.deactivate(); second(); second(); await flush();
  assert.equal(intervals.size, 0);
});

test("twenty direct calls share one pending command and cleanup releases timers", async () => {
  const { controller, counters, timeouts } = harness();
  let finish; counters.command = current => new Promise(resolve => { finish = () => resolve({ scope: current, marked_count: 6, read_at: "2026-10-15T04:00:00Z", through_notification_id: 6, unread_count: 0 }); });
  const disconnect = controller.connect(); controller.activate(scope, "list"); await flush();
  const calls = Array.from({ length: 20 }, () => controller.markAllRead());
  assert.equal(counters.writes, 1); assert.equal(controller.getSnapshot().readAllPending, true);
  counters.count = 0; finish(); await Promise.all(calls); await flush();
  assert.equal(controller.getSnapshot().readAllPending, false); assert.equal(timeouts.size, 0);
  disconnect(); await flush();
});

test("a response from an abandoned profile cannot replace the next scope", async () => {
  const { controller, counters } = harness();
  let finish; counters.command = current => new Promise(resolve => { finish = () => resolve({ scope: current, marked_count: 6, read_at: "2026-10-15T04:00:00Z", through_notification_id: 6, unread_count: 0 }); });
  const disconnect = controller.connect(); controller.activate(scope, "list"); await flush();
  const command = controller.markAllRead();
  controller.activate({ world_id: "world-b", recipient_world_character_id: "owner-b" }, "list"); await flush();
  finish(); await command; await flush();
  assert.equal(controller.getSnapshot().scope.world_id, "world-b");
  assert.equal(controller.getSnapshot().unreadCount, 3); assert.equal(counters.writes, 1);
  disconnect(); await flush();
});
