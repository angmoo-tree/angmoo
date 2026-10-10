export type CropState = { scale: number; offsetX: number; offsetY: number };
export type CropSpec = { width: number; height: number };
export const PROFILE_MEDIA_MAX_BYTES = 5 * 1024 * 1024;
export const INITIAL_CROP: CropState = { scale: 1, offsetX: 0, offsetY: 0 };

/** A cover crop with bounded positions: no slider value exposes an empty edge. */
export function cropGeometry(size: CropSpec, spec: CropSpec, crop: CropState) {
  const zoom = Math.min(3, Math.max(1, crop.scale));
  const scale = Math.max(spec.width / size.width, spec.height / size.height) * zoom;
  const width = size.width * scale, height = size.height * scale;
  const x = (spec.width - width) / 2 + Math.max(-45, Math.min(45, crop.offsetX)) / 45 * (width - spec.width) / 2;
  const y = (spec.height - height) / 2 + Math.max(-45, Math.min(45, crop.offsetY)) / 45 * (height - spec.height) / 2;
  return { width, height, x, y };
}

export function drawCroppedImage(context: CanvasRenderingContext2D, bitmap: ImageBitmap, size: CropSpec, spec: CropSpec, crop: CropState) {
  const { width, height, x, y } = cropGeometry(size, spec, crop);
  context.clearRect(0, 0, spec.width, spec.height);
  context.drawImage(bitmap, x, y, width, height);
}

export async function cropToBlob(bitmap: ImageBitmap, size: CropSpec, spec: CropSpec, crop: CropState): Promise<Blob> {
  const canvas = document.createElement("canvas");
  canvas.width = spec.width; canvas.height = spec.height;
  try {
    const context = canvas.getContext("2d");
    if (!context) throw new Error("image_crop_failed");
    drawCroppedImage(context, bitmap, size, spec, crop);
    const blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob(value => value ? resolve(value) : reject(new Error("image_crop_failed")), "image/webp", 0.8));
    if (!['image/webp', 'image/png', 'image/jpeg'].includes(blob.type) || blob.size > PROFILE_MEDIA_MAX_BYTES) throw new Error("image_crop_failed");
    const check = await createImageBitmap(blob);
    try { if (check.width !== spec.width || check.height !== spec.height) throw new Error("image_crop_failed"); }
    finally { check.close(); }
    return blob;
  } finally { canvas.width = 0; canvas.height = 0; }
}

export function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? "").split(",", 2)[1]);
    reader.onerror = () => reject(new Error("image_file_read_failed"));
    reader.readAsDataURL(blob);
  });
}
