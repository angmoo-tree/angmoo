"use client";

import { Mail, MessageCircle, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { createOrGetWorldChatThread, getWorldChatEntry, type WorldChatEntryRead, WorldChatApiError } from "@/features/chat/public";
import { parseWorldCharacterSocialProfileTab } from "@/features/social/utils/world-character-social-profile";
import { WorldCharacterSocialProfileActivity } from "@/features/social/components/world-character-social-profile-activity";
import { type WorldCharacterSocialProfileTab } from "@/features/social/types/world-character-social-profile-contract";
import { useRuntimeBack, useRuntimeRouter, useRuntimeSearchParams } from "@/hooks/use-runtime-navigation";
import { worldCharacterDirectoryRoute, worldCharacterProfileRoute, worldChatThreadRoute } from "@/lib/navigation/product-routes";
import { getWorldCharacterProfile } from "@/features/characters/api/world-character-profile-client";
import type { WorldCharacterPublicProfile } from "@/features/characters/types/world-character-profile";
import { ProfileStatus, ProfileError } from "@/features/characters/components/world-character-directory";
import { WorldCharacterProfileCard } from "@/features/characters/components/world-character-profile-card";
import styles from "@/features/characters/components/world-character-profile.module.css";

type LoadState = "loading" | "ready" | "error";

export function WorldCharacterProfile({
  worldCharacterId,
  worldId,
}: {
  worldCharacterId: string;
  worldId: string;
}) {
  const router = useRuntimeRouter();
  const goBack = useRuntimeBack(worldCharacterDirectoryRoute(worldId));
  const searchParams = useRuntimeSearchParams();
  const activeSocialTab = parseWorldCharacterSocialProfileTab(
    searchParams.get("tab"),
  );
  const [profile, setProfile] = useState<WorldCharacterPublicProfile | null>(null);
  const [chatEntry, setChatEntry] = useState<WorldChatEntryRead | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState<Error | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);
  const [chatStarting, setChatStarting] = useState(false);
  const chatStartInFlightRef = useRef(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    void Promise.allSettled([
      getWorldCharacterProfile(worldId, worldCharacterId, {
        signal: controller.signal,
      }),
      getWorldChatEntry(worldId, worldCharacterId, {
        signal: controller.signal,
      }),
    ]).then(([profileResult, entryResult]) => {
      if (controller.signal.aborted) return;
      if (profileResult.status === "rejected") {
        setProfile(null);
        setError(
          profileResult.reason instanceof Error
            ? profileResult.reason
            : new Error("world_character_profile_unavailable"),
        );
        setState("error");
        return;
      }
      setProfile(profileResult.value);
      setChatEntry(entryResult.status === "fulfilled" ? entryResult.value : null);
      setChatError(
        entryResult.status === "rejected"
          ? "채팅 가능 상태를 확인하지 못했어요. 잠시 후 다시 열어주세요."
          : null,
      );
      setState("ready");
    });
    return () => controller.abort();
  }, [attempt, worldCharacterId, worldId]);

  const retry = useCallback(() => {
    setState("loading");
    setError(null);
    setChatError(null);
    setAttempt((value) => value + 1);
  }, []);

  const selectSocialTab = useCallback(
    (tab: WorldCharacterSocialProfileTab) => {
      const next = new URLSearchParams(searchParams.toString());
      if (tab === "posts") next.delete("tab");
      else next.set("tab", tab);
      const query = next.toString();
      const pathname = worldCharacterProfileRoute(worldId, worldCharacterId);
      router.replace(query ? `${pathname}?${query}` : pathname);
    },
    [router, searchParams, worldCharacterId, worldId],
  );

  async function startChat() {
    if (
      !chatEntry ||
      chatEntry.create_or_get_capability !== "available" ||
      !chatEntry.requester ||
      chatStartInFlightRef.current
    ) {
      return;
    }
    chatStartInFlightRef.current = true;
    setChatStarting(true);
    setChatError(null);
    try {
      const result = await createOrGetWorldChatThread(worldId, {
        responding_world_character_id: worldCharacterId,
        requester_world_character_id: chatEntry.requester.world_character_id,
      });
      if (result.thread) {
        router.push(worldChatThreadRoute(worldId, result.thread.id));
        return;
      }
      setChatError(resolutionMessage(result.resolution_code));
    } catch (reason) {
      setChatError(chatStartError(reason));
    } finally {
      chatStartInFlightRef.current = false;
      setChatStarting(false);
    }
  }

  if (state === "loading") {
    return <ProfileStatus title="WorldCharacter 프로필을 불러오는 중" />;
  }
  if (state === "error" || !profile) {
    return <ProfileError error={error} onRetry={retry} />;
  }

  return (
    <WorldCharacterProfileCard
      profile={profile}
      worldId={worldId}
      worldCharacterId={worldCharacterId}
      onBack={goBack}
      chatAction={chatEntry ? (
            <button
              aria-label={`${profile.display_name}와 채팅 시작`}
              className={styles.letterButton}
              data-chat-entry-capability={chatEntry.create_or_get_capability}
              disabled={
                chatEntry.create_or_get_capability !== "available" || chatStarting
              }
              onClick={() => void startChat()}
              title="채팅 시작"
              type="button"
            >
              {chatStarting ? (
                <RotateCcw aria-hidden="true" className={styles.spin} size={20} />
              ) : (
                <Mail aria-hidden="true" size={20} />
              )}
            </button>
          ) : null}
      chatNotice={<>{chatEntry && chatEntry.create_or_get_capability === "unavailable" ? (
          <div className={styles.chatNotice} role="status">
            <MessageCircle aria-hidden="true" size={18} />
            <span>{chatEntryMessage(chatEntry.disabled_reason)}</span>
          </div>
        ) : null}
        {chatError ? (
          <div className={styles.chatError} role="alert">
            {chatError}
          </div>
        ) : null}</>}
    >
      <WorldCharacterSocialProfileActivity
        activeTab={activeSocialTab}
        onTabChange={selectSocialTab}
        worldCharacterId={worldCharacterId}
        worldId={worldId}
      />
    </WorldCharacterProfileCard>
  );
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
