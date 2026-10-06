"use client";

import { Mail, MessageCircle, Network, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { LocalProductLink } from "@/components/navigation/local-product-link";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT } from "@/lib/runtime/runtime-config";
import { useProductLeaveGuard } from "@/hooks/use-product-leave-guard";
import { useUiText } from "@/hooks/use-ui-text";
import { createOrGetWorldChatThread, getWorldChatEntry, WorldChatApiError } from "@/features/chat/api/world-chat-client";
import type { WorldChatEntryRead } from "@/features/chat/types/world-chat-contract";
import { parseWorldCharacterSocialProfileTab } from "@/features/social/utils/world-character-social-profile";
import { WorldCharacterSocialProfileActivity } from "@/features/social/components/world-character-social-profile-activity";
import type { WorldCharacterSocialProfileTab } from "@/features/social/types/world-character-social-profile-contract";
import { useRuntimeRouter, useRuntimeSearchParams } from "@/hooks/use-runtime-navigation";
import { relationshipGraphRoute, worldCharacterProfileRoute, worldChatThreadRoute } from "@/lib/navigation/product-routes";
import type { WorldCharacterPublicProfile } from "@/features/characters/types/world-character-profile";
import { WorldCharacterProfileCard } from "@/features/characters/components/world-character-profile-card";
import styles from "@/features/characters/components/world-character-profile.module.css";

export function WorldCharacterProfile({ worldCharacterId, worldId, profile, canViewGraph, onEditProfile }: {
  worldCharacterId: string; worldId: string; profile: WorldCharacterPublicProfile; canViewGraph: boolean; onEditProfile?: () => void;
}) {
  const uiText = useUiText("shell");
  const router = useRuntimeRouter(), searchParams = useRuntimeSearchParams();
  const activeSocialTab = parseWorldCharacterSocialProfileTab(searchParams.get("tab"));
  const [chatEntry, setChatEntry] = useState<WorldChatEntryRead | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);
  const [chatStarting, setChatStarting] = useState(false);
  const chatStartInFlight = useRef(false), generation = useRef(0);
  const releaseLeaveGuard = useProductLeaveGuard(chatStarting);

  useEffect(() => {
    const controller = new AbortController(), currentGeneration = ++generation.current;
    const scope = captureAuthRequestScope();
    const clear = () => { generation.current += 1; controller.abort(); setChatEntry(null); setChatError(null); setChatStarting(false); };
    void getWorldChatEntry(worldId, worldCharacterId, { signal: controller.signal }).then(read => {
      if (!controller.signal.aborted && currentGeneration === generation.current && isCurrentAuthRequestScope(scope)) setChatEntry(read);
    }).catch(() => {
      if (!controller.signal.aborted && currentGeneration === generation.current && isCurrentAuthRequestScope(scope)) setChatError("채팅 가능 상태를 확인하지 못했어요. 잠시 후 다시 열어주세요.");
    });
    window.addEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, clear);
    return () => { generation.current += 1; controller.abort(); window.removeEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, clear); };
  }, [worldCharacterId, worldId]);

  const selectSocialTab = useCallback((tab: WorldCharacterSocialProfileTab) => {
    const next = new URLSearchParams(searchParams.toString());
    if (tab === "posts") next.delete("tab"); else next.set("tab", tab);
    const query = next.toString(), pathname = worldCharacterProfileRoute(worldId, worldCharacterId);
    router.replace(query ? `${pathname}?${query}` : pathname);
  }, [router, searchParams, worldCharacterId, worldId]);

  async function startChat() {
    if (!chatEntry || chatEntry.create_or_get_capability !== "available" || !chatEntry.requester || chatStartInFlight.current) return;
    chatStartInFlight.current = true; setChatStarting(true); setChatError(null);
    const currentGeneration = generation.current, scope = captureAuthRequestScope();
    try {
      const result = await createOrGetWorldChatThread(worldId, { responding_world_character_id: worldCharacterId,
        requester_world_character_id: chatEntry.requester.world_character_id });
      if (currentGeneration !== generation.current || !isCurrentAuthRequestScope(scope)) return;
      if (result.thread) { releaseLeaveGuard(); router.push(worldChatThreadRoute(worldId, result.thread.id)); return; }
      setChatError(resolutionMessage(result.resolution_code));
    } catch (reason) {
      if (currentGeneration === generation.current && isCurrentAuthRequestScope(scope)) setChatError(chatStartError(reason));
    } finally {
      if (currentGeneration === generation.current) { chatStartInFlight.current = false; setChatStarting(false); }
    }
  }

  const isUser = profile.control_mode === "owner_controlled";
  const actions = <>
    {canViewGraph ? <LocalProductLink href={relationshipGraphRoute(profile.character_id, worldId)}
      ariaLabel={uiText("{{value0}}의 관계망 보기", { value0: profile.display_name })} title={uiText("관계망 보기")}
      className={styles.letterButton} data-profile-action="relationships"><Network aria-hidden="true" size={20} /></LocalProductLink> : null}
    {!isUser && chatEntry ? <button aria-label={uiText("{{value0}}와 채팅 시작", { value0: profile.display_name })}
      title={uiText("채팅 시작")} className={styles.letterButton} data-profile-action="mail" data-chat-entry-capability={chatEntry.create_or_get_capability}
      disabled={chatEntry.create_or_get_capability !== "available" || chatStarting} onClick={() => void startChat()} type="button">
      {chatStarting ? <RotateCcw aria-hidden="true" className={styles.spin} size={20} /> : <Mail aria-hidden="true" size={20} />}
    </button> : null}
    {onEditProfile ? <Button variant="secondary" onClick={onEditProfile} data-profile-action="edit">{uiText(isUser ? "내 프로필 편집" : "프로필 수정")}</Button> : null}
  </>;
  const notice = <>
    {chatEntry && !isUser && chatEntry.create_or_get_capability === "unavailable" ? <div className={styles.chatNotice} role="status">
      <MessageCircle aria-hidden="true" size={18} /><span>{uiText(chatEntryMessage(chatEntry.disabled_reason))}</span></div> : null}
    {chatError ? <div className={styles.chatError} role="alert">{uiText(chatError)}</div> : null}
  </>;
  return <WorldCharacterSocialProfileActivity activeTab={activeSocialTab} onTabChange={selectSocialTab} worldCharacterId={worldCharacterId} worldId={worldId}
    renderProfile={metrics => <WorldCharacterProfileCard profile={profile} worldId={worldId} worldCharacterId={worldCharacterId}
      profileActions={actions} metrics={metrics} chatNotice={notice} />} />;
}

function chatEntryMessage(reason: WorldChatEntryRead["disabled_reason"]) {
  const messages: Record<Exclude<WorldChatEntryRead["disabled_reason"], null>, string> = {
    requester_missing: "이 World에서 조종하는 앵무를 먼저 연결해 주세요.",
    requester_cardinality_anomaly: "조종 앵무 identity를 하나로 정리한 뒤 대화를 시작할 수 있어요.",
    self_target: "같은 WorldCharacter 자신과는 대화를 시작할 수 없어요.",
    blocked: "이 Character와는 지금 대화를 시작할 수 없어요.",
    target_not_chat_capable: "이 Character는 현재 채팅을 시작할 수 없어요.",
  };
  return reason ? messages[reason] : "현재 채팅을 시작할 수 없어요.";
}

function resolutionMessage(
  code: "requester_missing" | "requester_cardinality_anomaly" | null,
) {
  if (code === "requester_missing") {
    return "이 World에서 조종하는 앵무를 먼저 연결해 주세요.";
  }
  if (code === "requester_cardinality_anomaly") {
    return "조종 앵무 identity를 하나로 정리한 뒤 다시 시도해 주세요.";
  }
  return "대화 역할을 확인하지 못했어요.";
}

function chatStartError(reason: unknown) {
  if (reason instanceof WorldChatApiError) {
    if (reason.status === 403 || reason.status === 404) {
      return "이 Character와는 지금 대화를 시작할 수 없어요.";
    }
    if (reason.status === 409) return "대화 한도를 확인해 주세요.";
  }
  return "대화를 시작하지 못했어요. 잠시 후 다시 시도해 주세요.";
}
