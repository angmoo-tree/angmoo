import { readFileInput, withFileInputDeadline } from "@/lib/media/read-file-input";
import { inputBase64 } from "../utils/input-base64";

/** The card parser, not an image codec, receives the exact original PNG/JSON bytes. */
export function prepareCardInput(file: File, signal: AbortSignal): Promise<string> {
  return withFileInputDeadline(signal, 30_000, async scope => {
    const buffer = await readFileInput(file, 20 * 1024 * 1024, scope);
    if (!buffer.byteLength) throw new Error("카드 파일이 비어 있어요. 다른 카드를 선택해 주세요.");
    return inputBase64(buffer, scope.check);
  });
}
