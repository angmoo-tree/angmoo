import {
  fetchAuthenticatedMediaObjectUrl,
  type AgentCreationDraftMediaResult,
} from "@/lib/agents";

export type GeneratedMediaCandidate = {
  id: string;
  mediaType: "avatar" | "banner";
  objectUrl: string;
  width: number | null;
  height: number | null;
};

export async function generatedMediaCandidateFromResult(
  result: AgentCreationDraftMediaResult,
): Promise<GeneratedMediaCandidate> {
  if (!result.candidate_id || !result.candidate_url) {
    throw new Error("생성된 이미지 후보가 없습니다.");
  }
  return {
    id: result.candidate_id,
    mediaType: result.media_type,
    objectUrl: await fetchAuthenticatedMediaObjectUrl(result.candidate_url),
    width: result.width,
    height: result.height,
  };
}

export function revokeGeneratedMediaCandidate(
  candidate: GeneratedMediaCandidate | null,
) {
  if (candidate?.objectUrl.startsWith("blob:")) {
    URL.revokeObjectURL(candidate.objectUrl);
  }
}
