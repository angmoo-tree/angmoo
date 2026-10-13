import { checkPhotoDimensions, PhotoPreparationError, INPUT_PIXELS } from "./photo-header";

/** The pinned libheif WASM32 C ABI. C pointers never cross its Embind API. */
type HeifModule = {
  HEAPU8: Uint8Array;
  HEAP32: Int32Array;
  _malloc: (bytes: number) => number;
  _free: (pointer: number) => void;
  _heif_context_alloc: () => number;
  _heif_context_get_security_limits: (context: number) => number;
  _heif_context_free: (context: number) => void;
  _heif_context_read_from_memory: (error: number, context: number, bytes: number, length: number, options: number) => void;
  _heif_context_get_primary_image_handle: (error: number, context: number, handle: number) => void;
  _heif_image_handle_get_width: (handle: number) => number;
  _heif_image_handle_get_height: (handle: number) => number;
  _heif_image_handle_has_alpha_channel: (handle: number) => number;
  _heif_image_handle_release: (handle: number) => void;
  _heif_image_release: (image: number) => void;
  _heif_decode_image: (error: number, handle: number, image: number, colorspace: number, chroma: number, options: number) => void;
  _heif_image_get_plane_readonly: (image: number, channel: number, stride: number) => number;
};
export async function decodeHeifPrimary(bytes: Uint8Array): Promise<{ canvas: OffscreenCanvas; hasAlpha: boolean }> {
  // Only this branch loads the embedded local WASM. No network conversion or CDN.
  const { default: factory } = await import("libheif-js/libheif-wasm/libheif-bundle.mjs");
  const lib = await factory({ print: () => undefined, printErr: () => undefined }) as HeifModule;
  const context = lib._heif_context_alloc();
  let input = 0, error = 0, output = 0, handle = 0, decoded = 0;
  if (!context) throw new PhotoPreparationError("photo_codec");
  const checkError = () => {
    const code = lib.HEAP32[error >>> 2];
    if (code) throw new PhotoPreparationError(code === 4 ? "photo_codec" : "photo_damaged");
  };
  try {
    const pointer = lib._heif_context_get_security_limits(context);
    const limits = new DataView(lib.HEAPU8.buffer);
    if (!pointer || limits.getUint8(pointer) < 2) throw new PhotoPreparationError("photo_codec");
    // Official heif_security_limits layout: uint64 aligned at 8 in WASM32.
    // Keep all other codec defaults. Configure before parsing or allocating pixels.
    limits.setBigUint64(pointer + 8, BigInt(INPUT_PIXELS), true);
    limits.setBigUint64(pointer + 40, BigInt(512 * 1024 * 1024), true);
    limits.setBigUint64(pointer + 64, BigInt(512 * 1024 * 1024), true);
    input = lib._malloc(bytes.length); error = lib._malloc(12); output = lib._malloc(4);
    if (!input || !error || !output) throw new PhotoPreparationError("photo_codec");
    lib.HEAPU8.set(bytes, input);
    // heif_error uses a 12-byte structure return pointer in the WASM32 C ABI.
    lib._heif_context_read_from_memory(error, context, input, bytes.length, 0); checkError();
    lib._heif_context_get_primary_image_handle(error, context, output); checkError();
    handle = lib.HEAP32[output >>> 2];
    if (!handle) throw new PhotoPreparationError("photo_damaged");
    const width = lib._heif_image_handle_get_width(handle), height = lib._heif_image_handle_get_height(handle);
    checkPhotoDimensions(width, height);
    const hasAlpha = Boolean(lib._heif_image_handle_has_alpha_channel(handle));
    // Public enum values: RGB=1, interleaved RGBA=11, interleaved channel=10.
    lib._heif_decode_image(error, handle, output, 1, 11, 0); checkError();
    decoded = lib.HEAP32[output >>> 2];
    if (!decoded) throw new PhotoPreparationError("photo_damaged");
    const plane = lib._heif_image_get_plane_readonly(decoded, 10, output);
    const stride = lib.HEAP32[output >>> 2];
    if (!plane || stride < width * 4 || plane + stride * height > lib.HEAPU8.byteLength) throw new PhotoPreparationError("photo_damaged");
    const pixels = new Uint8ClampedArray(width * height * 4);
    for (let row = 0; row < height; row++) pixels.set(lib.HEAPU8.subarray(plane + row * stride, plane + row * stride + width * 4), row * width * 4);
    const canvas = new OffscreenCanvas(width, height), ctx = canvas.getContext("2d");
    if (!ctx) throw new PhotoPreparationError("photo_preparation");
    ctx.putImageData(new ImageData(pixels, width, height), 0, 0); return { canvas, hasAlpha };
  } finally {
    if (decoded) lib._heif_image_release(decoded);
    if (handle) lib._heif_image_handle_release(handle);
    if (output) lib._free(output);
    if (error) lib._free(error);
    if (input) lib._free(input);
    lib._heif_context_free(context);
  }
}
