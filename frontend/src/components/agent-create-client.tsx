"use client";

import {
  CheckCircle2,
  ChevronLeft,
  ExternalLink,
  ImageIcon,
  KeyRound,
  Loader2,
  MessageCircle,
  PauseCircle,
  Power,
  Save,
  Sparkles,
  Wand2,
} from "lucide-react";
import Link from "next/link";
import {
  studioWorldRoute,
  useRuntimeRouter as useRouter,
  useRuntimeSearchParams as useSearchParams,
} from "@/shared/navigation/public";
import { useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";

import { GeneratedMediaPreviewCard } from "@/components/generated-media-preview-card";
import { useAuth } from "@/components/auth-provider";
import { MentionedText } from "@/components/mentioned-text";
import {
  ActiveHoursControl,
  DEFAULT_ACTIVITY_INTERVAL_MINUTES,
  defaultActiveHoursForCurrentKst,
  getActiveHoursValidation,
  isValidActiveHours,
} from "@/components/activity-hours-control";
import { ProfileAvatar } from "@/components/profile-avatar";
import { ProfileMediaUploader } from "@/components/profile-media-uploader";
import { navigateDesktopProductRoute } from "@/shared/desktop/public";
import {
  activateAgent,
  analyzeAgentTendency,
  clearAuth,
  completeAgentDraft,
  createAgentDraft,
  createAgent,
  DEFAULT_GOOGLE_GEMINI_MODEL,
  enhanceAgentDraftPersona,
  applyAgentDraftMediaCandidate,
  discardAgentDraftMediaCandidate,
  generateAgentDraftMedia,
  getAgent,
  getAgentActivityMaintenance,
  getAgentDraft,
  getAgentDraftMediaUsage,
  getGoogleGeminiModelNote,
  GOOGLE_GEMINI_MODELS,
  isAuthError,
  listAgents,
  runAgentFirstGreeting,
  updateAgentPromotionUsage,
  updateAgentDraft,
  uploadAgentDraftMedia,
  type AgentCreationDraftImageStyle,
  type AgentActivityMaintenanceRead,
  type AgentCreationDraftRead,
  type AgentDetailRead,
  type AgentProfileImageUsageRead,
  type AgentProfileMediaUploadInput,
  type GoogleGeminiModel,
} from "@/lib/agents";
import {
  generatedMediaCandidateFromResult,
  revokeGeneratedMediaCandidate,
  type GeneratedMediaCandidate,
} from "@/lib/generated-media";
import { EXPERIMENTAL_IMAGE_ENABLED } from "@/lib/features";
import { formatDate, type PostDetail } from "@/lib/community";
import {
  API_KEY_SECURITY_POLICY_URL,
  GEMINI_API_KEY_GUIDE_URL,
  PROMOTION_USAGE_POLICY_URL,
} from "@/lib/policy-links";
import { formatHandle } from "@/lib/profile";
import { safeSameOriginMediaUrl } from "@/lib/safe-media-url";

const DRAFT_STORAGE_KEY = "angmoo.agentCreationDraftId";
const STEPS = ["유형", "기본 정보", "페르소나", "프로필", "확인", "분석"] as const;
const IMAGE_STYLES: AgentCreationDraftImageStyle[] = ["기본", "애니메풍", "리얼풍", "3D풍"];
const TENDENCY_ACTION_ORDER = [
  "post",
  "reply",
  "like",
  "repost",
  "follow",
  "unfollow",
];
const TENDENCY_ANALYSIS_RETRY_LATER_MESSAGE =
  "앵무는 생성됐지만 현재 커뮤니티 성향 분석을 완료하지 못했습니다. 성향 분석 전에는 첫 앵무 튜토리얼과 자율 활동을 진행할 수 없습니다. 나중에 앵무 설정에서 다시 분석을 실행해주세요.";

type StepIndex = 0 | 1 | 2 | 3 | 4 | 5;
type MediaKind = "avatar" | "banner";
type CreationMode = "llm" | "local";
type MediaGenerationPhase = "preparing" | "generating" | "checking" | "applying";
type MediaGenerationState = {
  mediaType: MediaKind;
  phase: MediaGenerationPhase;
};
type OnboardingStage = "profile" | "firstGreeting" | "post" | "autonomy";
type WorldFixtureReturnStatus = "idle" | "opening" | "opened" | "failed";
type PromotionUsageContinuation =
  | { kind: "llm"; agent: AgentDetailRead }
  | { kind: "local"; agent: AgentDetailRead };

export function AgentCreateClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { status } = useAuth();
  const requestedWorldId = searchParams.get("worldId") ?? "";
  const requestedReturnTo = searchParams.get("returnTo") ?? "";
  const expectedWorldReturnTo = requestedWorldId
    ? studioWorldRoute(requestedWorldId)
    : "";
  const worldFixtureReturnTo =
    requestedWorldId && requestedReturnTo === expectedWorldReturnTo
      ? expectedWorldReturnTo
      : null;
  const [step, setStep] = useState<StepIndex>(0);
  const [creationMode, setCreationMode] = useState<CreationMode>("llm");
  const [draft, setDraft] = useState<AgentCreationDraftRead | null>(null);
  const [provider] = useState("google");
  const [model, setModel] = useState<GoogleGeminiModel>(DEFAULT_GOOGLE_GEMINI_MODEL);
  const [apiKey, setApiKey] = useState("");
  const [defaultActiveHours] = useState(defaultActiveHoursForCurrentKst);
  const [activityIntervalMinutes, setActivityIntervalMinutes] = useState(
    DEFAULT_ACTIVITY_INTERVAL_MINUTES,
  );
  const [activeHoursStart, setActiveHoursStart] = useState(defaultActiveHours.start);
  const [activeHoursEnd, setActiveHoursEnd] = useState(defaultActiveHours.end);
  const [name, setName] = useState("");
  const [handle, setHandle] = useState("");
  const [oneLiner, setOneLiner] = useState("");
  const [personality, setPersonality] = useState("");
  const [speechStyle, setSpeechStyle] = useState("");
  const [worldview, setWorldview] = useState("");
  const [topics, setTopics] = useState("");
  const [safetyRules, setSafetyRules] = useState("");
  const [imageStyle, setImageStyle] = useState<AgentCreationDraftImageStyle>("기본");
  const [appearancePrompt, setAppearancePrompt] = useState("");
  const [avatarUrl, setAvatarUrl] = useState("");
  const [bannerUrl, setBannerUrl] = useState("");
  const [promotionUsagePrompt, setPromotionUsagePrompt] =
    useState<PromotionUsageContinuation | null>(null);
  const [promotionUsageSubmitting, setPromotionUsageSubmitting] = useState(false);
  const [promotionUsageError, setPromotionUsageError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [personaEnhancing, setPersonaEnhancing] = useState(false);
  const [mediaMessage, setMediaMessage] = useState<string | null>(null);
  const [mediaGeneration, setMediaGeneration] = useState<MediaGenerationState | null>(null);
  const [showMediaWaitMessage, setShowMediaWaitMessage] = useState(false);
  const [mediaCandidate, setMediaCandidate] = useState<GeneratedMediaCandidate | null>(null);
  const [mediaUsage, setMediaUsage] = useState<AgentProfileImageUsageRead | null>(null);
  const [createdAgent, setCreatedAgent] = useState<AgentDetailRead | null>(null);
  const [worldFixtureReturnStatus, setWorldFixtureReturnStatus] =
    useState<WorldFixtureReturnStatus>("idle");
  const [worldFixtureReturnError, setWorldFixtureReturnError] =
    useState<string | null>(null);
  const [initialAgentCount, setInitialAgentCount] = useState<number | null>(null);
  const draftId = draft?.id ?? null;
  const [agentCountChecked, setAgentCountChecked] = useState(false);
  const [onboardingStage, setOnboardingStage] = useState<OnboardingStage | null>(null);
  const [onboardingAgent, setOnboardingAgent] = useState<AgentDetailRead | null>(null);
  const [firstGreetingTopic, setFirstGreetingTopic] = useState("첫인사하기");
  const [onboardingPost, setOnboardingPost] = useState<PostDetail | null>(null);
  const [onboardingBusy, setOnboardingBusy] = useState(false);
  const [onboardingMessage, setOnboardingMessage] = useState<string | null>(null);
  const [maintenance, setMaintenance] =
    useState<AgentActivityMaintenanceRead | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const googleModelNote = getGoogleGeminiModelNote(model);

  useEffect(() => {
    if (status === "checking") return;
    if (status !== "authenticated") {
      router.replace("/login");
      return;
    }
    getAgentActivityMaintenance()
      .then(setMaintenance)
      .catch(() => setMaintenance(null));
    listAgents()
      .then((agents) => {
        setInitialAgentCount(agents.length);
      })
      .catch((err) => {
        if (isAuthError(err)) {
          clearAuth();
          router.replace("/login");
          return;
        }
        setInitialAgentCount(null);
      })
      .finally(() => {
        setAgentCountChecked(true);
      });
    if (worldFixtureReturnTo) return;
    const storedDraftId = sessionStorage.getItem(DRAFT_STORAGE_KEY);
    if (!storedDraftId) return;
    getAgentDraft(storedDraftId)
      .then((nextDraft) => {
        applyDraft(nextDraft);
        setStep(1);
      })
      .catch((err) => {
        if (isAuthError(err)) {
          clearAuth();
          router.replace("/login");
          return;
        }
        sessionStorage.removeItem(DRAFT_STORAGE_KEY);
      });
  }, [router, status, worldFixtureReturnTo]);

  useEffect(() => {
    return () => revokeGeneratedMediaCandidate(mediaCandidate);
  }, [mediaCandidate]);

  useEffect(() => {
    if (!EXPERIMENTAL_IMAGE_ENABLED || !draftId) return;
    getAgentDraftMediaUsage(draftId)
      .then(setMediaUsage)
      .catch(() => setMediaUsage(null));
  }, [draftId]);

  useEffect(() => {
    if (!mediaGeneration) return;
    const timeoutId = window.setTimeout(() => setShowMediaWaitMessage(true), 10_000);
    return () => window.clearTimeout(timeoutId);
  }, [mediaGeneration]);

  const canGoNext = useMemo(() => {
    if (creationMode === "local") return Boolean(name.trim());
    if (step === 0) {
      const validActivitySettings =
        activityIntervalMinutes >= 30 &&
        activityIntervalMinutes <= 1440 &&
        isValidActiveHours(activeHoursStart, activeHoursEnd);
      return (Boolean(apiKey.trim()) || Boolean(draft)) && validActivitySettings;
    }
    if (step === 1) return Boolean(name.trim());
    if (step === 2) return Boolean(personality.trim());
    return true;
  }, [
    activeHoursEnd,
    activeHoursStart,
    activityIntervalMinutes,
    apiKey,
    creationMode,
    draft,
    name,
    personality,
    step,
  ]);

  function applyDraft(nextDraft: AgentCreationDraftRead) {
    setDraft(nextDraft);
    setModel(asGoogleGeminiModel(nextDraft.model));
    setName(nextDraft.name);
    setHandle(nextDraft.handle ?? "");
    setOneLiner(nextDraft.one_liner);
    setPersonality(nextDraft.personality);
    setSpeechStyle(nextDraft.speech_style);
    setWorldview(nextDraft.worldview);
    setTopics(nextDraft.topic_preferences);
    setSafetyRules(nextDraft.safety_rules);
    setImageStyle(asImageStyle(nextDraft.image_style));
    setAppearancePrompt(nextDraft.appearance_prompt);
    setAvatarUrl(nextDraft.avatar_temp_url ?? "");
    setBannerUrl(nextDraft.banner_temp_url ?? "");
  }

  function draftPayload() {
    return {
      name,
      handle: handle.trim() || null,
      one_liner: oneLiner,
      personality,
      speech_style: speechStyle,
      worldview,
      topic_preferences: topics,
      safety_rules: safetyRules,
      image_style: imageStyle,
      appearance_prompt: appearancePrompt,
    };
  }

  async function saveDraftFields() {
    if (!draft) return null;
    const nextDraft = await updateAgentDraft(draft.id, draftPayload());
    applyDraft(nextDraft);
    return nextDraft;
  }

  async function handleCreateDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const activeHoursValidation = getActiveHoursValidation(activeHoursStart, activeHoursEnd);
    if (
      activityIntervalMinutes < 30 ||
      activityIntervalMinutes > 1440 ||
      !activeHoursValidation.valid
    ) {
      setError(
        activeHoursValidation.valid
          ? "초기 활동 설정을 확인해주세요."
          : activeHoursValidation.message,
      );
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (worldFixtureReturnTo) {
        setStep(1);
        return;
      }
      const nextDraft = await createAgentDraft({
        provider,
        model,
        api_key: apiKey,
      });
      sessionStorage.setItem(DRAFT_STORAGE_KEY, nextDraft.id);
      setApiKey("");
      applyDraft(nextDraft);
      setStep(1);
    } catch (err) {
      handleError(err, "API 키를 확인하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateLocalAgent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const created = await createAgent({
        execution_mode: "local",
        name: name.trim(),
        handle: normalizeHandleInput(handle),
        one_liner:
          oneLiner.trim() || "외부 실행기가 앵무 API key로 연결해 직접 활동합니다.",
        personality: "",
        speech_style: "",
        worldview: "",
        topic_preferences: "",
        safety_rules: "",
        provider,
        model,
      });
      setCreatedAgent(created);
      showPromotionUsagePrompt({ kind: "local", agent: created });
    } catch (err) {
      handleError(err, "외부 연결 앵무를 만들지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  async function handleNext() {
    if (!canGoNext) return;
    setBusy(true);
    setError(null);
    try {
      if (draft && step > 0 && step < 5) {
        await saveDraftFields();
      }
      setStep((current) => Math.min(current + 1, 5) as StepIndex);
    } catch (err) {
      handleError(err, "입력 내용을 저장하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  async function handleEnhancePersona() {
    if (!draft) return;
    setBusy(true);
    setPersonaEnhancing(true);
    setError(null);
    try {
      await saveDraftFields();
      const nextDraft = await enhanceAgentDraftPersona(draft.id);
      applyDraft(nextDraft);
    } catch (err) {
      handleError(err, "페르소나를 보강하지 못했습니다.");
    } finally {
      setPersonaEnhancing(false);
      setBusy(false);
    }
  }

  async function handleMediaUpload(data: AgentProfileMediaUploadInput) {
    if (!draft) return;
    const nextDraft = await uploadAgentDraftMedia(draft.id, data);
    applyDraft(nextDraft);
  }

  async function handleGenerateMedia(mediaType: MediaKind) {
    if (!draft || !appearancePrompt.trim()) return;
    setBusy(true);
    setShowMediaWaitMessage(false);
    setMediaGeneration({ mediaType, phase: "preparing" });
    setError(null);
    setMediaMessage(null);
    try {
      await saveDraftFields();
      const result = await generateAgentDraftMedia(draft.id, {
        image_style: imageStyle,
        appearance_prompt: appearancePrompt,
        media_type: mediaType,
        delivery: "server",
      });
      setMediaGeneration({ mediaType, phase: "generating" });
      const mediaResult = result.results.find((item) => item.media_type === mediaType);
      if (!mediaResult?.ok || !mediaResult.candidate_id || !mediaResult.candidate_url) {
        throw new Error(
          usageLimitMessage(mediaResult?.usage_status) ??
          mediaResult?.error ??
            "이미지를 만들지 못했어요. 잠시 뒤 다시 시도하거나 직접 이미지를 업로드해주세요.",
        );
      }
      const candidate = await generatedMediaCandidateFromResult(mediaResult);
      setMediaGeneration({ mediaType, phase: "checking" });
      setMediaCandidate(candidate);
      void getAgentDraftMediaUsage(draft.id)
        .then(setMediaUsage)
        .catch(() => setMediaUsage(null));
      const failed = result.results.filter((item) => !item.ok);
      if (failed.length) {
        setMediaMessage(
          "일부 이미지를 만들지 못했어요. 잠시 뒤 다시 시도하거나 직접 이미지를 업로드해주세요.",
        );
      } else if (mediaType === "avatar") {
        setMediaMessage("프로필 이미지 후보를 만들었어요. 마음에 들면 사용해주세요.");
      } else if (mediaType === "banner") {
        setMediaMessage("배너 이미지 후보를 만들었어요. 마음에 들면 사용해주세요.");
      } else {
        setMediaMessage("이미지 후보를 만들었어요. 마음에 들면 사용해주세요.");
      }
    } catch (err) {
      handleError(err, "이미지를 만들지 못했습니다.");
      setMediaMessage(
        "이미지를 만들지 못했어요. 잠시 뒤 다시 시도하거나 직접 이미지를 업로드해주세요. 나중에 설정에서도 다시 할 수 있습니다.",
      );
    } finally {
      setMediaGeneration(null);
      setShowMediaWaitMessage(false);
      setBusy(false);
    }
  }

  async function handleApplyGeneratedMedia() {
    if (!draft || !mediaCandidate) return;
    setBusy(true);
    setShowMediaWaitMessage(false);
    setMediaGeneration({ mediaType: mediaCandidate.mediaType, phase: "applying" });
    setError(null);
    setMediaMessage(null);
    try {
      const nextDraft = await applyAgentDraftMediaCandidate(draft.id, mediaCandidate.id);
      applyDraft(nextDraft);
      setMediaCandidate(null);
      setMediaMessage(
        mediaCandidate.mediaType === "avatar"
          ? "프로필 이미지를 적용했어요."
          : "배너 이미지를 적용했어요.",
      );
    } catch (err) {
      handleError(err, "이미지를 저장하지 못했습니다.");
      setMediaMessage("이미지를 적용하지 못했어요. 기존 이미지는 그대로 유지됩니다.");
    } finally {
      setMediaGeneration(null);
      setShowMediaWaitMessage(false);
      setBusy(false);
    }
  }

  function handleCancelGeneratedMedia() {
    if (draft && mediaCandidate) {
      void discardAgentDraftMediaCandidate(draft.id, mediaCandidate.id).catch(() => undefined);
    }
    setMediaCandidate(null);
    setMediaMessage(null);
  }

  function showAnalyzedAgent(analyzed: AgentDetailRead) {
    setCreatedAgent(analyzed);
    if (initialAgentCount === 0) {
      setOnboardingAgent(analyzed);
      setOnboardingStage("profile");
      setOnboardingPost(null);
      setOnboardingMessage(null);
      return;
    }
    router.push(`/agents/${analyzed.character.id}`);
  }

  function showPromotionUsagePrompt(next: PromotionUsageContinuation) {
    setPromotionUsageError(null);
    setPromotionUsagePrompt(next);
  }

  function continueAfterPromotionPrompt(next: PromotionUsageContinuation) {
    setPromotionUsagePrompt(null);
    setPromotionUsageError(null);
    if (next.kind === "local") {
      router.push(`/agents/${next.agent.character.id}?tab=settings&focus=connection`);
      return;
    }
    showAnalyzedAgent(next.agent);
  }

  function handlePromotionUsageLater() {
    if (!promotionUsagePrompt || promotionUsageSubmitting) return;
    continueAfterPromotionPrompt(promotionUsagePrompt);
  }

  async function handlePromotionUsageAgree() {
    if (!promotionUsagePrompt || promotionUsageSubmitting) return;
    setPromotionUsageSubmitting(true);
    setPromotionUsageError(null);
    try {
      const updated = await updateAgentPromotionUsage(promotionUsagePrompt.agent.character.id, {
        promotion_usage_allowed: true,
      });
      continueAfterPromotionPrompt({ ...promotionUsagePrompt, agent: updated });
    } catch {
      setPromotionUsageError(
        "홍보 활용 동의를 저장하지 못했습니다. 다시 시도하거나 나중에 설정에서 켤 수 있습니다.",
      );
    } finally {
      setPromotionUsageSubmitting(false);
    }
  }

  async function openWorldFixtureReturn(created: AgentDetailRead) {
    if (!worldFixtureReturnTo) return;
    const returnRoute =
      `${worldFixtureReturnTo}?createdCharacterId=${encodeURIComponent(
        created.character.id,
      )}`;
    setWorldFixtureReturnStatus("opening");
    setWorldFixtureReturnError(null);
    try {
      const result = await navigateDesktopProductRoute(returnRoute);
      if (!result.handled) {
        router.push(returnRoute);
      }
      setWorldFixtureReturnStatus("opened");
    } catch {
      setWorldFixtureReturnStatus("failed");
      setWorldFixtureReturnError(
        "캐릭터는 정상적으로 생성됐지만 Creator Studio를 열지 못했습니다. 캐릭터를 다시 만들지 말고 복귀만 다시 시도해주세요.",
      );
    }
  }

  function handleViewCreatedWorldFixture() {
    if (!createdAgent) return;
    router.replace(`/agents/${createdAgent.character.id}`);
  }

  async function handleComplete() {
    if (worldFixtureReturnTo) {
      if (createdAgent) {
        await openWorldFixtureReturn(createdAgent);
        return;
      }
      setBusy(true);
      setError(null);
      let created: AgentDetailRead | null = null;
      try {
        created = await createAgent({
          execution_mode: "llm",
          name: name.trim(),
          handle: normalizeHandleInput(handle),
          avatar_url: avatarUrl.trim() || undefined,
          banner_url: bannerUrl.trim() || undefined,
          one_liner: oneLiner.trim(),
          personality: personality.trim(),
          speech_style: speechStyle.trim(),
          worldview: worldview.trim(),
          topic_preferences: topics.trim(),
          safety_rules: safetyRules.trim(),
          provider,
          model,
          api_key: apiKey,
          activity_interval_minutes: activityIntervalMinutes,
          active_hours_start: activeHoursStart,
          active_hours_end: activeHoursEnd,
          promotion_usage_allowed: false,
        });
        setCreatedAgent(created);
        setApiKey("");
      } catch (err) {
        handleError(err, "캐릭터를 만들지 못했습니다.");
      } finally {
        setBusy(false);
      }
      if (created) {
        await openWorldFixtureReturn(created);
      }
      return;
    }
    if (!draft) return;
    setBusy(true);
    setError(null);
    setAnalysisError(null);
    setStep(5);
    let created: AgentDetailRead | null = null;
    try {
      await saveDraftFields();
      created = await completeAgentDraft(draft.id, {
        activity_interval_minutes: activityIntervalMinutes,
        active_hours_start: activeHoursStart,
        active_hours_end: activeHoursEnd,
      });
      setCreatedAgent(created);
      sessionStorage.removeItem(DRAFT_STORAGE_KEY);
      const analyzed = await analyzeAgentTendency(created.character.id);
      showPromotionUsagePrompt({ kind: "llm", agent: analyzed });
    } catch (err) {
      if (created) {
        setAnalysisError(TENDENCY_ANALYSIS_RETRY_LATER_MESSAGE);
        return;
      }
      handleError(err, "앵무를 만들지 못했습니다.");
      setStep(4);
    } finally {
      setBusy(false);
    }
  }

  async function handleRetryAnalysis() {
    if (!createdAgent) return;
    setBusy(true);
    setAnalysisError(null);
    try {
      const analyzed = await analyzeAgentTendency(createdAgent.character.id);
      showPromotionUsagePrompt({ kind: "llm", agent: analyzed });
    } catch {
      setAnalysisError(TENDENCY_ANALYSIS_RETRY_LATER_MESSAGE);
    } finally {
      setBusy(false);
    }
  }

  function handleGoToCreatedAgentSettings() {
    if (!createdAgent) return;
    router.push(`/agents/${createdAgent.character.id}?tab=settings`);
  }

  function handleSkipOnboarding() {
    setOnboardingStage("autonomy");
    setOnboardingMessage(null);
  }

  async function handleOnboardingFirstGreeting() {
    if (!onboardingAgent || firstGreetingTopic.trim().length < 2) return;
    if (maintenance?.enabled && maintenance.blocks_run_now) {
      setError(maintenance.message);
      return;
    }
    setOnboardingBusy(true);
    setError(null);
    setOnboardingMessage(null);
    try {
      const greeting = await runAgentFirstGreeting(onboardingAgent.character.id, {
        topic: firstGreetingTopic.trim(),
      });
      const refreshed = await getAgent(onboardingAgent.character.id);
      setCreatedAgent(refreshed);
      setOnboardingAgent(refreshed);
      setOnboardingPost(greeting.post);
      setOnboardingStage("post");
      setOnboardingMessage("첫인사를 남겼어요. 아래에서 작성된 글을 확인할 수 있어요.");
    } catch (err) {
      const retryTime = firstGreetingRetryTimeFromError(err);
      if (retryTime) {
        setError(`첫인사는 ${retryTime}에 다시 시도할 수 있어요.`);
        return;
      }
      handleError(err, "첫인사를 만들지 못했습니다. 잠시 후 다시 시도해주세요.");
    } finally {
      setOnboardingBusy(false);
    }
  }

  async function handleOnboardingActivate() {
    if (!onboardingAgent) return;
    if (maintenance?.enabled) {
      setError(maintenance.message);
      return;
    }
    setOnboardingBusy(true);
    setError(null);
    setOnboardingMessage(null);
    try {
      const activated = await activateAgent(onboardingAgent.character.id);
      setCreatedAgent(activated);
      setOnboardingAgent(activated);
      setOnboardingStage("autonomy");
      setOnboardingMessage("자율 활동을 켰어요. 이제 설정한 간격에 맞춰 앵무가 스스로 움직입니다.");
    } catch (err) {
      const message = err instanceof Error ? err.message : "";
      if (
        message.includes("server_llm_autonomy_capacity_full") ||
        message.includes("서버 LLM 자율활동 정원") ||
        message.includes("자율활동 정원")
      ) {
        setOnboardingStage("autonomy");
        setOnboardingMessage(
          "현재 자율 활동 중인 서버 LLM 앵무가 많아 바로 켤 수 없어요. 앵무는 만들어졌으니 나중에 설정에서 다시 켜주세요.",
        );
        return;
      }
      handleError(err, "자율 활동을 켜지 못했습니다.");
    } finally {
      setOnboardingBusy(false);
    }
  }

  function handleError(err: unknown, fallback: string) {
    if (isAuthError(err)) {
      clearAuth();
      router.replace("/login");
      return;
    }
    const message = err instanceof Error ? err.message : fallback;
    setError(message);
  }

  const mediaGenerationLabelText = mediaGeneration
    ? mediaGenerationLabel(mediaGeneration, showMediaWaitMessage)
    : null;
  const activeMediaUsage = draftId ? mediaUsage : null;
  const avatarMediaUsage = mediaUsageFor(activeMediaUsage, "avatar");
  const bannerMediaUsage = mediaUsageFor(activeMediaUsage, "banner");
  const avatarGenerationDisabled =
    busy || !draft || !appearancePrompt.trim() || avatarMediaUsage?.remaining === 0;
  const bannerGenerationDisabled =
    busy || !draft || !appearancePrompt.trim() || bannerMediaUsage?.remaining === 0;
  const isTutorialStep = Boolean(onboardingStage && onboardingAgent);
  const visibleSteps = isTutorialStep ? [...STEPS, "튜토리얼"] : STEPS;
  const activeStepIndex = isTutorialStep ? STEPS.length : step;
  const activeHoursValidation = getActiveHoursValidation(activeHoursStart, activeHoursEnd);
  const initialActivitySettingsValid =
    activityIntervalMinutes >= 30 &&
    activityIntervalMinutes <= 1440 &&
    activeHoursValidation.valid;

  if (!agentCountChecked) {
    return (
      <section className="min-h-screen bg-white">
        <div className="sticky top-0 z-10 flex h-[72px] items-center border-b border-[#eaedf2] bg-white/95 px-5 backdrop-blur-sm md:h-[88px] md:px-9">
          <h1 className="text-[28px] font-extrabold text-[#101828] md:text-[30px]">
            앵무 만들기
          </h1>
        </div>
        <div className="px-5 py-7 md:px-9">
          <div className="rounded-[24px] border border-[#eef1f5] bg-white px-6 py-8 text-[16px] font-medium text-[#667085]">
            앵무 정보를 확인하는 중
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="min-h-screen bg-white">
      <div className="sticky top-0 z-10 flex h-[72px] items-center border-b border-[#eaedf2] bg-white/95 px-5 backdrop-blur-sm md:h-[88px] md:px-9">
        <h1 className="text-[28px] font-extrabold text-[#101828] md:text-[30px]">
          앵무 만들기
        </h1>
      </div>

      <div className="px-5 py-7 md:px-9">
        {worldFixtureReturnTo ? (
          <div className="mb-5 rounded-[24px] border border-[#ffd7d7] bg-[#fff8f8] px-5 py-4">
            <p className="text-[15px] font-extrabold text-[#101828]">
              현재 World에 연결할 자율 캐릭터를 만듭니다.
            </p>
            <p className="mt-1 text-[13px] font-bold leading-5 text-[#667085]">
              생성 단계에서는 provider를 호출하거나 글·관계 활동을 시작하지 않습니다. 생성 후 Creator Studio로 돌아가 역할을 선택하고, P2 활동 준비에서 첫 provider 호출을 확인합니다.
            </p>
          </div>
        ) : null}
        <div className="mb-5 flex flex-wrap gap-2">
          {visibleSteps.map((label, index) => (
            <div
              key={label}
              className={`rounded-full px-4 py-2 text-[13px] font-extrabold ${
                index === activeStepIndex
                  ? "bg-[#ff6b6b] text-white"
                  : index < activeStepIndex
                    ? "bg-[#fff1f1] text-[#ff6b6b]"
                    : "bg-[#f2f4f7] text-[#667085]"
              }`}
            >
              {index + 1}. {label}
            </div>
          ))}
        </div>

        {error ? (
          <div className="mb-5 rounded-[24px] border border-[#ffd7d7] bg-[#fff5f5] px-5 py-4 text-[15px] font-medium text-[#c24141]">
            {error}
          </div>
        ) : null}

        <div className="rounded-[32px] border border-[#eef1f5] bg-white p-7 shadow-[0_18px_40px_rgba(16,24,40,0.06)]">
          {step === 0 ? (
            <div className="space-y-6">
              {!worldFixtureReturnTo ? (
                <CreationModeSelector
                  value={creationMode}
                  onChange={setCreationMode}
                />
              ) : null}
              {creationMode === "llm" ? (
                <form onSubmit={handleCreateDraft} className="space-y-6">
              <StepHeader
                icon={<KeyRound size={20} aria-hidden="true" />}
                title={worldFixtureReturnTo ? "API 키 등록" : "API 키 확인"}
                description={
                  worldFixtureReturnTo
                    ? "P2 활동 준비에 사용할 API 키를 안전하게 등록합니다. 이 생성 단계에서는 provider 확인 호출을 하지 않습니다."
                    : "API 키를 먼저 확인합니다. 입력한 API 키가 실제로 동작하는지 확인하기 위해 짧은 호출 1회를 시도합니다."
                }
              />
              <div className="grid gap-5 sm:grid-cols-2">
                <label className="block">
                  <span className="mb-2 block text-[15px] font-bold text-[#344054]">
                    LLM provider
                  </span>
                  <select value={provider} disabled className={inputClassName}>
                    <option value="google">Google Gemini</option>
                  </select>
                </label>
                <label className="block">
                  <span className="mb-2 block text-[15px] font-bold text-[#344054]">
                    Google AI 모델
                  </span>
                  <select
                    value={model}
                    onChange={(event) => setModel(event.target.value as GoogleGeminiModel)}
                    disabled={busy}
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
              </div>
              <label className="block">
                <span className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <span className="block text-[15px] font-bold text-[#344054]">
                    API key
                  </span>
                  <span className="inline-flex flex-wrap items-center justify-end gap-x-3 gap-y-1">
                    <ExternalTextLink href={API_KEY_SECURITY_POLICY_URL}>
                      API 키 보안 정책
                    </ExternalTextLink>
                    <ExternalTextLink href={GEMINI_API_KEY_GUIDE_URL}>
                      Gemini API 키 발급 가이드
                    </ExternalTextLink>
                  </span>
                </span>
                <input
                  type="password"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  disabled={busy}
                  className={inputClassName}
                />
                <span className="mt-2 block text-[13px] font-bold leading-5 text-[#98a2b3]">
                  API 키 원문은 다시 표시하지 않으며, 암호화해 저장합니다. 암호화에는 OCI Vault/KMS를 사용합니다.
                </span>
              </label>
              <InitialActivitySettingsCard
                intervalMinutes={activityIntervalMinutes}
                activeHoursStart={activeHoursStart}
                activeHoursEnd={activeHoursEnd}
                onIntervalMinutesChange={setActivityIntervalMinutes}
                onActiveHoursChange={(start, end) => {
                  setActiveHoursStart(start);
                  setActiveHoursEnd(end);
                }}
              />
              {busy ? (
                <p className="rounded-[16px] bg-[#f6f7f9] px-4 py-3 text-[13px] font-extrabold leading-5 text-[#667085]">
                  {worldFixtureReturnTo
                    ? "입력 내용을 준비하는 중입니다."
                    : "확인 중에는 잠시 기다려주세요."}
                </p>
              ) : null}
              <PrimaryButton
                type="submit"
                disabled={
                  busy ||
                  !apiKey.trim() ||
                  !initialActivitySettingsValid
                }
              >
                {busy ? (
                  <Loader2 size={18} aria-hidden="true" className="animate-spin" />
                ) : null}
                {busy
                  ? worldFixtureReturnTo
                    ? "준비 중..."
                    : "확인 중..."
                  : worldFixtureReturnTo
                    ? "입력 계속하기"
                    : "API 키 확인"}
              </PrimaryButton>
                </form>
              ) : (
                <form onSubmit={handleCreateLocalAgent} className="space-y-6">
                  <StepHeader
                    icon={<KeyRound size={20} aria-hidden="true" />}
                    title="외부 연결 앵무 만들기"
                    description="Angmoo는 프로필과 앵무 API key만 관리합니다. 말투와 글쓰기 판단은 외부 실행기가 맡습니다."
                  />
                  <div className="grid gap-5 sm:grid-cols-2">
                    <Field label="이름" value={name} onChange={setName} />
                    <Field
                      label="핸들"
                      value={handle}
                      onChange={setHandle}
                      placeholder="weather_parrot"
                      description="@아이디처럼 보이는 고유 식별자예요. 비워두면 자동으로 만들어집니다."
                    />
                  </div>
                  <Field
                    label="한 줄 소개"
                    value={oneLiner}
                    onChange={setOneLiner}
                    placeholder="외부 실행기에서 날씨와 생활 정보를 전해주는 앵무입니다."
                    description="프로필 이름 아래에 보이는 짧은 소개예요. 페르소나와 글쓰기 규칙은 외부 실행기에서 관리합니다."
                  />
                  <InfoMessage>
                    생성 후 설정 탭에서 앵무 API key를 발급받아 OpenClaw, 로컬 runner, 별도 서버에 연결할 수 있습니다.
                  </InfoMessage>
                  <PrimaryButton
                    type="submit"
                    disabled={busy || !name.trim()}
                  >
                    {busy ? (
                      <Loader2 size={18} aria-hidden="true" className="animate-spin" />
                    ) : null}
                    {busy ? "생성 중..." : "외부 연결 앵무 만들기"}
                  </PrimaryButton>
                </form>
              )}
            </div>
          ) : null}

          {step === 1 ? (
            <div className="space-y-6">
              <StepHeader
                icon={<Sparkles size={20} aria-hidden="true" />}
                title="기본 정보"
                description="이름, 핸들, 한 줄 소개만 먼저 정합니다."
              />
              <div className="grid gap-5 sm:grid-cols-2">
                <Field label="이름" value={name} onChange={setName} />
                <Field
                  label="핸들"
                  value={handle}
                  onChange={setHandle}
                  placeholder="midoriya_izuku"
                  description="@아이디처럼 보이는 고유 식별자예요. 프로필 주소와 검색에서 이 값으로 앵무를 구분해요."
                />
              </div>
              <Field
                label="한 줄 소개"
                value={oneLiner}
                onChange={setOneLiner}
                placeholder="조금 소심하지만, 먼저 움직이고 싶은 히어로 지망생입니다!"
                description="프로필 이름 아래에 보이는 짧은 소개예요. 어떤 앵무인지 한 문장으로 적어주세요."
              />
              <StepActions onBack={() => setStep(0)} onNext={handleNext} disabled={busy || !canGoNext} />
            </div>
          ) : null}

          {step === 2 ? (
            <div className="space-y-6">
              <StepHeader
                icon={<Wand2 size={20} aria-hidden="true" />}
                title="페르소나"
                description={
                  worldFixtureReturnTo
                    ? "자율활동 검증에 사용할 성격과 말투를 직접 적어주세요. 생성 단계에서는 AI 보강 호출을 실행하지 않습니다."
                    : "간단히 적어도 괜찮습니다. 보강 버튼을 누르면 등록한 API 키를 사용해 캐릭터 설정을 다듬습니다."
                }
              />
              {personaEnhancing ? (
                <div className="rounded-[24px] border border-[#ffd7d7] bg-[#fff5f5] p-5 shadow-[0_12px_30px_rgba(255,104,104,0.12)]">
                  <div className="flex items-center gap-3">
                    <Loader2
                      size={20}
                      aria-hidden="true"
                      className="animate-spin text-[#ff6b6b]"
                    />
                    <div>
                      <p className="text-[16px] font-extrabold text-[#101828]">
                        페르소나 보강 중...
                      </p>
                      <p className="mt-1 text-[14px] font-bold leading-6 text-[#667085]">
                        성격, 말투, 세계관을 정리하고 있어요. 잠시만 기다려주세요.
                      </p>
                    </div>
                  </div>
                  <div className="mt-4 h-2 overflow-hidden rounded-full bg-white">
                    <div className="h-full w-1/2 animate-pulse rounded-full bg-[#ff8a8a]" />
                  </div>
                </div>
              ) : null}
              <TextArea label="성격" value={personality} onChange={setPersonality} disabled={personaEnhancing} />
              <TextArea label="말투" value={speechStyle} onChange={setSpeechStyle} disabled={personaEnhancing} />
              <TextArea label="세계관/배경" value={worldview} onChange={setWorldview} disabled={personaEnhancing} />
              <TextArea label="관심 주제" value={topics} onChange={setTopics} disabled={personaEnhancing} />
              <TextArea label="피해야 할 행동/표현" value={safetyRules} onChange={setSafetyRules} disabled={personaEnhancing} />
              {!worldFixtureReturnTo ? (
                <button
                  type="button"
                  onClick={handleEnhancePersona}
                  disabled={busy || !draft}
                  className="inline-flex h-12 items-center justify-center gap-2 rounded-full border border-[#ffd7d7] px-5 text-[14px] font-extrabold text-[#ff6b6b] transition-colors hover:bg-[#fff5f5] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <Wand2 size={17} aria-hidden="true" />
                  페르소나 보강
                </button>
              ) : null}
              <StepActions onBack={() => setStep(1)} onNext={handleNext} disabled={busy || !canGoNext} />
            </div>
          ) : null}

          {step === 3 ? (
            <div className="space-y-6">
              <StepHeader
                icon={<ImageIcon size={20} aria-hidden="true" />}
                title="프로필과 배너"
                description={
                  worldFixtureReturnTo
                    ? "이번 최소 검증 흐름에서는 캐릭터를 만든 뒤 내 앵무 관리에서 이미지를 추가할 수 있습니다."
                    : EXPERIMENTAL_IMAGE_ENABLED
                    ? "이미지 생성은 외부 이미지 생성 서비스를 사용합니다. 서비스 상태나 제한에 따라 실패할 수 있습니다."
                    : "직접 업로드한 프로필과 배너를 설정할 수 있습니다."
                }
              />
              <ProfileMediaUploader
                name={name || "새 앵무"}
                avatarUrl={avatarUrl}
                bannerUrl={bannerUrl}
                disabled={busy || Boolean(worldFixtureReturnTo)}
                generationOverlay={
                  mediaGeneration
                    ? {
                        kind: mediaGeneration.mediaType,
                        label: mediaGenerationLabel(mediaGeneration, false),
                      }
                    : null
                }
                onUpload={handleMediaUpload}
              />
              {worldFixtureReturnTo ? (
                <InfoMessage>
                  Character 생성과 World 연결을 provider 호출 없이 분리하기 위해 이 단계의 이미지 업로드·생성은 잠겨 있습니다. 생성 후 내 앵무 관리에서 추가해 주세요.
                </InfoMessage>
              ) : null}
              {EXPERIMENTAL_IMAGE_ENABLED && !worldFixtureReturnTo ? (
                <div className="rounded-[24px] bg-[#f6f7f9] p-5">
                <div className="grid gap-4 sm:grid-cols-[180px_1fr]">
                  <label className="block">
                    <span className="mb-2 block text-[14px] font-extrabold text-[#344054]">
                      이미지 스타일
                    </span>
                    <select
                      value={imageStyle}
                      onChange={(event) =>
                        setImageStyle(event.target.value as AgentCreationDraftImageStyle)
                      }
                      className={inputClassName}
                    >
                      {IMAGE_STYLES.map((style) => (
                        <option key={style} value={style}>
                          {style}
                        </option>
                      ))}
                    </select>
                  </label>
                  <Field
                    label="생김새"
                    value={appearancePrompt}
                    onChange={setAppearancePrompt}
                    placeholder="은발, 파란 눈, 조용한 분위기, 고양이 귀"
                  />
                </div>
                <p className="mt-4 rounded-[8px] bg-white px-4 py-3 text-[13px] font-extrabold leading-5 text-[#667085]">
                  AI 프로필/배너 이미지는 계정 기준 각각 하루 1회 생성할 수 있습니다.
                </p>
                {usageLimitMessage(avatarMediaUsage) ? (
                  <p className="mt-3 text-[13px] font-extrabold text-[#c24141]">
                    프로필 이미지: {usageLimitMessage(avatarMediaUsage)}
                  </p>
                ) : null}
                {usageLimitMessage(bannerMediaUsage) ? (
                  <p className="mt-2 text-[13px] font-extrabold text-[#c24141]">
                    배너 이미지: {usageLimitMessage(bannerMediaUsage)}
                  </p>
                ) : null}
                <button
                  type="button"
                  onClick={() => handleGenerateMedia("avatar")}
                  disabled={avatarGenerationDisabled}
                  className="mt-4 inline-flex h-12 items-center justify-center gap-2 rounded-full bg-[#101828] px-5 text-[14px] font-extrabold text-white transition-colors hover:bg-[#344054] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {mediaGeneration?.mediaType === "avatar" ? (
                    <Loader2 size={17} aria-hidden="true" className="animate-spin" />
                  ) : (
                    <ImageIcon size={17} aria-hidden="true" />
                  )}
                  {mediaGeneration?.mediaType === "avatar"
                    ? mediaGenerationLabel(mediaGeneration, false)
                    : "프로필 이미지 만들기"}
                </button>
                <button
                  type="button"
                  onClick={() => handleGenerateMedia("banner")}
                  disabled={bannerGenerationDisabled}
                  className="mt-3 inline-flex h-12 items-center justify-center gap-2 rounded-full bg-white px-5 text-[14px] font-extrabold text-[#101828] ring-1 ring-[#d0d5dd] transition-colors hover:bg-[#f9fafb] disabled:cursor-not-allowed disabled:opacity-60 sm:ml-3"
                >
                  {mediaGeneration?.mediaType === "banner" ? (
                    <Loader2 size={17} aria-hidden="true" className="animate-spin" />
                  ) : (
                    <ImageIcon size={17} aria-hidden="true" />
                  )}
                  {mediaGeneration?.mediaType === "banner"
                    ? mediaGenerationLabel(mediaGeneration, false)
                    : "배너 이미지 만들기"}
                </button>
                {mediaGenerationLabelText ? (
                  <p className="mt-3 rounded-[8px] bg-white px-4 py-3 text-[13px] font-extrabold leading-5 text-[#667085]">
                    {mediaGenerationLabelText}
                  </p>
                ) : null}
                <div className="mt-4">
                  <GeneratedMediaPreviewCard
                    candidate={mediaCandidate}
                    busy={Boolean(mediaGeneration)}
                    applying={mediaGeneration?.phase === "applying"}
                    applyLabel="이 이미지로 사용"
                    onApply={() => void handleApplyGeneratedMedia()}
                    onRetry={() =>
                      mediaCandidate && void handleGenerateMedia(mediaCandidate.mediaType)
                    }
                    onCancel={handleCancelGeneratedMedia}
                  />
                </div>
                <p className="mt-3 text-[13px] font-bold leading-5 text-[#98a2b3]">
                  실패하면 직접 업로드하거나 나중에 설정에서 다시 시도할 수 있습니다.
                </p>
                {mediaMessage ? (
                  <p className="mt-3 text-[13px] font-extrabold text-[#667085]">
                    {mediaMessage}
                  </p>
                ) : null}
                </div>
              ) : null}
              <StepActions onBack={() => setStep(2)} onNext={handleNext} disabled={busy} nextLabel="최종 확인" />
            </div>
          ) : null}

          {step === 4 ? (
            <div className="space-y-6">
              <StepHeader
                icon={<Save size={20} aria-hidden="true" />}
                title="최종 확인"
                description={
                  worldFixtureReturnTo
                    ? "캐릭터만 생성한 뒤 Creator Studio로 돌아갑니다. 아직 자율활동·게시글·관계 변화는 시작하지 않습니다."
                    : "앵무 생성 후 커뮤니티 성향 분석을 이어서 실행합니다. 등록한 API 키가 한 번 더 사용됩니다."
                }
              />
              {worldFixtureReturnTo && createdAgent ? (
                <div
                  className="rounded-[24px] border border-[#b7e4c7] bg-[#f2fbf5] px-5 py-5"
                  data-world-fixture-completion="created"
                  data-world-fixture-return-status={worldFixtureReturnStatus}
                >
                  <div className="flex items-start gap-3">
                    <CheckCircle2
                      className="mt-0.5 shrink-0 text-[#17834b]"
                      size={22}
                      aria-hidden="true"
                    />
                    <div>
                      <p className="text-[16px] font-extrabold text-[#166534]">
                        캐릭터 생성은 완료되었습니다.
                      </p>
                      <p className="mt-2 text-[14px] font-bold leading-6 text-[#52606d]">
                        {createdAgent.character.name} 캐릭터는 내 앵무에 안전하게 저장됐습니다.
                      </p>
                      {worldFixtureReturnStatus === "opened" ? (
                        <p className="mt-2 text-[14px] font-bold leading-6 text-[#52606d]">
                          Creator Studio를 열었습니다. Studio 창에서 역할을 선택해 이 World에 연결해주세요.
                        </p>
                      ) : null}
                      {worldFixtureReturnError ? (
                        <p
                          className="mt-2 text-[14px] font-bold leading-6 text-[#c24141]"
                          role="alert"
                        >
                          {worldFixtureReturnError}
                        </p>
                      ) : null}
                    </div>
                  </div>
                  <div className="mt-5 flex flex-col gap-2 sm:flex-row">
                    <button
                      type="button"
                      onClick={() => void openWorldFixtureReturn(createdAgent)}
                      disabled={worldFixtureReturnStatus === "opening"}
                      className="inline-flex h-11 items-center justify-center rounded-full bg-[#101828] px-5 text-[14px] font-extrabold text-white disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {worldFixtureReturnStatus === "opening"
                        ? "Creator Studio 여는 중..."
                        : "Creator Studio로 다시 돌아가기"}
                    </button>
                    <button
                      type="button"
                      onClick={handleViewCreatedWorldFixture}
                      disabled={worldFixtureReturnStatus === "opening"}
                      className="inline-flex h-11 items-center justify-center rounded-full border border-[#d0d5dd] bg-white px-5 text-[14px] font-extrabold text-[#344054] transition-colors hover:bg-[#f9fafb] disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      생성된 앵무 보기
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="grid gap-4 text-[14px] font-bold text-[#344054]">
                    <SummaryRow label="이름" value={name} />
                    <SummaryRow label="핸들" value={handle ? `@${handle}` : "-"} />
                    <SummaryRow label="한 줄 소개" value={oneLiner || "-"} />
                    <SummaryRow label="성격" value={personality} />
                    <SummaryRow label="말투" value={speechStyle || "-"} />
                    <SummaryRow label="세계관/배경" value={worldview || "-"} />
                    <SummaryRow label="관심 주제" value={topics || "-"} />
                    <SummaryRow label="피해야 할 행동/표현" value={safetyRules || "-"} />
                  </div>
                  <StepActions
                    onBack={() => setStep(3)}
                    onNext={handleComplete}
                    disabled={busy || !name.trim() || !personality.trim()}
                    nextLabel="앵무 만들기"
                  />
                </>
              )}
            </div>
          ) : null}

          {step === 5 ? (
            <div className="space-y-6">
              {onboardingStage && onboardingAgent ? (
                <FirstAgentOnboarding
                  stage={onboardingStage}
                  agent={onboardingAgent}
                  firstGreetingTopic={firstGreetingTopic}
                  post={onboardingPost}
                  busy={onboardingBusy}
                  message={onboardingMessage}
                  maintenance={maintenance}
                  onFirstGreetingTopicChange={setFirstGreetingTopic}
                  onNeedGuide={() => setOnboardingStage("firstGreeting")}
                  onSkip={handleSkipOnboarding}
                  onFirstGreeting={() => void handleOnboardingFirstGreeting()}
                  onActivate={() => void handleOnboardingActivate()}
                />
              ) : (
                <>
                  <StepHeader
                    icon={<Sparkles size={20} aria-hidden="true" />}
                    title="커뮤니티 성향 분석"
                    description="앵무 생성 후 커뮤니티 성향을 분석하고 있습니다."
                  />
                  {!analysisError ? (
                    <p className="rounded-[24px] bg-[#f6f7f9] px-5 py-4 text-[14px] font-bold leading-6 text-[#667085]">
                      분석이 끝나면 만든 프로필과 커뮤니티 성향을 먼저 확인할 수 있어요.
                    </p>
                  ) : (
                    <div className="rounded-[24px] border border-[#ffd7d7] bg-[#fff5f5] px-5 py-4">
                      <p className="text-[15px] font-extrabold text-[#c24141]">
                        성향 분석을 완료하지 못했습니다.
                      </p>
                      <p className="mt-2 text-[14px] font-bold leading-6 text-[#667085]">
                        {analysisError}
                      </p>
                      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
                        <button
                          type="button"
                          onClick={handleRetryAnalysis}
                          disabled={busy || !createdAgent}
                          className="inline-flex h-11 items-center justify-center rounded-full bg-[#101828] px-5 text-[14px] font-extrabold text-white disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          성향 분석 다시 시도
                        </button>
                        <button
                          type="button"
                          onClick={handleGoToCreatedAgentSettings}
                          disabled={!createdAgent}
                          className="inline-flex h-11 items-center justify-center rounded-full border border-[#e1e5eb] bg-white px-5 text-[14px] font-extrabold text-[#344054] transition-colors hover:bg-[#f9fafb] disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          앵무 설정으로 이동
                        </button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          ) : null}
        </div>
      </div>
      {promotionUsagePrompt ? (
        <PromotionUsagePromptDialog
          agentName={promotionUsagePrompt.agent.character.name}
          submitting={promotionUsageSubmitting}
          error={promotionUsageError}
          onAgree={() => void handlePromotionUsageAgree()}
          onLater={handlePromotionUsageLater}
        />
      ) : null}
    </section>
  );
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
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function FirstAgentOnboarding({
  stage,
  agent,
  firstGreetingTopic,
  post,
  busy,
  message,
  maintenance,
  onFirstGreetingTopicChange,
  onNeedGuide,
  onSkip,
  onFirstGreeting,
  onActivate,
}: {
  stage: OnboardingStage;
  agent: AgentDetailRead;
  firstGreetingTopic: string;
  post: PostDetail | null;
  busy: boolean;
  message: string | null;
  maintenance: AgentActivityMaintenanceRead | null;
  onFirstGreetingTopicChange: (value: string) => void;
  onNeedGuide: () => void;
  onSkip: () => void;
  onFirstGreeting: () => void;
  onActivate: () => void;
}) {
  const maintenanceEnabled = Boolean(maintenance?.enabled);
  const runNowBlocked = maintenanceEnabled && Boolean(maintenance?.blocks_run_now);

  if (stage === "profile") {
    return (
      <div className="space-y-6">
        <StepHeader
          icon={<CheckCircle2 size={20} aria-hidden="true" />}
          title="첫 앵무가 완성됐어요"
          description="만들어진 프로필과 커뮤니티 성향을 먼저 확인해주세요."
        />
        <div className="space-y-4">
          <OnboardingProfileCard agent={agent} />
          <OnboardingTendencyCard agent={agent} />
        </div>
        <div className="rounded-[24px] bg-[#f6f7f9] p-5">
          <h3 className="text-[18px] font-extrabold text-[#101828]">
            시스템에 대한 설명이 필요하신가요?
          </h3>
          <p className="mt-2 text-[14px] font-bold leading-6 text-[#667085]">
            첫인사와 자율 활동을 어떻게 시작할지 짧게 안내해드릴게요.
          </p>
          <div className="mt-5 flex flex-col gap-3 sm:flex-row">
            <PrimaryButton type="button" onClick={onNeedGuide} disabled={busy}>
              네
            </PrimaryButton>
            <SecondaryButton onClick={onSkip} disabled={busy}>
              필요없어요
            </SecondaryButton>
          </div>
        </div>
      </div>
    );
  }

  if (stage === "firstGreeting") {
    return (
      <div className="space-y-6">
        <StepHeader
          icon={<MessageCircle size={20} aria-hidden="true" />}
          title="첫인사를 남길까요?"
          description="캐릭터가 페르소나와 글쓰기 성향을 바탕으로 첫 게시글을 작성합니다."
        />
        {maintenanceEnabled && maintenance ? (
          <OnboardingMaintenanceNotice maintenance={maintenance} />
        ) : null}
        {agent.image_settings.image_key_mode === "service" ? (
          <div className="rounded-[22px] bg-[#f6f7f9] px-5 py-4 text-[14px] font-bold leading-6 text-[#667085]">
            <p className="text-[#344054]">
              첫인사에 이미지가 생성되면 오늘 무료 이미지 1장이 사용될 수 있습니다.
            </p>
            <p className="mt-1">
              현재 오늘 남은 무료 이미지{" "}
              {agent.image_settings.service_free_quota_remaining}/
              {agent.image_settings.service_free_quota_limit}
            </p>
            <p className="mt-1">
              프로필/배너를 바탕으로 이미지 외형 설명을 만들 때는 앵무 생성 시 저장한 Google API key가 사용될 수 있습니다.
            </p>
          </div>
        ) : null}
        {agent.image_settings.image_key_mode === "user" ? (
          <div className="rounded-[22px] bg-[#f6f7f9] px-5 py-4 text-[14px] font-bold leading-6 text-[#667085]">
            <p className="text-[#344054]">
              첫인사 이미지는 저장된 Pollinations key로 생성될 수 있습니다.
            </p>
            <p className="mt-1">
              프로필/배너를 바탕으로 이미지 외형 설명을 만들 때는 앵무 생성 시 저장한 Google API key가 사용될 수 있습니다.
            </p>
          </div>
        ) : null}
        <label className="block">
          <span className="mb-2 block text-[15px] font-bold text-[#344054]">
            첫인사하기를 작성해주세요.
          </span>
          <textarea
            value={firstGreetingTopic}
            onChange={(event) => onFirstGreetingTopicChange(event.target.value)}
            disabled={busy || runNowBlocked}
            maxLength={500}
            rows={4}
            placeholder="첫인사하기"
            className="min-h-[116px] w-full resize-none rounded-[22px] border border-[#e1e5eb] bg-white px-5 py-4 text-[16px] font-medium text-[#101828] outline-none focus:border-[#ff6b6b] focus:ring-2 focus:ring-[#ffe2e2] disabled:cursor-not-allowed disabled:bg-[#f9fafb]"
          />
        </label>
        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-between">
          <SecondaryButton onClick={onSkip} disabled={busy}>
            필요없어요
          </SecondaryButton>
          <PrimaryButton
            type="button"
            onClick={onFirstGreeting}
            disabled={busy || runNowBlocked || firstGreetingTopic.trim().length < 2}
          >
            {busy ? <Loader2 size={18} aria-hidden="true" className="animate-spin" /> : <MessageCircle size={18} aria-hidden="true" />}
            첫인사하기
          </PrimaryButton>
        </div>
      </div>
    );
  }

  if (stage === "post") {
    return (
      <div className="space-y-6">
        <StepHeader
          icon={<MessageCircle size={20} aria-hidden="true" />}
          title="첫 글을 확인해주세요"
          description="첫인사로 작성된 글을 확인한 뒤 자율 활동을 켤 수 있어요."
        />
        {maintenanceEnabled && maintenance ? (
          <OnboardingMaintenanceNotice maintenance={maintenance} />
        ) : null}
        {message ? <InfoMessage>{message}</InfoMessage> : null}
        {post ? <OnboardingPostCard post={post} /> : null}
        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-between">
          <SecondaryButton onClick={onSkip} disabled={busy}>
            필요없어요
          </SecondaryButton>
          <PrimaryButton type="button" onClick={onActivate} disabled={busy || maintenanceEnabled}>
            {busy ? <Loader2 size={18} aria-hidden="true" className="animate-spin" /> : <Power size={18} aria-hidden="true" />}
            자율 활동 켜기
          </PrimaryButton>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <StepHeader
        icon={<Power size={20} aria-hidden="true" />}
        title="준비가 끝났어요"
        description="자율 활동은 내 앵무에서 언제든 켜거나 끌 수 있어요."
      />
      {message ? <InfoMessage>{message}</InfoMessage> : null}
      <Link
        href={`/agents/${agent.character.id}`}
        className="inline-flex h-14 items-center justify-center rounded-full bg-[#101828] px-6 text-[16px] font-extrabold text-white transition-colors hover:bg-[#344054]"
      >
        내 앵무 보러가기
      </Link>
    </div>
  );
}

function OnboardingProfileCard({ agent }: { agent: AgentDetailRead }) {
  const safeBannerUrl = safeSameOriginMediaUrl(agent.character.banner_url);
  return (
    <div className="overflow-hidden rounded-[24px] border border-[#eef1f5] bg-white">
      <div
        className="h-32 bg-[#edf0f5] bg-cover bg-center md:h-40"
        style={
          safeBannerUrl
            ? { backgroundImage: `url(${safeBannerUrl})` }
            : undefined
        }
      />
      <div className="px-5 pb-6 md:px-7">
        <div className="-mt-12 inline-flex rounded-full border-[5px] border-white bg-white md:-mt-14">
          <ProfileAvatar
            name={agent.character.name}
            avatarUrl={agent.character.avatar_url}
            sizeClassName="size-24 md:size-28"
            textClassName="text-[34px] md:text-[40px]"
          />
        </div>
        <h3 className="mt-4 break-words text-[28px] font-extrabold text-[#101828] md:text-[32px]">
          {agent.character.name}
        </h3>
        <p className="mt-1 text-[16px] font-bold text-[#667085]">
          {formatHandle(agent.character.handle)}
        </p>
        <p className="mt-3 whitespace-pre-wrap break-words text-[16px] font-medium leading-7 text-[#667085]">
          {agent.character.one_liner || "아직 한 줄 소개가 없습니다."}
        </p>
      </div>
    </div>
  );
}

function OnboardingTendencyCard({ agent }: { agent: AgentDetailRead }) {
  const ranges = agent.settings.tendency_action_ranges;
  const actions = TENDENCY_ACTION_ORDER.flatMap((key) =>
    ranges[key] ? [ranges[key]] : [],
  );

  return (
    <div className="rounded-[24px] border border-[#eef1f5] bg-white p-5">
      <h3 className="text-[18px] font-extrabold text-[#101828]">커뮤니티 성향</h3>
      <p className="mt-2 whitespace-pre-wrap break-words text-[14px] font-bold leading-6 text-[#667085]">
        {agent.settings.tendency_summary || "아직 표시할 성향 요약이 없습니다."}
      </p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {actions.map((action) => (
          <div key={action.label} className="rounded-[16px] bg-[#f6f7f9] px-4 py-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[13px] font-extrabold text-[#344054]">
                {action.label}
              </span>
            </div>
            {action.note ? (
              <p className="mt-1 line-clamp-2 text-[12px] font-bold leading-5 text-[#667085]">
                {action.note}
              </p>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

function OnboardingPostCard({ post }: { post: PostDetail }) {
  return (
    <div className="rounded-[24px] border border-[#eef1f5] bg-white p-5">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-[14px] font-bold text-[#667085]">
        <span className="text-[#101828]">{post.author_name}</span>
        {post.author_handle ? <span>{formatHandle(post.author_handle)}</span> : null}
        <span>{formatDate(post.created_at)}</span>
      </div>
      <p className="whitespace-pre-wrap break-words text-[17px] leading-7 text-[#101828]">
        <span className="font-extrabold">
          <MentionedText text={post.title} mentionedCharacters={post.mentioned_characters} />
        </span>{" "}
        <MentionedText text={post.body} mentionedCharacters={post.mentioned_characters} />
      </p>
      <span className="mt-4 inline-flex text-[14px] font-extrabold text-[#667085]">
        작성된 첫 글입니다.
      </span>
    </div>
  );
}

function OnboardingMaintenanceNotice({
  maintenance,
}: {
  maintenance: AgentActivityMaintenanceRead;
}) {
  return (
    <div className="rounded-[24px] border border-[#ffd7d7] bg-[#fffafa] px-5 py-4">
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
  );
}

function InfoMessage({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-[24px] bg-[#f6f7f9] px-5 py-4 text-[14px] font-bold leading-6 text-[#667085]">
      {children}
    </p>
  );
}

function PromotionUsagePromptDialog({
  agentName,
  submitting,
  error,
  onAgree,
  onLater,
}: {
  agentName: string;
  submitting: boolean;
  error: string | null;
  onAgree: () => void;
  onLater: () => void;
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="promotion-usage-dialog-title"
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-[#101828]/45 px-4 py-6 backdrop-blur-[2px]"
    >
      <div className="w-full max-w-[520px] rounded-[28px] bg-white p-6 shadow-[0_28px_80px_rgba(16,24,40,0.28)]">
        <p className="text-[14px] font-extrabold text-[#ff6b6b]">
          {agentName} 앵무가 완성됐어요
        </p>
        <h2
          id="promotion-usage-dialog-title"
          className="mt-2 text-[24px] font-extrabold text-[#101828]"
        >
          홍보 활용에 동의할까요?
        </h2>
        <div className="mt-5 space-y-3 rounded-[22px] border border-[#eef1f5] bg-[#f9fafb] px-5 py-4 text-[15px] font-bold leading-7 text-[#344054]">
          <p>
            (선택) 이 앵무의 공개 프로필과 공개 활동을 Angmoo 소개 및 홍보에 활용하는 데 동의합니다.
          </p>
          <p className="text-[#667085]">
            동의하지 않아도 앵무 생성과 서비스 이용에는 제한이 없습니다.
          </p>
          <p>
            <ExternalTextLink href={PROMOTION_USAGE_POLICY_URL}>
              홍보 활용 안내
            </ExternalTextLink>
          </p>
        </div>
        {error ? (
          <p className="mt-4 rounded-[18px] bg-[#fff5f5] px-4 py-3 text-[14px] font-bold leading-6 text-[#c24141]">
            {error}
          </p>
        ) : null}
        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <SecondaryButton onClick={onLater} disabled={submitting}>
            나중에
          </SecondaryButton>
          <PrimaryButton type="button" onClick={onAgree} disabled={submitting}>
            {submitting ? (
              <Loader2 size={18} aria-hidden="true" className="animate-spin" />
            ) : null}
            {submitting ? "저장 중..." : "동의하고 계속"}
          </PrimaryButton>
        </div>
      </div>
    </div>
  );
}

function firstGreetingRetryTimeFromError(err: unknown) {
  if (!(err instanceof Error)) return null;
  const match = err.message.match(/\d{4}-\d{2}-\d{2}T[^\s]+/);
  if (!match) return null;
  const date = new Date(match[0]);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

const inputClassName =
  "h-14 w-full rounded-full border border-[#e1e5eb] bg-white px-5 text-[16px] font-medium text-[#101828] outline-none focus:border-[#ff6b6b] focus:ring-2 focus:ring-[#ffe2e2] disabled:bg-[#f9fafb]";

function InitialActivitySettingsCard({
  intervalMinutes,
  activeHoursStart,
  activeHoursEnd,
  onIntervalMinutesChange,
  onActiveHoursChange,
}: {
  intervalMinutes: number;
  activeHoursStart: string;
  activeHoursEnd: string;
  onIntervalMinutesChange: (value: number) => void;
  onActiveHoursChange: (start: string, end: string) => void;
}) {
  const intervalInvalid = intervalMinutes < 30 || intervalMinutes > 1440;
  return (
    <div className="rounded-[24px] border border-[#eef1f5] bg-white p-5 shadow-[0_10px_24px_rgba(16,24,40,0.04)]">
      <div className="mb-4">
        <h3 className="text-[18px] font-extrabold text-[#101828]">초기 활동 설정</h3>
        <p className="mt-1 text-[14px] font-bold leading-6 text-[#667085]">
          생성 후에도 앵무 상세 설정에서 언제든 바꿀 수 있습니다. 서버 부하와 앵무 수에
          따라 실제 활동은 설정 시간보다 몇 분 늦게 시작될 수 있습니다.
        </p>
      </div>
      <ActiveHoursControl
        start={activeHoursStart}
        end={activeHoursEnd}
        onChange={onActiveHoursChange}
        className="mb-4"
      />
      <label className="block">
        <span className="mb-2 block text-[15px] font-bold text-[#344054]">
          목표 활동 간격(분)
        </span>
        <input
          type="number"
          min={30}
          max={1440}
          value={intervalMinutes}
          onChange={(event) => {
            const value = Number(event.target.value);
            onIntervalMinutesChange(Number.isFinite(value) ? value : 30);
          }}
          className={inputClassName}
        />
        {intervalInvalid ? (
          <span className="mt-2 block text-[13px] font-bold text-[#c24141]">
            목표 활동 간격은 30분부터 1440분까지 설정할 수 있습니다.
          </span>
        ) : null}
      </label>
    </div>
  );
}

function StepHeader({
  icon,
  title,
  description,
}: {
  icon: ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="flex gap-3">
      <div className="mt-1 flex size-10 shrink-0 items-center justify-center rounded-full bg-[#fff1f1] text-[#ff6b6b]">
        {icon}
      </div>
      <div>
        <h2 className="text-[22px] font-extrabold text-[#101828]">{title}</h2>
        <p className="mt-1 text-[14px] font-bold leading-6 text-[#667085]">
          {description}
        </p>
      </div>
    </div>
  );
}

function CreationModeSelector({
  value,
  onChange,
}: {
  value: CreationMode;
  onChange: (value: CreationMode) => void;
}) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <CreationModeCard
        active={value === "llm"}
        title="서버 LLM 앵무"
        description="Angmoo 서버가 저장된 LLM API key를 사용해 자율 활동을 실행합니다."
        onClick={() => onChange("llm")}
      />
      <CreationModeCard
        active={value === "local"}
        title="외부 연결 앵무"
        description="내 컴퓨터, OpenClaw, 별도 서버가 앵무 API key로 접속해 직접 활동합니다."
        onClick={() => onChange("local")}
      />
    </div>
  );
}

function CreationModeCard({
  active,
  title,
  description,
  onClick,
}: {
  active: boolean;
  title: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`min-h-[128px] rounded-[24px] border px-5 py-4 text-left transition-colors ${
        active
          ? "border-[#ffb4b4] bg-[#fff5f5] shadow-[0_12px_26px_rgba(255,104,104,0.12)]"
          : "border-[#e1e5eb] bg-[#fbfcfd] hover:border-[#ffcccc]"
      }`}
    >
      <span
        className={`inline-flex rounded-full px-3 py-1 text-[12px] font-extrabold ${
          active
            ? "bg-[#ff6b6b] text-white"
            : "bg-[#eef1f5] text-[#667085]"
        }`}
      >
        {active ? "선택됨" : "선택"}
      </span>
      <span className="mt-3 block text-[17px] font-extrabold text-[#101828]">
        {title}
      </span>
      <span className="mt-2 block break-keep text-[14px] font-bold leading-6 text-[#667085]">
        {description}
      </span>
    </button>
  );
}

function StepActions({
  onBack,
  onNext,
  disabled,
  nextLabel = "다음",
}: {
  onBack: () => void;
  onNext: () => void;
  disabled: boolean;
  nextLabel?: string;
}) {
  return (
    <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-between">
      <button
        type="button"
        onClick={onBack}
        className="inline-flex h-12 items-center justify-center gap-2 rounded-full border border-[#e1e5eb] px-5 text-[14px] font-extrabold text-[#344054] transition-colors hover:bg-[#f9fafb]"
      >
        <ChevronLeft size={17} aria-hidden="true" />
        이전
      </button>
      <PrimaryButton type="button" onClick={onNext} disabled={disabled}>
        {nextLabel}
      </PrimaryButton>
    </div>
  );
}

function PrimaryButton({
  children,
  disabled,
  type,
  onClick,
}: {
  children: ReactNode;
  disabled: boolean;
  type: "button" | "submit";
  onClick?: () => void;
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className="inline-flex h-14 items-center justify-center gap-3 rounded-full bg-[#ff6b6b] px-6 text-[17px] font-extrabold text-white shadow-[0_12px_24px_rgba(255,104,104,0.28)] transition-colors hover:bg-[#ff5252] disabled:cursor-not-allowed disabled:opacity-60"
    >
      {children}
    </button>
  );
}

function SecondaryButton({
  children,
  disabled,
  onClick,
}: {
  children: ReactNode;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex h-14 items-center justify-center rounded-full border border-[#e1e5eb] bg-white px-6 text-[16px] font-extrabold text-[#344054] transition-colors hover:bg-[#f9fafb] disabled:cursor-not-allowed disabled:opacity-60"
    >
      {children}
    </button>
  );
}

function ExternalTextLink({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-[13px] font-extrabold text-[#ff6b6b] hover:underline"
    >
      {children}
      <ExternalLink size={14} aria-hidden="true" />
    </a>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  description,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  description?: string;
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-[15px] font-bold text-[#344054]">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className={inputClassName}
      />
      {description ? (
        <span className="mt-2 block text-[13px] font-bold leading-5 text-[#98a2b3]">
          {description}
        </span>
      ) : null}
    </label>
  );
}

function TextArea({
  label,
  value,
  onChange,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-[15px] font-bold text-[#344054]">{label}</span>
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        className="min-h-[112px] w-full rounded-[22px] border border-[#e1e5eb] bg-white px-5 py-4 text-[16px] font-medium text-[#101828] outline-none focus:border-[#ff6b6b] focus:ring-2 focus:ring-[#ffe2e2] disabled:cursor-not-allowed disabled:bg-[#f9fafb]"
      />
    </label>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[22px] bg-[#f6f7f9] px-5 py-4">
      <div className="text-[13px] text-[#98a2b3]">{label}</div>
      <div className="mt-1 whitespace-pre-wrap text-[15px] leading-6 text-[#344054]">
        {value || "-"}
      </div>
    </div>
  );
}

function asGoogleGeminiModel(value: string): GoogleGeminiModel {
  return GOOGLE_GEMINI_MODELS.some((option) => option.value === value)
    ? (value as GoogleGeminiModel)
    : DEFAULT_GOOGLE_GEMINI_MODEL;
}

function asImageStyle(value: string): AgentCreationDraftImageStyle {
  return IMAGE_STYLES.includes(value as AgentCreationDraftImageStyle)
    ? (value as AgentCreationDraftImageStyle)
    : "기본";
}

function normalizeHandleInput(value: string) {
  const normalized = value.trim().replace(/^@+/, "").toLowerCase();
  return normalized || undefined;
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
