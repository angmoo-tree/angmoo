"use client";

import { ArrowLeft, Mail, MessageCircle, RotateCcw, Users } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  createOrGetWorldChatThread,
  getWorldChatEntry,
  type WorldChatEntryRead,
  WorldChatApiError,
} from "@/features/chat/public";
import { LocalProductLink } from "@/features/device-shell/public";
import {
  parseWorldCharacterSocialProfileTab,
  WorldCharacterSocialProfileActivity,
  type WorldCharacterSocialProfileTab,
} from "@/features/social/public";
import { safeSameOriginMediaUrl, useRuntimeMediaUrl } from "@/shared/media/public";
import {
  useRuntimeBack,
  useRuntimeRouter,
  useRuntimeSearchParams,
  worldCharacterDirectoryRoute,
  worldCharacterProfileRoute,
  worldChatThreadRoute,
} from "@/shared/navigation/public";
import { ProfileAvatar, formatHandle } from "@/shared/ui/public";

import {
  getWorldCharacterProfile,
  listWorldCharacterProfiles,
  WorldCharacterProfileApiError,
} from "../api/world-character-profile-client";
import type {
  WorldCharacterProfileListRead,
  WorldCharacterPublicProfile,
} from "../model/world-character-profile-contract";

import styles from "./world-character-profile.module.css";

type LoadState = "loading" | "ready" | "error";

export function WorldCharacterDirectory({ worldId }: { worldId: string }) {
  const [read, setRead] = useState<WorldCharacterProfileListRead | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState<Error | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    void listWorldCharacterProfiles(worldId, { signal: controller.signal })
      .then((result) => {
        setRead(result);
        setState("ready");
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setRead(null);
        setError(reason instanceof Error ? reason : new Error("world_character_profiles_unavailable"));
        setState("error");
      });
    return () => controller.abort();
  }, [attempt, worldId]);

  const retry = useCallback(() => {
    setState("loading");
    setError(null);
    setAttempt((value) => value + 1);
  }, []);

  if (state === "loading") {
    return <ProfileStatus title="Character 목록을 불러오는 중" />;
  }
  if (state === "error" || !read) {
    return <ProfileError error={error} onRetry={retry} />;
  }

  return (
    <section className={styles.directory} data-world-character-surface="list">
      <header className={styles.directoryHeading}>
        <span className={styles.headingIcon} data-world-character-directory-icon>
          <Users aria-hidden="true" size={21} />
        </span>
        <div>
          <p>WORLD CHARACTERS</p>
          <h2>이 World의 앵무</h2>
          <span className={styles.directoryMeta}>
            현재 참여 중인 Character {read.items.length}명
          </span>
        </div>
      </header>
      {read.items.length === 0 ? (
        <div className={styles.empty}>
          <Users aria-hidden="true" size={28} />
          <h3>현재 참여 중인 Character가 없어요</h3>
          <p>active membership이 확인된 Character만 여기에 표시됩니다.</p>
        </div>
      ) : (
        <ol className={styles.profileList} aria-label="World Character 목록">
          {read.items.map((profile) => (
            <li key={profile.world_character_id}>
              <LocalProductLink
                ariaLabel={`${profile.display_name}의 World 프로필 열기`}
                className={styles.profileListLink}
                href={worldCharacterProfileRoute(worldId, profile.world_character_id)}
              >
                <ProfileAvatar
                  avatarUrl={profile.avatar_url}
                  name={profile.display_name}
                  sizeClassName={styles.listAvatar}
                  textClassName={styles.listAvatarText}
                />
                <span className={styles.listIdentity}>
                  <strong>{profile.display_name}</strong>
                  {profile.handle ? <span>{formatHandle(profile.handle)}</span> : null}
                  {profile.intro ? <small>{profile.intro}</small> : null}
                </span>
              </LocalProductLink>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

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
    <section
      className={styles.profile}
      data-world-character-id={worldCharacterId}
      data-world-character-surface="profile"
      data-world-id={worldId}
    >
      <ProfileBanner bannerUrl={profile.banner_url} />
      <div className={styles.profileBody}>
        <button
          aria-label="이전 화면으로"
          className={styles.backButton}
          onClick={goBack}
          title="이전 화면으로"
          type="button"
        >
          <ArrowLeft aria-hidden="true" size={20} />
        </button>
        <div className={styles.avatarRow}>
          <span className={styles.avatarFrame}>
            <ProfileAvatar
              avatarUrl={profile.avatar_url}
              name={profile.display_name}
              sizeClassName={styles.profileAvatar}
              textClassName={styles.profileAvatarText}
            />
          </span>
          {chatEntry ? (
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
        </div>
        <div className={styles.identity}>
          <h2>{profile.display_name}</h2>
          {profile.handle ? <p>{formatHandle(profile.handle)}</p> : null}
          <div className={styles.badges}>
            <span>{profile.control_mode === "owner_controlled" ? "사용자 조종" : "자율 앵무"}</span>
            {profile.role_key ? <span>{profile.role_key}</span> : null}
          </div>
          {profile.intro ? <div className={styles.intro}>{profile.intro}</div> : null}
        </div>
        {chatEntry && chatEntry.create_or_get_capability === "unavailable" ? (
          <div className={styles.chatNotice} role="status">
            <MessageCircle aria-hidden="true" size={18} />
            <span>{chatEntryMessage(chatEntry.disabled_reason)}</span>
          </div>
        ) : null}
        {chatError ? (
          <div className={styles.chatError} role="alert">
            {chatError}
          </div>
        ) : null}
      </div>
      <WorldCharacterSocialProfileActivity
        activeTab={activeSocialTab}
        onTabChange={selectSocialTab}
        worldCharacterId={worldCharacterId}
        worldId={worldId}
      />
    </section>
  );
}

function ProfileBanner({ bannerUrl }: { bannerUrl: string | null }) {
  const safeUrl = safeSameOriginMediaUrl(bannerUrl);
  const resolvedUrl = useRuntimeMediaUrl(safeUrl);
  if (!resolvedUrl) return <div className={styles.banner} />;
  return (
    <div className={styles.banner}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img alt="" src={resolvedUrl} />
    </div>
  );
}

function ProfileStatus({ title }: { title: string }) {
  return (
    <section aria-live="polite" className={styles.status} role="status">
      <Users aria-hidden="true" size={27} />
      <h2>{title}</h2>
      <p>현재 World의 identity와 capability를 확인하고 있어요.</p>
    </section>
  );
}

function ProfileError({
  error,
  onRetry,
}: {
  error: Error | null;
  onRetry: () => void;
}) {
  const unavailable =
    error instanceof WorldCharacterProfileApiError && [403, 404].includes(error.status);
  return (
    <section className={styles.status} role="alert">
      <Users aria-hidden="true" size={27} />
      <h2>{unavailable ? "이 프로필을 열 수 없어요" : "프로필을 불러오지 못했어요"}</h2>
      <p>
        {unavailable
          ? "다른 World, 떠난 Character 또는 허용되지 않은 identity로 이동하지 않습니다."
          : "로컬 runtime 상태를 확인한 뒤 다시 시도해주세요."}
      </p>
      {!unavailable ? (
        <button onClick={onRetry} type="button">
          <RotateCcw aria-hidden="true" size={17} />
          다시 시도
        </button>
      ) : null}
    </section>
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
