/** A selected File can be backed by a mutable provider. Read its content before metadata. */
export class FileInputError extends Error {
  constructor(readonly code: "read" | "size" | "timeout") {
    super(`file_input_${code}`);
    this.name = "FileInputError";
  }
}

export type FileInputDeadline = {
  signal: AbortSignal;
  check: () => void;
  wait: <T>(pending: Promise<T>, disposeLate?: (value: T) => void) => Promise<T>;
};

/** One timer covers reading and the caller's remaining preparation, never network upload. */
export async function withFileInputDeadline<T>(
  signal: AbortSignal,
  timeoutMs: number,
  prepare: (scope: FileInputDeadline) => Promise<T>,
  disposeResult?: (value: T) => void,
): Promise<T> {
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) throw new RangeError("Invalid input deadline");
  if (signal.aborted) throw new DOMException("Aborted", "AbortError");
  const controller = new AbortController();
  const deadline = performance.now() + timeoutMs;
  const abort = () => controller.abort(new DOMException("Aborted", "AbortError"));
  const expire = () => controller.abort(new FileInputError("timeout"));
  const check = () => {
    if (signal.aborted && !controller.signal.aborted) abort();
    if (performance.now() >= deadline && !controller.signal.aborted) expire();
    if (controller.signal.aborted) throw controller.signal.reason;
  };
  signal.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(expire, Math.max(0, timeoutMs));
  const scope: FileInputDeadline = {
    signal: controller.signal,
    check,
    wait: <U>(pending: Promise<U>, disposeLate?: (value: U) => void) => new Promise<U>((resolve, reject) => {
      let finished = false;
      const dispose = (value: U) => { try { disposeLate?.(value); } catch { /* Preserve the primary outcome. */ } };
      const stop = () => {
        if (finished) return;
        finished = true;
        controller.signal.removeEventListener("abort", stop);
        reject(controller.signal.reason);
      };
      controller.signal.addEventListener("abort", stop, { once: true });
      if (controller.signal.aborted) stop();
      pending.then(value => {
        if (finished) { dispose(value); return; }
        try { check(); } catch (error) {
          dispose(value);
          if (!finished) { finished = true; reject(error); }
          controller.signal.removeEventListener("abort", stop);
          return;
        }
        finished = true;
        controller.signal.removeEventListener("abort", stop);
        resolve(value);
      }, error => {
        if (finished) return;
        finished = true;
        controller.signal.removeEventListener("abort", stop);
        reject(error);
      }).catch(() => { /* A late resource cleanup cannot replace the operation's result. */ });
    }),
  };
  try {
    check();
    const value = await prepare(scope);
    try { check(); } catch (error) {
      try { disposeResult?.(value); } catch { /* Preserve cancellation or timeout. */ }
      throw error;
    }
    return value;
  } finally {
    clearTimeout(timer);
    signal.removeEventListener("abort", abort);
  }
}

/** At most ceil(maxBytes / 256 KiB) owned blocks plus the exact final buffer. */
export async function readFileInput(file: Blob, maxBytes: number, scope: FileInputDeadline): Promise<ArrayBuffer> {
  scope.check();
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 1) throw new RangeError("Invalid input byte limit");
  let reader: ReadableStreamDefaultReader<Uint8Array>;
  try { reader = file.stream().getReader(); }
  catch { scope.check(); throw new FileInputError("read"); }
  const blocks: Uint8Array<ArrayBuffer>[] = [];
  const blockSize = 256 * 1024;
  let length = 0;
  let ended = false;
  try {
    while (true) {
      scope.check();
      const chunk = await scope.wait(reader.read());
      scope.check();
      if (chunk.done) { ended = true; break; }
      if (!(chunk.value instanceof Uint8Array)) throw new FileInputError("read");
      if (chunk.value.byteLength > maxBytes - length) throw new FileInputError("size");
      let offset = 0;
      while (offset < chunk.value.byteLength) {
        scope.check();
        const index = Math.floor(length / blockSize);
        const within = length % blockSize;
        if (!blocks[index]) blocks.push(new Uint8Array(Math.min(blockSize, maxBytes - length)));
        const count = Math.min(blocks[index].length - within, chunk.value.byteLength - offset);
        blocks[index].set(chunk.value.subarray(offset, offset + count), within);
        offset += count;
        length += count;
      }
    }
    scope.check();
    const result = new Uint8Array(length);
    for (let index = 0; index < blocks.length; index++) {
      scope.check();
      result.set(blocks[index].subarray(0, Math.min(blocks[index].length, length - index * blockSize)), index * blockSize);
    }
    blocks.length = 0;
    scope.check();
    return result.buffer;
  } catch (error) {
    scope.check();
    if (error instanceof FileInputError) throw error;
    throw new FileInputError("read");
  } finally {
    blocks.length = 0;
    const release = () => { try { reader.releaseLock(); } catch { /* Pending native reads may finish later. */ } };
    if (!ended) {
      try { void reader.cancel().then(release, release); } catch { /* Preserve the primary failure. */ }
    }
    release();
  }
}
