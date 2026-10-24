import { readFileInput, withFileInputDeadline } from "@/lib/media/read-file-input";
import { PROFILE_MEDIA_MAX_BYTES } from "@/utils/image-crop";

export class ProfileMediaInputError extends Error {
  constructor(readonly code: "format" | "decode") { super(`profile_media_${code}`); this.name = "ProfileMediaInputError"; }
}

export function prepareProfileMedia(file: File, signal: AbortSignal): Promise<ImageBitmap> {
  return withFileInputDeadline(signal, 30_000, async scope => {
    const buffer = await readFileInput(file, PROFILE_MEDIA_MAX_BYTES, scope);
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) throw new ProfileMediaInputError("format");
    try {
      return await scope.wait(createImageBitmap(new Blob([buffer], { type: file.type })), bitmap => bitmap.close());
    } catch {
      scope.check();
      throw new ProfileMediaInputError("decode");
    }
  }, bitmap => bitmap.close());
}
