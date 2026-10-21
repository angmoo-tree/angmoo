import { detailedServiceLogs } from "./service-log-policy";

/** Transport diagnostics contain only fixed categories, never request data. */
export type ProxyPhase = "request_body" | "upstream_headers" | "error_body" | "response_stream";
export type ProxyRoute = "backend" | "community";

const CONNECTION_CODES = new Set(["UND_ERR_SOCKET", "UND_ERR_CONNECT_TIMEOUT", "UND_ERR_HEADERS_TIMEOUT", "UND_ERR_BODY_TIMEOUT", "ECONNRESET", "ECONNREFUSED", "ETIMEDOUT", "EPIPE", "ENOTFOUND", "EAI_AGAIN"]);
export function proxyConnectionCode(error: unknown): string {
  const visited = new Set<object>();
  for (let depth = 0; depth < 4 && error && typeof error === "object"; depth++) {
    if (visited.has(error)) break;
    visited.add(error);
    // Inspect only own data properties; untrusted getters must not run in logging.
    try {
      const code = Object.getOwnPropertyDescriptor(error, "code")?.value;
      if (typeof code === "string" && CONNECTION_CODES.has(code)) return code;
      error = Object.getOwnPropertyDescriptor(error, "cause")?.value;
    } catch { return "unknown"; }
  }
  return "unknown";
}

export function proxyLifecycle(method: string, route: ProxyRoute = "backend") {
  detailedServiceLogs(); // Lazy service ACK includes time already spent starting.
  const started = performance.now();
  let reported = false;
  const requestId = crypto.randomUUID();
  return {
    finish(phase: ProxyPhase, outcome: "cancelled" | "failed", status?: number, error?: unknown) {
      if (reported) return;
      reported = true;
      const diagnostic = {
        event: "backend_proxy_terminal",
        request_id: requestId,
        connection_code: outcome === "failed" ? proxyConnectionCode(error) : undefined,
        method: ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"].includes(method) ? method : "OTHER",
        route,
        phase,
        outcome,
        elapsed_ms: Math.round(performance.now() - started),
        ...(status === undefined ? {} : { status }),
      };
      if (outcome === "cancelled") { if (detailedServiceLogs()) console.info(diagnostic); }
      else console.warn(diagnostic);
    },
  };
}

export type ProxyLifecycle = ReturnType<typeof proxyLifecycle>;

// Identity/cause matters: an unrelated error called ResponseAborted is not proof.
export function isRequestCancellation(error: unknown, signal?: AbortSignal | null): boolean {
  if (!signal?.aborted) return false;
  return error === signal.reason ||
    (error instanceof Error && error.cause === signal.reason);
}

export function cancelledResponse() {
  return new Response(null, { status: 499, headers: { "cache-control": "no-store" } });
}

export function failedProxyResponse() {
  return Response.json({ detail: "backend_transport_failed" }, {
    status: 502, headers: { "cache-control": "no-store" },
  });
}

/** One reader and pull-based forwarding; a broken stream must remain broken. */
export function forwardResponseStream(
  body: ReadableStream<Uint8Array>,
  upstream: AbortController,
  downstream: AbortSignal | null | undefined,
  lifecycle: ProxyLifecycle,
  status: number,
  detach: () => void,
) {
  const reader = body.getReader();
  let ended = false;
  let cancelReason: unknown;
  let cancellation: Promise<void> | undefined;
  const cancelReader = (reason: unknown) => cancellation ??= reader.cancel(reason).catch(() => {});
  const finish = () => {
    if (ended) return;
    ended = true;
    downstream?.removeEventListener("abort", onAbort);
    detach();
    reader.releaseLock();
  };
  const onAbort = () => {
    cancelReason = downstream?.reason;
    // Cancelling the reader releases a pending read. The pull below distinguishes
    // this from EOF and errors the stream instead of fabricating completion.
    void cancelReader(cancelReason);
  };
  downstream?.addEventListener("abort", onAbort, { once: true });
  if (downstream?.aborted) onAbort();
  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      try {
        const result = await reader.read();
        if (downstream?.aborted) throw cancelReason ?? downstream.reason;
        if (ended) return;
        if (result.done) {
          finish();
          controller.close();
        } else controller.enqueue(result.value);
      } catch (error) {
        if (ended) return;
        const cancelled = isRequestCancellation(error, downstream);
        lifecycle.finish("response_stream", cancelled ? "cancelled" : "failed", status, error);
        finish();
        controller.error(error);
      }
    },
    async cancel(reason) {
      if (ended) return;
      lifecycle.finish("response_stream", "cancelled", status);
      upstream.abort(reason);
      try { await cancelReader(reason); } finally { finish(); }
    },
  }, { highWaterMark: 0 });
}
