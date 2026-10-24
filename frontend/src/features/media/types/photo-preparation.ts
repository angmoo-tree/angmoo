import type { PhotoErrorCode } from "../utils/photo-header";

export type PhotoPreparationRequest = { kind: "prepare"; buffer: ArrayBuffer };
export type PhotoPreparationResponse =
  | { kind: "prepared"; blob: Blob }
  | { kind: "failed"; error: PhotoErrorCode };

/** The file is owned memory produced by preparation, never the external picker File. */
export type PreparedImageUpload = { file: File };
