import { FileInputError, readFileInput, withFileInputDeadline } from "@/lib/media/read-file-input";
import { ORIGINAL_PHOTO_BYTES, PHOTO_ERROR_CODES, PhotoPreparationError } from "../utils/photo-header";
import type { PhotoPreparationRequest, PhotoPreparationResponse, PreparedImageUpload } from "../types/photo-preparation";

/** The picker owns this operation; the single deadline includes both input and Worker. */
export async function prepareUserPhoto(file: File, signal: AbortSignal): Promise<PreparedImageUpload> {
  try {
    return await withFileInputDeadline(signal, 30_000, async scope => {
      const buffer = await readFileInput(file, ORIGINAL_PHOTO_BYTES, scope);
      scope.check();
      let worker: Worker | undefined;
      try {
        worker = new Worker(new URL("../workers/photo-preparation.worker.ts", import.meta.url), { type: "module" });
        const result = new Promise<Blob>((resolve, reject) => {
          worker!.onerror = () => reject(new PhotoPreparationError("photo_preparation"));
          worker!.onmessageerror = () => reject(new PhotoPreparationError("photo_preparation"));
          worker!.onmessage = (event: MessageEvent<PhotoPreparationResponse>) => {
            const response = event.data;
            if (response?.kind === "prepared" && response.blob instanceof Blob) resolve(response.blob);
            else if (response?.kind === "failed" && PHOTO_ERROR_CODES.includes(response.error)) reject(new PhotoPreparationError(response.error));
            else reject(new PhotoPreparationError("photo_preparation"));
          };
          scope.check();
          worker!.postMessage({ kind: "prepare", buffer } satisfies PhotoPreparationRequest, [buffer]);
        });
        const blob = await scope.wait(result);
        scope.check();
        return { file: new File([blob], file.name, { type: blob.type }) };
      } catch (error) {
        scope.check();
        if (error instanceof PhotoPreparationError) throw error;
        throw new PhotoPreparationError("photo_preparation");
      } finally {
        if (worker) { worker.onmessage = null; worker.onerror = null; worker.onmessageerror = null; worker.terminate(); }
      }
    });
  } catch (error) {
    if (error instanceof FileInputError) throw new PhotoPreparationError(error.code === "size" ? "photo_original_large" : error.code === "timeout" ? "photo_timeout" : "photo_read");
    throw error;
  }
}
