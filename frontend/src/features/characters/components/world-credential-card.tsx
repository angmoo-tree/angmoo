"use client";
import { KeyRound, MessagesSquare, ScanEye } from "lucide-react";
import { SettingsCard } from "@/components/ui/settings-card";
import { CredentialFields, type SecretProfile, type CredentialMetadataState } from "@/components/ui/credential-fields";
import { useUiText } from "@/hooks/use-ui-text";
import { worldCredentialTransport, type CredentialPurpose } from "../api/world-credentials";

export const TEXT_PROFILES: readonly SecretProfile[] = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"].flatMap(model => ["high", "medium"].map(thinking_level => ({
  provider: "google", model, thinking_level, label: `${model === "gemini-3.5-flash-lite" ? "Gemini 3.5" : "Gemini 3.1"} Flash-Lite (${thinking_level})`,
})));
export function WorldCredentialCard({ worldId, actorId, purpose, children, onSaved, onBusyChange, refreshRevision, externalBusy, onMetadataState }: { worldId: string; actorId: string; purpose: Exclude<CredentialPurpose, "image">; children?: React.ReactNode; onSaved?: () => void; onBusyChange?: (busy: boolean) => void; refreshRevision?: number; externalBusy?: boolean; onMetadataState?: (state: CredentialMetadataState) => void }) {
  const t = useUiText("characters");
  const title = { sns: "캐릭터 활동 API key", chat: "채팅용 API key", vision: "SNS·Chat 이미지 인식 API key" }[purpose];
  return <SettingsCard elevated title={t(title)} description={t("이 World 캐릭터의 키와 모델을 설정해요.")} icon={purpose === "vision" ? <ScanEye size={20} /> : purpose === "chat" ? <MessagesSquare size={20} /> : <KeyRound size={20} />}>
    <CredentialFields onMetadataState={onMetadataState} refreshRevision={refreshRevision} externalBusy={externalBusy} scopeKey={`${worldId}:${actorId}:${purpose}`} profiles={TEXT_PROFILES} onSaved={onSaved} onBusyChange={onBusyChange} {...worldCredentialTransport(worldId, actorId, purpose)}
      text={{ loadFailed: t("설정을 불러오지 못했어요."), keyLoadFailed: t("키 상태를 불러오지 못했어요."), saveFailed: t("설정을 저장하지 못했어요. 입력을 확인해 주세요."), deleteFailed: t("키를 삭제하지 못했어요."), conflict: t("설정이 변경됐어요. 최신 내용을 확인해 주세요."), unknown: t("요청 결과를 확인하지 못했어요. 다시 저장하기 전에 현재 상태를 확인해 주세요."), review: t("최신 값을 확인했어요. 내 입력 유지"), model: t("Google AI 모델"), key: t("새 API key"), stored: t("API key 저장됨"), missing: t("API key 없음"), save: t("모델 저장"), remove: t("저장된 key 삭제"), confirm: t("이 용도의 API key를 삭제할까요?"), failed: t("저장하지 못했어요. 최신 설정을 확인해 주세요."), saved: t("설정을 저장했어요."), keep: t("비워 두면 저장된 키를 유지해요."), unsupported: t("현재 저장된 모델"), reload: t("다시 불러오기") }} />
    {children}
  </SettingsCard>;
}
