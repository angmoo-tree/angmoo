import type { LocalClientState, StoredConnection } from "../types/local-entry";

const STORE = "connections";
export const LOCAL_CONNECTION_CHANGED = "angmoo:local-connection-changed";
const CHANNEL = "angmoo-local-connection";

function valid(value: unknown): value is StoredConnection {
  if (!value || typeof value !== "object") return false;
  const data = value as StoredConnection;
  return typeof data.clientId === "string" && /^[A-Za-z0-9_-]{16,64}$/.test(data.clientId) &&
    Number.isSafeInteger(data.generation) && data.generation >= 0 &&
    ["active", "ending", "stopped", "end_unconfirmed"].includes(data.intent);
}

/** A readwrite IDB transaction is atomic across tabs, including first access.
 * No tokens, runtime ports or launch secrets are persisted here. */
async function transaction(installation: string, mutate: (previous: StoredConnection | undefined) => StoredConnection) {
  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    let abandoned = false;
    const request = indexedDB.open("angmoo-local-identity", 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onsuccess = () => { if (abandoned) request.result.close(); else resolve(request.result); };
    request.onerror = () => reject(new Error("local_connection_storage_unavailable"));
    request.onblocked = () => { abandoned = true; reject(new Error("local_connection_storage_unavailable")); };
  });
  try {
    return await new Promise<StoredConnection>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite"), store = tx.objectStore(STORE);
      const read = store.get(installation);
      let result: StoredConnection;
      let failure: unknown;
      read.onsuccess = () => {
        try {
          if (read.result !== undefined && !valid(read.result)) throw new Error("local_connection_storage_invalid");
          result = mutate(read.result);
          if (!valid(result)) throw new Error("local_connection_storage_invalid");
          if (JSON.stringify(result) !== JSON.stringify(read.result)) store.put(result, installation);
        } catch (error) { failure = error; tx.abort(); }
      };
      tx.oncomplete = () => resolve(result);
      tx.onabort = tx.onerror = () => reject(failure ?? new Error("local_connection_storage_unavailable"));
    });
  } finally { db.close(); }
}

function announce() {
  window.dispatchEvent(new Event(LOCAL_CONNECTION_CHANGED));
  if (typeof BroadcastChannel !== "undefined") {
    const channel = new BroadcastChannel(CHANNEL);
    channel.postMessage("changed"); channel.close();
  }
}

export const connectionStore = {
  read(installation: string, server?: LocalClientState | null) {
    return transaction(installation, previous => {
      if (previous && server && previous.clientId !== server.client_instance_id) throw new Error("local_connection_storage_invalid");
      return previous ?? {
      clientId: server?.client_instance_id ?? crypto.randomUUID(), generation: server?.generation ?? 0,
      intent: server?.state ?? "active",
      };
    });
  },
  async update(installation: string, mutate: (previous: StoredConnection) => StoredConnection) {
    let changed = false;
    const value = await transaction(installation, previous => {
      if (!previous) throw new Error("local_connection_storage_unavailable");
      const next = mutate(previous);
      changed = JSON.stringify(next) !== JSON.stringify(previous);
      return next;
    });
    if (changed) announce();
    return value;
  },
  async serialize<T>(installation: string, work: () => Promise<T>): Promise<T> {
    // When unavailable, IDB still provides atomic intent and the server CAS
    // fences concurrent network operations. Never use localStorage as a CAS.
    if (navigator.locks) return navigator.locks.request(`angmoo-connection:${installation}`, work);
    return work();
  },
  subscribe(changed: () => void) {
    const channel = typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel(CHANNEL);
    if (channel) channel.onmessage = changed;
    window.addEventListener(LOCAL_CONNECTION_CHANGED, changed);
    return () => { channel?.close(); window.removeEventListener(LOCAL_CONNECTION_CHANGED, changed); };
  },
};
