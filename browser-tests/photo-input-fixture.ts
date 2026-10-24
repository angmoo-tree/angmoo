import type { Page } from "@playwright/test";

export async function guardExternalInput(page: Page) {
  await page.addInitScript(() => {
    const selected = new WeakSet<File>(), size = Object.getOwnPropertyDescriptor(Blob.prototype, "size")!.get!;
    const stream = Blob.prototype.stream;
    const state = { reads: 0, fail: false, transfers: 0, terminated: 0, revoked: [] as string[] };
    (window as any).inputProof = state;
    document.addEventListener("change", event => {
      const target = event.target as HTMLInputElement;
      if (target.type === "file") for (const file of target.files ?? []) selected.add(file);
    }, true);
    Object.defineProperty(File.prototype, "size", { configurable: true, get() { if (selected.has(this)) throw Error("external_metadata_before_read"); return size.call(this); } });
    File.prototype.stream = function() {
      if (selected.has(this)) { state.reads++; if (state.fail) return new ReadableStream({ start(controller) { controller.error(new DOMException("provider changed", "NotReadableError")); } }); }
      return stream.call(this);
    };
    const revoke = URL.revokeObjectURL;
    URL.revokeObjectURL = function(url) { state.revoked.push(url); revoke.call(this, url); };
    const NativeWorker = Worker;
    window.Worker = class extends NativeWorker {
      postMessage(message: any, transfer: Transferable[]) {
        if (!(message.buffer instanceof ArrayBuffer) || message.file || transfer[0] !== message.buffer) throw Error("invalid_photo_transfer");
        state.transfers++; super.postMessage(message, transfer);
        if (message.buffer.byteLength !== 0) throw Error("buffer_not_transferred");
      }
      terminate() { state.terminated++; super.terminate(); }
    } as typeof Worker;
  });
}
