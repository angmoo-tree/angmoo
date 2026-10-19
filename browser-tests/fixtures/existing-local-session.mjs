import { VISUAL_ENVIRONMENT } from "./visual-environment.mjs";

/**
 * Opt-in read responses for product tests that already assume a signed-in owner.
 * This models an existing protocol-2 session; it never accepts session mutations.
 * Real bootstrap, expiry, stop/resume and concurrency use local-entry.spec.ts.
 */
export function existingLocalSessionRead(url, method, owner, options = {}) {
  const path = url.pathname.replace(/^\/api\/(backend|v1)/, "");
  const installationId = options.installationId ?? "visual-installation";
  const client = {
    protocol: 2, installation_id: installationId,
    client_instance_id: "browser-fixture-client-0001", generation: 0, state: "active",
  };
  if (method === "GET" && path === "/auth/local/bootstrap") {
    return { protocol: 2, state: "claimed", automatic_prepare_allowed: false,
      installation_id: installationId, local_label: options.localLabel ?? null,
      owner, candidates: [], client_connection: client };
  }
  if (method === "GET" && path === "/auth/local/client") {
    for (const [key, expected] of Object.entries({ protocol: 2,
      installation_id: installationId, client_instance_id: client.client_instance_id,
      expected_generation: 0 })) {
      if (url.searchParams.get(key) !== String(expected)) {
        throw new Error(`Unexpected synthetic local client request: ${key}`);
      }
    }
    return client;
  }
  // Only suites without their own detector fixture opt into this response.
  if (options.environment && ["GET", "POST"].includes(method) && path === "/auth/local/environment") {
    return { ...VISUAL_ENVIRONMENT, installation_id: installationId };
  }
  return undefined;
}
