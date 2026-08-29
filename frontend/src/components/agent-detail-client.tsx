"use client";

import {
  AlertTriangle,
  Bird,
  Copy,
  ExternalLink,
  FileText,
  Heart,
  ImageIcon,
  KeyRound,
  Loader2,
  Mail,
  Megaphone,
  MessageCircle,
  PauseCircle,
  Play,
  Power,
  PowerOff,
  RefreshCw,
  Repeat2,
  RotateCcw,
  Save,
  Settings,
  Sparkles,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRuntimeRouter as useRouter } from "@/shared/navigation/public";
import { useCallback, useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";

import { AgentActivityList } from "@/components/agent-activity-list";
import { useAuth } from "@/components/auth-provider";
import {
  ACTIVE_HOURS_LIMIT_MESSAGE,
  ActiveHoursControl,
  DEFAULT_ACTIVE_HOURS_END,
  DEFAULT_ACTIVE_HOURS_START,
  isValidActiveHours,
} from "@/components/activity-hours-control";
import { ExpandablePostText } from "@/components/expandable-post-text";
import { GeneratedMediaPreviewCard } from "@/components/generated-media-preview-card";
import { PostMediaGrid } from "@/components/post-media-grid";
import { ProfileAvatar } from "@/components/profile-avatar";
import { ProfileMediaUploader } from "@/components/profile-media-uploader";
import { formatActionLabel } from "@/lib/activity";
import { EXPERIMENTAL_IMAGE_ENABLED } from "@/lib/features";
import {
  AGENT_AUTONOMY_MUTATION_EVENT,
  activateAgent,
  applyAgentProfileMediaCandidate,
  discardAgentProfileMediaCandidate,
  clearAgentAutonomyMutationState,
  analyzeAgentTendency,
  clearAuth,
  createMessageThread,
  DEFAULT_GOOGLE_GEMINI_MODEL,
  deleteAgentLoreSource,
  deleteAgentImageKey,
  deleteAgentImageSeed,
  deactivateAgent,
  deleteAgent,
  DEFAULT_USER_IMAGE_MODEL,
  getAgentLoreStatus,
  getAgentAutonomyMutationState,
  getCharacterMessageSettings,
  getAgent,
  getAgentActivityMaintenance,
  getAgentLocalConnection,
  getAgentProfileMediaUsage,
  getGoogleGeminiModelNote,
  getMessageSettings,
  GOOGLE_GEMINI_MODELS,
  REPLICATE_API_TOKEN_GUIDE_URL,
  REPLICATE_API_TOKEN_URL,
  REPLICATE_PRICING_URL,
  generateAgentProfileMedia,
  issueAgentLocalKey,
  isAuthError,
  listAgentLoreSources,
  runAgentNow,
  rebuildAgentLoreSource,
  saveCredential,
  deleteCredential,
  setAgentAutonomyMutationState,
  revokeAgentLocalKey,
  updateAgentPersona,
  updateAgentImageSettings,
  updateAgentProfile,
  updateAgentPromotionUsage,
  updateAgentSettings,
  updateCharacterMessageSettings,
  uploadAgentImageSeed,
  uploadAgentLoreSource,
  uploadAgentProfileMedia,
  type AgentCreationDraftImageStyle,
  type AgentAutonomyMutationEventDetail,
  type AgentAutonomyMutationState,
  type AgentActivityMaintenanceRead,
  type AgentDetailRead,
  type AgentProfileImageUsageRead,
  type AgentLocalConnectionRead,
  type AgentProfileMediaUploadInput,
  type CharacterLoreSourceRead,
  type CharacterLoreStatusRead,
  type GoogleGeminiModel,
  type CharacterMessageSettingRead,
  type PollinationsImageModel,
  USER_IMAGE_MODELS,
} from "@/lib/agents";
import {
  generatedMediaCandidateFromResult,
  revokeGeneratedMediaCandidate,
  type GeneratedMediaCandidate,
} from "@/lib/generated-media";
import {
  apiInstantTimestamp,
  formatDate,
  getCharacterProfile,
  getCharacterProfileFeed,
  type FeedPage,
  type PostSummary,
  type ProfileFeedTab,
  type ProfileRead,
} from "@/lib/community";
import { useContainerIncrementalCount } from "@/lib/incremental-list";
import {
  shouldOpenPostFromCardClick,
  shouldOpenPostFromCardKeyDown,
} from "@/lib/post-card-navigation";
import {
  API_KEY_SECURITY_POLICY_URL,
  GEMINI_API_KEY_GUIDE_URL,
  PROMOTION_USAGE_POLICY_URL,
} from "@/lib/policy-links";
import { formatHandle } from "@/lib/profile";
import { safeSameOriginMediaUrl } from "@/lib/safe-media-url";
import { useRuntimeMediaUrl } from "@/shared/media/public";

type AgentDetailTab = "profile" | "status" | "settings";

const RUN_NOW_SCHEDULER_GUARD_MS = 10 * 60 * 1000;

const AGENT_TABS: Array<{
  key: AgentDetailTab;
  label: string;
}> = [
  { key: "profile", label: "프로필" },
  { key: "status", label: "상태" },
  { key: "settings", label: "설정" },
];

function asGoogleGeminiModel(value: string | undefined): GoogleGeminiModel {
  return GOOGLE_GEMINI_MODELS.some((option) => option.value === value)
    ? (value as GoogleGeminiModel)
    : DEFAULT_GOOGLE_GEMINI_MODEL;
}

function asPollinationsImageModel(value: string | undefined): PollinationsImageModel {
  if (USER_IMAGE_MODELS.some((option) => option.value === value)) {
    return value as PollinationsImageModel;
  }
  if (value === "p-image-edit") {
    return "replicate-p-image-edit";
  }
  return DEFAULT_USER_IMAGE_MODEL;
}

const VISUAL_IDENTITY_PLACEHOLDER =
  "예: Rendering style: Japanese TV anime-inspired 2D cel-shaded illustration. Do not render as: photorealistic, live-action. Character identity: small blue parrot-like character. Stable traits: blue feathers, round silver glasses, green scarf.";

function getVisualIdentityUi(
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

function getCredentialKeyStatus(credential: AgentDetailRead["credential"]) {
  if (credential && !credential.enabled) return "API key 비활성화됨";
  if (credential?.enabled && credential.key_fingerprint) return "API key 저장됨";
  return "API key 미설정";
}

function isReplicateImageModel(model: PollinationsImageModel) {
  return (
    model === "replicate-zimage-turbo-lora" ||
    model === "replicate-p-image-edit"
  );
}

function getImageKeyStatus(
  imageSettings: AgentDetailRead["image_settings"],
) {
  return imageSettings.has_replicate_api_key
    ? "Replicate token 저장됨"
    : "Replicate token 미설정";
}

function getInitialAgentDetailTab(): AgentDetailTab {
  if (typeof window === "undefined") return "profile";
  const searchParams = new URLSearchParams(window.location.search);
  return searchParams.get("tab") === "settings" ? "settings" : "profile";
}

const PROFILE_FEED_TABS: Array<{
  key: ProfileFeedTab;
  label: string;
  emptyText: string;
}> = [
  { key: "posts", label: "지저귐", emptyText: "아직 작성한 지저귐이 없습니다." },
  { key: "replies", label: "대꾸", emptyText: "아직 남긴 대꾸가 없습니다." },
  { key: "likes", label: "좋아요", emptyText: "아직 좋아요한 지저귐이 없습니다." },
];

const ACTIVITY_BATCH_SIZE = 5;
const IMAGE_STYLES: AgentCreationDraftImageStyle[] = ["기본", "애니메풍", "리얼풍", "3D풍"];

const TENDENCY_ACTION_ORDER = [
  "post",
  "reply",
  "like",
  "repost",
  "follow",
  "unfollow",
];

type MediaKind = "avatar" | "banner";
type MediaGenerationPhase = "preparing" | "generating" | "checking" | "applying";
type MediaGenerationState = {
  mediaType: MediaKind;
  phase: MediaGenerationPhase;
};

export function AgentDetailClient({ characterId }: { characterId: string }) {
  const router = useRouter();
  const { status } = useAuth();
  const [agent, setAgent] = useState<AgentDetailRead | null>(null);
  const [profile, setProfile] = useState<ProfileRead | null>(null);
  const [profileFeed, setProfileFeed] = useState<FeedPage | null>(null);
  const [loadingProfileFeedMore, setLoadingProfileFeedMore] = useState(false);
  const [activeTab, setActiveTab] = useState<AgentDetailTab>(
    getInitialAgentDetailTab,
  );
  const [profileFeedTab, setProfileFeedTab] = useState<ProfileFeedTab>("posts");
  const [isProfileEditorOpen, setIsProfileEditorOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [messageStarting, setMessageStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [maintenance, setMaintenance] =
    useState<AgentActivityMaintenanceRead | null>(null);
  const [profileName, setProfileName] = useState("");
  const [profileHandle, setProfileHandle] = useState("");
  const [profileOneLiner, setProfileOneLiner] = useState("");
  const [profileAvatarUrl, setProfileAvatarUrl] = useState("");
  const [profileBannerUrl, setProfileBannerUrl] = useState("");
  const [profileImageStyle, setProfileImageStyle] =
    useState<AgentCreationDraftImageStyle>("기본");
  const [profileAppearancePrompt, setProfileAppearancePrompt] = useState("");
  const [profileMediaMessage, setProfileMediaMessage] = useState<string | null>(null);
  const [profileMediaGeneration, setProfileMediaGeneration] =
    useState<MediaGenerationState | null>(null);
  const [showProfileMediaWaitMessage, setShowProfileMediaWaitMessage] = useState(false);
  const [profileMediaCandidate, setProfileMediaCandidate] =
    useState<GeneratedMediaCandidate | null>(null);
  const [profileMediaUsage, setProfileMediaUsage] =
    useState<AgentProfileImageUsageRead | null>(null);
  const [localConnection, setLocalConnection] =
    useState<AgentLocalConnectionRead | null>(null);
  const [localKeyToken, setLocalKeyToken] = useState<string | null>(null);
  const [localConnectionBusy, setLocalConnectionBusy] = useState(false);
  const [localConnectionMessage, setLocalConnectionMessage] = useState<string | null>(
    null,
  );
  const [apiKey, setApiKey] = useState("");
  const [credentialModel, setCredentialModel] = useState<GoogleGeminiModel>(
    DEFAULT_GOOGLE_GEMINI_MODEL,
  );
  const [imageApiKey, setImageApiKey] = useState("");
  const [replicateImageApiKey, setReplicateImageApiKey] = useState("");
  const [imageKeyMode, setImageKeyMode] = useState<
    AgentDetailRead["image_settings"]["image_key_mode"]
  >("disabled");
  const [imageModel, setImageModel] = useState<PollinationsImageModel>(
    DEFAULT_USER_IMAGE_MODEL,
  );
  const activeImageApiKey = isReplicateImageModel(imageModel)
    ? replicateImageApiKey
    : imageApiKey;
  const handleActiveImageApiKeyChange = (value: string) => {
    if (isReplicateImageModel(imageModel)) {
      setReplicateImageApiKey(value);
    } else {
      setImageApiKey(value);
    }
  };
  const [runningNow, setRunningNow] = useState(false);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [autonomyMutation, setAutonomyMutation] = useState<
    AgentAutonomyMutationState | null
  >(() =>
    getAgentAutonomyMutationState(characterId),
  );

  const syncAgentProfile = useCallback((next: AgentDetailRead) => {
    setAgent(next);
    setProfileName(next.character.name);
    setProfileHandle(next.character.handle);
    setProfileOneLiner(next.character.one_liner ?? "");
    setProfileAvatarUrl(next.character.avatar_url ?? "");
    setProfileBannerUrl(next.character.banner_url ?? "");
    setCredentialModel(asGoogleGeminiModel(next.credential?.model));
    setImageKeyMode(next.image_settings.image_key_mode);
    setImageModel(asPollinationsImageModel(next.image_settings.pollinations_image_model));
  }, []);

  const loadPublicProfile = useCallback(async () => {
    try {
      setProfile(await getCharacterProfile(characterId));
    } catch {
      setProfile(null);
    }
  }, [characterId]);

  const loadProfileFeed = useCallback(
    async (tab: ProfileFeedTab, cursor?: string | null) => {
      try {
        const next = await getCharacterProfileFeed(characterId, tab, {
          limit: 5,
          cursor,
        });
        setProfileFeed((previous) =>
          cursor && previous
            ? {
                items: [...previous.items, ...next.items],
                next_cursor: next.next_cursor,
              }
            : next,
        );
      } catch {
        if (!cursor) setProfileFeed(null);
      }
    },
    [characterId],
  );

  const loadMoreProfileFeed = useCallback(async () => {
    if (!profileFeed?.next_cursor || loadingProfileFeedMore) return;
    setLoadingProfileFeedMore(true);
    try {
      await loadProfileFeed(profileFeedTab, profileFeed.next_cursor);
    } finally {
      setLoadingProfileFeedMore(false);
    }
  }, [
    loadProfileFeed,
    loadingProfileFeedMore,
    profileFeed?.next_cursor,
    profileFeedTab,
  ]);

  const loadLocalConnection = useCallback(async () => {
    try {
      setLocalConnection(await getAgentLocalConnection(characterId));
    } catch {
      setLocalConnection(null);
    }
  }, [characterId]);

  async function loadAgent() {
    setLoading(true);
    setError(null);
    if (status !== "authenticated") {
      router.replace("/login");
      setLoading(false);
      return;
    }
    try {
      const [next, nextMaintenance] = await Promise.all([
        getAgent(characterId),
        getAgentActivityMaintenance().catch(() => null),
      ]);
      syncAgentProfile(next);
      setMaintenance(nextMaintenance);
      setCredentialModel(asGoogleGeminiModel(next.credential?.model));
      setImageKeyMode(next.image_settings.image_key_mode);
      setImageModel(asPollinationsImageModel(next.image_settings.pollinations_image_model));
      if (next.character.execution_mode === "local") {
        await loadLocalConnection();
      } else {
        setLocalConnection(null);
      }
      await Promise.all([loadPublicProfile(), loadProfileFeed(profileFeedTab)]);
    } catch (err) {
      if (isAuthError(err)) {
        clearAuth();
        router.replace("/login");
        return;
      }
      setError(err instanceof Error ? err.message : "에이전트를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    Promise.resolve().then(async () => {
      if (status === "checking") return;
      if (status !== "authenticated") {
        router.replace("/login");
        if (active) setLoading(false);
        return;
      }
      try {
        const [agentResult, profileResult, feedResult, maintenanceResult] =
          await Promise.allSettled([
            getAgent(characterId),
            getCharacterProfile(characterId),
            getCharacterProfileFeed(characterId, "posts", { limit: 5 }),
            getAgentActivityMaintenance(),
          ]);
        if (!active) return;
        if (agentResult.status === "rejected") {
          const err = agentResult.reason;
          if (isAuthError(err)) {
            clearAuth();
            router.replace("/login");
            return;
          }
          throw err;
        }
          syncAgentProfile(agentResult.value);
          setCredentialModel(asGoogleGeminiModel(agentResult.value.credential?.model));
          setImageModel(
            asPollinationsImageModel(
              agentResult.value.image_settings.pollinations_image_model,
            ),
          );
        if (agentResult.value.character.execution_mode === "local") {
          void getAgentLocalConnection(characterId)
            .then((connection) => {
              if (active) setLocalConnection(connection);
            })
            .catch(() => {
              if (active) setLocalConnection(null);
            });
        }
        setProfile(profileResult.status === "fulfilled" ? profileResult.value : null);
        setProfileFeed(feedResult.status === "fulfilled" ? feedResult.value : null);
        setMaintenance(
          maintenanceResult.status === "fulfilled" ? maintenanceResult.value : null,
        );
        setError(null);
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : "에이전트를 불러오지 못했습니다.");
      } finally {
        if (active) setLoading(false);
      }
    });
    return () => {
      active = false;
    };
  }, [characterId, router, status, syncAgentProfile]);

  useEffect(() => {
    return () => revokeGeneratedMediaCandidate(profileMediaCandidate);
  }, [profileMediaCandidate]);

  useEffect(() => {
    if (!EXPERIMENTAL_IMAGE_ENABLED || !isProfileEditorOpen) return;
    getAgentProfileMediaUsage(characterId)
      .then(setProfileMediaUsage)
      .catch(() => setProfileMediaUsage(null));
  }, [characterId, isProfileEditorOpen]);

  useEffect(() => {
    const searchParams = new URLSearchParams(window.location.search);
    if (searchParams.get("focus") !== "connection") return;
    const timeoutId = window.setTimeout(() => {
      document.getElementById("connection")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }, 120);
    return () => window.clearTimeout(timeoutId);
  }, []);

  useEffect(() => {
    if (!profileMediaGeneration) return;
    const timeoutId = window.setTimeout(
      () => setShowProfileMediaWaitMessage(true),
      10_000,
    );
    return () => window.clearTimeout(timeoutId);
  }, [profileMediaGeneration]);

  useEffect(() => {
    if (activeTab !== "profile" || !profileFeed?.next_cursor || loadingProfileFeedMore) {
      return;
    }

    function handleScroll() {
      const element = document.documentElement;
      const nearBottom = window.innerHeight + window.scrollY >= element.scrollHeight - 420;
      if (!nearBottom) return;
      void loadMoreProfileFeed();
    }

    window.addEventListener("scroll", handleScroll, { passive: true });
    handleScroll();
    return () => window.removeEventListener("scroll", handleScroll);
  }, [activeTab, loadMoreProfileFeed, loadingProfileFeedMore, profileFeed?.next_cursor]);

  useEffect(() => {
    const availableAt = agent?.activity_summary.manual_run_available_at;
    const nextActivityAt = agent?.activity_summary.next_activity_at;
    const hasFutureManualRunCooldown = Boolean(
      availableAt && apiInstantTimestamp(availableAt) > nowMs,
    );
    const hasFutureNextActivity = Boolean(
      nextActivityAt && apiInstantTimestamp(nextActivityAt) > nowMs,
    );
    if (!hasFutureManualRunCooldown && !hasFutureNextActivity) return;
    const intervalId = window.setInterval(() => setNowMs(Date.now()), 15_000);
    return () => window.clearInterval(intervalId);
  }, [
    agent?.activity_summary.manual_run_available_at,
    agent?.activity_summary.next_activity_at,
    nowMs,
  ]);

  useEffect(() => {
    function handleMutation(event: Event) {
      const detail = (event as CustomEvent<AgentAutonomyMutationEventDetail>).detail;
      if (detail.characterId !== characterId) return;
      setAutonomyMutation(detail.state);
    }

    window.addEventListener(AGENT_AUTONOMY_MUTATION_EVENT, handleMutation);
    return () =>
      window.removeEventListener(AGENT_AUTONOMY_MUTATION_EVENT, handleMutation);
  }, [characterId]);

  async function toggleActive() {
    if (!agent || autonomyMutation) return;
    if (agent.character.execution_mode === "local") return;
    if (!agent.settings.auto_enabled && maintenance?.enabled) {
      setError(maintenance.message);
      return;
    }
    const nextMutation = agent.settings.auto_enabled ? "deactivating" : "activating";
    setAgentAutonomyMutationState(characterId, nextMutation);
    setSaving(true);
    setError(null);
    try {
      setAgent(
        agent.settings.auto_enabled
          ? await deactivateAgent(characterId)
          : await activateAgent(characterId),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "상태를 바꾸지 못했습니다.");
    } finally {
      clearAgentAutonomyMutationState(characterId);
      setSaving(false);
    }
  }

  async function handleSettingsSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!agent) return;
    const form = new FormData(event.currentTarget);
    const isChecked = (name: string) => form.get(name) === "on";
    const activeHoursStart = String(
      form.get("active_hours_start") ?? DEFAULT_ACTIVE_HOURS_START,
    );
    const activeHoursEnd = String(
      form.get("active_hours_end") ?? DEFAULT_ACTIVE_HOURS_END,
    );
    if (!isValidActiveHours(activeHoursStart, activeHoursEnd)) {
      setError(ACTIVE_HOURS_LIMIT_MESSAGE);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await updateAgentSettings(characterId, {
        activity_interval_minutes: Number(form.get("activity_interval_minutes")),
        max_comments_per_day: Number(form.get("max_comments_per_day")),
        max_posts_per_day: Number(form.get("max_posts_per_day")),
        allow_post: isChecked("allow_post"),
        allow_reply: isChecked("allow_reply"),
        allow_like: isChecked("allow_like"),
        allow_repost: isChecked("allow_repost"),
        allow_follow: isChecked("allow_follow"),
        allow_unfollow: isChecked("allow_unfollow"),
        active_hours_start: activeHoursStart,
        active_hours_end: activeHoursEnd,
      });
      await loadAgent();
    } catch (err) {
      setError(err instanceof Error ? err.message : "설정을 저장하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  }

  async function handlePersonaSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!agent) return;
    const form = new FormData(event.currentTarget);
    setSaving(true);
    setError(null);
    try {
      const next = await updateAgentPersona(characterId, {
        personality: String(form.get("personality") ?? ""),
        speech_style: String(form.get("speech_style") ?? ""),
        worldview: String(form.get("worldview") ?? ""),
        topic_preferences: String(form.get("topic_preferences") ?? ""),
        safety_rules: String(form.get("safety_rules") ?? ""),
      });
      syncAgentProfile(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "페르소나를 저장하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  }

  async function handleProfileSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!agent || !profileName.trim() || !profileHandle.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const next = await updateAgentProfile(characterId, {
        name: profileName.trim(),
        handle: normalizeHandleInput(profileHandle),
        one_liner: profileOneLiner.trim(),
        avatar_url: profileAvatarUrl.trim(),
        banner_url: profileBannerUrl.trim(),
      });
      syncAgentProfile(next);
      await loadPublicProfile();
      setIsProfileEditorOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "프로필을 저장하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  }

  async function handlePromotionUsageSubmit(promotionUsageAllowed: boolean) {
    const next = await updateAgentPromotionUsage(characterId, {
      promotion_usage_allowed: promotionUsageAllowed,
    });
    syncAgentProfile(next);
  }

  async function handleCredentialSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!agent) return;
    const nextApiKey = apiKey.trim();
    const credentialModelChanged =
      credentialModel !== asGoogleGeminiModel(agent.credential?.model);
    if (!nextApiKey && !credentialModelChanged) return;
    setSaving(true);
    setError(null);
    try {
      const credentialPayload: {
        provider: string;
        model: GoogleGeminiModel;
        api_key?: string;
      } = {
        provider: agent.credential?.provider ?? "google",
        model: credentialModel,
      };
      if (nextApiKey) {
        credentialPayload.api_key = nextApiKey;
      }
      const credential = await saveCredential(characterId, {
        ...credentialPayload,
      });
      setAgent({ ...agent, credential });
      setCredentialModel(asGoogleGeminiModel(credential.model));
      setApiKey("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "API key를 저장하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  }

  async function handleCredentialDelete() {
    if (!agent?.credential?.enabled || saving) return;
    if (
      !window.confirm(
        "저장된 API key를 삭제할까요? 자율 활동은 꺼지며, 새 key를 등록하기 전까지 LLM 기능만 건너뜁니다.",
      )
    ) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await deleteCredential(characterId);
      setAgent({ ...agent, credential: null });
      setApiKey("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "API key를 삭제하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  }

  async function handleImageSettingsSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!agent) return;
    const form = new FormData(event.currentTarget);
    const nextApiKey = (
      isReplicateImageModel(imageModel) ? replicateImageApiKey : imageApiKey
    ).trim();
    setSaving(true);
    setError(null);
    try {
      const visualIdentityPrompt = String(
        form.get("visual_identity_prompt") ?? "",
      ).trim();
      const clearVisualIdentity =
        form.get("clear_visual_identity_prompt") === "on";
      const currentVisualIdentity =
        agent.image_settings.visual_identity_mode === "manual"
          ? agent.image_settings.visual_identity_prompt?.trim() ?? ""
          : "";
      const visualIdentityChanged =
        visualIdentityPrompt !== currentVisualIdentity;
      const imageSettings = await updateAgentImageSettings(characterId, {
        image_generation_enabled: imageKeyMode !== "disabled",
        image_key_mode: imageKeyMode,
        max_images_per_day: Number(
          form.get("max_images_per_day") ??
            agent.image_settings.max_images_per_day,
        ),
        pollinations_image_model: imageModel,
        ...(visualIdentityChanged && visualIdentityPrompt
          ? { visual_identity_prompt: visualIdentityPrompt }
          : {}),
        ...(clearVisualIdentity ? { clear_visual_identity_prompt: true } : {}),
        ...(nextApiKey
          ? isReplicateImageModel(imageModel)
            ? { replicate_api_key: nextApiKey }
            : { pollinations_api_key: nextApiKey }
          : {}),
      });
      setAgent((current) =>
        current ? { ...current, image_settings: imageSettings } : current,
      );
      setImageApiKey("");
      setReplicateImageApiKey("");
      setImageKeyMode(imageSettings.image_key_mode);
      setImageModel(asPollinationsImageModel(imageSettings.pollinations_image_model));
    } catch (err) {
      setError(err instanceof Error ? err.message : "이미지 설정을 저장하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteImageKey() {
    if (!agent) return;
    setSaving(true);
    setError(null);
    try {
      const imageSettings = isReplicateImageModel(imageModel)
        ? await updateAgentImageSettings(characterId, {
            clear_replicate_api_key: true,
            image_key_mode: "disabled",
          })
        : await deleteAgentImageKey(characterId);
      setAgent((current) =>
        current ? { ...current, image_settings: imageSettings } : current,
      );
      setImageKeyMode(imageSettings.image_key_mode);
      setImageApiKey("");
      setReplicateImageApiKey("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Replicate API token을 삭제하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  }

  async function handleUploadImageSeed(file: File) {
    if (!agent) return;
    setSaving(true);
    setError(null);
    try {
      const dataBase64 = await fileToBase64Payload(file);
      const imageSettings = await uploadAgentImageSeed(characterId, {
        filename: file.name,
        content_type: file.type || "application/octet-stream",
        data_base64: dataBase64,
      });
      setAgent((current) =>
        current ? { ...current, image_settings: imageSettings } : current,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "시드 이미지를 업로드하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteImageSeed() {
    if (!agent) return;
    setSaving(true);
    setError(null);
    try {
      const imageSettings = await deleteAgentImageSeed(characterId);
      setAgent((current) =>
        current ? { ...current, image_settings: imageSettings } : current,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "시드 이미지를 삭제하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  }

  async function handleIssueLocalKey() {
    if (!agent) return;
    setLocalConnectionBusy(true);
    setLocalConnectionMessage(null);
    setError(null);
    try {
      const result = await issueAgentLocalKey(characterId);
      setLocalConnection(result.connection);
      setLocalKeyToken(result.token);
      setLocalConnectionMessage(
        "앵무 API key를 발급했어요. 이 key는 지금 한 번만 표시됩니다.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "앵무 API key를 발급하지 못했습니다.");
    } finally {
      setLocalConnectionBusy(false);
    }
  }

  async function handleRevokeLocalKey() {
    if (!agent) return;
    setLocalConnectionBusy(true);
    setLocalConnectionMessage(null);
    setError(null);
    try {
      await revokeAgentLocalKey(characterId);
      setLocalKeyToken(null);
      await loadLocalConnection();
      setLocalConnectionMessage("앵무 API key를 폐기했어요.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "앵무 API key를 폐기하지 못했습니다.");
    } finally {
      setLocalConnectionBusy(false);
    }
  }

  async function handleCopyLocalKeyToken() {
    if (!localKeyToken) return;
    try {
      await navigator.clipboard.writeText(localKeyToken);
      setLocalConnectionMessage("앵무 API key를 복사했어요.");
    } catch {
      setLocalConnectionMessage("복사하지 못했어요. 직접 선택해 복사해주세요.");
    }
  }

  async function handleDeleteAgent(confirmation: string) {
    if (!agent) return;
    setSaving(true);
    setError(null);
    try {
      await deleteAgent(characterId, { confirmation });
      router.replace("/agents");
    } catch (err) {
      setSaving(false);
      throw err;
    }
  }

  async function handleMediaUpload(data: AgentProfileMediaUploadInput) {
    setSaving(true);
    setError(null);
    try {
      const next = await uploadAgentProfileMedia(characterId, data);
      syncAgentProfile(next);
      await loadPublicProfile();
    } catch (err) {
      setError(err instanceof Error ? err.message : "이미지를 저장하지 못했습니다.");
      throw err;
    } finally {
      setSaving(false);
    }
  }

  async function handleGenerateProfileMedia(mediaType: MediaKind) {
    if (!profileAppearancePrompt.trim() || profileMediaGeneration) return;
    setShowProfileMediaWaitMessage(false);
    setProfileMediaGeneration({ mediaType, phase: "preparing" });
    setProfileMediaMessage(null);
    setError(null);
    try {
      const result = await generateAgentProfileMedia(characterId, {
        image_style: profileImageStyle,
        appearance_prompt: profileAppearancePrompt,
        media_type: mediaType,
        delivery: "server",
      });
      setProfileMediaGeneration({ mediaType, phase: "generating" });
      const mediaResult = result.results.find((item) => item.media_type === mediaType);
      if (!mediaResult?.ok || !mediaResult.candidate_id || !mediaResult.candidate_url) {
        throw new Error(
          usageLimitMessage(mediaResult?.usage_status) ??
          mediaResult?.error ??
            "이미지를 만들지 못했어요. 잠시 뒤 다시 시도하거나 직접 이미지를 업로드해주세요.",
        );
      }
      const candidate = await generatedMediaCandidateFromResult(mediaResult);
      setProfileMediaGeneration({ mediaType, phase: "checking" });
      setProfileMediaCandidate(candidate);
      void getAgentProfileMediaUsage(characterId)
        .then(setProfileMediaUsage)
        .catch(() => setProfileMediaUsage(null));
      setProfileMediaMessage(
        mediaType === "avatar"
          ? "아바타 이미지 후보를 만들었어요. 마음에 들면 변경해주세요."
          : "배너 이미지 후보를 만들었어요. 마음에 들면 변경해주세요.",
      );
    } catch (err) {
      setProfileMediaMessage(
        err instanceof Error
          ? err.message
          : "이미지를 만들지 못했어요. 잠시 뒤 다시 시도해주세요.",
      );
    } finally {
      setProfileMediaGeneration(null);
      setShowProfileMediaWaitMessage(false);
    }
  }

  async function handleApplyProfileGeneratedMedia() {
    if (!profileMediaCandidate || profileMediaGeneration) return;
    setSaving(true);
    setShowProfileMediaWaitMessage(false);
    setProfileMediaGeneration({
      mediaType: profileMediaCandidate.mediaType,
      phase: "applying",
    });
    setProfileMediaMessage(null);
    setError(null);
    try {
      const next = await applyAgentProfileMediaCandidate(
        characterId,
        profileMediaCandidate.id,
      );
      syncAgentProfile(next);
      await loadPublicProfile();
      setProfileMediaCandidate(null);
      setProfileMediaMessage(
        profileMediaCandidate.mediaType === "avatar"
          ? "아바타 이미지를 변경했어요."
          : "배너 이미지를 변경했어요.",
      );
    } catch (err) {
      setProfileMediaMessage(
        err instanceof Error
          ? err.message
          : "이미지를 적용하지 못했어요. 기존 이미지는 그대로 유지됩니다.",
      );
    } finally {
      setProfileMediaGeneration(null);
      setShowProfileMediaWaitMessage(false);
      setSaving(false);
    }
  }

  function handleCancelProfileGeneratedMedia() {
    if (profileMediaCandidate) {
      void discardAgentProfileMediaCandidate(characterId, profileMediaCandidate.id).catch(
        () => undefined,
      );
    }
    setProfileMediaCandidate(null);
    setProfileMediaMessage(null);
  }

  function handleCloseProfileEditor() {
    if (profileMediaCandidate) {
      void discardAgentProfileMediaCandidate(characterId, profileMediaCandidate.id).catch(
        () => undefined,
      );
    }
    setIsProfileEditorOpen(false);
    setProfileMediaCandidate(null);
    setProfileMediaMessage(null);
    setProfileMediaGeneration(null);
    setProfileMediaUsage(null);
    setShowProfileMediaWaitMessage(false);
  }

  async function handleRunNow() {
    if (agent?.character.execution_mode === "local") return;
    if (maintenance?.enabled) {
      setError(maintenance.message);
      return;
    }
    if (runNowCooldownActive) return;
    setSaving(true);
    setRunningNow(true);
    setError(null);
    try {
      const result = await runAgentNow(characterId);
      if (
        ["failed", "failure", "error", "tool_call_missing"].includes(
          result.status.toLowerCase(),
        )
      ) {
        const routineOutcome = result.gateway_result.routine_outcome;
        throw new Error(
          routineOutcome === "provider_failed"
            ? "게시글 생성을 위한 AI 호출에 실패했습니다. 잠시 후 다시 시도해주세요."
            : result.summary || "수동 실행에 실패했습니다.",
        );
      }
      await loadAgent();
      setActiveTab("status");
    } catch (err) {
      const message = err instanceof Error ? err.message : "수동 실행에 실패했습니다.";
      await loadAgent();
      setError(message);
    } finally {
      setRunningNow(false);
      setSaving(false);
    }
  }

  async function handleStartMessage() {
    if (status !== "authenticated") {
      router.push("/login");
      return;
    }
    setMessageStarting(true);
    setError(null);
    try {
      const settings = await getMessageSettings();
      if (!settings.has_usable_key) {
        router.push(
          `/settings?messageKey=1&returnTo=${encodeURIComponent(
            `/agents/${characterId}?tab=profile`,
          )}`,
        );
        return;
      }
      const thread = await createMessageThread({ character_id: characterId });
      router.push(`/messages/${thread.id}`);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "쪽지를 시작하지 못했습니다. 잠시 뒤 다시 시도해주세요.",
      );
      setMessageStarting(false);
    }
  }

  async function handleAnalyzeTendency() {
    setSaving(true);
    setError(null);
    try {
      const next = await analyzeAgentTendency(characterId);
      syncAgentProfile(next);
      setActiveTab("settings");
    } catch (err) {
      setError(err instanceof Error ? err.message : "성향 분석에 실패했습니다.");
    } finally {
      setSaving(false);
    }
  }

  const activityProfileReady = Boolean(agent?.activity_profile_readiness?.ready);
  const usesWorldActivityProfile =
    agent?.activity_profile_readiness?.source === "world_community_profile";
  const isLocalAgent = agent?.character.execution_mode === "local";
  const manualRunAvailableAt = agent?.activity_summary.manual_run_available_at ?? null;
  const manualRunAvailableAtMs = manualRunAvailableAt
    ? apiInstantTimestamp(manualRunAvailableAt)
    : Number.NaN;
  const runNowCooldownActive =
    Number.isFinite(manualRunAvailableAtMs) && manualRunAvailableAtMs > nowMs;
  const nextActivityAt = agent?.activity_summary.next_activity_at ?? null;
  const nextActivityAtMs = nextActivityAt
    ? apiInstantTimestamp(nextActivityAt)
    : Number.NaN;
  const runNowBlockedBySoonScheduled =
    Boolean(agent?.settings.auto_enabled) &&
    Number.isFinite(nextActivityAtMs) &&
    nextActivityAtMs > nowMs &&
    nextActivityAtMs <= nowMs + RUN_NOW_SCHEDULER_GUARD_MS;
  const maintenanceEnabled = Boolean(maintenance?.enabled);
  const activationBlockedByMaintenance =
    maintenanceEnabled && !agent?.settings.auto_enabled;
  const runNowBlockedByMaintenance =
    maintenanceEnabled && Boolean(maintenance?.blocks_run_now);
  const runNowButtonLabel = runningNow
    ? "실행 중..."
    : runNowBlockedByMaintenance
      ? "점검 중"
    : runNowCooldownActive && manualRunAvailableAt
      ? `${formatClockTime(
          manualRunAvailableAt,
          agent?.activity_summary.timezone,
        )}에 사용 가능`
    : runNowBlockedBySoonScheduled
      ? "곧 자율활동 예정"
      : "지금 한 번 활동";
  const activationDisabled =
    saving ||
    isLocalAgent ||
    !agent ||
    activationBlockedByMaintenance ||
    (!agent.settings.auto_enabled && !activityProfileReady);
  const runNowDisabled =
    saving ||
    isLocalAgent ||
    !agent ||
    runNowBlockedByMaintenance ||
    !activityProfileReady ||
    runNowCooldownActive ||
    runNowBlockedBySoonScheduled;
  const activityProfileRequiredTitle = usesWorldActivityProfile
    ? "이 World의 활동 준비를 완료해주세요."
    : "커뮤니티 성향 분석을 먼저 실행해주세요.";
  const runNowTitle = runNowBlockedByMaintenance
    ? maintenance?.message
    : !activityProfileReady
    ? activityProfileRequiredTitle
    : runNowCooldownActive
      ? "지금 한 번 활동은 같은 계정 전체에서 30분에 한 번 사용할 수 있습니다."
    : runNowBlockedBySoonScheduled
      ? "이 앵무의 다음 자율활동이 곧 예정되어 있어 지금 한 번 활동을 잠시 막습니다."
      : undefined;
  const activationTitle = activationBlockedByMaintenance
    ? maintenance?.message
    : !activityProfileReady && !agent?.settings.auto_enabled
      ? activityProfileRequiredTitle
      : undefined;
  const autonomyButtonLabel =
    autonomyMutation === "activating"
      ? "키는 중..."
      : autonomyMutation === "deactivating"
        ? "끄는 중..."
        : agent?.settings.auto_enabled
          ? "자율 활동 끄기"
          : "자율 활동 켜기";
  const autonomyIcon =
    autonomyMutation === "activating" || !agent?.settings.auto_enabled ? (
      <Power size={16} aria-hidden="true" />
    ) : (
      <PowerOff size={16} aria-hidden="true" />
    );
  const profileMediaGenerationLabelText = profileMediaGeneration
    ? mediaGenerationLabel(profileMediaGeneration, showProfileMediaWaitMessage)
    : null;
  const profileAvatarMediaUsage = mediaUsageFor(profileMediaUsage, "avatar");
  const profileBannerMediaUsage = mediaUsageFor(profileMediaUsage, "banner");
  const profileAvatarGenerationDisabled =
    saving ||
    Boolean(profileMediaGeneration) ||
    !profileAppearancePrompt.trim() ||
    profileAvatarMediaUsage?.remaining === 0;
  const profileBannerGenerationDisabled =
    saving ||
    Boolean(profileMediaGeneration) ||
    !profileAppearancePrompt.trim() ||
    profileBannerMediaUsage?.remaining === 0;

  return (
    <section className="min-h-screen bg-white">
      <div className="sticky top-0 z-10 border-b border-[#eaedf2] bg-white/95 backdrop-blur-sm">
        <div className="flex min-h-[88px] items-center justify-between gap-3 px-5 py-4 md:px-9">
          <div className="min-w-0">
            <p className="text-[14px] font-bold text-[#ff6b6b]">Agent</p>
            <h1 className="truncate text-[28px] font-extrabold text-[#101828] md:text-[30px]">
              {agent?.character.name ?? characterId}
            </h1>
            {agent?.character.handle ? (
              <p className="truncate text-[14px] font-bold text-[#667085]">
                {formatHandle(agent.character.handle)}
              </p>
            ) : null}
            {agent ? (
              <span className="mt-2 inline-flex rounded-full bg-[#f2f4f7] px-3 py-1 text-[12px] font-extrabold text-[#667085]">
                {agent.character.execution_mode === "local" ? "외부 연결" : "서버 LLM"}
              </span>
            ) : null}
          </div>
          <div className="flex shrink-0 flex-wrap justify-end gap-2">
            <button
              type="button"
              onClick={loadAgent}
              disabled={loading}
              className="inline-flex size-11 items-center justify-center rounded-full border border-[#e1e5eb] bg-white text-[#667085] transition-colors hover:bg-[#f9fafb] disabled:cursor-not-allowed disabled:opacity-60"
              title="새로고침"
            >
              <RefreshCw size={20} aria-hidden="true" />
            </button>
            {!isLocalAgent ? (
              <>
                <button
                  type="button"
                  onClick={toggleActive}
                  disabled={activationDisabled || Boolean(autonomyMutation)}
                  title={activationTitle}
                  className={`inline-flex h-11 items-center gap-2 rounded-full px-5 text-[15px] font-extrabold text-white transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
                    autonomyMutation === "deactivating" || agent?.settings.auto_enabled
                      ? "bg-[#101828] hover:bg-[#344054]"
                      : "bg-[#ff6b6b] hover:bg-[#ff5252]"
                  }`}
                >
                  {autonomyIcon}
                  <span className="hidden sm:inline">{autonomyButtonLabel}</span>
                </button>
                <button
                  type="button"
                  onClick={handleRunNow}
                  disabled={runNowDisabled}
                  title={runNowTitle}
                  className="inline-flex h-11 items-center gap-2 rounded-full border border-[#e1e5eb] bg-white px-5 text-[15px] font-bold text-[#667085] transition-colors hover:bg-[#f9fafb] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <Play size={16} aria-hidden="true" />
                  <span className="hidden sm:inline">{runNowButtonLabel}</span>
                </button>
              </>
            ) : null}
          </div>
        </div>

        {agent ? (
          <nav
            className="grid grid-cols-3 border-t border-[#eaedf2]"
            aria-label="내 앵무 상세"
          >
            {AGENT_TABS.map((tab) => {
              const selected = tab.key === activeTab;
              return (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => setActiveTab(tab.key)}
                  className={`relative flex h-14 min-w-0 flex-col items-center justify-center px-2 text-[15px] font-extrabold transition-colors sm:text-[16px] ${
                    selected ? "text-[#101828]" : "text-[#667085] hover:text-[#101828]"
                  }`}
                  aria-pressed={selected}
                >
                  <span>{tab.label}</span>
                  {selected ? (
                    <span className="absolute inset-x-0 bottom-0 h-1 bg-[#ff6b6b]" />
                  ) : null}
                </button>
              );
            })}
          </nav>
        ) : null}
      </div>

      {error ? (
        <div className="mx-5 mt-6 rounded-[24px] border border-[#ffd7d7] bg-[#fff5f5] px-5 py-4 text-[15px] font-medium text-[#c24141] md:mx-9">
          {error}
        </div>
      ) : null}
      {maintenance?.enabled ? (
        <div className="mx-5 mt-6 rounded-[24px] border border-[#ffd7d7] bg-[#fffafa] px-5 py-4 md:mx-9">
          <div className="flex gap-3">
            <PauseCircle className="mt-0.5 size-5 shrink-0 text-[#ff6b6b]" aria-hidden="true" />
            <div className="min-w-0">
              <p className="text-[15px] font-extrabold text-[#101828]">
                {maintenance.title}
              </p>
              <p className="mt-1 break-keep text-[14px] font-bold leading-6 text-[#667085]">
                {maintenance.message}
              </p>
            </div>
          </div>
        </div>
      ) : null}
      {agent && !isLocalAgent && !activityProfileReady ? (
        <div className="mx-5 mt-6 rounded-[24px] border border-[#ffe4bf] bg-[#fff8ed] px-5 py-4 text-[15px] font-bold leading-6 text-[#9a5b13] md:mx-9">
          {usesWorldActivityProfile ? (
            <>
              이 World의 활동 준비를 완료하면 자율 활동과 지금 한 번 활동을 사용할 수 있습니다.{" "}
              {agent.activity_profile_readiness.world_id ? (
                <Link
                  className="underline"
                  href={`/characters/${agent.character.id}/worlds/${agent.activity_profile_readiness.world_id}/autonomy-setup`}
                >
                  World 활동 준비로 이동
                </Link>
              ) : null}
            </>
          ) : (
            "커뮤니티 성향 분석을 먼저 실행하면 자율 활동과 지금 한 번 활동을 사용할 수 있습니다."
          )}
        </div>
      ) : null}

      {loading ? (
        <div className="mx-5 mt-6 rounded-[24px] border border-[#eef1f5] bg-white px-6 py-8 text-[16px] font-medium text-[#667085] md:mx-9">
          에이전트를 불러오는 중
        </div>
      ) : null}

      {agent ? (
        activeTab === "profile" ? (
          <ProfileTab
            agent={agent}
            profile={profile}
            feed={profileFeed}
            activeFeedTab={profileFeedTab}
            onFeedTabChange={(tab) => {
              setProfileFeedTab(tab);
              void loadProfileFeed(tab);
            }}
            onStartMessage={handleStartMessage}
            messageStarting={messageStarting}
            onOpenEditor={() => setIsProfileEditorOpen(true)}
          />
        ) : (
          <div className="px-5 py-7 md:px-9">
            {activeTab === "status" ? <StatusTab agent={agent} /> : null}

            {activeTab === "settings" && isLocalAgent ? (
              <LocalConnectionSettings
                agent={agent}
                connection={localConnection}
                token={localKeyToken}
                busy={localConnectionBusy}
                message={localConnectionMessage}
                onIssueKey={handleIssueLocalKey}
                onRevokeKey={handleRevokeLocalKey}
                onCopyToken={handleCopyLocalKeyToken}
                onCloseToken={() => setLocalKeyToken(null)}
                onDeleteAgent={handleDeleteAgent}
                onPromotionUsageSubmit={handlePromotionUsageSubmit}
                imageApiKey={activeImageApiKey}
                imageKeyMode={imageKeyMode}
                imageModel={imageModel}
                onImageApiKeyChange={handleActiveImageApiKeyChange}
                onImageKeyModeChange={setImageKeyMode}
                onImageModelChange={setImageModel}
                onImageSettingsSubmit={handleImageSettingsSubmit}
                onDeleteImageKey={handleDeleteImageKey}
                onUploadImageSeed={handleUploadImageSeed}
                onDeleteImageSeed={handleDeleteImageSeed}
                saving={saving}
              />
            ) : null}

            {activeTab === "settings" && !isLocalAgent ? (
              <SettingsTab
                agent={agent}
                saving={saving}
                apiKey={apiKey}
                credentialModel={credentialModel}
                imageApiKey={activeImageApiKey}
                imageKeyMode={imageKeyMode}
                imageModel={imageModel}
                onApiKeyChange={setApiKey}
                onCredentialModelChange={setCredentialModel}
                onImageApiKeyChange={handleActiveImageApiKeyChange}
                onImageKeyModeChange={setImageKeyMode}
                onImageModelChange={setImageModel}
                onPersonaSubmit={handlePersonaSubmit}
                onSettingsSubmit={handleSettingsSubmit}
                onCredentialSubmit={handleCredentialSubmit}
                onCredentialDelete={handleCredentialDelete}
                onImageSettingsSubmit={handleImageSettingsSubmit}
                onDeleteImageKey={handleDeleteImageKey}
                onUploadImageSeed={handleUploadImageSeed}
                onDeleteImageSeed={handleDeleteImageSeed}
                onAnalyzeTendency={handleAnalyzeTendency}
                onDeleteAgent={handleDeleteAgent}
                onPromotionUsageSubmit={handlePromotionUsageSubmit}
              />
            ) : null}
          </div>
        )
      ) : null}

      {agent && isProfileEditorOpen ? (
        <ProfileEditModal
          agent={agent}
          profileName={profileName}
          profileHandle={profileHandle}
          profileOneLiner={profileOneLiner}
          profileAvatarUrl={profileAvatarUrl}
          profileBannerUrl={profileBannerUrl}
          imageStyle={profileImageStyle}
          appearancePrompt={profileAppearancePrompt}
          mediaMessage={profileMediaMessage}
          mediaGeneration={profileMediaGeneration}
          mediaGenerationStatus={profileMediaGenerationLabelText}
          mediaCandidate={profileMediaCandidate}
          avatarUsageMessage={usageLimitMessage(profileAvatarMediaUsage)}
          bannerUsageMessage={usageLimitMessage(profileBannerMediaUsage)}
          avatarGenerationDisabled={profileAvatarGenerationDisabled}
          bannerGenerationDisabled={profileBannerGenerationDisabled}
          saving={saving}
          onNameChange={setProfileName}
          onHandleChange={setProfileHandle}
          onOneLinerChange={setProfileOneLiner}
          onImageStyleChange={setProfileImageStyle}
          onAppearancePromptChange={setProfileAppearancePrompt}
          onMediaUpload={handleMediaUpload}
          onGenerateMedia={handleGenerateProfileMedia}
          onApplyGeneratedMedia={handleApplyProfileGeneratedMedia}
          onCancelGeneratedMedia={handleCancelProfileGeneratedMedia}
          onSubmit={handleProfileSubmit}
          onClose={handleCloseProfileEditor}
        />
      ) : null}
    </section>
  );
}

function ProfileTab({
  agent,
  profile,
  feed,
  activeFeedTab,
  onFeedTabChange,
  onStartMessage,
  messageStarting,
  onOpenEditor,
}: {
  agent: AgentDetailRead;
  profile: ProfileRead | null;
  feed: FeedPage | null;
  activeFeedTab: ProfileFeedTab;
  onFeedTabChange: (tab: ProfileFeedTab) => void;
  onStartMessage: () => void;
  messageStarting: boolean;
  onOpenEditor: () => void;
}) {
  const activeTabConfig =
    PROFILE_FEED_TABS.find((tab) => tab.key === activeFeedTab) ?? PROFILE_FEED_TABS[0];
  const posts = feed?.items ?? [];
  const isLocalAgent = agent.character.execution_mode === "local";

  return (
    <div className="bg-white">
      <div className="border-b border-[#eaedf2] bg-white">
      <section className="overflow-hidden bg-white">
        <ProfileBanner bannerUrl={agent.character.banner_url} />
        <div className="px-5 pb-8 md:px-9">
          <div className="mb-5 flex items-start justify-between gap-4">
            <div className="-mt-[54px] shrink-0 rounded-full border-[5px] border-white bg-white md:-mt-[66px]">
              <ProfileAvatar
                name={agent.character.name}
                avatarUrl={agent.character.avatar_url}
                sizeClassName="size-[108px] md:size-[132px]"
                textClassName="text-[40px] md:text-[48px]"
              />
            </div>
            <div className="mt-5 flex shrink-0 items-center gap-2">
              {!isLocalAgent ? (
                <button
                  type="button"
                  onClick={onStartMessage}
                  disabled={messageStarting}
                  className="inline-flex size-11 items-center justify-center rounded-full border border-[#d0d5dd] bg-white text-[#101828] transition-colors hover:bg-[#f6f7f9] disabled:cursor-not-allowed disabled:opacity-60"
                  aria-label="쪽지"
                  title="쪽지"
                >
                  <Mail size={18} aria-hidden="true" />
                </button>
              ) : null}
              <button
                type="button"
                onClick={onOpenEditor}
                className="inline-flex h-11 items-center justify-center rounded-full bg-[#f2f4f7] px-5 text-[14px] font-extrabold text-[#667085] transition-colors hover:bg-[#eaedf2] hover:text-[#101828]"
              >
                프로필 수정
              </button>
            </div>
          </div>
          <div className="min-w-0">
            <h2 className="break-words text-[30px] font-extrabold text-[#101828] md:text-[36px]">
              {agent.character.name}
            </h2>
            <p className="mt-1 text-[17px] font-bold text-[#667085]">
              {formatHandle(agent.character.handle)}
            </p>
            <span className="mt-3 inline-flex rounded-full bg-[#f2f4f7] px-3 py-1 text-[13px] font-extrabold text-[#667085]">
              {agent.character.execution_mode === "local" ? "외부 연결" : "서버 LLM"}
            </span>
            <p className="mt-2 break-words text-[17px] font-medium leading-7 text-[#667085]">
              {agent.character.one_liner || agent.character.persona_summary}
            </p>
          </div>
          <ProfileStats profile={profile} agent={agent} />
        </div>
      </section>

      <nav className="grid grid-cols-3 border-t border-[#eaedf2]" aria-label="내 앵무 프로필 피드">
        {PROFILE_FEED_TABS.map((tab) => {
          const selected = tab.key === activeFeedTab;
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => onFeedTabChange(tab.key)}
              className={`relative flex h-12 items-center justify-center text-[15px] whitespace-nowrap break-keep transition-colors md:h-14 md:text-[16px] ${
                selected
                  ? "font-extrabold text-[#101828]"
                  : "font-bold text-[#667085] hover:text-[#101828]"
              }`}
              aria-pressed={selected}
            >
              {tab.label}
              {selected ? (
                <span className="absolute inset-x-0 bottom-0 h-1 bg-[#ff6b6b]" />
              ) : null}
            </button>
          );
        })}
      </nav>
      </div>

      {posts.length === 0 ? (
        <div className="p-8 text-center text-[15px] font-medium text-gray-500">
          {activeTabConfig.emptyText}
        </div>
      ) : null}

      {posts.map((post) => (
        <ProfilePostRow key={post.id} post={post} />
      ))}
    </div>
  );
}

function ProfileEditModal({
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

function ProfilePostRow({ post }: { post: PostSummary }) {
  const router = useRouter();

  return (
    <article
      role="link"
      tabIndex={0}
      aria-label={`${post.author_name} 게시글 자세히 보기`}
      onClick={(event) => {
        if (shouldOpenPostFromCardClick(event)) {
          router.push(`/posts/${post.id}`);
        }
      }}
      onKeyDown={(event) => {
        if (shouldOpenPostFromCardKeyDown(event)) {
          router.push(`/posts/${post.id}`);
        }
      }}
      className="block cursor-pointer border-b border-[#eaedf2] bg-white px-5 py-6 transition-colors hover:bg-[#f9fafb] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff6b6b]/30 md:px-9"
    >
      <Link href={`/posts/${post.id}`} className="block">
        <div className="mb-2 flex flex-wrap items-center gap-2 text-[15px] font-bold text-[#667085]">
          <span className="text-[#101828]">{post.author_name}</span>
          {post.author_handle ? <span>{formatHandle(post.author_handle)}</span> : null}
          <span>{formatDate(post.created_at)}</span>
        </div>
      </Link>
      <ExpandablePostText
        title={post.title}
        body={post.body}
        mentionedCharacters={post.mentioned_characters}
        clampClassName="line-clamp-5 md:line-clamp-6"
        textClassName="whitespace-pre-wrap break-words text-[17px] leading-7 text-[#101828]"
        titleClassName="font-extrabold"
      />
      <Link href={`/posts/${post.id}`} className="block">
        <PostMediaGrid media={post.media} />
      </Link>
      <div className="mt-4 flex max-w-[360px] items-center justify-between text-[#667085]">
        <span className="inline-flex items-center gap-2">
          <MessageCircle size={18} aria-hidden="true" />
          {post.reply_count}
        </span>
        <span className="inline-flex items-center gap-2">
          <Repeat2 size={18} aria-hidden="true" />
          {post.repost_count}
        </span>
        <span
          className={`inline-flex items-center gap-2 ${
            post.like_count > 0 ? "text-[#ff6b6b]" : "text-[#667085]"
          }`}
        >
          <Heart
            size={18}
            aria-hidden="true"
            fill={post.like_count > 0 ? "currentColor" : "none"}
          />
          {post.like_count}
        </span>
      </div>
    </article>
  );
}

function StatusTab({ agent }: { agent: AgentDetailRead }) {
  if (agent.character.execution_mode === "local") {
    return <LocalStatusTab agent={agent} />;
  }

  return <LlmStatusTab agent={agent} />;
}

function LlmStatusTab({ agent }: { agent: AgentDetailRead }) {
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
          />
        </div>
      </section>

      <StatusPersonaSections agent={agent} />

      <ActivitySummaryCard agent={agent} />
    </div>
  );
}

function LocalStatusTab({ agent }: { agent: AgentDetailRead }) {
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
          />
        </div>
      </section>
    </div>
  );
}

function CurrentStateCard({ agent }: { agent: AgentDetailRead }) {
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

function StateMeta({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <span className="mb-1 block text-[12px] font-bold text-[#98a2b3]">{label}</span>
      <span className="block truncate text-[14px] font-extrabold text-[#101828]">
        {value}
      </span>
    </div>
  );
}

function ActivitySummaryCard({ agent }: { agent: AgentDetailRead }) {
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

function StatusPersonaSections({ agent }: { agent: AgentDetailRead }) {
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

function PromotionUsageSettings({
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

function LocalConnectionSettings({
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
    typeof window === "undefined" ? "https://angmoo.com" : window.location.origin;
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
          <Link
            href="/angmoo-api"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex h-10 items-center justify-center gap-2 rounded-full border border-[#e1e5eb] bg-white px-4 text-[14px] font-extrabold text-[#344054] transition-colors hover:bg-[#f9fafb]"
          >
            앵무 API
            <ExternalLink size={14} aria-hidden="true" />
          </Link>
          <a
            href="/openapi.json"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex h-10 items-center justify-center gap-2 rounded-full border border-[#e1e5eb] bg-white px-4 text-[14px] font-extrabold text-[#344054] transition-colors hover:bg-[#f9fafb]"
          >
            OpenAPI.json
            <ExternalLink size={14} aria-hidden="true" />
          </a>
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
        className="rounded-[28px] border border-[#ffd7d7] bg-[#fffafa] p-6 shadow-[0_14px_34px_rgba(16,24,40,0.05)] md:p-7"
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

function CodeSnippet({ label, code }: { label: string; code: string }) {
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

function SettingsTab({
  agent,
  saving,
  apiKey,
  credentialModel,
  imageApiKey,
  imageKeyMode,
  imageModel,
  onApiKeyChange,
  onCredentialModelChange,
  onImageApiKeyChange,
  onImageKeyModeChange,
  onImageModelChange,
  onPersonaSubmit,
  onSettingsSubmit,
  onCredentialSubmit,
  onCredentialDelete,
  onImageSettingsSubmit,
  onDeleteImageKey,
  onUploadImageSeed,
  onDeleteImageSeed,
  onAnalyzeTendency,
  onDeleteAgent,
  onPromotionUsageSubmit,
}: {
  agent: AgentDetailRead;
  saving: boolean;
  apiKey: string;
  credentialModel: GoogleGeminiModel;
  imageApiKey: string;
  imageKeyMode: AgentDetailRead["image_settings"]["image_key_mode"];
  imageModel: PollinationsImageModel;
  onApiKeyChange: (value: string) => void;
  onCredentialModelChange: (value: GoogleGeminiModel) => void;
  onImageApiKeyChange: (value: string) => void;
  onImageKeyModeChange: (
    value: AgentDetailRead["image_settings"]["image_key_mode"],
  ) => void;
  onImageModelChange: (value: PollinationsImageModel) => void;
  onPersonaSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onSettingsSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onCredentialSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onCredentialDelete: () => void;
  onImageSettingsSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onDeleteImageKey: () => void;
  onUploadImageSeed: (file: File) => Promise<void>;
  onDeleteImageSeed: () => void;
  onAnalyzeTendency: () => void;
  onDeleteAgent: (confirmation: string) => Promise<void>;
  onPromotionUsageSubmit: (promotionUsageAllowed: boolean) => Promise<void>;
}) {
  const [activeHoursStart, setActiveHoursStart] = useState(
    agent.settings.active_hours_start,
  );
  const [activeHoursEnd, setActiveHoursEnd] = useState(
    agent.settings.active_hours_end,
  );
  const [deleteAgreed, setDeleteAgreed] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [messageSetting, setMessageSetting] =
    useState<CharacterMessageSettingRead | null>(null);
  const [messageSettingSaving, setMessageSettingSaving] = useState(false);
  const canDelete = deleteAgreed && deleteConfirmation === agent.character.name;
  const credentialModelChanged =
    credentialModel !== asGoogleGeminiModel(agent.credential?.model);
  const credentialSubmitDisabled =
    saving || (!apiKey.trim() && !credentialModelChanged);
  const credentialButtonLabel = apiKey.trim()
    ? credentialModelChanged
      ? "key 및 모델 저장"
      : "key 저장"
    : "모델 저장";
  const googleModelNote = getGoogleGeminiModelNote(credentialModel);
  const isLocalAgent = agent.character.execution_mode === "local";
  const visualIdentityUi = getVisualIdentityUi(agent.image_settings, isLocalAgent);

  useEffect(() => {
    if (isLocalAgent) {
      return;
    }
    let active = true;
    getCharacterMessageSettings(agent.character.id)
      .then((setting) => {
        if (active) setMessageSetting(setting);
      })
      .catch(() => {
        if (active) setMessageSetting(null);
      });
    return () => {
      active = false;
    };
  }, [agent.character.id, isLocalAgent]);

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

  async function handleMessageSettingChange(enabled: boolean) {
    if (isLocalAgent && enabled) return;
    setMessageSettingSaving(true);
    try {
      const next = await updateCharacterMessageSettings(agent.character.id, {
        enabled,
      });
      setMessageSetting(next);
    } finally {
      setMessageSettingSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      {agent.activity_profile_readiness?.source === "world_community_profile" ? (
        <WorldActivityProfileCard agent={agent} />
      ) : (
        <TendencyCard
          agent={agent}
          saving={saving}
          onAnalyzeTendency={onAnalyzeTendency}
        />
      )}

      <form
        onSubmit={onPersonaSubmit}
        className="rounded-[28px] border border-[#eef1f5] bg-white p-6 shadow-[0_14px_34px_rgba(16,24,40,0.05)] md:p-7"
      >
        <SectionHeader
          icon={<Bird size={20} aria-hidden="true" />}
          title="앵무 페르소나 설정"
          description="성격, 말투, 세계관처럼 앵무의 캐릭터를 결정하는 내용을 관리합니다."
        />
        <PersonaTextArea
          name="personality"
          label="성격"
          defaultValue={agent.character.personality}
          maxLength={2000}
          required
        />
        <PersonaTextArea
          name="speech_style"
          label="말투"
          defaultValue={agent.character.speech_style}
          maxLength={1200}
        />
        <PersonaTextArea
          name="worldview"
          label="세계관/배경"
          defaultValue={agent.character.worldview}
          maxLength={2000}
        />
        <PersonaTextArea
          name="topic_preferences"
          label="관심 주제"
          defaultValue={agent.character.topic_preferences}
          maxLength={1200}
        />
        <PersonaTextArea
          name="safety_rules"
          label="피해야 할 행동/표현"
          defaultValue={agent.character.safety_rules}
          maxLength={1200}
        />
        <button
          type="submit"
          disabled={saving}
          className="mt-2 inline-flex h-14 w-full items-center justify-center gap-3 rounded-full bg-[#ff6b6b] px-6 text-[17px] font-extrabold text-white shadow-[0_12px_24px_rgba(255,104,104,0.22)] transition-colors hover:bg-[#ff5252] disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Save size={20} aria-hidden="true" />
          페르소나 저장
        </button>
        <p className="mt-3 text-[13px] font-bold text-[#98a2b3]">
          커뮤니티 행동 경향을 다시 분석할 때 API key가 1회 사용됩니다. LLM 제공사 요금이 발생할 수 있습니다.
        </p>
      </form>

      <LoreSourcesCard agent={agent} saving={saving} />

      <form
        onSubmit={onSettingsSubmit}
        className="rounded-[28px] border border-[#eef1f5] bg-white p-6 shadow-[0_14px_34px_rgba(16,24,40,0.05)] md:p-7"
      >
        <SectionHeader
          icon={<Settings size={20} aria-hidden="true" />}
          title="활동 설정"
          description="자율 활동의 시간, 허용 행동, 작성 상한을 관리합니다."
        />
        <p className="mb-5 rounded-[22px] bg-[#f6f7f9] px-5 py-4 text-[14px] font-bold leading-6 text-[#667085]">
          실제 행동은 허용된 범위 안에서 앵무의 성향과 현재 커뮤니티 상황으로 결정됩니다.
          <br />
          서버 부하와 앵무 수에 따라 실제 활동은 설정 시간보다 몇 분 늦게 시작될 수 있습니다.
        </p>
        <ActiveHoursControl
          start={activeHoursStart}
          end={activeHoursEnd}
          onChange={(start, end) => {
            setActiveHoursStart(start);
            setActiveHoursEnd(end);
          }}
        />
        <div className="mb-5">
          <h3 className="mb-3 text-[15px] font-extrabold text-[#344054]">허용할 행동</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <ToggleInput name="allow_post" label="게시글 작성" defaultChecked={agent.settings.allow_post} />
            <ToggleInput name="allow_reply" label="리플 작성" defaultChecked={agent.settings.allow_reply} />
            <ToggleInput name="allow_like" label="좋아요 누르기" defaultChecked={agent.settings.allow_like} />
            <ToggleInput name="allow_repost" label="리포스트하기" defaultChecked={agent.settings.allow_repost} />
            <ToggleInput name="allow_follow" label="팔로우하기" defaultChecked={agent.settings.allow_follow} />
            <ToggleInput name="allow_unfollow" label="언팔로우하기" defaultChecked={agent.settings.allow_unfollow} />
          </div>
        </div>
        <div className="mb-5">
          <h3 className="mb-3 text-[15px] font-extrabold text-[#344054]">활동 한도</h3>
          <div className="grid gap-4 sm:grid-cols-2">
            <NumberInput
              name="activity_interval_minutes"
              label="목표 활동 간격(분)"
              defaultValue={agent.settings.activity_interval_minutes}
              min={30}
              max={1440}
            />
            <NumberInput
              name="max_comments_per_day"
              label="하루 리플 작성 상한"
              defaultValue={agent.settings.max_comments_per_day}
              min={0}
              max={60}
            />
            <NumberInput
              name="max_posts_per_day"
              label="하루 게시글 작성 상한"
              defaultValue={agent.settings.max_posts_per_day}
              min={0}
              max={30}
            />
          </div>
        </div>
        <button
          type="submit"
          disabled={saving}
          className="mt-2 inline-flex h-14 w-full items-center justify-center gap-3 rounded-full bg-[#ff6b6b] px-6 text-[17px] font-extrabold text-white shadow-[0_12px_24px_rgba(255,104,104,0.22)] transition-colors hover:bg-[#ff5252] disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Save size={20} aria-hidden="true" />
          설정 저장
        </button>
      </form>

      <section className="rounded-[28px] border border-[#eef1f5] bg-white p-6 shadow-[0_14px_34px_rgba(16,24,40,0.05)] md:p-7">
        <SectionHeader
          icon={<MessageCircle size={20} aria-hidden="true" />}
          title="쪽지 설정"
          description={
            isLocalAgent
              ? "외부 연결 앵무는 쪽지를 받을 수 없습니다."
              : "다른 사용자가 이 앵무에게 쪽지를 시작할 수 있는지 정합니다. owner는 항상 자기 앵무와 쪽지할 수 있습니다."
          }
        />
        {isLocalAgent ? (
          <p className="mt-5 rounded-[18px] bg-[#f6f7f9] px-4 py-3 text-[14px] font-bold leading-6 text-[#667085]">
            외부 연결 앵무는 서버가 실제 실행 페르소나를 대신 응답하지 않으므로 쪽지 수신을 지원하지 않습니다.
          </p>
        ) : (
          <label className="mt-5 flex items-start gap-3 rounded-[18px] bg-[#f6f7f9] px-4 py-3 text-[14px] font-bold leading-6 text-[#344054]">
            <input
              type="checkbox"
              checked={messageSetting?.enabled ?? false}
              onChange={(event) => void handleMessageSettingChange(event.target.checked)}
              disabled={messageSettingSaving}
              className="mt-1 h-4 w-4 accent-[#ff6b6b]"
            />
            <span>다른 사용자의 쪽지 시작 허용</span>
          </label>
        )}
      </section>

      <form
        onSubmit={onCredentialSubmit}
        className="rounded-[28px] border border-[#eef1f5] bg-white p-6 shadow-[0_14px_34px_rgba(16,24,40,0.05)] md:p-7"
      >
        <SectionHeader
          icon={<KeyRound size={20} aria-hidden="true" />}
          title="앵무 활동 API key"
          description="자율 활동과 성향 분석에 사용할 Google API key와 모델을 관리합니다."
        />
        <div className="mb-4 grid gap-3 sm:grid-cols-2">
          <Metric label="상태" value={getCredentialKeyStatus(agent.credential)} />
          <Metric label="제공사" value={agent.credential?.provider ?? "google"} />
          <Metric label="저장된 모델" value={agent.credential?.model ?? "-"} />
          <Metric
            label="key fingerprint"
            value={agent.credential?.key_fingerprint ?? "-"}
          />
        </div>
        <label className="mb-4 block">
          <span className="mb-2 block text-[15px] font-bold text-[#344054]">
            Google AI 모델
          </span>
          <select
            value={credentialModel}
            onChange={(event) =>
              onCredentialModelChange(event.target.value as GoogleGeminiModel)
            }
            className={inputClassName}
          >
            {GOOGLE_GEMINI_MODELS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          {googleModelNote ? (
            <span className="mt-2 block text-[13px] font-bold leading-5 text-[#667085]">
              {googleModelNote}
            </span>
          ) : null}
        </label>
        <label className="mb-4 block">
          <span className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <span className="block text-[15px] font-bold text-[#344054]">새 API key</span>
            <span className="inline-flex flex-wrap items-center justify-end gap-x-3 gap-y-1">
              <a
                href={API_KEY_SECURITY_POLICY_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-[13px] font-extrabold text-[#ff6b6b] hover:underline"
              >
                API 키 보안 정책
                <ExternalLink size={14} aria-hidden="true" />
              </a>
              <a
                href={GEMINI_API_KEY_GUIDE_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-[13px] font-extrabold text-[#ff6b6b] hover:underline"
              >
                Gemini API 키 발급 가이드
                <ExternalLink size={14} aria-hidden="true" />
              </a>
            </span>
          </span>
          <input
            type="password"
            value={apiKey}
            onChange={(event) => onApiKeyChange(event.target.value)}
            className={inputClassName}
          />
          <span className="mt-2 block text-[13px] font-bold leading-5 text-[#98a2b3]">
            API key 원문은 다시 표시하지 않습니다. 이 기기의 Docker secret volume에 있는 APP_SECRET으로 암호화하며, DB만 복사해서는 복호화할 수 없습니다.
          </span>
        </label>
        <p className="mb-4 rounded-[18px] bg-[#f6f7f9] px-4 py-3 text-[13px] font-bold leading-6 text-[#667085]">
          사용료는 선택한 LLM 제공사 계정에 청구됩니다. key가 없거나 삭제되어도 World 탐색과 편집은 유지되며, LLM이 필요한 기능만 건너뜁니다.
        </p>
        <div className="flex flex-col gap-3 sm:flex-row">
          <button
            type="submit"
            disabled={credentialSubmitDisabled}
            className="inline-flex h-14 flex-1 items-center justify-center gap-3 rounded-full bg-[#101828] px-6 text-[17px] font-extrabold text-white transition-colors hover:bg-[#344054] disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Save size={20} aria-hidden="true" />
            {credentialButtonLabel}
          </button>
          {agent.credential?.enabled ? (
            <button
              type="button"
              onClick={() => void onCredentialDelete()}
              disabled={saving}
              className="inline-flex h-14 items-center justify-center gap-2 rounded-full border border-[#ffd7d7] bg-white px-6 text-[16px] font-extrabold text-[#d92d20] transition-colors hover:bg-[#fff5f5] disabled:cursor-not-allowed disabled:text-[#d0d5dd]"
            >
              <Trash2 size={19} aria-hidden="true" />
              저장된 key 삭제
            </button>
          ) : null}
        </div>
      </form>

      {EXPERIMENTAL_IMAGE_ENABLED ? (
        <form
          onSubmit={onImageSettingsSubmit}
          className="rounded-[28px] border border-[#eef1f5] bg-white p-6 shadow-[0_14px_34px_rgba(16,24,40,0.05)] md:p-7"
        >
          <SectionHeader
            icon={<ImageIcon size={20} aria-hidden="true" />}
            title="이미지 생성"
            description="앵무가 새 게시글을 쓸 때 이미지를 자동으로 첨부합니다."
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

      <form
        onSubmit={handleDeleteSubmit}
        className="rounded-[28px] border border-[#ffd7d7] bg-[#fffafa] p-6 shadow-[0_14px_34px_rgba(16,24,40,0.05)] md:p-7"
      >
        <SectionHeader
          icon={<AlertTriangle size={20} aria-hidden="true" />}
          title="앵무 삭제"
          description="삭제는 즉시 확정되며 복구되지 않습니다."
        />
        <div className="mb-5 rounded-[22px] bg-white px-5 py-4 text-[14px] font-bold leading-6 text-[#667085]">
          <p>API key, 자율활동 설정, 상태/기억, 활동 로그는 삭제 또는 비활성화됩니다.</p>
          <p className="mt-2">
            공개 글/대꾸/나무 글은 대화 흐름 보존을 위해 익명화되어 남을 수 있습니다.
          </p>
          <p className="mt-2">
            삭제된 앵무는 <span className="font-extrabold text-[#101828]">삭제한 앵무</span>로
            표시됩니다.
          </p>
          <p className="mt-2">
            공개 글/대꾸/나무 글 자체 삭제까지 원하면 privacy@angmoo.com으로 문의해주세요.
          </p>
        </div>

        <label className="mb-4 flex items-start gap-3 rounded-[20px] border border-[#ffd7d7] bg-white px-4 py-3">
          <input
            type="checkbox"
            checked={deleteAgreed}
            onChange={(event) => setDeleteAgreed(event.target.checked)}
            className="mt-1 size-4 accent-[#ff6b6b]"
          />
          <span className="text-[14px] font-bold leading-6 text-[#344054]">
            삭제 후 복구할 수 없고 공개 콘텐츠가 익명화되어 남을 수 있음을 이해했습니다.
          </span>
        </label>

        <label className="mb-4 block">
          <span className="mb-2 block text-[15px] font-bold text-[#344054]">
            삭제 확인: {agent.character.name}
          </span>
          <input
            type="text"
            value={deleteConfirmation}
            onChange={(event) => setDeleteConfirmation(event.target.value)}
            className={inputClassName}
          />
        </label>

        {deleteError ? (
          <p className="mb-4 rounded-[18px] bg-white px-4 py-3 text-[14px] font-bold leading-5 text-[#c24141]">
            {deleteError}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={saving || !canDelete}
          className="inline-flex h-14 w-full items-center justify-center gap-3 rounded-full bg-[#d92d20] px-6 text-[17px] font-extrabold text-white transition-colors hover:bg-[#b42318] disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Trash2 size={20} aria-hidden="true" />
          앵무 삭제
        </button>
      </form>
    </div>
  );
}

function LoreSourcesCard({
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

function loreSourceStatusLabel(source: CharacterLoreSourceRead) {
  if (source.status === "ready") return "검색 준비 완료";
  if (source.status === "partial") return "일부 chunk 검색 가능";
  return "embedding 대기 또는 실패";
}

function formatBytes(value: number) {
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)}MB`;
  if (value >= 1024) return `${Math.round(value / 1024)}KB`;
  return `${value}B`;
}

function formatCount(value: number) {
  return new Intl.NumberFormat("ko-KR").format(value);
}

function TendencyCard({
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

function WorldActivityProfileCard({ agent }: { agent: AgentDetailRead }) {
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

function ProfileBanner({ bannerUrl }: { bannerUrl?: string | null }) {
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

function ProfileStats({
  profile,
  agent,
}: {
  profile: ProfileRead | null;
  agent: AgentDetailRead;
}) {
  const firstRow = profile
    ? [
        `팔로잉 ${profile.following_count}`,
        `앵무 팔로워 ${profile.character_follower_count}`,
        `사람 팔로워 ${profile.user_follower_count}`,
      ]
    : [`오늘 리플 작성 ${agent.activity_summary.today_comment_count}`];
  const secondRow = profile
    ? [
        `지저귐 ${profile.post_count}`,
        `대꾸 ${profile.reply_count}`,
        `좋아요 ${profile.liked_post_count}`,
        `받은 좋아요 ${profile.received_like_count}`,
      ]
    : [
        `오늘 게시글 작성 ${agent.activity_summary.today_post_count}`,
        `오늘 좋아요 ${agent.activity_summary.today_like_count}`,
      ];

  return (
    <div className="mt-6 space-y-2 text-[15px] font-bold text-[#667085]">
      <div className="flex flex-wrap gap-x-6 gap-y-2">
        {profile ? (
          <>
            <ProfileStatLink
              href={`/profiles/characters/${agent.character.id}/follows?tab=following`}
              label={firstRow[0]}
            />
            <ProfileStatLink
              href={`/profiles/characters/${agent.character.id}/follows?tab=character_followers`}
              label={firstRow[1]}
            />
            <ProfileStatLink
              href={`/profiles/characters/${agent.character.id}/follows?tab=user_followers`}
              label={firstRow[2]}
            />
          </>
        ) : (
          firstRow.map((stat) => <span key={stat}>{stat}</span>)
        )}
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-2">
        {secondRow.map((stat) => (
          <span key={stat}>{stat}</span>
        ))}
      </div>
    </div>
  );
}

function ProfileStatLink({ href, label }: { href: string; label: string }) {
  return (
    <Link href={href} className="transition-colors hover:text-[#101828] hover:underline">
      {label}
    </Link>
  );
}

function SectionHeader({
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

const inputClassName =
  "h-14 w-full rounded-full border border-[#e1e5eb] bg-white px-5 text-[16px] font-medium text-[#101828] outline-none focus:border-[#ff6b6b] focus:ring-2 focus:ring-[#ffe2e2]";

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[22px] bg-[#f6f7f9] px-5 py-4">
      <span className="mb-1 block text-[13px] font-bold text-[#98a2b3]">{label}</span>
      <span className="break-words text-[18px] font-extrabold text-[#101828]">{value}</span>
    </div>
  );
}

function ImageGenerationSettingsFields({
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

function ImageModeOption({
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

function formatActionList(actions: string[]) {
  const visibleActions = actions.filter((action) => action !== "observe");
  if (visibleActions.length === 0) return "없음";
  return visibleActions.map(formatActionLabel).join(", ");
}

function currentStateText(agent: AgentDetailRead) {
  return (
    agent.state?.memory_note?.trim() ||
    agent.state?.summary?.trim() ||
    agent.character.one_liner?.trim() ||
    agent.character.persona_summary.trim() ||
    "아직 저장된 상태가 없습니다."
  );
}

function nextActivityText(agent: AgentDetailRead) {
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

function formatClockTime(value: string, timeZone = "Asia/Seoul") {
  const formatted = formatDate(value, timeZone);
  return formatted === "-" ? "-" : formatted.slice(-5);
}

function mediaGenerationLabel(
  state: MediaGenerationState,
  showWaitMessage: boolean,
) {
  if (state.phase === "applying") return "프로필에 적용 중...";
  if (showWaitMessage) return "이미지 생성 중이에요. 최대 2분 정도 걸릴 수 있어요.";
  if (state.phase === "preparing") return "생성 준비 중...";
  if (state.phase === "checking") return "결과 확인 중...";
  return "이미지 생성 중...";
}

function mediaUsageFor(
  usage: AgentProfileImageUsageRead | null,
  mediaType: MediaKind,
) {
  return usage?.items.find((item) => item.media_type === mediaType) ?? null;
}

function usageLimitMessage(
  status: AgentProfileImageUsageRead["items"][number] | null | undefined,
) {
  if (!status || status.remaining > 0 || !status.next_available_at) return null;
  return `오늘 사용 완료되었습니다. ${formatNextAvailableAt(
    status.next_available_at,
  )} 이후 다시 생성할 수 있습니다.`;
}

function formatNextAvailableAt(value: string) {
  const formatted = formatDate(value);
  return formatted === "-" ? value : formatted;
}

function formatActiveHours(agent: AgentDetailRead) {
  const start = agent.settings.active_hours_start;
  const end = agent.settings.active_hours_end;
  return `${start}-${end}`;
}

function fileToBase64Payload(file: File): Promise<string> {
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

function formatTendencyActionLabel(action: string, fallback: string) {
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

function normalizeHandleInput(value: string) {
  return value.trim().toLowerCase().replace(/^@/, "");
}

function NumberInput({
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

function ToggleInput({
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

function TextInput({
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

function PersonaTextArea({
  name,
  label,
  defaultValue,
  maxLength,
  required = false,
}: {
  name: string;
  label: string;
  defaultValue: string;
  maxLength: number;
  required?: boolean;
}) {
  return (
    <label className="mb-4 block">
      <span className="mb-2 block text-[15px] font-bold text-[#344054]">{label}</span>
      <textarea
        name={name}
        defaultValue={defaultValue}
        rows={4}
        maxLength={maxLength}
        required={required}
        className="block min-h-28 w-full resize-y rounded-[24px] border border-[#e1e5eb] bg-white px-5 py-4 text-[16px] font-medium leading-7 text-[#101828] outline-none focus:border-[#ff6b6b] focus:ring-2 focus:ring-[#ffe2e2]"
      />
    </label>
  );
}

function TextAreaInput({
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
  return (
    <label className="mb-4 block">
      <span className="mb-2 block text-[15px] font-bold text-[#344054]">{label}</span>
      <textarea
        name={name}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={4}
        maxLength={300}
        className="w-full resize-none rounded-[24px] border border-[#e1e5eb] bg-white px-5 py-4 text-[16px] font-medium leading-7 text-[#101828] outline-none focus:border-[#ff6b6b] focus:ring-2 focus:ring-[#ffe2e2]"
      />
    </label>
  );
}
