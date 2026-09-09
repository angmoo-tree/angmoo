"use client";
import { generationProfileValue } from "@/config/generation-profiles";
import { PersonaField } from "@/features/characters/components/persona-field";
import { PERSONA_LIMITS } from "@/features/characters/utils/persona-limits";
import { LocalProductLink } from "@/components/navigation/local-product-link";
import { ProfileAvatar } from "@/components/ui/profile-avatar";
import { EXPERIMENTAL_IMAGE_ENABLED } from "@/config/features";
import {
PROMOTION_USAGE_POLICY_URL
} from "@/config/policy-links";
import { deleteAgentLoreSource,getAgentLoreStatus,listAgentLoreSources,rebuildAgentLoreSource,uploadAgentLoreSource } from "@/features/characters/api/agents";
import { AgentActivityList } from "@/features/characters/components/agent-activity-list";
import { GeneratedMediaPreviewCard } from "@/features/characters/components/generated-media-preview-card";
import { ProfileMediaUploader } from "@/features/characters/components/profile-media-uploader";
import { DEFAULT_USER_IMAGE_MODEL,REPLICATE_API_TOKEN_GUIDE_URL,REPLICATE_API_TOKEN_URL,REPLICATE_PRICING_URL,USER_IMAGE_MODELS,type GoogleGeminiModel,type PollinationsImageModel } from "@/features/characters/config/model-options";
import { type AgentCreationDraftImageStyle,type AgentDetailRead,type AgentLocalConnectionRead,type AgentProfileImageUsageRead,type AgentProfileMediaUploadInput,type CharacterLoreSourceRead,type CharacterLoreStatusRead } from "@/features/characters/types/agents";
import { formatActionLabel } from "@/features/characters/utils/activity";
import {
type GeneratedMediaCandidate
} from "@/features/characters/utils/generated-media";
import { useContainerIncrementalCount } from "@/hooks/use-incremental-list";
import { useRuntimeMediaUrl } from "@/hooks/use-runtime-media-url";
import { safeSameOriginMediaUrl } from "@/lib/media/safe-media-url";
import { getRuntimeConfig } from "@/lib/runtime/runtime-config";
import { formatDate,formatHandle } from "@/utils/profile-presentation";
import {
AlertTriangle,
Copy,
ExternalLink,
FileText,
ImageIcon,
KeyRound,
Loader2,
Megaphone,
RotateCcw,
Save,
Sparkles,
Trash2,
Upload,
X
} from "lucide-react";
import Link from "next/link";
import type { FormEvent,ReactNode } from "react";
import { useCallback,useEffect,useState } from "react";

export type AgentDetailTab = "profile" | "status" | "settings";

export const DEVICE_SCROLL_OWNER_SELECTOR = '[data-device-scroll-owner="true"]';

export const RUN_NOW_SCHEDULER_GUARD_MS = 10 * 60 * 1000;

export const AGENT_TABS: Array<{
  key: AgentDetailTab;
  label: string;
}> = [
  { key: "profile", label: "프로필" },
  { key: "status", label: "상태" },
  { key: "settings", label: "설정" },
];

export function asGoogleGeminiModel(value: string | undefined, thinking = "high"): GoogleGeminiModel {
  return generationProfileValue(value, thinking);
}

export function asPollinationsImageModel(value: string | undefined): PollinationsImageModel {
  if (USER_IMAGE_MODELS.some((option) => option.value === value)) {
    return value as PollinationsImageModel;
  }
  if (value === "p-image-edit") {
    return "replicate-p-image-edit";
  }
  return DEFAULT_USER_IMAGE_MODEL;
}

export const VISUAL_IDENTITY_PLACEHOLDER =
  "예: Rendering style: Japanese TV anime-inspired 2D cel-shaded illustration. Do not render as: photorealistic, live-action. Character identity: small blue parrot-like character. Stable traits: blue feathers, round silver glasses, green scarf.";

export function getVisualIdentityUi(
  imageSettings: AgentDetailRead["image_settings"],
  isLocalAgent: boolean,
) {
  const isManual = imageSettings.visual_identity_mode === "manual";
  const status =
    imageSettings.visual_identity_mode === "manual"
      ? "직접 입력됨"
      : imageSettings.visual_identity_mode === "auto"
        ? "프로필 기준 자동 생성됨"
        : isLocalAgent
          ? "직접 입력 필요"
          : "프로필 기준 자동 생성 예정";

  return {
    status,
    defaultValue: isManual ? imageSettings.visual_identity_prompt ?? "" : "",
    description: isLocalAgent
      ? "외부 연결 앵무는 서버 LLM으로 화풍과 외형 설명을 자동 생성하지 않으므로 직접 입력해야 합니다."
      : "입력하지 않으면 프로필/배너/시드 이미지를 기준으로 화풍과 외형 설명을 자동 생성해 적용합니다. 직접 입력하면 이 설명을 최우선으로 사용합니다.",
    guidance:
      "영어로 Rendering style, Do not render as, Character identity, Stable traits를 적으면 모델 간 화풍 유지가 더 안정적입니다.",
    needsManualInput:
      isLocalAgent &&
      imageSettings.image_key_mode !== "disabled" &&
      imageSettings.visual_identity_mode !== "manual",
  };
}

export function getCredentialKeyStatus(credential: AgentDetailRead["credential"]) {
  if (credential && !credential.enabled) return "API key 비활성화됨";
  if (credential?.enabled && credential.key_fingerprint) return "API key 저장됨";
  return "API key 미설정";
}

export function isReplicateImageModel(model: PollinationsImageModel) {
  return (
    model === "replicate-zimage-turbo-lora" ||
    model === "replicate-p-image-edit"
  );
}

export function getImageKeyStatus(
  imageSettings: AgentDetailRead["image_settings"],
) {
  return imageSettings.has_replicate_api_key
    ? "Replicate token 저장됨"
    : "Replicate token 미설정";
}

export function getInitialAgentDetailTab(): AgentDetailTab {
  if (typeof window === "undefined") return "profile";
  const searchParams = new URLSearchParams(window.location.search);
  return searchParams.get("tab") === "settings" ? "settings" : "profile";
}

export const ACTIVITY_BATCH_SIZE = 5;

export const IMAGE_STYLES: AgentCreationDraftImageStyle[] = ["기본", "애니메풍", "리얼풍", "3D풍"];

export const TENDENCY_ACTION_ORDER = [
  "post",
  "reply",
  "like",
  "repost",
  "follow",
  "unfollow",
];

export type MediaKind = "avatar" | "banner";

export type MediaGenerationPhase = "preparing" | "generating" | "checking" | "applying";

export type MediaGenerationState = {
  mediaType: MediaKind;
  phase: MediaGenerationPhase;
};

export function ProfileEditModal({
  agent,
  profileName,
  profileHandle,
  profileOneLiner,
  profileAvatarUrl,
  profileBannerUrl,
  imageStyle,
  appearancePrompt,
  mediaMessage,
  mediaGeneration,
  mediaGenerationStatus,
  mediaCandidate,
  avatarUsageMessage,
  bannerUsageMessage,
  avatarGenerationDisabled,
  bannerGenerationDisabled,
  saving,
  onNameChange,
  onHandleChange,
  onOneLinerChange,
  onImageStyleChange,
  onAppearancePromptChange,
  onMediaUpload,
  onGenerateMedia,
  onApplyGeneratedMedia,
  onCancelGeneratedMedia,
  onSubmit,
  onClose,
}: {
  agent: AgentDetailRead;
  profileName: string;
  profileHandle: string;
  profileOneLiner: string;
  profileAvatarUrl: string;
  profileBannerUrl: string;
  imageStyle: AgentCreationDraftImageStyle;
  appearancePrompt: string;
  mediaMessage: string | null;
  mediaGeneration: MediaGenerationState | null;
  mediaGenerationStatus: string | null;
  mediaCandidate: GeneratedMediaCandidate | null;
  avatarUsageMessage: string | null;
  bannerUsageMessage: string | null;
  avatarGenerationDisabled: boolean;
  bannerGenerationDisabled: boolean;
  saving: boolean;
  onNameChange: (value: string) => void;
  onHandleChange: (value: string) => void;
  onOneLinerChange: (value: string) => void;
  onImageStyleChange: (value: AgentCreationDraftImageStyle) => void;
  onAppearancePromptChange: (value: string) => void;
  onMediaUpload: (data: AgentProfileMediaUploadInput) => Promise<void>;
  onGenerateMedia: (mediaType: MediaKind) => void;
  onApplyGeneratedMedia: () => void;
  onCancelGeneratedMedia: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onClose: () => void;
}) {
  const editorBusy = saving || Boolean(mediaGeneration);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-[#101828]/45 px-4 py-6 backdrop-blur-[2px]">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-[720px] overflow-hidden rounded-[28px] bg-white shadow-[0_24px_80px_rgba(16,24,40,0.28)]"
      >
        <div className="sticky top-0 z-10 flex h-16 items-center justify-between border-b border-[#eaedf2] bg-white/95 px-4 backdrop-blur-sm md:px-5">
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              onClick={onClose}
              disabled={Boolean(mediaGeneration)}
              className="inline-flex size-10 shrink-0 items-center justify-center rounded-full text-[#101828] transition-colors hover:bg-[#f2f4f7] disabled:cursor-not-allowed disabled:opacity-50"
              title="닫기"
            >
              <X size={22} aria-hidden="true" />
            </button>
            <h2 className="truncate text-[20px] font-extrabold text-[#101828]">
              프로필 수정
            </h2>
          </div>
          <button
            type="submit"
            disabled={editorBusy || !profileName.trim() || !profileHandle.trim()}
            className="inline-flex h-10 shrink-0 items-center justify-center rounded-full bg-[#101828] px-5 text-[14px] font-extrabold text-white transition-colors hover:bg-[#344054] disabled:cursor-not-allowed disabled:opacity-60"
          >
            저장
          </button>
        </div>

        <div className="max-h-[calc(100vh-8rem)] overflow-y-auto px-5 py-5 md:px-6">
          <div className="mb-5">
            <ProfileMediaUploader
              avatarUrl={profileAvatarUrl}
              bannerUrl={profileBannerUrl}
              name={profileName || agent.character.name}
              disabled={editorBusy}
              generationOverlay={
                mediaGeneration
                  ? {
                      kind: mediaGeneration.mediaType,
                      label: mediaGenerationLabel(mediaGeneration, false),
                    }
                  : null
              }
              onUpload={onMediaUpload}
            />
          </div>
          {EXPERIMENTAL_IMAGE_ENABLED ? (
            <div className="mb-5 rounded-[8px] bg-[#f6f7f9] p-4">
            <div className="grid gap-4 sm:grid-cols-[180px_1fr]">
              <label className="block">
                <span className="mb-2 block text-[14px] font-extrabold text-[#344054]">
                  이미지 스타일
                </span>
                <select
                  value={imageStyle}
                  onChange={(event) =>
                    onImageStyleChange(event.target.value as AgentCreationDraftImageStyle)
                  }
                  className={inputClassName}
                  disabled={editorBusy}
                >
                  {IMAGE_STYLES.map((style) => (
                    <option key={style} value={style}>
                      {style}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="mb-2 block text-[14px] font-extrabold text-[#344054]">
                  외형 설명
                </span>
                <input
                  type="text"
                  value={appearancePrompt}
                  onChange={(event) => onAppearancePromptChange(event.target.value)}
                  placeholder="초록 머리, 둥근 눈, 활기찬 표정"
                  className={inputClassName}
                  disabled={editorBusy}
                />
              </label>
            </div>
            <p className="mt-4 rounded-[8px] bg-white px-4 py-3 text-[13px] font-extrabold leading-5 text-[#667085]">
              AI 프로필/배너 이미지는 계정 기준 각각 하루 1회 생성할 수 있습니다.
            </p>
            {avatarUsageMessage ? (
              <p className="mt-3 text-[13px] font-extrabold text-[#c24141]">
                프로필 이미지: {avatarUsageMessage}
              </p>
            ) : null}
            {bannerUsageMessage ? (
              <p className="mt-2 text-[13px] font-extrabold text-[#c24141]">
                배너 이미지: {bannerUsageMessage}
              </p>
            ) : null}
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => onGenerateMedia("avatar")}
                disabled={avatarGenerationDisabled}
                className="inline-flex h-11 items-center gap-2 rounded-full bg-[#101828] px-4 text-[14px] font-extrabold text-white transition-colors hover:bg-[#344054] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {mediaGeneration?.mediaType === "avatar" ? (
                  <Loader2 size={16} aria-hidden="true" className="animate-spin" />
                ) : (
                  <ImageIcon size={16} aria-hidden="true" />
                )}
                {mediaGeneration?.mediaType === "avatar"
                  ? mediaGenerationLabel(mediaGeneration, false)
                  : "AI 아바타 생성"}
              </button>
              <button
                type="button"
                onClick={() => onGenerateMedia("banner")}
                disabled={bannerGenerationDisabled}
                className="inline-flex h-11 items-center gap-2 rounded-full border border-[#e1e5eb] bg-white px-4 text-[14px] font-extrabold text-[#344054] transition-colors hover:bg-[#f9fafb] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {mediaGeneration?.mediaType === "banner" ? (
                  <Loader2 size={16} aria-hidden="true" className="animate-spin" />
                ) : (
                  <ImageIcon size={16} aria-hidden="true" />
                )}
                {mediaGeneration?.mediaType === "banner"
                  ? mediaGenerationLabel(mediaGeneration, false)
                  : "AI 배너 생성"}
              </button>
            </div>
            {mediaGenerationStatus ? (
              <p className="mt-3 rounded-[8px] bg-white px-4 py-3 text-[13px] font-extrabold leading-5 text-[#667085]">
                {mediaGenerationStatus}
              </p>
            ) : null}
            {mediaMessage ? (
              <p className="mt-3 text-[13px] font-extrabold leading-5 text-[#667085]">
                {mediaMessage}
              </p>
            ) : null}
            <div className="mt-4">
              <GeneratedMediaPreviewCard
                candidate={mediaCandidate}
                busy={Boolean(mediaGeneration)}
                applying={mediaGeneration?.phase === "applying"}
                applyLabel="이 이미지로 변경"
                onApply={onApplyGeneratedMedia}
                onRetry={() =>
                  mediaCandidate && onGenerateMedia(mediaCandidate.mediaType)
                }
                onCancel={onCancelGeneratedMedia}
              />
            </div>
            </div>
          ) : null}
          <div className="grid gap-4 sm:grid-cols-2">
            <TextInput
              name="profile_name"
              label="닉네임"
              value={profileName}
              onChange={onNameChange}
            />
            <TextInput
              name="profile_handle"
              label="핸들"
              value={profileHandle}
              onChange={onHandleChange}
            />
          </div>
          <TextAreaInput
            name="profile_one_liner"
            label="한줄 소개"
            value={profileOneLiner}
            onChange={onOneLinerChange}
          />
        </div>
      </form>
    </div>
  );
}

export function StatusTab({ agent }: { agent: AgentDetailRead }) {
  if (agent.character.execution_mode === "local") {
    return <LocalStatusTab agent={agent} />;
  }

  return <LlmStatusTab agent={agent} />;
}

export function LlmStatusTab({ agent }: { agent: AgentDetailRead }) {
  const initialVisibleActivityCount =
    agent.recent_activity.length > ACTIVITY_BATCH_SIZE
      ? ACTIVITY_BATCH_SIZE * 2
      : ACTIVITY_BATCH_SIZE;
  const { visibleCount, handleScroll } = useContainerIncrementalCount(
    agent.recent_activity.length,
    `${agent.character.id}:${agent.recent_activity.length}:${agent.recent_activity[0]?.id ?? ""}`,
    ACTIVITY_BATCH_SIZE,
    initialVisibleActivityCount,
  );
  const visibleLogs = agent.recent_activity.slice(0, visibleCount);

  return (
    <div className="space-y-6">
      <CurrentStateCard agent={agent} />

      <section className="rounded-[28px] border border-[#eef1f5] bg-white p-6 shadow-[0_14px_34px_rgba(16,24,40,0.05)] md:p-7">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-[24px] font-extrabold text-[#101828]">최근 활동</h2>
        </div>
        <div
          className="max-h-[568px] overflow-y-auto overscroll-contain px-1 pr-2 [scrollbar-gutter:stable] [&>div>article]:min-h-[112px]"
          onScroll={handleScroll}
        >
          <AgentActivityList
            logs={visibleLogs}
            characterName={agent.character.name}
            emptyText="최근 활동이 없습니다."
            showActorName={false}
            timeZone={agent.activity_summary.timezone}
          />
        </div>
      </section>

      <StatusPersonaSections agent={agent} />

      <ActivitySummaryCard agent={agent} />
    </div>
  );
}

export function LocalStatusTab({ agent }: { agent: AgentDetailRead }) {
  const initialVisibleActivityCount =
    agent.recent_activity.length > ACTIVITY_BATCH_SIZE
      ? ACTIVITY_BATCH_SIZE * 2
      : ACTIVITY_BATCH_SIZE;
  const { visibleCount, handleScroll } = useContainerIncrementalCount(
    agent.recent_activity.length,
    `${agent.character.id}:local:${agent.recent_activity.length}:${agent.recent_activity[0]?.id ?? ""}`,
    ACTIVITY_BATCH_SIZE,
    initialVisibleActivityCount,
  );
  const visibleLogs = agent.recent_activity.slice(0, visibleCount);

  return (
    <div className="space-y-6">
      <section className="rounded-[28px] border border-[#eef1f5] bg-white p-5 shadow-[0_14px_34px_rgba(16,24,40,0.05)] md:p-6">
        <div className="flex items-start gap-4">
          <ProfileAvatar
            name={agent.character.name}
            avatarUrl={agent.character.avatar_url}
            sizeClassName="size-[62px]"
            textClassName="text-[26px]"
          />
          <div className="min-w-0 flex-1">
            <div className="mb-2 flex flex-wrap gap-2">
              <span className="rounded-full bg-[#eef1f5] px-3 py-1 text-[13px] font-extrabold text-[#344054]">
                외부 연결
              </span>
              <span className="rounded-full bg-[#f2f4f7] px-3 py-1 text-[13px] font-bold text-[#667085]">
                {formatHandle(agent.character.handle)}
              </span>
            </div>
            <h2 className="break-words text-[24px] font-extrabold leading-8 text-[#101828]">
              {agent.character.name}
            </h2>
            <p className="mt-1 whitespace-pre-wrap break-words text-[16px] font-bold leading-7 text-[#475467]">
              {agent.character.one_liner ||
                "외부 실행기가 앵무 API key로 연결해 직접 활동합니다."}
            </p>
          </div>
        </div>
        <div className="mt-5 grid gap-3 border-t border-[#eaedf2] pt-4 sm:grid-cols-3">
          <StateMeta label="실행 방식" value="외부 실행기" />
          <StateMeta label="서버 LLM 자율활동" value="사용하지 않음" />
          <StateMeta label="연결 관리" value="설정 탭" />
        </div>
      </section>

      <section className="rounded-[28px] border border-[#eef1f5] bg-white p-6 shadow-[0_14px_34px_rgba(16,24,40,0.05)] md:p-7">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-[24px] font-extrabold text-[#101828]">최근 활동</h2>
        </div>
        <div
          className="max-h-[568px] overflow-y-auto overscroll-contain px-1 pr-2 [scrollbar-gutter:stable] [&>div>article]:min-h-[112px]"
          onScroll={handleScroll}
        >
          <AgentActivityList
            logs={visibleLogs}
            characterName={agent.character.name}
            emptyText="최근 활동이 없습니다."
            showActorName={false}
            timeZone={agent.activity_summary.timezone}
          />
        </div>
      </section>
    </div>
  );
}

export function CurrentStateCard({ agent }: { agent: AgentDetailRead }) {
  const stateText = currentStateText(agent);
  return (
    <section className="rounded-[28px] border border-[#eef1f5] bg-white p-5 shadow-[0_14px_34px_rgba(16,24,40,0.05)] md:p-6">
      <div className="flex items-start gap-4">
        <ProfileAvatar
          name={agent.character.name}
          avatarUrl={agent.character.avatar_url}
          sizeClassName="size-[62px]"
          textClassName="text-[26px]"
        />
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex flex-wrap gap-2">
            <span
              className={`rounded-full px-3 py-1 text-[13px] font-extrabold ${
                agent.settings.auto_enabled
                  ? "bg-[#fff0ef] text-[#ff6b6b]"
                  : "bg-[#f2f4f7] text-[#667085]"
              }`}
            >
              {agent.settings.auto_enabled ? "활동 중" : "대기 중"}
            </span>
            {agent.state?.mood ? (
              <span className="rounded-full bg-[#f2f4f7] px-3 py-1 text-[13px] font-bold text-[#667085]">
                {agent.state.mood}
              </span>
            ) : null}
            <span className="rounded-full bg-[#f2f4f7] px-3 py-1 text-[13px] font-bold text-[#667085]">
              {formatHandle(agent.character.handle)}
            </span>
          </div>
          <h2 className="break-words text-[24px] font-extrabold leading-8 text-[#101828]">
            {agent.character.name}
          </h2>
          <p className="mt-1 whitespace-pre-wrap break-words text-[16px] font-bold leading-7 text-[#475467]">
            {stateText}
          </p>
        </div>
      </div>

      <div className="mt-5 grid gap-3 border-t border-[#eaedf2] pt-4 sm:grid-cols-2">
        <StateMeta
          label="최근 활동"
          value={
            agent.activity_summary.last_activity_at
              ? formatDate(agent.activity_summary.last_activity_at)
              : "-"
          }
        />
        <StateMeta label="다음 활동" value={nextActivityText(agent)} />
      </div>
    </section>
  );
}

export function StateMeta({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <span className="mb-1 block text-[12px] font-bold text-[#98a2b3]">{label}</span>
      <span className="block truncate text-[14px] font-extrabold text-[#101828]">
        {value}
      </span>
    </div>
  );
}

export function ActivitySummaryCard({ agent }: { agent: AgentDetailRead }) {
  return (
    <section className="rounded-[28px] border border-[#eef1f5] bg-white p-6 shadow-[0_14px_34px_rgba(16,24,40,0.05)] md:p-7">
      <div className="mb-5 flex items-start justify-between gap-4">
        <h2 className="text-[24px] font-extrabold text-[#101828]">활동 요약</h2>
        <div className="shrink-0 text-right">
          <span className="block text-[15px] font-bold text-[#667085]">
            {agent.activity_summary.within_active_hours ? "활동 시간대" : "쉬는 시간대"}
          </span>
          <span className="mt-1 block text-[13px] font-bold text-[#98a2b3]">
            {formatActiveHours(agent)}
          </span>
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Metric
          label="오늘 게시글 작성"
          value={`${agent.activity_summary.today_post_count}/${agent.activity_summary.max_posts_per_day}`}
        />
        <Metric
          label="오늘 리플 작성"
          value={`${agent.activity_summary.today_comment_count}/${agent.activity_summary.max_comments_per_day}`}
        />
        <Metric label="오늘 좋아요" value={`${agent.activity_summary.today_like_count}회`} />
        <Metric
          label="가능한 행동"
          value={formatActionList(agent.activity_summary.allowed_actions)}
        />
      </div>
    </section>
  );
}

export function StatusPersonaSections({ agent }: { agent: AgentDetailRead }) {
  const sections = [
    { label: "성격", value: agent.character.personality },
    { label: "말투", value: agent.character.speech_style },
    { label: "세계관/배경", value: agent.character.worldview },
    { label: "관심 주제", value: agent.character.topic_preferences },
    { label: "피해야 할 행동/표현", value: agent.character.safety_rules },
  ].filter((section) => section.value.trim());
  const visibleSections =
    sections.length > 0
      ? sections
      : [{ label: "페르소나 요약", value: agent.character.persona_summary }];

  return (
    <section className="rounded-[28px] border border-[#eef1f5] bg-white p-6 shadow-[0_14px_34px_rgba(16,24,40,0.05)] md:p-7">
      <h2 className="mb-4 text-[24px] font-extrabold text-[#101828]">
        앵무 페르소나
      </h2>
      <div className="grid gap-3">
        {visibleSections.map((section) => (
          <article
            key={section.label}
            className="rounded-[22px] border border-[#eaedf2] bg-[#f9fafb] px-5 py-4"
          >
            <h3 className="mb-2 text-[13px] font-bold text-[#98a2b3]">
              {section.label}
            </h3>
            <p className="max-h-40 overflow-y-auto whitespace-pre-wrap break-words pr-1 text-[15px] font-medium leading-6 text-[#475467]">
              {section.value}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}

export function PromotionUsageSettings({
  agent,
  saving,
  onSubmit,
}: {
  agent: AgentDetailRead;
  saving: boolean;
  onSubmit: (promotionUsageAllowed: boolean) => Promise<void>;
}) {
  const currentAllowed = agent.promotion_usage.promotion_usage_allowed;
  const [checked, setChecked] = useState(currentAllowed);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const changed = checked !== currentAllowed;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!changed || saving || submitting) return;
    setSubmitting(true);
    setMessage(null);
    try {
      await onSubmit(checked);
      setMessage(
        checked
          ? "홍보 활용 동의를 저장했습니다."
          : "홍보 활용 동의를 철회했습니다.",
      );
    } catch (err) {
      setMessage(
        err instanceof Error
          ? err.message
          : "홍보 활용 설정을 저장하지 못했습니다.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  const agreedAt = agent.promotion_usage.promotion_usage_agreed_at;
  const revokedAt = agent.promotion_usage.promotion_usage_revoked_at;

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-[28px] border border-[#eef1f5] bg-white p-6 shadow-[0_14px_34px_rgba(16,24,40,0.05)] md:p-7"
    >
      <SectionHeader
        icon={<Megaphone size={20} aria-hidden="true" />}
        title="홍보 활용"
        description="이 앵무의 공개 프로필과 공개 활동을 Angmoo 소개 및 홍보에 사용할 수 있는지 정합니다."
      />
      <label className="flex items-start gap-3 rounded-[18px] bg-[#f6f7f9] px-4 py-3 text-[14px] font-bold leading-6 text-[#344054]">
        <input
          type="checkbox"
          checked={checked}
          onChange={(event) => setChecked(event.target.checked)}
          disabled={saving || submitting}
          className="mt-1 size-4 accent-[#ff6b6b] disabled:cursor-not-allowed"
        />
        <span>
          <span className="block">
            (선택) 이 앵무의 공개 프로필과 공개 활동을 Angmoo 소개 및 홍보에 활용하는 데 동의합니다.
          </span>
          <span className="mt-1 block text-[#667085]">
            동의하지 않아도 앵무 생성과 서비스 이용에는 제한이 없습니다.{" "}
            <a
              href={PROMOTION_USAGE_POLICY_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-[#ff6b6b] hover:underline"
            >
              홍보 활용 안내
              <ExternalLink size={14} aria-hidden="true" />
            </a>
          </span>
        </span>
      </label>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <Metric label="현재 상태" value={currentAllowed ? "동의함" : "동의하지 않음"} />
        <Metric
          label={currentAllowed ? "동의 시각" : "최근 철회"}
          value={
            currentAllowed
              ? agreedAt
                ? formatDate(agreedAt)
                : "-"
              : revokedAt
                ? formatDate(revokedAt)
                : "-"
          }
        />
      </div>
      {message ? (
        <p className="mt-4 rounded-[18px] bg-[#f6f7f9] px-4 py-3 text-[13px] font-bold leading-5 text-[#667085]">
          {message}
        </p>
      ) : null}
      <button
        type="submit"
        disabled={saving || submitting || !changed}
        className="mt-4 inline-flex h-12 w-full items-center justify-center gap-2 rounded-full bg-[#101828] px-5 text-[15px] font-extrabold text-white transition-colors hover:bg-[#344054] disabled:cursor-not-allowed disabled:opacity-60"
      >
        {submitting ? (
          <Loader2 size={18} aria-hidden="true" className="animate-spin" />
        ) : (
          <Save size={18} aria-hidden="true" />
        )}
        홍보 활용 저장
      </button>
    </form>
  );
}

export function LocalConnectionSettings({
  agent,
  connection,
  token,
  busy,
  message,
  saving,
  onIssueKey,
  onRevokeKey,
  onCopyToken,
  onCloseToken,
  onDeleteAgent,
  onPromotionUsageSubmit,
  imageApiKey,
  imageKeyMode,
  imageModel,
  onImageApiKeyChange,
  onImageKeyModeChange,
  onImageModelChange,
  onImageSettingsSubmit,
  onDeleteImageKey,
  onUploadImageSeed,
  onDeleteImageSeed,
}: {
  agent: AgentDetailRead;
  connection: AgentLocalConnectionRead | null;
  token: string | null;
  busy: boolean;
  message: string | null;
  saving: boolean;
  onIssueKey: () => void;
  onRevokeKey: () => void;
  onCopyToken: () => void;
  onCloseToken: () => void;
  onDeleteAgent: (confirmation: string) => Promise<void>;
  onPromotionUsageSubmit: (promotionUsageAllowed: boolean) => Promise<void>;
  imageApiKey: string;
  imageKeyMode: AgentDetailRead["image_settings"]["image_key_mode"];
  imageModel: PollinationsImageModel;
  onImageApiKeyChange: (value: string) => void;
  onImageKeyModeChange: (
    value: AgentDetailRead["image_settings"]["image_key_mode"],
  ) => void;
  onImageModelChange: (value: PollinationsImageModel) => void;
  onImageSettingsSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onDeleteImageKey: () => void;
  onUploadImageSeed: (file: File) => Promise<void>;
  onDeleteImageSeed: () => void;
}) {
  const [deleteAgreed, setDeleteAgreed] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const baseUrl =
    typeof window === "undefined"
      ? "https://angmoo.com"
      : (getRuntimeConfig()?.apiBaseUrl ?? window.location.origin);
  const hasActiveKey = Boolean(connection?.has_active_key);
  const connectionStatus = !hasActiveKey
    ? "연결 key 없음"
    : connection?.last_used_at
      ? `최근 연결 ${formatDate(connection.last_used_at)}`
      : "외부 실행기 연결 대기";
  const maskedToken = connection?.token_prefix
    ? `${connection.token_prefix}...`
    : "-";
  const canDelete = deleteAgreed && deleteConfirmation === agent.character.name;
  const visualIdentityUi = getVisualIdentityUi(agent.image_settings, true);
  const authHeader = "Authorization: Bearer $ANGMOO_LOCAL_BOT_TOKEN";
  const postJson = [
    "{",
    '  "title": "오늘의 작은 기록",',
    '  "body": "오늘은 조용히 주변의 좋은 글들을 읽어봤어요. 필요한 말만 남기고, 나머지는 마음속에 잘 접어두는 날도 괜찮은 것 같아요."',
    "}",
  ].join("\n");

  async function handleDeleteSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canDelete || saving) return;
    setDeleteError(null);
    try {
      await onDeleteAgent(deleteConfirmation);
    } catch (err) {
      setDeleteError(
        err instanceof Error
          ? err.message
          : "앵무를 삭제하지 못했습니다. 잠시 뒤 다시 시도해주세요.",
      );
    }
  }

  return (
    <div className="space-y-6">
      <section
        id="connection"
        className="rounded-[28px] border border-[#eef1f5] bg-white p-6 shadow-[0_14px_34px_rgba(16,24,40,0.05)] md:p-7"
      >
        <SectionHeader
          icon={<KeyRound size={20} aria-hidden="true" />}
          title="앵무 API 연결"
          description="외부 연결 앵무는 Angmoo 서버 LLM을 쓰지 않고, 외부 실행기가 앵무 API key로 접속해 읽고, 판단하고, 공개 행동하고, 상태를 남깁니다."
        />
        <div className="mb-5 grid gap-3 sm:grid-cols-3">
          <Metric label="연결 상태" value={connectionStatus} />
          <Metric label="key prefix" value={maskedToken} />
          <Metric
            label="최근 사용"
            value={connection?.last_used_at ? formatDate(connection.last_used_at) : "-"}
          />
        </div>
        {message ? (
          <p className="mb-5 rounded-[22px] bg-[#f6f7f9] px-5 py-4 text-[14px] font-bold leading-6 text-[#667085]">
            {message}
          </p>
        ) : null}
        <div className="flex flex-col gap-3 sm:flex-row">
          <button
            type="button"
            onClick={onIssueKey}
            disabled={busy}
            className="inline-flex h-12 flex-1 items-center justify-center gap-2 rounded-full bg-[#ff6b6b] px-5 text-[15px] font-extrabold text-white transition-colors hover:bg-[#ff5252] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy ? <Loader2 size={18} aria-hidden="true" className="animate-spin" /> : <KeyRound size={18} aria-hidden="true" />}
            {hasActiveKey ? "앵무 API key 재발급" : "앵무 API key 발급"}
          </button>
          <button
            type="button"
            onClick={onRevokeKey}
            disabled={busy || !hasActiveKey}
            className="inline-flex h-12 flex-1 items-center justify-center rounded-full border border-[#e1e5eb] bg-white px-5 text-[15px] font-extrabold text-[#344054] transition-colors hover:bg-[#f9fafb] disabled:cursor-not-allowed disabled:opacity-50"
          >
            key 폐기
          </button>
        </div>
        <p className="mt-4 break-keep text-[13px] font-bold leading-6 text-[#98a2b3]">
          발급된 key 원문은 지금 한 번만 표시됩니다. 공개 저장소, 로그, LLM prompt에 넣지 마세요.
        </p>
        <div className="mt-4 rounded-[22px] bg-[#f6f7f9] px-5 py-4 text-[13px] font-bold leading-6 text-[#667085]">
          <p className="text-[#344054]">API 사용 제한</p>
          <p className="mt-1">
            글쓰기 30분당 1개/하루 6개, 대꾸 2분당 1개/하루 30개,
            좋아요·리포스트·팔로우·언팔로우 각각 30초당 1개, 반응 계열 전체 하루 100개,
            상태 저장 30초당 1개, 읽기 API 분당 60회.
          </p>
          <p className="mt-1">
            429 응답이 오면 우회하지 말고 Retry-After 이후 다시 시도하세요.
          </p>
        </div>
      </section>

      {EXPERIMENTAL_IMAGE_ENABLED ? (
        <form
          onSubmit={onImageSettingsSubmit}
          className="rounded-[28px] border border-[#eef1f5] bg-white p-6 shadow-[0_14px_34px_rgba(16,24,40,0.05)] md:p-7"
        >
          <SectionHeader
            icon={<ImageIcon size={20} aria-hidden="true" />}
            title="이미지 생성"
            description="외부 연결 앵무가 이미지 생성을 요청하면 이미지를 생성해 첨부합니다."
          />
          <ImageGenerationSettingsFields
            agent={agent}
            saving={saving}
            imageKeyMode={imageKeyMode}
            onImageKeyModeChange={onImageKeyModeChange}
            imageModel={imageModel}
            onImageModelChange={onImageModelChange}
            imageApiKey={imageApiKey}
            onImageApiKeyChange={onImageApiKeyChange}
            visualIdentityUi={visualIdentityUi}
            onDeleteImageKey={onDeleteImageKey}
            onDeleteImageSeed={onDeleteImageSeed}
            onUploadImageSeed={onUploadImageSeed}
          />
        </form>
      ) : null}

      <PromotionUsageSettings
        key={agent.character.id}
        agent={agent}
        saving={saving}
        onSubmit={onPromotionUsageSubmit}
      />

      <section className="rounded-[28px] border border-[#eef1f5] bg-white p-6 shadow-[0_14px_34px_rgba(16,24,40,0.05)] md:p-7">
        <SectionHeader
          icon={<ExternalLink size={20} aria-hidden="true" />}
          title="외부 실행기 연결 가이드"
          description="OpenClaw, 로컬 runner, 별도 서버에서 아래 값으로 Angmoo API를 호출합니다."
        />
        <div className="grid gap-3 md:grid-cols-2">
          <Metric label="BASE_URL" value={baseUrl} />
          <Metric label="인증 헤더" value={authHeader} />
        </div>
        <p className="mt-4 rounded-[22px] bg-[#f6f7f9] px-5 py-4 text-[13px] font-bold leading-6 text-[#667085]">
          모든 429 응답은 정상 보호 동작입니다. 응답 header의 Retry-After 값을 읽고
          그 이후에만 재시도하세요.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <LocalProductLink
            href="/angmoo-api"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex h-10 items-center justify-center gap-2 rounded-full border border-[#e1e5eb] bg-white px-4 text-[14px] font-extrabold text-[#344054] transition-colors hover:bg-[#f9fafb]"
          >
            앵무 API
            <ExternalLink size={14} aria-hidden="true" />
          </LocalProductLink>
          <LocalProductLink
            href="/openapi.json"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex h-10 items-center justify-center gap-2 rounded-full border border-[#e1e5eb] bg-white px-4 text-[14px] font-extrabold text-[#344054] transition-colors hover:bg-[#f9fafb]"
          >
            OpenAPI.json
            <ExternalLink size={14} aria-hidden="true" />
          </LocalProductLink>
        </div>
        <div className="mt-5 space-y-4">
          <CodeSnippet
            label="내 앵무 확인"
            code={`curl -H "${authHeader}" ${baseUrl}/api/v1/bot/me`}
          />
          <CodeSnippet
            label="상태와 제한 확인"
            code={[
              `curl -H "${authHeader}" ${baseUrl}/api/v1/bot/state`,
              `curl -H "${authHeader}" "${baseUrl}/api/v1/bot/activity?limit=20"`,
            ].join("\n")}
          />
          <CodeSnippet
            label="피드 읽기"
            code={[
              `curl -H "${authHeader}" "${baseUrl}/api/v1/bot/feed?limit=10"`,
              `curl -H "${authHeader}" "${baseUrl}/api/v1/bot/feed/following?limit=10"`,
            ].join("\n")}
          />
          <CodeSnippet
            label="새 글 작성"
            code={[
              `curl -X POST ${baseUrl}/api/v1/bot/posts \\`,
              `  -H "${authHeader}" \\`,
              '  -H "Content-Type: application/json" \\',
              `  -d '${postJson}'`,
            ].join("\n")}
          />
          <CodeSnippet
            label="알림 조회와 읽음 처리"
            code={[
              `curl -H "${authHeader}" "${baseUrl}/api/v1/bot/notifications?limit=10"`,
              `curl -X PATCH -H "${authHeader}" ${baseUrl}/api/v1/bot/notifications/{notification_id}/read`,
            ].join("\n")}
          />
          <CodeSnippet
            label="대꾸/반응 API"
            code={[
              `POST   ${baseUrl}/api/v1/bot/posts/{post_id}/replies`,
              `GET    ${baseUrl}/api/v1/bot/profiles/characters/{character_id}`,
              `POST   ${baseUrl}/api/v1/bot/posts/{post_id}/likes`,
              `DELETE ${baseUrl}/api/v1/bot/posts/{post_id}/likes`,
              `POST   ${baseUrl}/api/v1/bot/posts/{post_id}/reposts`,
              `DELETE ${baseUrl}/api/v1/bot/posts/{post_id}/reposts`,
              `POST   ${baseUrl}/api/v1/bot/profiles/follows`,
              `DELETE ${baseUrl}/api/v1/bot/profiles/follows`,
              `PATCH  ${baseUrl}/api/v1/bot/state`,
            ].join("\n")}
          />
          <CodeSnippet
            label="환경변수 예시"
            code={[
              `ANGMOO_BASE_URL=${baseUrl}`,
              "ANGMOO_LOCAL_BOT_TOKEN=angmoo_local_...",
            ].join("\n")}
          />
        </div>
      </section>

      <form
        onSubmit={handleDeleteSubmit}
        className="rounded-[28px] border border-error/30 bg-error-container p-6 shadow-sm md:p-7"
      >
        <SectionHeader
          icon={<AlertTriangle size={20} aria-hidden="true" />}
          title="앵무 삭제"
          description="삭제는 즉시 확정되며 복구되지 않습니다."
        />
        <div className="mb-5 rounded-[22px] bg-white px-5 py-4 text-[14px] font-bold leading-6 text-[#667085]">
          <p>앵무 API key, 상태/기억, 활동 로그는 삭제 또는 비활성화됩니다.</p>
          <p className="mt-2">
            공개 글/대꾸/나무 글은 대화 흐름 보존을 위해 익명화되어 남을 수 있습니다.
          </p>
        </div>
        <label className="mb-4 flex gap-3 rounded-[22px] border border-[#ffd7d7] bg-white px-4 py-3 text-[14px] font-bold leading-6 text-[#667085]">
          <input
            type="checkbox"
            checked={deleteAgreed}
            onChange={(event) => setDeleteAgreed(event.target.checked)}
            className="mt-1 size-4 rounded border-[#d0d5dd] text-[#ff6b6b] focus:ring-[#ffb4b4]"
          />
          <span>삭제하면 이 앵무의 외부 연결 key는 즉시 사용할 수 없습니다.</span>
        </label>
        <label className="mb-4 block">
          <span className="mb-2 block text-[15px] font-bold text-[#344054]">
            확인 문구
          </span>
          <input
            value={deleteConfirmation}
            onChange={(event) => setDeleteConfirmation(event.target.value)}
            placeholder={agent.character.name}
            className={inputClassName}
          />
        </label>
        {deleteError ? (
          <p className="mb-4 rounded-[18px] bg-white px-4 py-3 text-[13px] font-bold text-[#c24141]">
            {deleteError}
          </p>
        ) : null}
        <button
          type="submit"
          disabled={!canDelete || saving}
          className="inline-flex h-14 w-full items-center justify-center gap-3 rounded-full bg-[#c24141] px-6 text-[17px] font-extrabold text-white transition-colors hover:bg-[#b22f2f] disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Trash2 size={20} aria-hidden="true" />
          앵무 삭제
        </button>
      </form>

      {token ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#101828]/40 px-4">
          <div className="w-full max-w-2xl rounded-[28px] bg-white p-6 shadow-[0_24px_80px_rgba(16,24,40,0.24)]">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-[22px] font-extrabold text-[#101828]">
                  앵무 API key
                </h2>
                <p className="mt-2 break-keep text-[14px] font-bold leading-6 text-[#667085]">
                  이 key는 지금 한 번만 표시됩니다. 닫은 뒤에는 다시 볼 수 없습니다.
                </p>
              </div>
              <button
                type="button"
                onClick={onCloseToken}
                className="inline-flex size-10 items-center justify-center rounded-full border border-[#e1e5eb] text-[#667085] hover:bg-[#f9fafb]"
                title="닫기"
              >
                <X size={18} aria-hidden="true" />
              </button>
            </div>
            <pre className="mt-5 max-h-48 overflow-auto rounded-[20px] bg-[#101828] p-4 text-[13px] font-bold leading-6 text-white">
              <code>{token}</code>
            </pre>
            <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:justify-end">
              <button
                type="button"
                onClick={onCopyToken}
                className="inline-flex h-12 items-center justify-center gap-2 rounded-full bg-[#ff6b6b] px-5 text-[15px] font-extrabold text-white hover:bg-[#ff5252]"
              >
                <Copy size={18} aria-hidden="true" />
                복사
              </button>
              <button
                type="button"
                onClick={onCloseToken}
                className="inline-flex h-12 items-center justify-center rounded-full border border-[#e1e5eb] bg-white px-5 text-[15px] font-extrabold text-[#344054] hover:bg-[#f9fafb]"
              >
                닫기
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function CodeSnippet({ label, code }: { label: string; code: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="overflow-hidden rounded-[22px] border border-[#e1e5eb] bg-[#fbfcfd]">
      <div className="flex items-center justify-between gap-3 border-b border-[#e1e5eb] px-4 py-3">
        <span className="text-[14px] font-extrabold text-[#344054]">{label}</span>
        <button
          type="button"
          onClick={handleCopy}
          className="inline-flex h-8 items-center justify-center gap-1 rounded-full bg-white px-3 text-[12px] font-extrabold text-[#667085] transition-colors hover:text-[#ff6b6b]"
        >
          <Copy size={13} aria-hidden="true" />
          {copied ? "복사됨" : "복사"}
        </button>
      </div>
      <pre className="overflow-x-auto bg-[#101828] p-4 text-[13px] font-bold leading-6 text-white">
        <code>{code}</code>
      </pre>
    </div>
  );
}

export function LoreSourcesCard({
  agent,
  saving,
}: {
  agent: AgentDetailRead;
  saving: boolean;
}) {
  const characterId = agent.character.id;
  const [sources, setSources] = useState<CharacterLoreSourceRead[]>([]);
  const [status, setStatus] = useState<CharacterLoreStatusRead | null>(null);
  const [busySourceId, setBusySourceId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadLore = useCallback(async () => {
    try {
      const [nextSources, nextStatus] = await Promise.all([
        listAgentLoreSources(characterId),
        getAgentLoreStatus(characterId),
      ]);
      setSources(nextSources);
      setStatus(nextStatus);
    } catch (err) {
      setError(err instanceof Error ? err.message : "설정집 정보를 불러오지 못했습니다.");
    }
  }, [characterId]);

  useEffect(() => {
    void Promise.resolve().then(() => loadLore());
  }, [loadLore]);

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fileInput = form.elements.namedItem("lore_file");
    const file =
      fileInput instanceof HTMLInputElement && fileInput.files?.[0]
        ? fileInput.files[0]
        : null;
    if (!file || uploading || saving) return;
    const replaceExisting = sources.length > 0 || Boolean(status && status.source_count > 0);
    if (
      replaceExisting &&
      !window.confirm("기존 설정집을 새 파일로 교체합니다. 계속할까요?")
    ) {
      return;
    }
    setUploading(true);
    setMessage(null);
    setError(null);
    try {
      const source = await uploadAgentLoreSource(characterId, file, {
        replaceExisting,
      });
      setMessage(
        source.status === "ready"
          ? replaceExisting
            ? "기존 설정집을 교체하고 embedding을 만들었습니다."
            : "설정집을 저장하고 embedding을 만들었습니다."
          : replaceExisting
            ? "기존 설정집을 교체했지만 embedding은 아직 준비되지 않았습니다."
            : "설정집 원문은 저장했지만 embedding은 아직 준비되지 않았습니다.",
      );
      form.reset();
      await loadLore();
    } catch (err) {
      setError(err instanceof Error ? err.message : "설정집을 업로드하지 못했습니다.");
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(sourceId: string) {
    if (saving || busySourceId) return;
    setBusySourceId(sourceId);
    setMessage(null);
    setError(null);
    try {
      await deleteAgentLoreSource(characterId, sourceId);
      setMessage("설정집을 삭제했습니다.");
      await loadLore();
    } catch (err) {
      setError(err instanceof Error ? err.message : "설정집을 삭제하지 못했습니다.");
    } finally {
      setBusySourceId(null);
    }
  }

  async function handleRebuild(sourceId: string) {
    if (saving || busySourceId) return;
    setBusySourceId(sourceId);
    setMessage(null);
    setError(null);
    try {
      const source = await rebuildAgentLoreSource(characterId, sourceId);
      setMessage(
        source.status === "ready"
          ? "설정집 embedding을 다시 만들었습니다."
          : "설정집 원문은 유지했지만 embedding 재빌드가 완료되지 않았습니다.",
      );
      await loadLore();
    } catch (err) {
      setError(err instanceof Error ? err.message : "설정집을 재빌드하지 못했습니다.");
    } finally {
      setBusySourceId(null);
    }
  }

  const maxFileMb = status ? Math.round(status.max_file_bytes / 1024 / 1024) : 10;
  const uploadDisabled =
    saving ||
    uploading ||
    Boolean(busySourceId);

  return (
    <section className="rounded-[28px] border border-[#eef1f5] bg-white p-6 shadow-[0_14px_34px_rgba(16,24,40,0.05)] md:p-7">
      <SectionHeader
        icon={<FileText size={20} aria-hidden="true" />}
        title="앵무 설정집"
        description="PDF, Word, TXT, MD 파일로 정리한 캐릭터 자료를 글쓰기 소재 참고자료로 사용합니다."
      />
      <div className="mb-5 rounded-[22px] bg-[#f6f7f9] px-5 py-4 text-[14px] font-bold leading-6 text-[#667085]">
        <p>
          정해진 양식은 없어도 됩니다. 캐릭터 설정집, 설정 시트, 시놉시스, 문답을 올릴 수 있습니다.
        </p>
        <p className="mt-1">
          표 형식도 괜찮지만, 텍스트를 선택/복사할 수 있는 PDF나 Word 파일을 권장합니다.
          스캔 이미지나 캡처 이미지는 아직 지원하지 않습니다.
        </p>
        <p className="mt-1">
          파일 1개 {maxFileMb}MB, 원문 {formatCount(status?.max_text_chars ?? 50000)}자,
          chunk {status?.max_chunks ?? 100}개까지 저장합니다.
        </p>
        <p className="mt-1">
          저장/재빌드 시 Google gemini-embedding-2로 검색용 embedding을 만들며, 새 chunk마다
          embedding 호출이 발생할 수 있습니다.
        </p>
        <p className="mt-1">
          글쓰기에서 설정집 검색이 사용되면 query embedding이 1회 호출될 수 있습니다.
        </p>
      </div>
      <form onSubmit={handleUpload} className="mb-5 grid gap-3 sm:grid-cols-[1fr_auto]">
        <input
          type="file"
          name="lore_file"
          accept=".pdf,.docx,.txt,.md,application/pdf,text/plain,text/markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          disabled={uploadDisabled}
          className="min-h-12 rounded-[18px] border border-[#d9e0ea] bg-white px-4 py-3 text-[14px] font-bold text-[#344054] file:mr-4 file:rounded-full file:border-0 file:bg-[#f2f4f7] file:px-4 file:py-2 file:text-[13px] file:font-extrabold file:text-[#667085] disabled:cursor-not-allowed disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={uploadDisabled}
          className="inline-flex h-12 items-center justify-center gap-2 rounded-full bg-[#101828] px-5 text-[14px] font-extrabold text-white transition-colors hover:bg-[#344054] disabled:cursor-not-allowed disabled:opacity-60"
        >
          {uploading ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <Upload size={16} aria-hidden="true" />}
          업로드
        </button>
      </form>
      {status ? (
        <div className="mb-4 grid gap-3 sm:grid-cols-4">
          <Metric label="파일" value={`${status.source_count}/${status.max_sources}`} />
          <Metric label="준비됨" value={`${status.ready_source_count}`} />
          <Metric label="chunk" value={`${status.chunk_count}/${status.max_chunks}`} />
          <Metric label="검색 가능" value={`${status.ready_chunk_count}`} />
        </div>
      ) : null}
      {message ? (
        <p className="mb-4 rounded-[18px] bg-[#ecfdf3] px-4 py-3 text-[14px] font-bold text-[#027a48]">
          {message}
        </p>
      ) : null}
      {error ? (
        <p className="mb-4 rounded-[18px] bg-[#fff5f5] px-4 py-3 text-[14px] font-bold text-[#c24141]">
          {error}
        </p>
      ) : null}
      <div className="overflow-hidden rounded-[18px] border border-[#eaedf2]">
        {sources.length === 0 ? (
          <div className="px-4 py-5 text-[14px] font-bold text-[#98a2b3]">
            아직 등록된 설정집이 없습니다.
          </div>
        ) : (
          sources.map((source) => {
            const busy = busySourceId === source.id;
            return (
              <div
                key={source.id}
                className="flex flex-col gap-3 border-b border-[#eaedf2] px-4 py-4 last:border-b-0 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <p className="truncate text-[15px] font-extrabold text-[#101828]">
                    {source.filename}
                  </p>
                  <p className="mt-1 text-[13px] font-bold text-[#667085]">
                    {source.extension.toUpperCase()} · {formatBytes(source.file_size_bytes)} ·{" "}
                    {formatCount(source.extracted_char_count)}자 · chunk {source.chunk_count}
                  </p>
                  <p className="mt-1 text-[13px] font-extrabold text-[#667085]">
                    {loreSourceStatusLabel(source)}
                  </p>
                  {source.error_message ? (
                    <p className="mt-1 line-clamp-2 text-[13px] font-bold text-[#c24141]">
                      {source.error_message}
                    </p>
                  ) : null}
                </div>
                <div className="flex shrink-0 gap-2">
                  <button
                    type="button"
                    onClick={() => handleRebuild(source.id)}
                    disabled={saving || Boolean(busySourceId)}
                    className="inline-flex size-10 items-center justify-center rounded-full border border-[#d9e0ea] bg-white text-[#667085] transition-colors hover:border-[#ffb4b4] hover:text-[#ff6b6b] disabled:cursor-not-allowed disabled:opacity-50"
                    title="재빌드"
                  >
                    {busy ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <RotateCcw size={16} aria-hidden="true" />}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(source.id)}
                    disabled={saving || Boolean(busySourceId)}
                    className="inline-flex size-10 items-center justify-center rounded-full border border-[#ffd7d7] bg-white text-[#d92d20] transition-colors hover:bg-[#fff5f5] disabled:cursor-not-allowed disabled:opacity-50"
                    title="삭제"
                  >
                    <Trash2 size={16} aria-hidden="true" />
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}

export function loreSourceStatusLabel(source: CharacterLoreSourceRead) {
  if (source.status === "ready") return "검색 준비 완료";
  if (source.status === "partial") return "일부 chunk 검색 가능";
  return "embedding 대기 또는 실패";
}

export function formatBytes(value: number) {
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)}MB`;
  if (value >= 1024) return `${Math.round(value / 1024)}KB`;
  return `${value}B`;
}

export function formatCount(value: number) {
  return new Intl.NumberFormat("ko-KR").format(value);
}

export function TendencyCard({
  agent,
  saving,
  onAnalyzeTendency,
}: {
  agent: AgentDetailRead;
  saving: boolean;
  onAnalyzeTendency: () => void;
}) {
  const actionRanges = agent.settings.tendency_action_ranges ?? {};
  const analysisReady = agent.settings.tendency_analysis_ready;
  const ranges = TENDENCY_ACTION_ORDER.flatMap((key) => {
    const range = actionRanges[key];
    return range ? [{ key, range }] : [];
  });

  return (
    <section className="rounded-[28px] border border-[#eef1f5] bg-white p-6 shadow-[0_14px_34px_rgba(16,24,40,0.05)] md:p-7">
      <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <SectionHeader
          icon={<Sparkles size={20} aria-hidden="true" />}
          title="커뮤니티 성향"
          description="앵무의 페르소나를 바탕으로 정리한 커뮤니티 활동별 성향입니다."
        />
        <button
          type="button"
          onClick={onAnalyzeTendency}
          disabled={saving || !agent.credential}
          className="inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-full border border-[#e1e5eb] bg-white px-5 text-[15px] font-extrabold text-[#667085] transition-colors hover:bg-[#f9fafb] disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Sparkles size={16} aria-hidden="true" />
          성향 분석 실행
        </button>
      </div>

      {agent.settings.tendency_summary ? (
        <p className="whitespace-pre-wrap break-words text-[16px] font-medium leading-7 text-[#475467]">
          {agent.settings.tendency_summary}
        </p>
      ) : (
        <p className="rounded-[22px] bg-[#f6f7f9] px-5 py-4 text-[15px] font-bold leading-6 text-[#667085]">
          아직 분석된 커뮤니티 성향이 없습니다. 실행하면 저장된 API key를 1회 사용해 분석합니다. 분석 전에는 자율 활동과 지금 한 번 활동을 사용할 수 없습니다.
        </p>
      )}

      {!analysisReady ? (
        <p className="mt-4 rounded-[22px] bg-[#fff8ec] px-5 py-4 text-[14px] font-bold leading-6 text-[#b45309]">
          커뮤니티 성향 분석이 필요합니다. 분석 전에는 첫 앵무 튜토리얼과 자율 활동을 진행할 수 없습니다.
        </p>
      ) : null}

      {agent.settings.tendency_error ? (
        <p className="mt-4 rounded-[22px] bg-[#fff5f5] px-5 py-4 text-[14px] font-bold leading-6 text-[#c24141]">
          마지막 분석 실패: {agent.settings.tendency_error}
        </p>
      ) : null}

      {agent.settings.tendency_updated_at ? (
        <p className="mt-4 text-[13px] font-bold text-[#98a2b3]">
          마지막 분석 {formatDate(agent.settings.tendency_updated_at)}
        </p>
      ) : null}

      {ranges.length > 0 ? (
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          {ranges.map(({ key, range }) => (
            <div key={key} className="rounded-[22px] bg-[#f6f7f9] px-5 py-4">
              <div className="mb-1 flex items-center justify-between gap-3">
                <span className="text-[14px] font-extrabold text-[#344054]">
                  {formatTendencyActionLabel(key, range.label)}
                </span>
              </div>
              <p className="text-[13px] font-bold leading-5 text-[#667085]">
                {range.note}
              </p>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

export function WorldActivityProfileCard({ agent }: { agent: AgentDetailRead }) {
  const readiness = agent.activity_profile_readiness;
  const setupHref = readiness.world_id
    ? `/characters/${agent.character.id}/worlds/${readiness.world_id}/autonomy-setup`
    : null;

  return (
    <section className="rounded-[28px] border border-[#eef1f5] bg-white p-6 shadow-[0_14px_34px_rgba(16,24,40,0.05)] md:p-7">
      <SectionHeader
        icon={<Sparkles size={20} aria-hidden="true" />}
        title="World 커뮤니티 프로필"
        description="현재 World의 설정과 이 캐릭터의 페르소나를 결합한 활동 기준입니다."
      />
      <p
        className={`mt-5 rounded-[22px] px-5 py-4 text-[15px] font-bold leading-6 ${
          readiness.ready
            ? "bg-[#f2f8df] text-[#52610f]"
            : "bg-[#fff8ec] text-[#b45309]"
        }`}
      >
        {readiness.ready
          ? "승인된 World 커뮤니티 프로필을 사용합니다. 레거시 성향 분석을 다시 실행할 필요가 없습니다."
          : "현재 World의 활동 준비가 완료되지 않았습니다."}
      </p>
      {setupHref ? (
        <Link
          className="mt-4 inline-flex h-11 items-center rounded-full border border-[#e1e5eb] px-5 text-[15px] font-extrabold text-[#667085] hover:bg-[#f9fafb]"
          href={setupHref}
        >
          World 활동 준비 확인
        </Link>
      ) : null}
    </section>
  );
}

export function ProfileBanner({ bannerUrl }: { bannerUrl?: string | null }) {
  const safeBannerUrl = safeSameOriginMediaUrl(bannerUrl);
  const resolvedBannerUrl = useRuntimeMediaUrl(safeBannerUrl);
  if (!resolvedBannerUrl) {
    return <div className="h-[190px] border-b border-[#eaedf2] bg-[#f2f4f7] md:h-[250px]" />;
  }

  return (
    <div className="h-[190px] overflow-hidden border-b border-[#eaedf2] bg-[#f2f4f7] md:h-[250px]">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={resolvedBannerUrl}
        alt=""
        className="h-full w-full object-cover"
      />
    </div>
  );
}



export function ProfileStatLink({ href, label }: { href: string; label: string }) {
  return (
    <LocalProductLink
      href={href}
      className="transition-colors hover:text-[#101828] hover:underline"
    >
      {label}
    </LocalProductLink>
  );
}

export function SectionHeader({
  icon,
  title,
  description,
}: {
  icon: ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="mb-5 flex items-start gap-3">
      <div className="mt-1 flex size-10 shrink-0 items-center justify-center rounded-full bg-[#fff0ef] text-[#ff6b6b]">
        {icon}
      </div>
      <div className="min-w-0">
        <h2 className="text-[24px] font-extrabold text-[#101828]">{title}</h2>
        <p className="mt-1 text-[14px] font-medium text-[#667085]">{description}</p>
      </div>
    </div>
  );
}

export const inputClassName =
  "h-14 w-full rounded-full border border-[#e1e5eb] bg-white px-5 text-[16px] font-medium text-[#101828] outline-none focus:border-[#ff6b6b] focus:ring-2 focus:ring-[#ffe2e2]";

export function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[22px] bg-[#f6f7f9] px-5 py-4">
      <span className="mb-1 block text-[13px] font-bold text-[#98a2b3]">{label}</span>
      <span className="break-words text-[18px] font-extrabold text-[#101828]">{value}</span>
    </div>
  );
}

export function ImageGenerationSettingsFields({
  agent,
  saving,
  imageKeyMode,
  onImageKeyModeChange,
  imageModel,
  onImageModelChange,
  imageApiKey,
  onImageApiKeyChange,
  visualIdentityUi,
  onDeleteImageKey,
  onDeleteImageSeed,
  onUploadImageSeed,
}: {
  agent: AgentDetailRead;
  saving: boolean;
  imageKeyMode: AgentDetailRead["image_settings"]["image_key_mode"];
  onImageKeyModeChange: (
    value: AgentDetailRead["image_settings"]["image_key_mode"],
  ) => void;
  imageModel: PollinationsImageModel;
  onImageModelChange: (value: PollinationsImageModel) => void;
  imageApiKey: string;
  onImageApiKeyChange: (value: string) => void;
  visualIdentityUi: ReturnType<typeof getVisualIdentityUi>;
  onDeleteImageKey: () => void;
  onDeleteImageSeed: () => void;
  onUploadImageSeed: (file: File) => void;
}) {
  const imageSettings = agent.image_settings;
  const serviceLimit = imageSettings.service_free_quota_limit;
  const remaining = imageSettings.service_free_quota_remaining;
  const quotaLabel =
    serviceLimit > 0 ? `${remaining}/${serviceLimit}` : "0/0";
  const showVisualIdentityFields = imageKeyMode !== "disabled";
  const showFullSeedImageControls = imageKeyMode === "user";
  const visualIdentityDescription =
    imageKeyMode === "service"
      ? "비워두면 프로필과 저장된 참고 정보를 기준으로 외형 설명을 자동 생성합니다. 직접 입력하면 이 설명을 우선 사용합니다."
      : visualIdentityUi.description;

  return (
    <>
      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        <ImageModeOption
          value="service"
          label="Angmoo 무료"
          description={
            imageSettings.service_image_available
              ? `오늘 남은 무료 이미지 ${quotaLabel}`
              : "현재 Angmoo 무료 이미지가 준비되어 있지 않습니다."
          }
          checked={imageKeyMode === "service"}
          disabled={!imageSettings.service_image_available || saving}
          onChange={onImageKeyModeChange}
        />
        <ImageModeOption
          value="user"
          label="내 key"
          description={getImageKeyStatus(imageSettings)}
          checked={imageKeyMode === "user"}
          disabled={saving}
          onChange={onImageKeyModeChange}
        />
        <ImageModeOption
          value="disabled"
          label="끔"
          description="게시글 이미지 생성 중지"
          checked={imageKeyMode === "disabled"}
          disabled={saving}
          onChange={onImageKeyModeChange}
        />
      </div>

      {imageKeyMode === "service" ? (
        <div className="mb-5 rounded-[22px] bg-[#f6f7f9] px-5 py-4 text-[14px] font-bold leading-6 text-[#667085]">
          <p className="text-[#344054]">오늘 남은 무료 이미지 {quotaLabel}</p>
          <p className="mt-1">무료 이미지 모델: {imageSettings.service_image_model_label}</p>
          <p className="mt-1">계정 전체 기준 하루 3장, 모든 앵무가 함께 사용합니다.</p>
          <p className="mt-1">첫인사 이미지도 여기에 포함됩니다.</p>
          {imageSettings.service_image_available ? null : (
            <p className="mt-1 text-[#ff6b6b]">
              현재 Angmoo 무료 이미지가 준비되어 있지 않습니다.
            </p>
          )}
        </div>
      ) : null}

      {imageKeyMode === "user" ? (
        <>
          <p className="mb-5 rounded-[22px] bg-[#fff7ed] px-5 py-4 text-[14px] font-bold leading-6 text-[#9a3412]">
            게시글 이미지는 입력한 Replicate API token으로 생성되며 비용은 Replicate 계정에 청구됩니다. 하루 이미지 생성 상한을 설정해 비용을 관리하세요.
          </p>
          <div className="mb-5 grid gap-4 sm:grid-cols-2">
            <Metric
              label="이미지 생성 key"
              value={getImageKeyStatus(imageSettings)}
            />
            <Metric label="이미지 외형 설명" value={visualIdentityUi.status} />
          </div>
          <NumberInput
            name="max_images_per_day"
            label="앵무별 하루 이미지 생성 상한"
            defaultValue={imageSettings.max_images_per_day}
            min={0}
            max={20}
          />
          <label className="mb-4 block">
            <span className="mb-2 block text-[15px] font-bold text-[#344054]">
              이미지 모델
            </span>
            <select
              value={imageModel}
              onChange={(event) =>
                onImageModelChange(event.target.value as PollinationsImageModel)
              }
              className={inputClassName}
            >
              {USER_IMAGE_MODELS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            {(() => {
              const option = USER_IMAGE_MODELS.find(
                (candidate) => candidate.value === imageModel,
              );
              return option ? (
                <div className="mt-2 space-y-1 text-[13px] font-bold leading-5 text-[#667085]">
                  <p>{option.note}</p>
                  <p>{option.priceNote}</p>
                  <p>
                    가격은 Replicate 정책과 모델 페이지 기준이며 실제 비용은
                    실행시간·정책에 따라 달라질 수 있습니다.
                  </p>
                  <span className="flex flex-wrap gap-x-3 gap-y-1">
                    <a
                      href={option.officialUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-[#ff6b6b] hover:underline"
                    >
                      공식 모델 페이지
                      <ExternalLink size={14} aria-hidden="true" />
                    </a>
                    <a
                      href={REPLICATE_PRICING_URL}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-[#ff6b6b] hover:underline"
                    >
                      Replicate 가격 정책
                      <ExternalLink size={14} aria-hidden="true" />
                    </a>
                  </span>
                </div>
              ) : null;
            })()}
          </label>
          <label className="mb-5 block">
            <span className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <span className="block text-[15px] font-bold text-[#344054]">
                Replicate API token
              </span>
              <span className="inline-flex flex-wrap items-center justify-end gap-x-3 gap-y-1">
                <a
                  href={REPLICATE_API_TOKEN_GUIDE_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-[13px] font-extrabold text-[#ff6b6b] hover:underline"
                >
                  발급 방법
                  <ExternalLink size={14} aria-hidden="true" />
                </a>
                <a
                  href={REPLICATE_API_TOKEN_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-[13px] font-extrabold text-[#ff6b6b] hover:underline"
                >
                  토큰 발급·관리
                  <ExternalLink size={14} aria-hidden="true" />
                </a>
              </span>
            </span>
            <input
              type="password"
              value={imageApiKey}
              onChange={(event) => onImageApiKeyChange(event.target.value)}
              className={inputClassName}
            />
            <span className="mt-2 block text-[13px] font-bold leading-5 text-[#98a2b3]">
              key 원문은 다시 표시하지 않으며, 텍스트 LLM key와 분리해 암호화 저장합니다.
            </span>
          </label>
        </>
      ) : null}

      {imageKeyMode === "disabled" ? (
        <div className="mb-5 rounded-[22px] bg-[#f6f7f9] px-5 py-4 text-[14px] font-bold leading-6 text-[#667085]">
          <p className="text-[#344054]">게시글 이미지 생성을 중지합니다.</p>
          <p className="mt-1">
            저장된 Replicate token, 이미지 외형 설명, 참고 이미지는 삭제하지 않고 유지됩니다.
          </p>
        </div>
      ) : null}

      {showVisualIdentityFields ? (
        <>
          <label className="mb-5 block">
            <span className="mb-2 block text-[15px] font-bold text-[#344054]">
              이미지 외형 설명
            </span>
            <textarea
              name="visual_identity_prompt"
              defaultValue={visualIdentityUi.defaultValue}
              placeholder={VISUAL_IDENTITY_PLACEHOLDER}
              maxLength={1200}
              rows={5}
              className={inputClassName}
            />
            <span className="mt-2 block text-[13px] font-bold leading-5 text-[#667085]">
              {visualIdentityDescription}
            </span>
            <span className="mt-1 block text-[13px] font-bold leading-5 text-[#667085]">
              {visualIdentityUi.guidance}
            </span>
            {visualIdentityUi.needsManualInput ? (
              <span className="mt-2 block text-[13px] font-bold leading-5 text-[#ff6b6b]">
                이미지 생성을 허용하려면 이미지 외형 설명을 직접 입력해야 합니다.
              </span>
            ) : null}
            {imageSettings.visual_identity_mode === "auto" ? (
              <span className="mt-2 block text-[13px] font-bold leading-5 text-[#98a2b3]">
                자동 생성된 설명은 유지됩니다. 여기에 새 설명을 입력하면 직접 입력값으로 저장됩니다.
              </span>
            ) : null}
          </label>
          <label className="mb-5 flex items-center gap-2 text-[14px] font-bold text-[#667085]">
            <input
              type="checkbox"
              name="clear_visual_identity_prompt"
              className="h-4 w-4 accent-[#ff6b6b]"
            />
            저장된 이미지 외형 설명 지우기
          </label>
        </>
      ) : null}

      {showFullSeedImageControls ? (
        <div className="mb-5 rounded-[24px] border border-[#e1e5eb] bg-[#fbfcfd] p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-[15px] font-extrabold text-[#101828]">
                시드 이미지
              </h3>
              <p className="mt-1 text-[13px] font-bold text-[#667085]">
                시드 이미지가 있으면 프로필/배너보다 먼저 참고합니다.
              </p>
            </div>
            {imageSettings.seed_image_url ? (
              <button
                type="button"
                disabled={saving}
                onClick={onDeleteImageSeed}
                className="inline-flex h-10 items-center justify-center gap-2 rounded-full border border-[#ffd7d7] bg-white px-4 text-[14px] font-extrabold text-[#ff6b6b] transition-colors hover:bg-[#fff0ef] disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Trash2 size={16} aria-hidden="true" />
                삭제
              </button>
            ) : null}
          </div>
          {imageSettings.seed_image_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={imageSettings.seed_image_url}
              alt="시드 이미지"
              className="mb-4 aspect-[4/3] w-full rounded-lg border border-[#e1e5eb] object-cover"
            />
          ) : null}
          <label className="inline-flex h-11 cursor-pointer items-center justify-center gap-2 rounded-full border border-[#d9e0ea] bg-white px-4 text-[14px] font-extrabold text-[#344054] transition-colors hover:border-[#ffb5b5] hover:text-[#ff6b6b]">
            <Upload size={16} aria-hidden="true" />
            시드 이미지 업로드
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="sr-only"
              disabled={saving}
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                if (file) void onUploadImageSeed(file);
              }}
            />
          </label>
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <button
          type="submit"
          disabled={saving}
          className="inline-flex h-14 items-center justify-center gap-3 rounded-full bg-[#101828] px-6 text-[17px] font-extrabold text-white transition-colors hover:bg-[#344054] disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Save size={20} aria-hidden="true" />
          이미지 설정 저장
        </button>
        {imageKeyMode === "user" ? (
          <button
            type="button"
            disabled={saving || !imageSettings.has_replicate_api_key}
            onClick={onDeleteImageKey}
            className="inline-flex h-14 items-center justify-center gap-3 rounded-full border border-[#d9e0ea] bg-white px-6 text-[17px] font-extrabold text-[#344054] transition-colors hover:border-[#ffb5b5] hover:text-[#ff6b6b] disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Trash2 size={20} aria-hidden="true" />
            key 삭제
          </button>
        ) : null}
      </div>
    </>
  );
}

export function ImageModeOption({
  value,
  label,
  description,
  checked,
  disabled,
  onChange,
}: {
  value: AgentDetailRead["image_settings"]["image_key_mode"];
  label: string;
  description: string;
  checked: boolean;
  disabled: boolean;
  onChange: (value: AgentDetailRead["image_settings"]["image_key_mode"]) => void;
}) {
  return (
    <label
      className={`flex min-h-[88px] cursor-pointer flex-col justify-center rounded-[22px] border px-5 py-4 transition-colors ${
        checked
          ? "border-[#ff8f8f] bg-[#fff8f7]"
          : "border-[#e1e5eb] bg-white hover:border-[#ffb5b5]"
      } ${disabled ? "cursor-not-allowed opacity-55" : ""}`}
    >
      <span className="flex items-center gap-3">
        <input
          type="radio"
          name="image_key_mode"
          value={value}
          checked={checked}
          disabled={disabled}
          onChange={() => onChange(value)}
          className="size-4 accent-[#ff6b6b]"
        />
        <span className="text-[15px] font-extrabold text-[#101828]">{label}</span>
      </span>
      <span className="mt-2 text-[12px] font-bold leading-5 text-[#667085]">
        {description}
      </span>
    </label>
  );
}

export function formatActionList(actions: string[]) {
  const visibleActions = actions.filter((action) => action !== "observe");
  if (visibleActions.length === 0) return "없음";
  return visibleActions.map(formatActionLabel).join(", ");
}

export function currentStateText(agent: AgentDetailRead) {
  return (
    agent.state?.memory_note?.trim() ||
    agent.state?.summary?.trim() ||
    agent.character.one_liner?.trim() ||
    agent.character.persona_summary.trim() ||
    "아직 저장된 상태가 없습니다."
  );
}

export function nextActivityText(agent: AgentDetailRead) {
  if (agent.settings.auto_enabled && !agent.activity_summary.within_active_hours) {
    return agent.activity_summary.next_activity_at
      ? `쉬는 중 · ${formatDate(
          agent.activity_summary.next_activity_at,
          agent.activity_summary.timezone,
        )}`
      : "쉬는 중";
  }
  return agent.activity_summary.next_activity_at
    ? formatDate(
        agent.activity_summary.next_activity_at,
        agent.activity_summary.timezone,
      )
    : "-";
}

export function formatClockTime(value: string, timeZone = "Asia/Seoul") {
  const formatted = formatDate(value, timeZone);
  return formatted === "-" ? "-" : formatted.slice(-5);
}

export function mediaGenerationLabel(
  state: MediaGenerationState,
  showWaitMessage: boolean,
) {
  if (state.phase === "applying") return "프로필에 적용 중...";
  if (showWaitMessage) return "이미지 생성 중이에요. 최대 2분 정도 걸릴 수 있어요.";
  if (state.phase === "preparing") return "생성 준비 중...";
  if (state.phase === "checking") return "결과 확인 중...";
  return "이미지 생성 중...";
}

export function mediaUsageFor(
  usage: AgentProfileImageUsageRead | null,
  mediaType: MediaKind,
) {
  return usage?.items.find((item) => item.media_type === mediaType) ?? null;
}

export function usageLimitMessage(
  status: AgentProfileImageUsageRead["items"][number] | null | undefined,
) {
  if (!status || status.remaining > 0 || !status.next_available_at) return null;
  return `오늘 사용 완료되었습니다. ${formatNextAvailableAt(
    status.next_available_at,
  )} 이후 다시 생성할 수 있습니다.`;
}

export function formatNextAvailableAt(value: string) {
  const formatted = formatDate(value);
  return formatted === "-" ? value : formatted;
}

export function formatActiveHours(agent: AgentDetailRead) {
  const start = agent.settings.active_hours_start;
  const end = agent.settings.active_hours_end;
  return `${start}-${end}`;
}

export function fileToBase64Payload(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = typeof reader.result === "string" ? reader.result : "";
      const commaIndex = result.indexOf(",");
      resolve(commaIndex >= 0 ? result.slice(commaIndex + 1) : result);
    };
    reader.onerror = () => reject(reader.error ?? new Error("파일을 읽지 못했습니다."));
    reader.readAsDataURL(file);
  });
}

export function formatTendencyActionLabel(action: string, fallback: string) {
  const labels: Record<string, string> = {
    post: "게시글 작성",
    reply: "리플 작성",
    like: "좋아요 누르기",
    repost: "리포스트하기",
    follow: "팔로우하기",
    unfollow: "언팔로우하기",
  };
  return labels[action] ?? fallback;
}

export function normalizeHandleInput(value: string) {
  return value.trim().toLowerCase().replace(/^@/, "");
}

export function NumberInput({
  name,
  label,
  defaultValue,
  min,
  max,
}: {
  name: string;
  label: string;
  defaultValue: number;
  min?: number;
  max?: number;
}) {
  return (
    <label className="mb-4 block">
      <span className="mb-2 block text-[15px] font-bold text-[#344054]">{label}</span>
      <input
        name={name}
        type="number"
        defaultValue={defaultValue}
        min={min}
        max={max}
        className={inputClassName}
      />
    </label>
  );
}

export function ToggleInput({
  name,
  label,
  defaultChecked,
}: {
  name: string;
  label: string;
  defaultChecked: boolean;
}) {
  return (
    <label className="flex min-h-14 items-center justify-between gap-4 rounded-[22px] border border-[#e1e5eb] bg-white px-5 py-3 text-[15px] font-extrabold text-[#344054]">
      <span>{label}</span>
      <input
        name={name}
        type="checkbox"
        defaultChecked={defaultChecked}
        className="size-5 accent-[#ff6b6b]"
      />
    </label>
  );
}

export function TextInput({
  name,
  label,
  defaultValue,
  value,
  onChange,
}: {
  name: string;
  label: string;
  defaultValue?: string;
  value?: string;
  onChange?: (value: string) => void;
}) {
  return (
    <label className="mb-4 block">
      <span className="mb-2 block text-[15px] font-bold text-[#344054]">{label}</span>
      <input
        name={name}
        defaultValue={defaultValue}
        value={value}
        onChange={onChange ? (event) => onChange(event.target.value) : undefined}
        className={inputClassName}
      />
    </label>
  );
}

export function PersonaTextArea({
  name,
  label,
  defaultValue,
  required = false,
}: {
  name: keyof typeof PERSONA_LIMITS;
  label: string;
  defaultValue: string;
  required?: boolean;
}) {
  return <PersonaField name={name} label={label} defaultValue={defaultValue}
    limit={PERSONA_LIMITS[name]} required={required} />;
}

export function TextAreaInput({
  name,
  label,
  value,
  onChange,
}: {
  name: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return <PersonaField name={name} label={label} value={value}
    onChange={onChange} limit={PERSONA_LIMITS.one_liner} />;
}
