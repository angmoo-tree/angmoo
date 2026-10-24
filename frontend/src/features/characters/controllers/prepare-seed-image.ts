import { readFileInput, withFileInputDeadline } from "@/lib/media/read-file-input";
import { inputBase64 } from "../utils/input-base64";

/** 8,000,000 base64 characters is the DTO ceiling; the server's configured byte cap still applies. */
export function prepareSeedImage(file: File, signal: AbortSignal) {
  return withFileInputDeadline(signal, 30_000, async scope => {
    const buffer = await readFileInput(file, 6_000_000, scope);
    if (!buffer.byteLength) throw new Error("이미지 파일이 비어 있어요. 다른 사진을 선택해 주세요.");
    return { filename: file.name, content_type: file.type || "application/octet-stream", data_base64: inputBase64(buffer, scope.check) };
  });
}
