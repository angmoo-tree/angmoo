/** Encode already owned bytes without decoding or changing PNG-card metadata. */
export function inputBase64(buffer: ArrayBuffer, check: () => void): string {
  const bytes = new Uint8Array(buffer);
  const parts: string[] = [];
  for (let offset = 0; offset < bytes.length; offset += 32 * 1024) {
    check();
    parts.push(String.fromCharCode(...bytes.subarray(offset, offset + 32 * 1024)));
  }
  const encoded = btoa(parts.join(""));
  check();
  return encoded;
}
