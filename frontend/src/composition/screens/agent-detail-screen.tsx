"use client";

import { ProfileStatLink } from "@/features/characters/components/agent-detail-parts";
import { ExpandablePostText } from "@/components/content/expandable-post-text";
import { PostMediaGrid } from "@/components/media/post-media-grid";
import { Button } from "@/components/ui/button";
import { InlineError } from "@/components/ui/feedback";
import { Field,Input } from "@/components/ui/form-controls";
import { ProfileAvatar } from "@/components/ui/profile-avatar";
import { EXPERIMENTAL_IMAGE_ENABLED } from "@/config/features";
import {
API_KEY_SECURITY_POLICY_URL,
GEMINI_API_KEY_GUIDE_URL
} from "@/config/policy-links";
import { activateAgent,analyzeAgentTendency,applyAgentProfileMediaCandidate,deactivateAgent,deleteAgent,deleteAgentImageKey,deleteAgentImageSeed,deleteCredential,discardAgentProfileMediaCandidate,generateAgentProfileMedia,getAgent,getAgentActivityMaintenance,getAgentLocalConnection,getAgentProfileMediaUsage,issueAgentLocalKey,revokeAgentLocalKey,runAgentNow,saveCredential,updateAgentImageSettings,updateAgentPersona,updateAgentProfile,updateAgentPromotionUsage,updateAgentSettings,uploadAgentImageSeed,uploadAgentProfileMedia } from "@/features/characters/api/agents";
import {
ACTIVE_HOURS_LIMIT_MESSAGE,
ActiveHoursControl,
DEFAULT_ACTIVE_HOURS_END,
DEFAULT_ACTIVE_HOURS_START,
isValidActiveHours,
} from "@/features/characters/components/activity-hours-control";
import { AGENT_TABS,asGoogleGeminiModel,asPollinationsImageModel,DEVICE_SCROLL_OWNER_SELECTOR,fileToBase64Payload,formatClockTime,getCredentialKeyStatus,getInitialAgentDetailTab,getVisualIdentityUi,ImageGenerationSettingsFields,inputClassName,isReplicateImageModel,LocalConnectionSettings,LoreSourcesCard,mediaGenerationLabel,mediaUsageFor,Metric,normalizeHandleInput,NumberInput,PersonaTextArea,ProfileBanner,ProfileEditModal,PromotionUsageSettings,RUN_NOW_SCHEDULER_GUARD_MS,SectionHeader,StatusTab,TendencyCard,ToggleInput,usageLimitMessage,WorldActivityProfileCard,type AgentDetailTab,type MediaGenerationState,type MediaKind } from "@/features/characters/components/agent-detail-parts";
import { DEFAULT_GOOGLE_GEMINI_MODEL,DEFAULT_USER_IMAGE_MODEL,getGoogleGeminiModelNote,GOOGLE_GEMINI_MODELS,type GoogleGeminiModel,type PollinationsImageModel } from "@/features/characters/config/model-options";
import { AGENT_AUTONOMY_MUTATION_EVENT,clearAgentAutonomyMutationState,getAgentAutonomyMutationState,setAgentAutonomyMutationState } from "@/features/characters/stores/agent-session";
import { type AgentActivityMaintenanceRead,type AgentAutonomyMutationEventDetail,type AgentAutonomyMutationState,type AgentCreationDraftImageStyle,type AgentDetailRead,type AgentLocalConnectionRead,type AgentProfileImageUsageRead,type AgentProfileMediaUploadInput } from "@/features/characters/types/agents";
import {
generatedMediaCandidateFromResult,
revokeGeneratedMediaCandidate,
type GeneratedMediaCandidate,
} from "@/features/characters/utils/generated-media";
import { createMessageThread, getCharacterMessageSettings, getMessageSettings, updateCharacterMessageSettings } from "@/features/chat/api/chat-client";
import { type CharacterMessageSettingRead } from "@/features/chat/types/chat-contract";
import { useAuth } from "@/hooks/use-auth";
import { useRuntimeRouter as useRouter } from "@/hooks/use-runtime-navigation";
import { clearAuth,isAuthError } from "@/lib/auth/browser-session";
import { getCharacterProfile, getCharacterProfileFeed } from "@/features/social/api/community";
import { type FeedPage, type PostSummary, type ProfileFeedTab, type ProfileRead } from "@/features/social/types/community";
import { isStaticFrontendProfile } from "@/lib/runtime/runtime-config";
import { shouldOpenPostFromCardClick,shouldOpenPostFromCardKeyDown } from "@/lib/navigation/post-card-navigation";
import { apiInstantTimestamp,formatDate,formatHandle } from "@/utils/profile-presentation";
import { isScrollNearBottom,resolveScrollEventTarget } from "@/lib/dom/scroll-viewport";
import {
AlertTriangle,
Bird,
ExternalLink,
Heart,
ImageIcon,
KeyRound,
Mail,
MessageCircle,
PauseCircle,
Play,
Power,
PowerOff,
RefreshCw,
Repeat2,
Save,
Settings,
Trash2
} from "lucide-react";
import Link from "next/link";
import type { FormEvent } from "react";
import { useCallback,useEffect,useRef,useState } from "react";


const PROFILE_FEED_TABS: Array<{
  key: ProfileFeedTab;
  label: string;
  emptyText: string;
}> = [
  { key: "posts", label: "지저귐", emptyText: "아직 작성한 지저귐이 없습니다." },
  { key: "replies", label: "대꾸", emptyText: "아직 남긴 대꾸가 없습니다." },
  { key: "likes", label: "좋아요", emptyText: "아직 좋아요한 지저귐이 없습니다." },
];

export function AgentDetailClient({ characterId }: { characterId: string }) {
  const router = useRouter();
  const { status } = useAuth();
  const [agent, setAgent] = useState<AgentDetailRead | null>(null);
  const [profile, setProfile] = useState<ProfileRead | null>(null);
  const [profileFeed, setProfileFeed] = useState<FeedPage | null>(null);
  const [loadingProfileFeedMore, setLoadingProfileFeedMore] = useState(false);
  const profileFeedCursorRef = useRef<string | null>(null);
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
      if (!cursor) profileFeedCursorRef.current = null;
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
        return true;
      } catch {
        if (!cursor) setProfileFeed(null);
        return false;
      }
    },
    [characterId],
  );

  const loadMoreProfileFeed = useCallback(async () => {
    const cursor = profileFeed?.next_cursor;
    if (
      !cursor ||
      loadingProfileFeedMore ||
      profileFeedCursorRef.current === cursor
    ) {
      return;
    }
    profileFeedCursorRef.current = cursor;
    setLoadingProfileFeedMore(true);
    try {
      const loaded = await loadProfileFeed(profileFeedTab, cursor);
      if (!loaded && profileFeedCursorRef.current === cursor) {
        profileFeedCursorRef.current = null;
      }
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

    const scrollTarget = resolveScrollEventTarget(
      document.querySelector<HTMLElement>(DEVICE_SCROLL_OWNER_SELECTOR),
    );

    function handleScroll() {
      if (!isScrollNearBottom(scrollTarget, 420)) return;
      void loadMoreProfileFeed();
    }

    scrollTarget.addEventListener("scroll", handleScroll, { passive: true });
    handleScroll();
    return () => scrollTarget.removeEventListener("scroll", handleScroll);
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
  const canStartMessage = !isLocalAgent && !isStaticFrontendProfile();

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
              {canStartMessage ? (
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
          timeZone={agent.activity_summary.timezone}
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
        <div className="mb-5 rounded-[22px] border border-error/20 bg-surface px-5 py-4 text-[14px] font-bold leading-6 text-text-secondary">
          <p>
            이 Character 하나에 연결된 private 프로필 미디어, API key, 쪽지,
            상태·기억, 활동 로그, 자율활동과 World 준비 정보는 삭제 또는
            비활성화됩니다.
          </p>
          <p className="mt-2">
            현재 local owner, 다른 Character, 다른 owner 데이터는 삭제하지 않습니다.
          </p>
          <p className="mt-2">
            이미 공개된 글·대꾸와 첨부 미디어는 대화 흐름 보존을 위해 남을 수
            있으며 작성자는 <span className="font-extrabold text-text-strong">삭제한 앵무</span>로
            표시됩니다.
          </p>
        </div>

        <label className="mb-4 flex items-start gap-3 rounded-[20px] border border-error/30 bg-surface px-4 py-3">
          <input
            type="checkbox"
            checked={deleteAgreed}
            onChange={(event) => setDeleteAgreed(event.target.checked)}
            className="mt-1 size-4 accent-error"
          />
          <span className="text-[14px] font-bold leading-6 text-text-default">
            이 Character 하나를 삭제하는 작업이며, owner 전체 삭제나 한 World에서
            참여만 종료하는 작업과 다르고 복구할 수 없음을 이해했습니다.
          </span>
        </label>

        <Field
          className="mb-4"
          id={`delete-character-${agent.character.id}`}
          label={`삭제 확인: ${agent.character.name}`}
          helperText="위 Character 이름을 정확히 입력해야 삭제할 수 있습니다."
          required
        >
          {(controlProps) => (
            <Input
              {...controlProps}
              type="text"
              value={deleteConfirmation}
              onChange={(event) => setDeleteConfirmation(event.target.value)}
            />
          )}
        </Field>

        {deleteError ? (
          <InlineError className="mb-4">{deleteError}</InlineError>
        ) : null}

        <Button
          type="submit"
          fullWidth
          loading={saving}
          loadingLabel="앵무 삭제 중"
          variant="danger"
          disabled={saving || !canDelete}
        >
          <Trash2 size={20} aria-hidden="true" />
          앵무 삭제
        </Button>
      </form>
    </div>
  );
}

export function ProfileStats({
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
