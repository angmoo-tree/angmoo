import { ORIGINAL_PHOTO_BYTES, PhotoPreparationError, type PhotoErrorCode } from "./photo-header";

/** Each picker owns one operation. Termination also interrupts a stuck native codec. */
export async function prepareUserPhoto(file: File, signal: AbortSignal): Promise<File> {
  if (signal.aborted) throw new DOMException("Aborted", "AbortError");
  if (file.size > ORIGINAL_PHOTO_BYTES) throw new PhotoPreparationError("photo_original_large");
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL("../workers/photo-preparation.worker.ts", import.meta.url), { type: "module" });
    const cleanup = () => { clearTimeout(timer); signal.removeEventListener("abort", abort); worker.terminate(); };
    const abort = () => { cleanup(); reject(new DOMException("Aborted", "AbortError")); };
    const timer = setTimeout(() => { cleanup(); reject(new PhotoPreparationError("photo_timeout")); }, 30000);
    signal.addEventListener("abort", abort, { once: true });
    worker.onerror = () => { cleanup(); reject(new PhotoPreparationError("photo_codec")); };
    worker.onmessage = (event: MessageEvent<{ blob?: Blob; error?: PhotoErrorCode }>) => {
      cleanup();
      if (event.data.blob) resolve(new File([event.data.blob], file.name, { type: event.data.blob.type }));
      else reject(new PhotoPreparationError(event.data.error ?? "photo_preparation"));
    };
    worker.postMessage(file);
  });
}
