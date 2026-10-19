import { isAuthError } from "@/lib/auth/browser-session";
import { ApiRequestError } from "@/lib/http/error-contract";
import type { localEntryApi } from "../api/local-entry";
import type { connectionStore } from "./local-connection-store";
import type { LocalClientRequest, LocalEntrySnapshot, StoredConnection } from "../types/local-entry";

type Dependencies = {
  api: typeof localEntryApi;
  store: typeof connectionStore;
  language: () => string | null;
  abort?: () => void;
  onUser?: (user: LocalEntrySnapshot["user"]) => void;
};

export function createLocalEntryController(deps: Dependencies) {
  let snapshot: LocalEntrySnapshot = { phase: "checking", user: null, bootstrap: null, errorCode: null, sessionRevision: 0 };
  let flight: Promise<void> | null = null;
  let epoch = 0;
  let ending = false;
  let invalidated = false;
  const listeners = new Set<() => void>();
  const publish = (change: Partial<LocalEntrySnapshot>) => {
    if (invalidated) return;
    if ("user" in change && change.user !== snapshot.user) deps.onUser?.(change.user ?? null);
    snapshot = { ...snapshot, ...change }; for (const listener of listeners) listener();
  };
  const request = (installation: string, local: StoredConnection): LocalClientRequest => ({ protocol: 2, installation_id: installation,
    client_instance_id: local.clientId, expected_generation: local.generation });
  const fail = (error: unknown) => {
    const code = error instanceof ApiRequestError ? error.code : error instanceof Error && error.message.startsWith("local_") ? error.message : null;
    publish({ phase: ending ? "end_unconfirmed" : "unavailable", user: null, errorCode: code ?? "local_connection_unavailable" });
  };
  const refresh = (attempt = 0): Promise<void> => {
    if (invalidated) return Promise.resolve();
    if (flight) return flight;
    const admittedEpoch = epoch;
    const current = () => epoch === admittedEpoch;
    let reconcile = false;
    flight = (async () => {
      try {
        let bootstrap = await deps.api.bootstrap();
        if (!current()) return;
        if (bootstrap.protocol !== 2) throw new Error("local_auth_contract_mismatch");
        if (!bootstrap.installation_id) {
          await deps.api.challenge();
          bootstrap = await deps.api.bootstrap();
        }
        if (!current()) return;
        publish({ bootstrap });
        const installation = bootstrap.installation_id;
        if (!installation) throw new Error("local_auth_contract_mismatch");
        if (bootstrap.state === "recovery_required") { publish({ phase: "recovery_required", user: null }); return; }
        await deps.store.read(installation, bootstrap.client_connection);
        if (!current()) return;
        await deps.store.serialize(installation, async () => {
          if (!current()) return;
          const latest = await deps.store.read(installation);
          const state = await deps.api.status(request(installation, latest));
          if (!current()) return;
          if (state.state === "stopped") {
            await deps.store.update(installation, value => ({ ...value, intent: "stopped", generation: Math.max(value.generation, state.generation) }));
            if (current()) publish({ phase: "stopped", user: null, errorCode: null });
            return;
          }
          if (ending || latest.intent !== "active") {
            publish({ phase: "end_unconfirmed", user: null }); return;
          }
          if (bootstrap.state === "unclaimed" && !bootstrap.automatic_prepare_allowed) {
            publish({ phase: bootstrap.candidates.length ? "selection_required" : "recovery_required", user: null }); return;
          }
          const synchronized = await deps.store.update(installation, value => value.intent === "active"
            ? { ...value, generation: state.generation } : value);
          if (!current() || ending || synchronized.intent !== "active") return;
          const data = request(installation, synchronized);
          let user;
          let issued = false;
          if (bootstrap.state === "claimed") {
            try { user = await deps.api.currentUser(); } catch (error) { if (!isAuthError(error)) throw error; }
            if (!current() || ending) return;
            if (!user || !bootstrap.client_connection) { user = (await deps.api.issue(data)).user; issued = true; }
          } else {
            publish({ phase: "preparing", user: null });
            await deps.api.challenge();
            if (!current() || ending) return;
            user = (await deps.api.prepare(data, deps.language())).user;
            issued = true;
          }
          const intent = await deps.store.read(installation);
          if (current() && !ending && intent.intent === "active") publish({ phase: "authenticated", user, errorCode: null,
            sessionRevision: snapshot.sessionRevision + (issued ? 1 : 0) });
        });
      } catch (error) {
        if (current()) {
          reconcile = !ending && attempt === 0 && error instanceof ApiRequestError &&
            ["bootstrap_closed", "bootstrap_race_lost", "local_client_revision_conflict"].includes(error.code ?? "");
          if (!reconcile) fail(error);
        }
      }
    })().finally(() => { flight = null; }).then(() => {
      if (reconcile && current() && !ending) return refresh(attempt + 1);
    });
    return flight;
  };
  async function stop() {
    if (invalidated) return;
    ending = true;
    const admittedEpoch = ++epoch;
    const current = () => !invalidated && epoch === admittedEpoch;
    publish({ phase: "ending", user: null, errorCode: null });
    try {
      const bootstrap = snapshot.bootstrap ?? await deps.api.bootstrap();
      if (!current()) return;
      const installation = bootstrap.installation_id;
      if (!installation) throw new Error("local_auth_contract_mismatch");
      await deps.store.read(installation, bootstrap.client_connection);
      const admitted = await deps.store.update(installation, value => ({ ...value, intent: "ending" }));
      // Do not claim aborting a request rolled back its server effects.
      await flight;
      if (!current()) return;
      await deps.store.serialize(installation, async () => {
        if (!current()) return;
        // Keep the generation admitted by this click. A delayed stop must not
        // silently terminate a later explicit resume from another tab.
        const result = await deps.api.stop(request(installation, admitted));
        if (!current()) return;
        const saved = await deps.store.update(installation, value => value.generation <= result.generation
          ? { ...value, intent: "stopped", generation: result.generation } : value);
        if (saved.generation > result.generation) {
          // Another tab explicitly resumed a newer generation while this
          // response was in transit. Reconcile after releasing the lock.
          ending = saved.intent !== "active";
          publish({ phase: "checking", user: null });
          return;
        }
        publish({ phase: "stopped", user: null });
      });
      if (current() && !ending) await refresh();
    } catch (error) { if (current()) fail(error); }
  }
  async function resume() {
    const installation = snapshot.bootstrap?.installation_id;
    if (invalidated || !installation || snapshot.phase === "ending") return;
    const admittedEpoch = epoch;
    const current = () => !invalidated && epoch === admittedEpoch;
    await flight;
    try {
      await deps.store.serialize(installation, async () => {
        const local = await deps.store.read(installation);
        if (!current()) return;
        const state = await deps.api.status(request(installation, local));
        if (!current()) return;
        if (local.intent === "ending" || snapshot.phase === "end_unconfirmed") {
          if (state.state !== "stopped") throw new Error("local_session_stop_unconfirmed");
        }
        const data = request(installation, { ...local, generation: state.generation });
        if (state.state === "stopped") await deps.api.resume(data);
        if (!current()) return;
        // A previous explicit resume may have committed despite a lost response.
        const confirmed = await deps.api.status(data);
        if (!current()) return;
        if (confirmed.state !== "active") throw new Error("local_client_stopped");
        const saved = await deps.store.update(installation, value => value.intent === local.intent && value.generation === local.generation
          ? { ...value, intent: "active", generation: confirmed.generation } : value);
        if (!current() || saved.intent !== "active") return;
        ending = false;
        publish({ sessionRevision: snapshot.sessionRevision + 1 });
      });
      if (current()) await refresh();
    } catch (error) { if (current()) fail(error); }
  }
  async function selectOwner(ownerId: string) {
    const installation = snapshot.bootstrap?.installation_id;
    if (invalidated || !installation || snapshot.phase !== "selection_required") return;
    const admittedEpoch = epoch;
    const current = () => !invalidated && epoch === admittedEpoch && !ending;
    try {
      await deps.store.serialize(installation, async () => {
        const local = await deps.store.read(installation);
        if (!current()) return;
        if (local.intent !== "active") throw new Error("local_client_stopped");
        await deps.api.challenge();
        if (!current()) return;
        await deps.api.claim(request(installation, local), ownerId);
      });
      if (current()) await refresh();
    } catch (error) { if (current()) fail(error); }
  }
  return {
    getSnapshot: () => snapshot,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    refresh, stop, resume, selectOwner,
    invalidate() { epoch++; deps.abort?.(); ending = false; publish({ phase: "checking", user: null, bootstrap: null, errorCode: null }); invalidated = true; },
  };
}
