import { FileInputError, readFileInput, withFileInputDeadline } from "@/lib/media/read-file-input";
import { PhotoPreparationError } from "../utils/photo-header";
import type { PreparedImageUpload } from "../types/photo-preparation";

export class ReferenceImageInputError extends Error {
  constructor() { super("reference_image_unsupported"); this.name = "ReferenceImageInputError"; }
}

/** Reference images keep their own 10 MiB/PNG/JPEG/WebP policy; no photo conversion. */
export async function prepareReferenceImage(file: File, signal: AbortSignal): Promise<PreparedImageUpload> {
  try {
    return await withFileInputDeadline(signal, 30_000, async scope => {
      const buffer = await readFileInput(file, 10 * 1024 * 1024, scope);
      scope.check();
      if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) throw new ReferenceImageInputError();
      if (!buffer.byteLength) throw new PhotoPreparationError("photo_damaged");
      return { file: new File([buffer], file.name, { type: file.type }) };
    });
  } catch (error) {
    if (error instanceof FileInputError) {
      if (error.code === "size") throw new ReferenceImageInputError();
      throw new PhotoPreparationError(error.code === "timeout" ? "photo_timeout" : "photo_read");
    }
    throw error;
  }
}
