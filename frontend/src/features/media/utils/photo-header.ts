/** Bounded container inspection before invoking any pixel decoder. */
export const ORIGINAL_PHOTO_BYTES = 20 * 1024 * 1024;
export const ATTACHMENT_PHOTO_BYTES = 10 * 1024 * 1024;
export const PHOTO_REQUEST_BYTES = 14 * 1024 * 1024;
export const INPUT_PIXELS = 64_000_000;
export type PhotoErrorCode = "photo_original_large" | "photo_unsupported" | "photo_damaged" | "photo_animated" | "photo_dimensions" | "photo_codec" | "photo_timeout" | "photo_preparation";
export class PhotoPreparationError extends Error {
  constructor(readonly code: PhotoErrorCode) { super(code); this.name = "PhotoPreparationError"; }
}
export function checkPhotoDimensions(width: number, height: number) {
  if (!Number.isSafeInteger(width) || !Number.isSafeInteger(height) || width < 1 || height < 1) throw new PhotoPreparationError("photo_damaged");
  if (width > 16384 || height > 16384 || width * height > INPUT_PIXELS) throw new PhotoPreparationError("photo_dimensions");
}
export function inspectPhoto(buffer: ArrayBuffer): { mime: string; width: number; height: number; orientation: number } {
  const v = new DataView(buffer), bytes = new Uint8Array(buffer);
  const damaged = () => { throw new PhotoPreparationError("photo_damaged"); };
  const text = (at: number, length: number) => String.fromCharCode(...bytes.subarray(at, at + length));
  const finish = (mime: string, width: number, height: number, orientation = 1) => { checkPhotoDimensions(width, height); return { mime, width, height, orientation }; };
  if (bytes.length < 12) return damaged();
  if (text(0, 8) === "\x89PNG\r\n\x1a\n") {
    let width = 0, height = 0, ended = false;
    for (let at = 8, count = 0; at + 12 <= bytes.length && count++ < 100000;) {
      const length = v.getUint32(at), kind = text(at + 4, 4), end = at + length + 12;
      if (end > bytes.length) return damaged();
      if (kind === "IHDR") { if (length !== 13 || at !== 8) return damaged(); width = v.getUint32(at + 8); height = v.getUint32(at + 12); }
      if (kind === "acTL") throw new PhotoPreparationError("photo_animated");
      if (kind === "IEND") { ended = true; break; }
      at = end;
    }
    if (!ended) return damaged(); return finish("image/png", width, height);
  }
  if (text(0, 4) === "RIFF" && text(8, 4) === "WEBP") {
    if (v.getUint32(4, true) + 8 !== bytes.length) return damaged();
    let width = 0, height = 0;
    for (let at = 12; at + 8 <= bytes.length;) {
      const kind = text(at, 4), length = v.getUint32(at + 4, true), p = at + 8;
      if (p + length > bytes.length) return damaged();
      if (kind === "ANIM" || kind === "ANMF" || kind === "VP8X" && (bytes[p] & 2)) throw new PhotoPreparationError("photo_animated");
      if (kind === "VP8X" && length >= 10) { width = 1 + bytes[p + 4] + (bytes[p + 5] << 8) + (bytes[p + 6] << 16); height = 1 + bytes[p + 7] + (bytes[p + 8] << 8) + (bytes[p + 9] << 16); }
      if (kind === "VP8 " && length >= 10 && !width) { if (text(p + 3, 3) !== "\x9d\x01\x2a") return damaged(); width = v.getUint16(p + 6, true) & 0x3fff; height = v.getUint16(p + 8, true) & 0x3fff; }
      if (kind === "VP8L" && length >= 5 && !width) { if (bytes[p] !== 0x2f) return damaged(); const n = v.getUint32(p + 1, true); width = (n & 0x3fff) + 1; height = ((n >>> 14) & 0x3fff) + 1; }
      at = p + length + (length & 1);
    }
    return finish("image/webp", width, height);
  }
  if (bytes[0] === 0xff && bytes[1] === 0xd8) {
    let width = 0, height = 0, orientation = 1;
    for (let at = 2, count = 0; at + 4 <= bytes.length && count++ < 100000;) {
      if (bytes[at] !== 0xff) return damaged();
      while (bytes[at] === 0xff) at++;
      const marker = bytes[at++]; if (marker === 0xda || marker === 0xd9) break;
      if (marker === 0x01 || marker >= 0xd0 && marker <= 0xd7) continue;
      if (at + 2 > bytes.length) return damaged(); const length = v.getUint16(at), p = at + 2;
      if (length < 2 || at + length > bytes.length) return damaged();
      if ([0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf].includes(marker)) { if (length < 8) return damaged(); height = v.getUint16(p + 1); width = v.getUint16(p + 3); }
      if (marker === 0xe1 && text(p, 6) === "Exif\0\0" && length >= 16) {
        const base = p + 6, little = text(base, 2) === "II";
        if (!little && text(base, 2) !== "MM") return damaged();
        const ifd = base + v.getUint32(base + 4, little);
        if (ifd + 2 > at + length) return damaged();
        const entries = v.getUint16(ifd, little);
        if (ifd + 2 + entries * 12 > at + length) return damaged();
        for (let i = 0; i < entries; i++) { const entry = ifd + 2 + i * 12; if (v.getUint16(entry, little) === 0x112) { orientation = v.getUint16(entry + 8, little); if (orientation < 1 || orientation > 8) return damaged(); } }
      }
      at += length;
    }
    return finish("image/jpeg", width, height, orientation);
  }
  if (text(4, 4) === "ftyp") {
    const length = v.getUint32(0); if (length < 16 || length > bytes.length || length > 256) return damaged();
    const brands = [text(8, 4)]; for (let at = 16; at + 4 <= length; at += 4) brands.push(text(at, 4));
    if (brands.some(b => ["msf1", "hevc", "hevx"].includes(b))) throw new PhotoPreparationError("photo_animated");
    if (!brands.some(b => ["heic", "heix", "mif1"].includes(b))) throw new PhotoPreparationError("photo_unsupported");
    let width = 0, height = 0, count = 0, meta = false;
    function boxes(start: number, end: number, depth: number) {
      if (depth > 8) return damaged();
      for (let at = start; at < end;) {
        if (at + 8 > end || ++count > 10000) return damaged();
        let size = v.getUint32(at), head = 8; const kind = text(at + 4, 4);
        if (size === 1) { if (at + 16 > end) return damaged(); const n = v.getBigUint64(at + 8); if (n > BigInt(bytes.length)) return damaged(); size = Number(n); head = 16; }
        if (size === 0) size = end - at;
        if (size < head || at + size > end) return damaged();
        if (kind === "moov") throw new PhotoPreparationError("photo_animated");
        if (kind === "ispe") { if (size < head + 12) return damaged(); const w = v.getUint32(at + head + 4), h = v.getUint32(at + head + 8); checkPhotoDimensions(w, h); if (w * h > width * height) { width = w; height = h; } }
        if (["meta", "iprp", "ipco"].includes(kind)) { if (kind === "meta") meta = true; boxes(at + head + (kind === "meta" ? 4 : 0), at + size, depth + 1); }
        at += size;
      }
    }
    boxes(0, bytes.length, 0); if (!meta) return damaged();
    return finish("image/heif", width, height);
  }
  throw new PhotoPreparationError("photo_unsupported");
}
