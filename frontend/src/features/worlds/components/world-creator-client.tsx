"use client";
import { useProductLeaveGuard } from "@/hooks/use-product-leave-guard";
import { useUiText } from "@/hooks/use-ui-text";
import { useUserEnvironment } from "@/hooks/use-user-environment";


import {
  AlertTriangle,
  CheckCircle2,
  ImagePlus,
  Loader2,
  Plus,
  Save,
  Send,
  ShieldCheck,
  X,
} from "lucide-react";
import { useRuntimeRouter as useRouter } from "@/hooks/use-runtime-navigation";
import { useEffect, useEffectEvent, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import { useAuthRuntimeIdentity } from "@/hooks/use-auth-runtime-identity";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { Button } from "@/components/ui/button";
import { ImageCropDialog } from "@/components/media/image-crop-dialog";
import { AppIcon } from "@/components/ui/app-icon";
import { AppIconVisual, appIconBackground } from "@/components/ui/app-icon-visual";
import { blobToBase64, cropToBlob, INITIAL_CROP, PROFILE_MEDIA_MAX_BYTES, type CropState } from "@/utils/image-crop";
import { WorldBanner } from "./world-banner";
import { WorldDeleteControl } from "./world-delete-control";
import { WorldDeletionProgress } from "./world-deletion-progress";
import type { WorldDeletionReceipt } from "../types/world-deletion";
import {useWorldDeletionWatch} from "../hooks/use-world-deletion-watch";
import { PRODUCT_ROUTES, studioWorldRoute } from "@/lib/navigation/product-routes";
import { safeSameOriginMediaUrl } from "@/lib/media/safe-media-url";
import { useRuntimeMediaUrl } from "@/hooks/use-runtime-media-url";

import { useAuth } from "@/hooks/use-auth";
import { createWorld, getWorldCreatorContext, publishWorld, removeWorldBanner, updateWorld, uploadWorldBanner, validateWorld, WorldApiError } from "@/features/worlds/api/worlds";
import type { WorldCreatorContext, WorldDaypart, WorldDefinition, WorldPlaceInput, WorldRoleInput, WorldValidationIssue } from "@/features/worlds/types/worlds";

const DAYPARTS: { key: WorldDaypart; label: string; hours: string }[] = [
  { key: "dawn", label: "새벽", hours: "00:00~06:00" },
  { key: "morning", label: "오전", hours: "06:00~12:00" },
  { key: "afternoon", label: "오후", hours: "12:00~18:00" },
  { key: "evening", label: "저녁", hours: "18:00~24:00" },
];
const DAYPART_KEYS = DAYPARTS.map((entry) => entry.key);
const NO_SPECIFIC_ROLE_KEY = "no_specific_role";

const EMPTY_DEFINITION: WorldDefinition = {
  name: "",
  tagline: "",
  setting_description: "",
  daily_life_description: "",
  genre_tags: [],
  tone_tags: [],
  timezone: "UTC",
  language: "en",
  visibility: "private",
  join_policy: "approval_required",
  additional_generation_guidance: "",
  places: [],
  roles: [],
  daypart_profiles: [],
  rules: [],
  glossary: [],
};

const REASON_LABELS: Record<string, string> = {
  world_not_found: "World를 찾을 수 없거나 접근할 수 없어요.",
  world_archived: "보관한 World는 변경할 수 없어요.",
  membership_required: "이 World에 참여한 뒤 사용할 수 있어요.",
  creator_role_required: "이 World를 편집할 권한이 없어요.",
  world_definition_incomplete: "필수 세계관 설정을 먼저 완성해 주세요.",
  invalid_world_name: "World 이름은 2~120자로 작성해 주세요.",
  invalid_tagline: "한 줄 소개는 10~160자로 작성해 주세요.",
  invalid_setting_description: "세계관 설명은 200~4,000자로 작성해 주세요.",
  invalid_daily_life_description: "일상 설명은 150~3,000자로 작성해 주세요.",
  invalid_genre_tags: "장르 태그를 1~5개 입력해 주세요.",
  invalid_tone_tags: "분위기 태그를 1~5개 입력해 주세요.",
  invalid_timezone: "올바른 시간대를 확인해주세요.",
  invalid_language: "기억과 검색에 사용할 언어를 확인해주세요.",
  unsafe_banner_reference: "배너 이미지 형식이나 크기를 확인해 주세요.",
  row_version_conflict: "다른 변경이 먼저 저장됐어요. 새로고침한 뒤 다시 확인해주세요.",
  request_validation_error: "입력값과 형식을 확인해 주세요.",
  local_owner_required: "먼저 사용자 연결을 완료해주세요.",
  owner_world_required: "내가 만든 World에서만 만들 수 있어요.",
  owner_controlled_identity_exists: "이 World에는 이미 내 프로필이 있어요.",
  owner_controlled_role_invalid: "이 World에서 사용할 수 있는 역할을 선택해 주세요.",
};

function splitList(value: string) {
  return Array.from(
    new Set(
      value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
}

function worldToDefinition(context: WorldCreatorContext): WorldDefinition {
  const { world } = context;
  return {
    name: world.name,
    tagline: world.tagline,
    setting_description: world.setting_description,
    daily_life_description: world.daily_life_description,
    genre_tags: world.genre_tags,
    tone_tags: world.tone_tags,
    timezone: world.timezone,
    language: world.language,
    visibility: world.visibility,
    join_policy: world.join_policy,
    additional_generation_guidance: world.additional_generation_guidance,
    places: world.places.map(({ key, name, description, available_dayparts, access_role_keys }) => ({
      key,
      name,
      description,
      available_dayparts,
      access_role_keys,
    })),
    roles: world.roles
      .filter(({ key }) => key !== NO_SPECIFIC_ROLE_KEY)
      .map(
        ({ key, name, description, responsibilities, allowed_activity_scope, autonomous_allowed }) => ({
          key,
          name,
          description,
          responsibilities,
          allowed_activity_scope,
          autonomous_allowed,
        }),
      ),
    daypart_profiles: world.daypart_profiles.map(
      ({ daypart, description, available_features, restricted_features }) => ({
        daypart,
        description,
        available_features,
        restricted_features,
      }),
    ),
    rules: world.rules.map(({ key, rule_kind, description }) => ({
      key,
      rule_kind,
      description,
    })),
    glossary: world.glossary.map(({ key, term, meaning }) => ({
      key,
      term,
      meaning,
    })),
  };
}

function errorMessage(error: unknown) {
  if (error instanceof WorldApiError) {
    if (error.message === "request_validation_error") {
      return REASON_LABELS.request_validation_error;
    }
    if (error.status === 413) return "이미지 업로드 요청이 너무 커요. 더 작은 이미지를 선택해주세요.";
    return REASON_LABELS[error.message] ?? "요청을 처리하지 못했어요. 다시 시도해주세요.";
  }
  return "요청을 처리하지 못했어요. 다시 시도해주세요.";
}

function newIdempotencyKey() {
  return `world-create-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

type CreatorProps = { worldId?: string; renderDeleteExport?: (worldId: string) => ReactNode; renderWorldTools: (worldId: string, roles: WorldRoleInput[]) => ReactNode; renderMyProfile: (worldId: string) => ReactNode };
export function WorldCreatorClient(props: CreatorProps) {
  const identity = useAuthRuntimeIdentity(props.worldId ?? "new-world");
  return <WorldCreatorEditor key={identity} {...props} />;
}
function WorldCreatorEditor({ worldId, renderWorldTools, renderMyProfile, renderDeleteExport }: CreatorProps) {
  const [deletionReceipt, setDeletionReceipt] = useState<WorldDeletionReceipt | null>(null);
  const uiText = useUiText("worlds");
  const { environment, ready: environmentReady, errorCode: environmentError } = useUserEnvironment();
  const router = useRouter();
  const { status: authStatus } = useAuth();
  const scopeClosed=useWorldDeletionWatch(worldId,authStatus==="authenticated"&&!deletionReceipt);
  const idempotencyKey = useRef(newIdempotencyKey());
  const [context, setContext] = useState<WorldCreatorContext | null>(null);
  const [definition, setDefinition] = useState<WorldDefinition>(EMPTY_DEFINITION);
  const [loading, setLoading] = useState(Boolean(worldId));
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const dirty = JSON.stringify(definition) !== JSON.stringify(context ? worldToDefinition(context) : EMPTY_DEFINITION);
  const [imageDraft, setImageDraft] = useState<{ bitmap: ImageBitmap; kind: "icon" | "banner" } | null>(null);
  const iconInput = useRef<HTMLInputElement>(null);
  const bannerInput = useRef<HTMLInputElement>(null);
  const [imageConflict, setImageConflict] = useState(false);
  const imageRef = useRef<typeof imageDraft>(null);
  const imageRequest = useRef<AbortController | null>(null);
  const imageEpoch = useRef(0);
  const imageBusy = useRef(false);
  const [crop, setCrop] = useState<CropState>(INITIAL_CROP);
  const [cropError, setCropError] = useState<string | null>(null);
  const permitCommittedNavigation = useProductLeaveGuard(dirty || Boolean(imageDraft) || pending !== null);
  useEffect(() => () => { imageEpoch.current++; imageRequest.current?.abort(); imageRef.current?.bitmap.close(); }, []);
  useEffect(()=>{if(scopeClosed){imageEpoch.current++;imageRequest.current?.abort();imageRef.current?.bitmap.close();}},[scopeClosed]);
  const presentError = useEffectEvent((reason: unknown) => setError(uiText(errorMessage(reason))));
  const worldBannerUrl = useRuntimeMediaUrl(
    scopeClosed?null:safeSameOriginMediaUrl(context?.world.banner_media_id),
  );
  const worldIconUrl = useRuntimeMediaUrl(scopeClosed?null:safeSameOriginMediaUrl(context?.world.icon_media_id));

  const returnPath = worldId
    ? studioWorldRoute(worldId)
    : PRODUCT_ROUTES.studioNewWorld;

  useEffect(() => {
    if (authStatus === "unauthenticated") {
      router.replace(`/login?returnTo=${encodeURIComponent(returnPath)}`);
      return;
    }
    if (authStatus !== "authenticated") return;
    if (!worldId) return;

    let active = true;
    void getWorldCreatorContext(worldId)
      .then((next) => {
        if (!active) return;
        setContext(next);
        setDefinition(worldToDefinition(next));
      })
      .catch((nextError) => {
        if (active) presentError(nextError);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [authStatus, returnPath, router, worldId]);

  function change<K extends keyof WorldDefinition>(
    key: K,
    value: WorldDefinition[K],
  ) {
    setDefinition((current) => ({ ...current, [key]: value }));
    setNotice(null);
  }

  async function persist() {
    const editable = { name: definition.name, tagline: definition.tagline, setting_description: definition.setting_description, daily_life_description: definition.daily_life_description, genre_tags: definition.genre_tags, tone_tags: definition.tone_tags, places: definition.places, roles: definition.roles, additional_generation_guidance: definition.additional_generation_guidance };
    const saved = context
      ? await updateWorld(context.world.id, {
          ...editable,
          row_version: context.world.row_version,
        })
      : await createWorld({
          ...definition,
          timezone: environment?.timezone ?? "UTC",
          language: environment?.memory_search_locale ?? "en",
          idempotency_key: idempotencyKey.current,
        });
    setContext(saved);
    setDefinition(worldToDefinition(saved));
    if (!worldId) {
      permitCommittedNavigation();
      router.replace(studioWorldRoute(saved.world.id));
    }
    return saved;
  }

  async function handleSave() {
    setPending("save");
    setError(null);
    setNotice(null);
    try {
      await persist();
      setNotice(uiText("World 초안을 저장했어요."));
    } catch (nextError) {
      setError(uiText(errorMessage(nextError)));
    } finally {
      setPending(null);
    }
  }

  async function handleValidate() {
    if (!context) {
      setError(uiText("먼저 World 초안을 저장해 주세요."));
      return;
    }
    setPending("validate");
    setError(null);
    try {
      const readiness = await validateWorld(context.world.id);
      setContext((current) => (current ? { ...current, readiness } : current));
      setNotice(
        readiness.ready_for_publish
          ? uiText("저장한 내용은 사용할 준비가 되었어요.")
          : uiText("사용 시작 전에 아래 항목을 확인해주세요."),
      );
    } catch (nextError) {
      setError(uiText(errorMessage(nextError)));
    } finally {
      setPending(null);
    }
  }

  async function handlePublish() {
    setPending("publish");
    setError(null);
    setNotice(null);
    try {
      const saved = await persist();
      const published = await publishWorld(
        saved.world.id,
        saved.world.row_version,
      );
      setContext(published);
      setDefinition(worldToDefinition(published));
      setNotice(uiText("World를 사용할 수 있어요."));
    } catch (nextError) {
      setError(uiText(errorMessage(nextError)));
    } finally {
      setPending(null);
    }
  }

  function cancelImage() {
    if (imageBusy.current) return;
    imageEpoch.current++; imageRef.current?.bitmap.close(); imageRef.current = null;
    setImageDraft(null); setCropError(null);
  }
  async function selectImage(file: File | null, kind: "icon" | "banner") {
    if (!file || !context || pending || imageBusy.current) return;
    if (file.size > PROFILE_MEDIA_MAX_BYTES) { setError(uiText("이미지는 5MB 이하로 선택해주세요.")); return; }
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) { setError(uiText("PNG, JPG, WebP 이미지를 선택해주세요.")); return; }
    const epoch = ++imageEpoch.current, scope = captureAuthRequestScope();
    imageBusy.current = true; setPending("image-decode"); setError(null);
    try {
      const bitmap = await createImageBitmap(file);
      if (epoch !== imageEpoch.current || !isCurrentAuthRequestScope(scope)) { bitmap.close(); return; }
      imageRef.current?.bitmap.close();
      const next = { bitmap, kind }; imageRef.current = next; setImageDraft(next);
      setCrop(INITIAL_CROP); setCropError(null); setImageConflict(false);
    } catch { if (epoch === imageEpoch.current) setError(uiText("이미지를 읽지 못했어요. 다른 이미지를 선택해주세요.")); }
    finally { if (epoch === imageEpoch.current) { imageBusy.current = false; setPending(null); } }
  }
  async function applyImage() {
    if (!imageDraft || !context || pending || imageBusy.current) return;
    const epoch = imageEpoch.current, scope = captureAuthRequestScope(), controller = new AbortController();
    const current = () => epoch === imageEpoch.current && !controller.signal.aborted && isCurrentAuthRequestScope(scope);
    imageRequest.current = controller; imageBusy.current = true; setPending("banner"); setCropError(null);
    try {
      const kind = imageDraft.kind;
      const blob = await cropToBlob(imageDraft.bitmap, imageDraft.bitmap, kind === "icon" ? { width: 768, height: 768 } : { width: 1024, height: 384 }, crop);
      const data_base64 = await blobToBase64(blob);
      if (!current()) return;
      const next = await uploadWorldBanner(context.world.id, { row_version: context.world.row_version, content_type: blob.type, data_base64, alt_text: kind === "icon" ? uiText("{{value0}} 아이콘", { value0: definition.name || "World" }) : uiText("{{value0}} 배너", { value0: definition.name || "World" }) }, kind, controller.signal);
      if (!current()) return;
      setContext(next); imageRef.current?.bitmap.close(); imageRef.current = null; setImageDraft(null);
      setNotice(uiText("이미지를 저장했어요."));
    } catch (reason) { if (current()) { setCropError(uiText(errorMessage(reason))); setImageConflict(reason instanceof WorldApiError && reason.status === 409); } }
    finally { if (current()) { imageBusy.current = false; setPending(null); } }
  }

  async function refreshImageVersion() {
    if (!context || pending || imageBusy.current) return;
    const epoch = imageEpoch.current, scope = captureAuthRequestScope(), id = context.world.id;
    const controller = new AbortController(); imageRequest.current = controller;
    const current = () => epoch === imageEpoch.current && !controller.signal.aborted && isCurrentAuthRequestScope(scope);
    imageBusy.current = true; setPending("image-refresh");
    try {
      const next = await getWorldCreatorContext(id, controller.signal);
      if (!current() || next.world.id !== id) return;
      setContext(next); setImageConflict(false); setCropError(null);
    } catch (reason) { if (current()) setCropError(uiText(errorMessage(reason))); }
    finally { if (current()) { imageBusy.current = false; setPending(null); } }
  }

  async function handleRemoveBanner(kind: "banner" | "icon" = "banner") {
    if (!context || pending || imageBusy.current) return;
    const epoch = imageEpoch.current, scope = captureAuthRequestScope(), controller = new AbortController();
    const current = () => epoch === imageEpoch.current && !controller.signal.aborted && isCurrentAuthRequestScope(scope);
    imageRequest.current = controller; imageBusy.current = true;
    setPending("banner");
    setError(null);
    try {
      const next = await removeWorldBanner(
        context.world.id,
        context.world.row_version,
        kind,
        controller.signal,
      );
      if (!current()) return;
      setContext(next);
      setNotice(uiText("이미지를 제거했어요."));
    } catch (nextError) {
      if (current()) setError(uiText(errorMessage(nextError)));
    } finally {
      if (current()) { setPending(null); imageBusy.current = false; }
    }
  }

  const issueByField = useMemo(
    () =>
      new Map(
        (context?.readiness.issues ?? [])
          .filter((issue) => issue.field)
          .map((issue) => [issue.field as string, issue]),
      ),
    [context],
  );

  if (authStatus === "checking" || loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center text-[#667085]">
        <Loader2 className="mr-3 size-5 animate-spin" /> {uiText("World를 불러오는 중입니다.")}</div>
    );
  }

  if (deletionReceipt) return <WorldDeletionProgress initial={deletionReceipt} />;
  if(scopeClosed)return <p role="status">{uiText("이 World는 더 이상 사용할 수 없어요.")}</p>;
  return (
    <div
      className="min-h-screen bg-[#f7f8fa] px-4 py-8 md:px-8"
      data-product-content="creator-studio-world"
    >
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="overflow-hidden rounded-[28px] border border-[#e1e5eb] bg-white shadow-[var(--shadow-summary)]">
          {worldBannerUrl ? (
            <div className="relative h-44 bg-[#eef1f5]">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={worldBannerUrl}
                alt={context?.world.banner_alt_text || uiText("{{value0}} 배너", {value0: definition.name})}
                className="size-full object-cover"
              />
            </div>
          ) : null}
          <div className="p-6 md:p-8">
            <p className="text-sm font-extrabold uppercase tracking-[0.14em] text-[#ff6b6b]">
              {uiText(context ? "World 편집" : "새 World 만들기")}
            </p>
            <div className="mt-2 flex flex-col justify-between gap-4 md:flex-row md:items-start">
              <div>
                <h1 className="text-3xl font-black text-[#101828]">
                  {context ? definition.name || uiText("이름 없는 World") : uiText("새 World 만들기")}
                </h1>
                <p className="mt-3 max-w-3xl text-sm font-medium leading-6 text-[#667085]">
                  {uiText("이 World의 배경과 일상을 작성해요. 캐릭터는 이 설정을 참고해 하루를 보내요.")}</p>
              </div>
              {context ? (
                <div className="flex flex-wrap gap-2 text-xs font-extrabold">
                  <Badge>{uiText(context.world.status === "published" ? "사용 가능" : context.world.status === "archived" ? "보관됨" : "작성 중")}</Badge>
                </div>
              ) : null}
            </div>
          </div>
        </header>

        {error ? <Notice tone="error" text={error} /> : null}
        {notice ? <Notice tone="success" text={notice} /> : null}

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.5fr)_340px]">
          <section className="space-y-6">
            <Panel title={uiText("필수 세계관 설정")} description={uiText("World의 배경과 평소 일상을 적어주세요. 캐릭터가 이곳에서 어떻게 지낼지 정하는 데 참고해요.")}>
              <div className="grid gap-5 md:grid-cols-2">
                <Field label={uiText("World 이름")} issue={issueByField.get("name")} counter={`${definition.name.length}/120`}>
                  <input className={inputClass} value={definition.name} maxLength={120} onChange={(event) => change("name", event.target.value)} placeholder={uiText("예: 비늘항구의 밤")} />
                </Field>
                <Field label={uiText("한 줄 소개")} issue={issueByField.get("tagline")} counter={`${definition.tagline.length}/160`}>
                  <input className={inputClass} value={definition.tagline} maxLength={160} onChange={(event) => change("tagline", event.target.value)} placeholder={uiText("어떤 World인지 한 문장으로 소개해주세요.")} />
                </Field>
              </div>
              <Field label={uiText("세계관 설명")} issue={issueByField.get("setting_description")} counter={`${definition.setting_description.length}/4000`} hint={uiText("시대와 장소, 기술이나 마법, 사회 분위기를 설명해주세요.")}>
                <textarea className={largeTextareaClass} value={definition.setting_description} maxLength={4000} onChange={(event) => change("setting_description", event.target.value)} />
              </Field>
              <Field label={uiText("이 세계의 일상")} issue={issueByField.get("daily_life_description")} counter={`${definition.daily_life_description.length}/3000`} hint={uiText("사람들이 주로 어디에서 무엇을 하며 지내는지 적어주세요.")}>
                <textarea className={largeTextareaClass} value={definition.daily_life_description} maxLength={3000} onChange={(event) => change("daily_life_description", event.target.value)} />
              </Field>
              <div className="grid gap-5 md:grid-cols-2">
                <Field label={uiText("장르 태그")} issue={issueByField.get("genre_tags")} hint={uiText("쉼표로 구분해 1~5개 입력해주세요.")}>
                  <CommaListInput values={definition.genre_tags} maxItems={5} onChange={(values) => change("genre_tags", values)} placeholder={uiText("판타지, 항구도시")} />
                </Field>
                <Field label={uiText("분위기 태그")} issue={issueByField.get("tone_tags")} hint={uiText("쉼표로 구분해 1~5개 입력해주세요.")}>
                  <CommaListInput values={definition.tone_tags} maxItems={5} onChange={(values) => change("tone_tags", values)} placeholder={uiText("따뜻함, 모험적")} />
                </Field>
              </div>
            </Panel>

            <Panel title={uiText("시간대와 언어")} description={uiText("하루의 시간대를 나누고 기억을 저장·검색할 때 사용하는 기준이에요.")}>
              <div className="grid gap-5 md:grid-cols-2">
                <p>{uiText("사용자 시간대")}: {environmentReady && !environmentError && environment ? environment.timezone : uiText(environmentError ? "설정을 불러오지 못했어요. 저장 시 기본값을 사용해요." : "설정 확인 중 · 저장 시 기본값을 사용해요.")}</p>
                <p>{uiText("기억·검색 언어")}: {environmentReady && !environmentError && environment ? uiText(environment.memory_search_locale === "ko" ? "한국어" : "영어") : uiText("기본값: 영어")}</p>
              </div>
            </Panel>

            <OptionalSettings definition={definition} change={change} />
            {context && <details><summary>{uiText("이전 상세 설정 보기 (고급)")}</summary><pre className="overflow-auto whitespace-pre-wrap">{JSON.stringify({ visibility: context.world.visibility, join_policy: context.world.join_policy, daypart_profiles: context.world.daypart_profiles, rules: context.world.rules, glossary: context.world.glossary }, null, 2)}</pre></details>}
            {context && <Panel title={uiText("캐릭터 추가")} description={uiText("World를 저장했어요. 지금 캐릭터를 추가하거나 나중에 이어갈 수 있어요.")}>
              <button type="button" className={secondaryButtonClass} onClick={() => router.push(`/agents/new?worldId=${encodeURIComponent(context.world.id)}&returnTo=${encodeURIComponent(studioWorldRoute(context.world.id))}`)}>{uiText("직접 만들기 · 캐릭터 카드 가져오기")}</button>
              <button type="button" className={secondaryButtonClass} onClick={() => router.push(PRODUCT_ROUTES.studio)}>{uiText("나중에 하기")}</button>
            </Panel>}

            {context ? (
              <>
                {renderWorldTools(context.world.id, definition.roles)}
                <div id="owner-controlled-identity" className="scroll-mt-6">
                  {renderMyProfile(context.world.id)}
                </div>
              </>
            ) : null}

            <Panel title={uiText("World 아이콘·배너 (선택)")} description={uiText("아이콘과 배너를 고르고, 기기 홈과 World 화면에 표시되는 모습을 확인해요. 나중에도 바꿀 수 있어요.")}>
              <input ref={iconInput} type="file" accept="image/png,image/jpeg,image/webp" hidden aria-label={uiText("아이콘 업로드")} disabled={!context || pending !== null} onChange={(event) => { void selectImage(event.target.files?.[0] ?? null, "icon"); event.target.value = ""; }} />
              <input ref={bannerInput} type="file" accept="image/png,image/jpeg,image/webp" hidden aria-label={uiText("배너 업로드")} disabled={!context || pending !== null} onChange={(event) => { void selectImage(event.target.files?.[0] ?? null, "banner"); event.target.value = ""; }} />
              {!context ? <p className="text-xs text-text-muted">{uiText("이미지를 고르려면 먼저 초안을 저장해주세요.")}</p> : null}
              <p className="text-xs text-text-muted">{uiText("이미지는 적용하면 저장돼요. 이름과 소개는 초안 저장으로 저장해요.")}</p>
              <div className="grid min-w-0 grid-cols-1 gap-6" data-world-image-previews>
                <div><h3 className="mb-4 font-bold">{uiText("기기 홈 미리보기")}</h3>
                  <div role="list"><AppIcon label={definition.name.trim()} visual={<AppIconVisual source={worldIconUrl} name={definition.name.trim()} />} visualBackground={appIconBackground(context?.world.id)} /></div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Button type="button" variant="secondary" disabled={!context || pending !== null} onClick={() => iconInput.current?.click()}>{uiText("아이콘 업로드")}</Button>
                    {context?.world.icon_media_id && <Button type="button" variant="danger" disabled={pending !== null} onClick={() => void handleRemoveBanner("icon")}>{uiText("아이콘 제거")}</Button>}
                  </div>
                </div>
                <div className="min-w-0 overflow-hidden rounded-2xl border border-border-subtle">
                  <h3 className="p-4 font-bold">{uiText("World 화면 미리보기")}</h3>
                  <div className="relative">
                    <WorldBanner source={context?.world.banner_media_id ?? null} alt={context?.world.banner_alt_text || uiText("World 배너")} />
                    <div className="absolute right-3 top-3 flex flex-wrap justify-end gap-2">
                      <Button type="button" variant="secondary" disabled={!context || pending !== null} onClick={() => bannerInput.current?.click()}><ImagePlus className="mr-2 size-4" aria-hidden="true" />{uiText("배너 업로드")}</Button>
                      {context?.world.banner_media_id && <Button type="button" variant="danger" disabled={pending !== null} onClick={() => void handleRemoveBanner()}>{uiText("배너 제거")}</Button>}
                    </div>
                  </div>
                  {(definition.name.trim() || definition.genre_tags.length || definition.tone_tags.length || definition.tagline.trim()) ? <div className="space-y-3 p-4">
                    {definition.name.trim() ? <h4 className="text-xl font-bold break-words">{definition.name.trim()}</h4> : null}
                    {definition.genre_tags.length || definition.tone_tags.length ? <div className="flex flex-wrap gap-2">{[...definition.genre_tags, ...definition.tone_tags].map((tag, index) => <Badge key={`${index}:${tag}`}>{tag}</Badge>)}</div> : null}
                    {definition.tagline.trim() ? <p className="break-words">{definition.tagline.trim()}</p> : null}
                  </div> : null}
                </div>
              </div>
            </Panel>
          </section>

          <aside className="h-fit space-y-4 lg:sticky lg:top-6">
            <ReadinessCard context={context} dirty={dirty} />
            <div className="rounded-[28px] border border-[#e1e5eb] bg-white p-5 shadow-[var(--shadow-summary)]">
              <div className="grid gap-3">
                <button type="button" className={primaryButtonClass} disabled={pending !== null || definition.name.trim().length < 2} onClick={() => void handleSave()}>
                  {pending === "save" ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />} {uiText("초안 저장")}</button>
                <button type="button" className={secondaryButtonClass} disabled={!context || pending !== null} onClick={() => void handleValidate()}>
                  <ShieldCheck className="size-4" /> {uiText("사용 준비 확인")}</button>
                <button type="button" className={publishButtonClass} disabled={pending !== null || context?.world.status === "published"} onClick={() => void handlePublish()}>
                  {pending === "publish" ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />} {uiText("World 사용 시작")}</button>
                {context ? <WorldDeleteControl worldId={context.world.id} canDelete={pending === null && context.world.can_delete}
                  isDefaultSpace={context.world.is_default_space} renderExport={renderDeleteExport} onAccepted={receipt => { cancelImage(); setDeletionReceipt(receipt); }} /> : null}
              </div>
            </div>
          </aside>
        </div>
        {imageDraft ? <ImageCropDialog bitmap={imageDraft.bitmap} spec={imageDraft.kind === "icon" ? { width: 768, height: 768 } : { width: 1024, height: 384 }} crop={crop} busy={pending === "banner" || pending === "image-refresh"} error={cropError} disabled={imageConflict}
          recoveryAction={imageConflict ? <Button type="button" variant="secondary" disabled={pending !== null} onClick={() => void refreshImageVersion()}>{uiText("현재 이미지 상태 새로고침")}</Button> : undefined}
          labels={{ title: uiText(imageDraft.kind === "icon" ? "아이콘 자르기" : "배너 자르기"), close: uiText("닫기"), zoom: uiText("확대"), horizontal: uiText("가로 위치"), vertical: uiText("세로 위치"), cancel: uiText("취소"), apply: uiText("적용"), applying: uiText("이미지를 적용하는 중…") }}
          onCrop={setCrop} onApply={() => void applyImage()} onCancel={cancelImage} /> : null}

      </div>
    </div>
  );
}

function OptionalSettings({
  definition,
  change,
}: {
  definition: WorldDefinition;
  change: <K extends keyof WorldDefinition>(key: K, value: WorldDefinition[K]) => void;
}) {
  const uiText = useUiText("worlds");
  return (
    <Panel title={uiText("상세 설정 (선택)")} description={uiText("선택 항목이에요. 장소와 역할을 적으면 캐릭터의 일과를 만들 때 참고해요.")}>
      <div className="space-y-3">
        <OptionalSection title={uiText("장소")} count={definition.places.length} onAdd={() => change("places", [...definition.places, emptyPlace()])}>
          {definition.places.map((item, index) => (
            <PlaceEditor key={index} item={item} onChange={(next) => change("places", replaceAt(definition.places, index, next))} onRemove={() => change("places", removeAt(definition.places, index))} />
          ))}
        </OptionalSection>
        <OptionalSection title={uiText("역할·직업")} count={definition.roles.length} onAdd={() => change("roles", [...definition.roles, emptyRole()])}>
          {definition.roles.map((item, index) => (
            <RoleEditor key={index} item={item} onChange={(next) => change("roles", replaceAt(definition.roles, index, next))} onRemove={() => change("roles", removeAt(definition.roles, index))} />
          ))}
        </OptionalSection>
        <details className={detailsClass}>
          <summary className={summaryClass}>{uiText("일과 작성 안내")}</summary>
          <textarea className={`${textareaClass} mt-4`} value={definition.additional_generation_guidance} maxLength={1000} onChange={(event) => change("additional_generation_guidance", event.target.value)} placeholder={uiText("캐릭터가 일과를 만들 때 지켜야 할 조건을 적어주세요.")} />
        </details>
      </div>
    </Panel>
  );
}

function OptionalSection({ title, count, onAdd, children }: { title: string; count: number; onAdd: () => void; children: ReactNode }) {
  const uiText = useUiText("worlds");
  return (
    <details className={detailsClass}>
      <summary className={summaryClass}><span>{title} <span className="text-[#98a2b3]">{count}</span></span></summary>
      <div className="mt-4 space-y-4">
        {children}
        <button type="button" className={smallButtonClass} onClick={onAdd}><Plus className="size-4" /> {uiText("항목 추가")}</button>
      </div>
    </details>
  );
}

function PlaceEditor({ item, onChange, onRemove }: { item: WorldPlaceInput; onChange: (item: WorldPlaceInput) => void; onRemove: () => void }) {
  const uiText = useUiText("worlds");
  return <EditorCard onRemove={onRemove}><div className="grid gap-3 md:grid-cols-2"><MiniInput label="key" value={item.key} onChange={(value) => onChange({ ...item, key: value })} /><MiniInput label={uiText("이름")} value={item.name} onChange={(value) => onChange({ ...item, name: value })} /></div><MiniInput label={uiText("설명")} value={item.description} onChange={(value) => onChange({ ...item, description: value })} /><CommaListMiniInput label={uiText("이용 가능한 시간대 (쉼표)")} values={item.available_dayparts} maxItems={4} allowedValues={DAYPART_KEYS} onChange={(values) => onChange({ ...item, available_dayparts: values as WorldDaypart[] })} /><CommaListMiniInput label={uiText("접근 역할 key (쉼표)")} values={item.access_role_keys} maxItems={20} onChange={(values) => onChange({ ...item, access_role_keys: values })} /></EditorCard>;
}

function RoleEditor({ item, onChange, onRemove }: { item: WorldRoleInput; onChange: (item: WorldRoleInput) => void; onRemove: () => void }) {
  const uiText = useUiText("worlds");
  return <EditorCard onRemove={onRemove}><div className="grid gap-3 md:grid-cols-2"><MiniInput label="key" value={item.key} onChange={(value) => onChange({ ...item, key: value })} /><MiniInput label={uiText("이름")} value={item.name} onChange={(value) => onChange({ ...item, name: value })} /></div><MiniInput label={uiText("설명")} value={item.description} onChange={(value) => onChange({ ...item, description: value })} /><CommaListMiniInput label={uiText("책임 (쉼표)")} values={item.responsibilities} maxItems={12} onChange={(values) => onChange({ ...item, responsibilities: values })} /><CommaListMiniInput label={uiText("가능 활동 범위 (쉼표)")} values={item.allowed_activity_scope} maxItems={12} onChange={(values) => onChange({ ...item, allowed_activity_scope: values })} /><label className="flex items-center gap-2 text-xs font-bold text-[#475467]"><input type="checkbox" checked={item.autonomous_allowed} onChange={(event) => onChange({ ...item, autonomous_allowed: event.target.checked })} /> {uiText("자율활동 허용")}</label></EditorCard>;
}

function EditorCard({ onRemove, children }: { onRemove: () => void; children: ReactNode }) {
  const uiText = useUiText("worlds");
  return <div className="relative space-y-3 rounded-[18px] border border-[#e1e5eb] bg-white p-4"><button type="button" aria-label={uiText("항목 삭제")} className="absolute right-3 top-3 rounded-full p-1 text-[#98a2b3] hover:bg-[#fff0f0] hover:text-[#d92d20]" onClick={onRemove}><X className="size-4" /></button>{children}</div>;
}

function MiniInput({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="block text-xs font-bold text-[#475467]">{label}<input className={`${inputClass} mt-1`} value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}

function CommaListInput({ values, maxItems, allowedValues, onChange, placeholder }: { values: string[]; maxItems: number; allowedValues?: readonly string[]; onChange: (values: string[]) => void; placeholder?: string }) {
  return <input className={inputClass} defaultValue={values.join(", ")} placeholder={placeholder} onChange={(event) => onChange(parseCommaList(event.target.value, maxItems, allowedValues))} onBlur={(event) => { event.currentTarget.value = values.join(", "); }} />;
}

function CommaListMiniInput({ label, values, maxItems, allowedValues, onChange }: { label: string; values: string[]; maxItems: number; allowedValues?: readonly string[]; onChange: (values: string[]) => void }) {
  return <label className="block text-xs font-bold text-[#475467]">{label}<span className="mt-1 block"><CommaListInput values={values} maxItems={maxItems} allowedValues={allowedValues} onChange={onChange} /></span></label>;
}

function parseCommaList(value: string, maxItems: number, allowedValues?: readonly string[]) {
  const allowed = allowedValues ? new Set(allowedValues) : null;
  return splitList(value).filter((item) => !allowed || allowed.has(item)).slice(0, maxItems);
}

function ReadinessCard({ context, dirty }: { context: WorldCreatorContext | null; dirty: boolean }) {
  const uiText = useUiText("worlds");
  const readiness = context?.readiness;
  return (
    <div className="rounded-[28px] border border-[#e1e5eb] bg-white p-5 shadow-[var(--shadow-summary)]">
      <div className="flex items-center gap-3">
        {readiness?.ready_for_publish ? <CheckCircle2 className="size-6 text-[#12b76a]" /> : <AlertTriangle className="size-6 text-[#f79009]" />}
        <div><h2 className="font-black text-[#101828]">{uiText("사용 준비")}</h2><p className="text-xs font-extrabold text-[#667085]">{uiText(readiness?.ready_for_publish ? "저장한 내용은 사용 준비 완료" : "확인할 항목이 있어요")}</p></div>
      </div>
      {!context ? <p className="mt-4 text-sm font-medium leading-6 text-[#667085]">{uiText("이름을 입력해 초안을 저장한 뒤, 나머지 항목을 채워주세요.")}</p> : null}
      {dirty ? <p className="mt-4 text-sm" role="status">{uiText("아직 저장하지 않은 변경이 있어요. 사용 준비는 마지막으로 저장한 내용을 기준으로 확인해요.")}</p> : null}
      <IssueList issues={readiness?.issues ?? []} />
      {readiness ? <p className="mt-4 text-xs font-bold text-[#667085]">{uiText("선택 항목 {{count}}개 작성됨", {count: readiness.optional_setting_count})}</p> : null}
    </div>
  );
}

function IssueList({ issues }: { issues: WorldValidationIssue[] }) {
  const uiText = useUiText("worlds");
  if (!issues.length) return null;
  return <ul className="mt-4 space-y-2">{issues.map((issue) => <li key={`${issue.reason_code}-${issue.field}`} className="text-xs font-bold leading-5 text-[#b42318]">{uiText(REASON_LABELS[issue.reason_code] ?? "입력값과 형식을 확인해주세요.")}</li>)}</ul>;
}

function Field({ label, hint, counter, issue, children }: { label: string; hint?: string; counter?: string; issue?: WorldValidationIssue; children: ReactNode }) {
  const uiText = useUiText("worlds");
  return <label className="block"><span className="flex items-center justify-between gap-3 text-sm font-extrabold text-[#344054]"><span>{label}</span>{counter ? <span className="text-xs text-[#98a2b3]">{counter}</span> : null}</span>{hint ? <span className="mt-1 block text-xs font-medium leading-5 text-[#98a2b3]">{hint}</span> : null}<span className="mt-2 block">{children}</span>{issue ? <span className="mt-2 block text-xs font-bold text-[#b42318]">{uiText(REASON_LABELS[issue.reason_code] ?? "입력값과 형식을 확인해주세요.")}</span> : null}</label>;
}

function Panel({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return <section className="rounded-[28px] border border-[#e1e5eb] bg-white p-6 shadow-[var(--shadow-summary)] md:p-8"><h2 className="text-xl font-black text-[#101828]">{title}</h2><p className="mt-2 text-sm font-medium leading-6 text-[#667085]">{description}</p><div className="mt-6 space-y-5">{children}</div></section>;
}

function Notice({ tone, text }: { tone: "error" | "success"; text: string }) {
  return <div className={`flex items-start gap-3 rounded-[22px] border px-5 py-4 text-sm font-bold ${tone === "error" ? "border-[#ffd2d2] bg-[#fff5f5] text-[#b42318]" : "border-[#b7ebcd] bg-[#f0fff6] text-[#027a48]"}`}>{tone === "error" ? <AlertTriangle className="mt-0.5 size-5 shrink-0" /> : <CheckCircle2 className="mt-0.5 size-5 shrink-0" />}{text}</div>;
}

function Badge({ children }: { children: ReactNode }) {
  return <span className="rounded-full bg-[#f2f4f7] px-3 py-1.5 text-[#475467]">{children}</span>;
}

function replaceAt<T>(values: T[], index: number, value: T) { return values.map((item, itemIndex) => itemIndex === index ? value : item); }
function removeAt<T>(values: T[], index: number) { return values.filter((_, itemIndex) => itemIndex !== index); }
function emptyPlace(): WorldPlaceInput { return { key: "", name: "", description: "", available_dayparts: [], access_role_keys: [] }; }
function emptyRole(): WorldRoleInput { return { key: "", name: "", description: "", responsibilities: [], allowed_activity_scope: [], autonomous_allowed: true }; }
const inputClass = "h-12 w-full rounded-[16px] border border-[#dfe3e8] bg-white px-4 text-sm font-semibold text-[#101828] outline-none transition focus:border-[#ff6b6b] focus:ring-2 focus:ring-[#ffe2e2] disabled:bg-[#f2f4f7]";
const textareaClass = "min-h-24 w-full resize-y rounded-[18px] border border-[#dfe3e8] bg-white px-4 py-3 text-sm font-semibold leading-6 text-[#101828] outline-none transition focus:border-[#ff6b6b] focus:ring-2 focus:ring-[#ffe2e2]";
const largeTextareaClass = `${textareaClass} min-h-44`;
const primaryButtonClass = "inline-flex h-12 w-full items-center justify-center gap-2 rounded-full bg-[#101828] px-5 text-sm font-extrabold text-white transition hover:bg-[#344054] disabled:cursor-not-allowed disabled:opacity-50";
const secondaryButtonClass = "inline-flex h-11 items-center justify-center gap-2 rounded-full border border-[#d0d5dd] bg-white px-5 text-sm font-extrabold text-[#344054] transition hover:bg-[#f9fafb] disabled:cursor-not-allowed disabled:opacity-50";
const publishButtonClass = "inline-flex h-12 w-full items-center justify-center gap-2 rounded-full bg-[#ff6b6b] px-5 text-sm font-extrabold text-white transition hover:bg-[#ff5252] disabled:cursor-not-allowed disabled:opacity-50";

const smallButtonClass = "inline-flex h-9 items-center justify-center gap-1.5 rounded-full border border-[#d0d5dd] bg-white px-4 text-xs font-extrabold text-[#344054] transition hover:bg-[#f9fafb]";
const detailsClass = "rounded-[20px] border border-[#e1e5eb] bg-[#fbfcfd] p-4 open:bg-[#f8fafc]";
const summaryClass = "cursor-pointer list-none text-sm font-extrabold text-[#344054] marker:hidden";
