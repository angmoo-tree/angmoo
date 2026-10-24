import { readFileInput, withFileInputDeadline } from "@/lib/media/read-file-input";
import { PROFILE_MEDIA_MAX_BYTES } from "@/utils/image-crop";

export class WorldImageInputError extends Error {
  constructor(readonly code: "format" | "decode") { super(`world_image_${code}`); this.name = "WorldImageInputError"; }
}

export function prepareWorldImage(file: File, signal: AbortSignal): Promise<ImageBitmap> {
  return withFileInputDeadline(signal, 30_000, async scope => {
    const buffer = await readFileInput(file, PROFILE_MEDIA_MAX_BYTES, scope);
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) throw new WorldImageInputError("format");
    try { return await scope.wait(createImageBitmap(new Blob([buffer], { type: file.type })), bitmap => bitmap.close()); }
    catch { scope.check(); throw new WorldImageInputError("decode"); }
  }, bitmap => bitmap.close());
}
