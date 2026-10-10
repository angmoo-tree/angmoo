import { ATTACHMENT_PHOTO_BYTES, checkPhotoDimensions, inspectPhoto, ORIGINAL_PHOTO_BYTES, PhotoPreparationError } from "../utils/photo-header";
import { decodeHeifPrimary } from "../utils/heif-decoder";

async function prepare(file: File) {
  if (file.size > ORIGINAL_PHOTO_BYTES) throw new PhotoPreparationError("photo_original_large");
  const buffer = await file.arrayBuffer(), header = inspectPhoto(buffer);
  let pixels: ImageBitmap | OffscreenCanvas | null = null;
  let canvas: OffscreenCanvas | null = null;
  try {
    let outputMime = header.mime;
    if (header.mime === "image/heif") {
      const primary = await decodeHeifPrimary(new Uint8Array(buffer));
      pixels = primary.canvas;
      outputMime = primary.hasAlpha ? "image/png" : "image/jpeg";
    } else {
      pixels = await createImageBitmap(new Blob([buffer], { type: header.mime }), { imageOrientation: "from-image" });
    }
    checkPhotoDimensions(pixels.width, pixels.height);
    if (header.mime !== "image/heif" && file.size <= ATTACHMENT_PHOTO_BYTES && pixels.width <= 4096 && pixels.height <= 4096) return new Blob([buffer], { type: header.mime });
    let scale = Math.min(1, 4096 / pixels.width, 4096 / pixels.height), quality = 0.9;
    for (let attempt = 0; attempt < 6; attempt++) {
      const width = Math.max(1, Math.round(pixels.width * scale)), height = Math.max(1, Math.round(pixels.height * scale));
      canvas = new OffscreenCanvas(width, height);
      const ctx = canvas.getContext("2d"); if (!ctx) throw new PhotoPreparationError("photo_preparation");
      ctx.drawImage(pixels, 0, 0, width, height);
      const blob = await canvas.convertToBlob({ type: outputMime, quality });
      if (["image/webp", "image/png", "image/jpeg"].includes(blob.type) && blob.size <= ATTACHMENT_PHOTO_BYTES) {
        const check = await createImageBitmap(blob);
        try { if (check.width !== width || check.height !== height || width > 4096 || height > 4096 || width * height > 16777216) throw new PhotoPreparationError("photo_preparation"); }
        finally { check.close(); }
        return blob;
      }
      canvas.width = 0; canvas.height = 0; canvas = null;
      quality = Math.max(0.55, quality - 0.1); scale *= 0.85;
    }
    throw new PhotoPreparationError("photo_preparation");
  } finally {
    if (pixels instanceof ImageBitmap) pixels.close();
    else if (pixels) { pixels.width = 0; pixels.height = 0; }
    if (canvas) { canvas.width = 0; canvas.height = 0; }
  }
}
self.onmessage = async (event: MessageEvent<File>) => {
  try { self.postMessage({ blob: await prepare(event.data) }); }
  catch (reason) { self.postMessage({ error: reason instanceof PhotoPreparationError ? reason.code : "photo_damaged" }); }
};
