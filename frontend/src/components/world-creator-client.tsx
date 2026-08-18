"use client";

import {
  AlertTriangle,
  CheckCircle2,
  ImagePlus,
  Loader2,
  Plus,
  Save,
  Send,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import { PRODUCT_ROUTES, studioWorldRoute } from "@/shared/navigation/public";

import { useAuth } from "@/components/auth-provider";
import {
  createOwnerControlledIdentity,
  createWorld,
  getOwnerControlledIdentity,
  getWorldCreatorContext,
  publishWorld,
  removeWorldBanner,
  requestValidationFields,
  updateWorld,
  updateOwnerControlledIdentity,
  uploadWorldBanner,
  validateWorld,
  WorldApiError,
  type WorldCreatorContext,
  type OwnerControlledIdentityRead,
  type OwnerControlledProfileWrite,
  type WorldDaypart,
  type WorldDefinition,
  type WorldGlossaryTermInput,
  type WorldPlaceInput,
  type WorldRoleInput,
  type WorldRuleInput,
  type WorldValidationIssue,
} from "@/lib/worlds";

const DAYPARTS: { key: WorldDaypart; label: string; hours: string }[] = [
  { key: "dawn", label: "새벽", hours: "00:00~06:00" },
  { key: "morning", label: "오전", hours: "06:00~12:00" },
  { key: "afternoon", label: "오후", hours: "12:00~18:00" },
  { key: "evening", label: "저녁", hours: "18:00~24:00" },
];
const DAYPART_KEYS = DAYPARTS.map((entry) => entry.key);

const EMPTY_DEFINITION: WorldDefinition = {
  name: "",
  tagline: "",
  setting_description: "",
  daily_life_description: "",
  genre_tags: [],
  tone_tags: [],
  timezone: "Asia/Seoul",
  language: "ko",
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
  world_not_found: "World를 찾을 수 없거나 접근할 수 없습니다.",
  world_archived: "보관된 World는 변경할 수 없습니다.",
  membership_required: "이 World의 활성 멤버십이 필요합니다.",
  creator_role_required: "World owner 또는 editor 권한이 필요합니다.",
  world_definition_incomplete: "필수 세계관 설정을 먼저 완성해 주세요.",
  invalid_world_name: "World 이름은 2~120자로 작성해 주세요.",
  invalid_tagline: "한 줄 소개는 10~160자로 작성해 주세요.",
  invalid_setting_description: "세계관 설명은 200~4,000자로 작성해 주세요.",
  invalid_daily_life_description: "일상 설명은 150~3,000자로 작성해 주세요.",
  invalid_genre_tags: "장르 태그를 1~5개 입력해 주세요.",
  invalid_tone_tags: "분위기 태그를 1~5개 입력해 주세요.",
  invalid_timezone: "올바른 IANA timezone을 입력해 주세요.",
  invalid_language: "올바른 언어 코드를 입력해 주세요.",
  unsafe_banner_reference: "배너 이미지 형식이나 크기를 확인해 주세요.",
  row_version_conflict: "다른 변경이 먼저 저장됐습니다. 새로고침 후 다시 시도해 주세요.",
  request_validation_error: "입력값과 형식을 확인해 주세요.",
  local_owner_required: "이 설치의 Local Owner 연결이 필요합니다.",
  owner_world_required: "Local Owner가 소유한 World에서만 만들 수 있습니다.",
  owner_controlled_identity_exists: "이 World에는 이미 사용자 조종 앵무가 있습니다.",
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
    roles: world.roles.map(
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
      const fields = requestValidationFields(error.detail);
      return fields.length
        ? `입력값을 확인하세요: ${fields.join(", ")}`
        : REASON_LABELS.request_validation_error;
    }
    return REASON_LABELS[error.message] ?? error.message;
  }
  return error instanceof Error ? error.message : "요청을 처리하지 못했습니다.";
}

function newIdempotencyKey() {
  return `world-create-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function fileAsBase64(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result ?? "");
      resolve(result.includes(",") ? result.split(",", 2)[1] : result);
    };
    reader.onerror = () => reject(new Error("이미지를 읽지 못했습니다."));
    reader.readAsDataURL(file);
  });
}

export function WorldCreatorClient({ worldId }: { worldId?: string }) {
  const router = useRouter();
  const { status: authStatus } = useAuth();
  const idempotencyKey = useRef(newIdempotencyKey());
  const [context, setContext] = useState<WorldCreatorContext | null>(null);
  const [definition, setDefinition] = useState<WorldDefinition>(EMPTY_DEFINITION);
  const [loading, setLoading] = useState(Boolean(worldId));
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

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
        if (active) setError(errorMessage(nextError));
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
    const saved = context
      ? await updateWorld(context.world.id, {
          ...definition,
          row_version: context.world.row_version,
        })
      : await createWorld({
          ...definition,
          idempotency_key: idempotencyKey.current,
        });
    setContext(saved);
    setDefinition(worldToDefinition(saved));
    if (!worldId) {
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
      setNotice("World 초안을 저장했습니다.");
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(null);
    }
  }

  async function handleValidate() {
    if (!context) {
      setError("먼저 World 초안을 저장해 주세요.");
      return;
    }
    setPending("validate");
    setError(null);
    try {
      const readiness = await validateWorld(context.world.id);
      setContext((current) => (current ? { ...current, readiness } : current));
      setNotice(
        readiness.ready_for_publish
          ? "공개 준비 검증을 통과했습니다."
          : "아직 보완해야 할 필수 설정이 있습니다.",
      );
    } catch (nextError) {
      setError(errorMessage(nextError));
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
      setNotice("World를 공개했습니다.");
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(null);
    }
  }

  async function handleBanner(file: File | null) {
    if (!file || !context) return;
    setPending("banner");
    setError(null);
    try {
      const next = await uploadWorldBanner(context.world.id, {
        row_version: context.world.row_version,
        content_type: file.type,
        data_base64: await fileAsBase64(file),
        alt_text: `${definition.name || "World"} 배너`,
      });
      setContext(next);
      setNotice("배너를 저장했습니다. 배너 변경은 World 계약 hash를 바꾸지 않습니다.");
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(null);
    }
  }

  async function handleRemoveBanner() {
    if (!context) return;
    setPending("banner");
    setError(null);
    try {
      const next = await removeWorldBanner(
        context.world.id,
        context.world.row_version,
      );
      setContext(next);
      setNotice("배너를 제거했습니다.");
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(null);
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
        <Loader2 className="mr-3 size-5 animate-spin" /> World를 불러오는 중입니다.
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-[#f7f8fa] px-4 py-8 md:px-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="overflow-hidden rounded-[28px] border border-[#e1e5eb] bg-white shadow-sm">
          {context?.world.banner_media_id ? (
            <div className="relative h-44 bg-[#eef1f5]">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={context.world.banner_media_id}
                alt={context.world.banner_alt_text || `${definition.name} 배너`}
                className="size-full object-cover"
              />
            </div>
          ) : null}
          <div className="p-6 md:p-8">
            <p className="text-sm font-extrabold uppercase tracking-[0.14em] text-[#ff6b6b]">
              World Creator · P1
            </p>
            <div className="mt-2 flex flex-col justify-between gap-4 md:flex-row md:items-start">
              <div>
                <h1 className="text-3xl font-black text-[#101828]">
                  {context ? definition.name || "이름 없는 World" : "새 World 만들기"}
                </h1>
                <p className="mt-3 max-w-3xl text-sm font-medium leading-6 text-[#667085]">
                  세계관과 그 안의 일상을 작성합니다. P2에서 이 정의와 캐릭터 정체성을 결합해
                  캐릭터별 일과 40개를 생성하며, 이 화면에서는 AI를 호출하지 않습니다.
                </p>
              </div>
              {context ? (
                <div className="flex flex-wrap gap-2 text-xs font-extrabold">
                  <Badge>{context.world.status}</Badge>
                  <Badge>{context.readiness.quality_tier}</Badge>
                  <Badge>v{context.world.definition_version}</Badge>
                </div>
              ) : null}
            </div>
          </div>
        </header>

        {error ? <Notice tone="error" text={error} /> : null}
        {notice ? <Notice tone="success" text={notice} /> : null}

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.5fr)_340px]">
          <section className="space-y-6">
            <Panel title="필수 세계관 설정" description="어렵지 않지만, 이 정보만으로도 캐릭터의 World별 일과를 만들 수 있어야 합니다.">
              <div className="grid gap-5 md:grid-cols-2">
                <Field label="World 이름" issue={issueByField.get("name")} counter={`${definition.name.length}/120`}>
                  <input className={inputClass} value={definition.name} maxLength={120} onChange={(event) => change("name", event.target.value)} placeholder="예: 비늘항구의 밤" />
                </Field>
                <Field label="한 줄 소개" issue={issueByField.get("tagline")} counter={`${definition.tagline.length}/160`}>
                  <input className={inputClass} value={definition.tagline} maxLength={160} onChange={(event) => change("tagline", event.target.value)} placeholder="이 세계의 핵심 매력을 한 문장으로 설명해 주세요." />
                </Field>
              </div>
              <Field label="세계관 설명" issue={issueByField.get("setting_description")} counter={`${definition.setting_description.length}/4000`} hint="장소, 시대, 기술·마법 수준, 사회 분위기와 캐릭터가 마주할 환경을 설명해 주세요.">
                <textarea className={largeTextareaClass} value={definition.setting_description} maxLength={4000} onChange={(event) => change("setting_description", event.target.value)} />
              </Field>
              <Field label="이 세계의 일상" issue={issueByField.get("daily_life_description")} counter={`${definition.daily_life_description.length}/3000`} hint="주민이 언제 어디서 무엇을 하며 하루를 보내는지 적어 주세요.">
                <textarea className={largeTextareaClass} value={definition.daily_life_description} maxLength={3000} onChange={(event) => change("daily_life_description", event.target.value)} />
              </Field>
              <div className="grid gap-5 md:grid-cols-2">
                <Field label="장르 태그" issue={issueByField.get("genre_tags")} hint="쉼표로 구분 · 1~5개">
                  <CommaListInput values={definition.genre_tags} maxItems={5} onChange={(values) => change("genre_tags", values)} placeholder="판타지, 항구도시" />
                </Field>
                <Field label="분위기 태그" issue={issueByField.get("tone_tags")} hint="쉼표로 구분 · 1~5개">
                  <CommaListInput values={definition.tone_tags} maxItems={5} onChange={(values) => change("tone_tags", values)} placeholder="따뜻함, 모험적" />
                </Field>
              </div>
            </Panel>

            <Panel title="운영 기본값" description="시간대는 이 World의 새벽·오전·오후·저녁을 계산하는 기준입니다.">
              <div className="grid gap-5 md:grid-cols-2">
                <Field label="Timezone" issue={issueByField.get("timezone")}>
                  <input className={inputClass} value={definition.timezone} maxLength={64} onChange={(event) => change("timezone", event.target.value)} />
                </Field>
                <Field label="언어" issue={issueByField.get("language")}>
                  <input className={inputClass} value={definition.language} maxLength={16} onChange={(event) => change("language", event.target.value)} />
                </Field>
                <Field label="공개 범위">
                  <select className={inputClass} value={definition.visibility} onChange={(event) => change("visibility", event.target.value as WorldDefinition["visibility"])}>
                    <option value="private">private</option>
                    <option value="unlisted">unlisted</option>
                    <option value="public">public</option>
                  </select>
                </Field>
                <Field label="참여 정책">
                  <select className={inputClass} value={definition.join_policy} onChange={(event) => change("join_policy", event.target.value as WorldDefinition["join_policy"])}>
                    <option value="approval_required">approval required</option>
                    <option value="open">open</option>
                    <option value="invite_only">invite only</option>
                    <option value="private">private</option>
                  </select>
                </Field>
              </div>
            </Panel>

            <OptionalSettings definition={definition} change={change} />

            {context ? (
              <OwnerControlledIdentityPanel
                roles={definition.roles}
                worldId={context.world.id}
              />
            ) : null}

            <Panel title="배너 이미지 (선택)" description="초안을 저장한 뒤 업로드할 수 있습니다. 이미지 변경은 캐릭터 일과 생성 계약 hash를 바꾸지 않습니다.">
              <div className="flex flex-wrap items-center gap-3">
                <label className={secondaryButtonClass}>
                  {pending === "banner" ? <Loader2 className="size-4 animate-spin" /> : <ImagePlus className="size-4" />}
                  배너 선택
                  <input type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" disabled={!context || pending !== null} onChange={(event) => void handleBanner(event.target.files?.[0] ?? null)} />
                </label>
                {context?.world.banner_media_id ? (
                  <button type="button" className={dangerButtonClass} disabled={pending !== null} onClick={() => void handleRemoveBanner()}>
                    <Trash2 className="size-4" /> 배너 제거
                  </button>
                ) : null}
                {!context ? <span className="text-xs font-bold text-[#98a2b3]">초안을 먼저 저장해 주세요.</span> : null}
              </div>
            </Panel>
          </section>

          <aside className="h-fit space-y-4 lg:sticky lg:top-6">
            <ReadinessCard context={context} />
            <div className="rounded-[28px] border border-[#e1e5eb] bg-white p-5 shadow-sm">
              <div className="grid gap-3">
                <button type="button" className={primaryButtonClass} disabled={pending !== null || definition.name.trim().length < 2} onClick={() => void handleSave()}>
                  {pending === "save" ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />} 초안 저장
                </button>
                <button type="button" className={secondaryButtonClass} disabled={!context || pending !== null} onClick={() => void handleValidate()}>
                  <ShieldCheck className="size-4" /> 공개 준비 확인
                </button>
                <button type="button" className={publishButtonClass} disabled={pending !== null || context?.world.status === "published"} onClick={() => void handlePublish()}>
                  {pending === "publish" ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />} World 공개
                </button>
              </div>
              {context ? (
                <div className="mt-5 space-y-2 border-t border-[#eaecf0] pt-4 font-mono text-[10px] leading-5 text-[#667085]">
                  <p>row {context.world.row_version} · definition {context.world.definition_version}</p>
                  <p className="break-all">{context.world.contract_hash}</p>
                </div>
              ) : null}
            </div>
          </aside>
        </div>
      </div>
    </main>
  );
}

const EMPTY_OWNER_PROFILE: OwnerControlledProfileWrite = {
  display_name: "",
  avatar_url: "",
  intro: "",
  role_key: null,
  preferred_address: "",
  interests: [],
  background: "",
};

function OwnerControlledIdentityPanel({
  roles,
  worldId,
}: {
  roles: WorldRoleInput[];
  worldId: string;
}) {
  const [identity, setIdentity] = useState<OwnerControlledIdentityRead | null>(null);
  const [profile, setProfile] = useState<OwnerControlledProfileWrite>(
    EMPTY_OWNER_PROFILE,
  );
  const [interestsText, setInterestsText] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void getOwnerControlledIdentity(worldId)
      .then((next) => {
        if (!active) return;
        setIdentity(next);
        setProfile(next.profile);
        setInterestsText(next.profile.interests.join(", "));
      })
      .catch((reason: unknown) => {
        if (
          active &&
          reason instanceof WorldApiError &&
          reason.status !== 404
        ) {
          setMessage(errorMessage(reason));
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [worldId]);

  function patchProfile<K extends keyof OwnerControlledProfileWrite>(
    key: K,
    value: OwnerControlledProfileWrite[K],
  ) {
    setProfile((current) => ({ ...current, [key]: value }));
    setMessage(null);
  }

  async function saveIdentity() {
    setSaving(true);
    setMessage(null);
    const payload = {
      ...profile,
      interests: parseCommaList(interestsText, 12),
    };
    try {
      const next = identity
        ? await updateOwnerControlledIdentity(worldId, payload)
        : await createOwnerControlledIdentity(worldId, payload);
      setIdentity(next);
      setProfile(next.profile);
      setInterestsText(next.profile.interests.join(", "));
      setMessage(identity ? "사용자 조종 앵무를 수정했습니다." : "사용자 조종 앵무를 만들었습니다.");
    } catch (reason) {
      setMessage(errorMessage(reason));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Panel
      title="내가 조종하는 앵무"
      description="이 World에서 Local Owner가 직접 말하고 행동할 identity입니다. 자동 활동·BYOK·AI 호출은 연결되지 않습니다."
    >
      {loading ? (
        <p className="text-sm font-bold text-[#667085]">identity를 확인하는 중입니다.</p>
      ) : (
        <>
          {identity ? (
            <div className="flex flex-wrap gap-2 text-xs font-extrabold">
              <Badge>owner controlled</Badge>
              <Badge>자동 활동 OFF</Badge>
              <Badge>v{identity.version}</Badge>
            </div>
          ) : (
            <p className="rounded-[18px] bg-[#f2f4f7] px-4 py-3 text-sm font-bold text-[#475467]">
              아직 이 World에서 사용자가 조종할 앵무가 없습니다.
            </p>
          )}
          <div className="grid gap-5 md:grid-cols-2">
            <Field label="표시 이름" counter={`${profile.display_name.length}/80`}>
              <input className={inputClass} maxLength={80} value={profile.display_name} onChange={(event) => patchProfile("display_name", event.target.value)} placeholder="예: 진구의 앵무" />
            </Field>
            <Field label="World 역할">
              <select className={inputClass} value={profile.role_key ?? ""} onChange={(event) => patchProfile("role_key", event.target.value || null)}>
                <option value="">역할 없음</option>
                {roles.map((role) => <option key={role.key} value={role.key}>{role.name || role.key}</option>)}
              </select>
            </Field>
            <Field label="불리고 싶은 이름" counter={`${profile.preferred_address.length}/80`}>
              <input className={inputClass} maxLength={80} value={profile.preferred_address} onChange={(event) => patchProfile("preferred_address", event.target.value)} />
            </Field>
            <Field label="관심사" hint="쉼표로 구분 · 최대 12개">
              <input className={inputClass} value={interestsText} onChange={(event) => setInterestsText(event.target.value)} placeholder="마법약, 친구, 산책" />
            </Field>
          </div>
          <Field label="한 줄 소개" counter={`${profile.intro.length}/280`}>
            <textarea className={textareaClass} maxLength={280} value={profile.intro} onChange={(event) => patchProfile("intro", event.target.value)} />
          </Field>
          <Field label="World 안의 배경" counter={`${profile.background.length}/500`}>
            <textarea className={textareaClass} maxLength={500} value={profile.background} onChange={(event) => patchProfile("background", event.target.value)} />
          </Field>
          <Field label="아바타 URL" hint="필수 · http 또는 https 이미지 주소">
            <input className={inputClass} maxLength={500} value={profile.avatar_url} onChange={(event) => patchProfile("avatar_url", event.target.value)} />
          </Field>
          {message ? <p className="text-sm font-bold text-[#475467]">{message}</p> : null}
          <button type="button" className={secondaryButtonClass} disabled={saving || !profile.display_name.trim() || !profile.avatar_url.trim() || !profile.intro.trim()} onClick={() => void saveIdentity()}>
            {saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
            {identity ? "조종 앵무 수정" : "조종 앵무 만들기"}
          </button>
        </>
      )}
    </Panel>
  );
}

function OptionalSettings({
  definition,
  change,
}: {
  definition: WorldDefinition;
  change: <K extends keyof WorldDefinition>(key: K, value: WorldDefinition[K]) => void;
}) {
  return (
    <Panel title="상세 설정 (선택)" description="비워도 공개할 수 있습니다. 작성할수록 P2가 더 구체적인 캐릭터 일과를 만들 수 있습니다.">
      <div className="space-y-3">
        <OptionalSection title="장소" count={definition.places.length} onAdd={() => change("places", [...definition.places, emptyPlace()])}>
          {definition.places.map((item, index) => (
            <PlaceEditor key={index} item={item} onChange={(next) => change("places", replaceAt(definition.places, index, next))} onRemove={() => change("places", removeAt(definition.places, index))} />
          ))}
        </OptionalSection>
        <OptionalSection title="역할·직업" count={definition.roles.length} onAdd={() => change("roles", [...definition.roles, emptyRole()])}>
          {definition.roles.map((item, index) => (
            <RoleEditor key={index} item={item} onChange={(next) => change("roles", replaceAt(definition.roles, index, next))} onRemove={() => change("roles", removeAt(definition.roles, index))} />
          ))}
        </OptionalSection>
        <OptionalSection title="4개 시간대 환경" count={definition.daypart_profiles.length} onAdd={() => {
          const missing = DAYPARTS.find((entry) => !definition.daypart_profiles.some((item) => item.daypart === entry.key));
          if (missing) change("daypart_profiles", [...definition.daypart_profiles, { daypart: missing.key, description: "", available_features: [], restricted_features: [] }]);
        }}>
          {definition.daypart_profiles.map((item, index) => (
            <DaypartEditor key={item.daypart} item={item} onChange={(next) => change("daypart_profiles", replaceAt(definition.daypart_profiles, index, next))} onRemove={() => change("daypart_profiles", removeAt(definition.daypart_profiles, index))} />
          ))}
        </OptionalSection>
        <OptionalSection title="허용·금지 규칙" count={definition.rules.length} onAdd={() => change("rules", [...definition.rules, emptyRule()])}>
          {definition.rules.map((item, index) => (
            <RuleEditor key={index} item={item} onChange={(next) => change("rules", replaceAt(definition.rules, index, next))} onRemove={() => change("rules", removeAt(definition.rules, index))} />
          ))}
        </OptionalSection>
        <OptionalSection title="고유 용어" count={definition.glossary.length} onAdd={() => change("glossary", [...definition.glossary, emptyGlossary()])}>
          {definition.glossary.map((item, index) => (
            <GlossaryEditor key={index} item={item} onChange={(next) => change("glossary", replaceAt(definition.glossary, index, next))} onRemove={() => change("glossary", removeAt(definition.glossary, index))} />
          ))}
        </OptionalSection>
        <details className={detailsClass}>
          <summary className={summaryClass}>추가 생성 지침</summary>
          <textarea className={`${textareaClass} mt-4`} value={definition.additional_generation_guidance} maxLength={1000} onChange={(event) => change("additional_generation_guidance", event.target.value)} placeholder="일과 생성 시 특별히 지켜야 할 세계관 지침" />
        </details>
      </div>
    </Panel>
  );
}

function OptionalSection({ title, count, onAdd, children }: { title: string; count: number; onAdd: () => void; children: ReactNode }) {
  return (
    <details className={detailsClass}>
      <summary className={summaryClass}><span>{title} <span className="text-[#98a2b3]">{count}</span></span></summary>
      <div className="mt-4 space-y-4">
        {children}
        <button type="button" className={smallButtonClass} onClick={onAdd}><Plus className="size-4" /> 항목 추가</button>
      </div>
    </details>
  );
}

function PlaceEditor({ item, onChange, onRemove }: { item: WorldPlaceInput; onChange: (item: WorldPlaceInput) => void; onRemove: () => void }) {
  return <EditorCard onRemove={onRemove}><div className="grid gap-3 md:grid-cols-2"><MiniInput label="key" value={item.key} onChange={(value) => onChange({ ...item, key: value })} /><MiniInput label="이름" value={item.name} onChange={(value) => onChange({ ...item, name: value })} /></div><MiniInput label="설명" value={item.description} onChange={(value) => onChange({ ...item, description: value })} /><CommaListMiniInput label="이용 가능한 시간대 (쉼표)" values={item.available_dayparts} maxItems={4} allowedValues={DAYPART_KEYS} onChange={(values) => onChange({ ...item, available_dayparts: values as WorldDaypart[] })} /><CommaListMiniInput label="접근 역할 key (쉼표)" values={item.access_role_keys} maxItems={20} onChange={(values) => onChange({ ...item, access_role_keys: values })} /></EditorCard>;
}

function RoleEditor({ item, onChange, onRemove }: { item: WorldRoleInput; onChange: (item: WorldRoleInput) => void; onRemove: () => void }) {
  return <EditorCard onRemove={onRemove}><div className="grid gap-3 md:grid-cols-2"><MiniInput label="key" value={item.key} onChange={(value) => onChange({ ...item, key: value })} /><MiniInput label="이름" value={item.name} onChange={(value) => onChange({ ...item, name: value })} /></div><MiniInput label="설명" value={item.description} onChange={(value) => onChange({ ...item, description: value })} /><CommaListMiniInput label="책임 (쉼표)" values={item.responsibilities} maxItems={12} onChange={(values) => onChange({ ...item, responsibilities: values })} /><CommaListMiniInput label="가능 활동 범위 (쉼표)" values={item.allowed_activity_scope} maxItems={12} onChange={(values) => onChange({ ...item, allowed_activity_scope: values })} /><label className="flex items-center gap-2 text-xs font-bold text-[#475467]"><input type="checkbox" checked={item.autonomous_allowed} onChange={(event) => onChange({ ...item, autonomous_allowed: event.target.checked })} /> 자율활동 허용</label></EditorCard>;
}

function DaypartEditor({ item, onChange, onRemove }: { item: WorldDefinition["daypart_profiles"][number]; onChange: (item: WorldDefinition["daypart_profiles"][number]) => void; onRemove: () => void }) {
  return <EditorCard onRemove={onRemove}><select className={inputClass} value={item.daypart} onChange={(event) => onChange({ ...item, daypart: event.target.value as WorldDaypart })}>{DAYPARTS.map((entry) => <option key={entry.key} value={entry.key}>{entry.label} · {entry.hours}</option>)}</select><MiniInput label="환경 설명" value={item.description} onChange={(value) => onChange({ ...item, description: value })} /><CommaListMiniInput label="가능 요소 (쉼표)" values={item.available_features} maxItems={12} onChange={(values) => onChange({ ...item, available_features: values })} /><CommaListMiniInput label="제한 요소 (쉼표)" values={item.restricted_features} maxItems={12} onChange={(values) => onChange({ ...item, restricted_features: values })} /></EditorCard>;
}

function RuleEditor({ item, onChange, onRemove }: { item: WorldRuleInput; onChange: (item: WorldRuleInput) => void; onRemove: () => void }) {
  return <EditorCard onRemove={onRemove}><div className="grid gap-3 md:grid-cols-2"><MiniInput label="key" value={item.key} onChange={(value) => onChange({ ...item, key: value })} /><label className="text-xs font-bold text-[#475467]">종류<select className={`${inputClass} mt-1`} value={item.rule_kind} onChange={(event) => onChange({ ...item, rule_kind: event.target.value as "allow" | "forbid" })}><option value="allow">allow</option><option value="forbid">forbid</option></select></label></div><MiniInput label="설명" value={item.description} onChange={(value) => onChange({ ...item, description: value })} /></EditorCard>;
}

function GlossaryEditor({ item, onChange, onRemove }: { item: WorldGlossaryTermInput; onChange: (item: WorldGlossaryTermInput) => void; onRemove: () => void }) {
  return <EditorCard onRemove={onRemove}><div className="grid gap-3 md:grid-cols-2"><MiniInput label="key" value={item.key} onChange={(value) => onChange({ ...item, key: value })} /><MiniInput label="용어" value={item.term} onChange={(value) => onChange({ ...item, term: value })} /></div><MiniInput label="의미" value={item.meaning} onChange={(value) => onChange({ ...item, meaning: value })} /></EditorCard>;
}

function EditorCard({ onRemove, children }: { onRemove: () => void; children: ReactNode }) {
  return <div className="relative space-y-3 rounded-[18px] border border-[#e1e5eb] bg-white p-4"><button type="button" aria-label="항목 삭제" className="absolute right-3 top-3 rounded-full p-1 text-[#98a2b3] hover:bg-[#fff0f0] hover:text-[#d92d20]" onClick={onRemove}><X className="size-4" /></button>{children}</div>;
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

function ReadinessCard({ context }: { context: WorldCreatorContext | null }) {
  const readiness = context?.readiness;
  return (
    <div className="rounded-[28px] border border-[#e1e5eb] bg-white p-5 shadow-sm">
      <div className="flex items-center gap-3">
        {readiness?.ready_for_publish ? <CheckCircle2 className="size-6 text-[#12b76a]" /> : <AlertTriangle className="size-6 text-[#f79009]" />}
        <div><h2 className="font-black text-[#101828]">공개 준비</h2><p className="text-xs font-extrabold text-[#667085]">{readiness?.ready_for_publish ? "READY" : "DRAFT"}</p></div>
      </div>
      {!context ? <p className="mt-4 text-sm font-medium leading-6 text-[#667085]">이름만으로 초안을 저장할 수 있습니다. 저장 후 필수 설정을 검증합니다.</p> : null}
      <IssueList issues={readiness?.issues ?? []} />
      {readiness ? <p className="mt-4 text-xs font-bold text-[#667085]">선택 설정 {readiness.optional_setting_count}개 그룹 · {readiness.quality_tier}</p> : null}
    </div>
  );
}

function IssueList({ issues }: { issues: WorldValidationIssue[] }) {
  if (!issues.length) return null;
  return <ul className="mt-4 space-y-2">{issues.map((issue) => <li key={`${issue.reason_code}-${issue.field}`} className="text-xs font-bold leading-5 text-[#b42318]">{REASON_LABELS[issue.reason_code] ?? issue.message}</li>)}</ul>;
}

function Field({ label, hint, counter, issue, children }: { label: string; hint?: string; counter?: string; issue?: WorldValidationIssue; children: ReactNode }) {
  return <label className="block"><span className="flex items-center justify-between gap-3 text-sm font-extrabold text-[#344054]"><span>{label}</span>{counter ? <span className="text-xs text-[#98a2b3]">{counter}</span> : null}</span>{hint ? <span className="mt-1 block text-xs font-medium leading-5 text-[#98a2b3]">{hint}</span> : null}<span className="mt-2 block">{children}</span>{issue ? <span className="mt-2 block text-xs font-bold text-[#b42318]">{REASON_LABELS[issue.reason_code] ?? issue.message}</span> : null}</label>;
}

function Panel({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return <section className="rounded-[28px] border border-[#e1e5eb] bg-white p-6 shadow-sm md:p-8"><h2 className="text-xl font-black text-[#101828]">{title}</h2><p className="mt-2 text-sm font-medium leading-6 text-[#667085]">{description}</p><div className="mt-6 space-y-5">{children}</div></section>;
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
function emptyRule(): WorldRuleInput { return { key: "", rule_kind: "forbid", description: "" }; }
function emptyGlossary(): WorldGlossaryTermInput { return { key: "", term: "", meaning: "" }; }

const inputClass = "h-12 w-full rounded-[16px] border border-[#dfe3e8] bg-white px-4 text-sm font-semibold text-[#101828] outline-none transition focus:border-[#ff6b6b] focus:ring-2 focus:ring-[#ffe2e2] disabled:bg-[#f2f4f7]";
const textareaClass = "min-h-24 w-full resize-y rounded-[18px] border border-[#dfe3e8] bg-white px-4 py-3 text-sm font-semibold leading-6 text-[#101828] outline-none transition focus:border-[#ff6b6b] focus:ring-2 focus:ring-[#ffe2e2]";
const largeTextareaClass = `${textareaClass} min-h-44`;
const primaryButtonClass = "inline-flex h-12 w-full items-center justify-center gap-2 rounded-full bg-[#101828] px-5 text-sm font-extrabold text-white transition hover:bg-[#344054] disabled:cursor-not-allowed disabled:opacity-50";
const secondaryButtonClass = "inline-flex h-11 items-center justify-center gap-2 rounded-full border border-[#d0d5dd] bg-white px-5 text-sm font-extrabold text-[#344054] transition hover:bg-[#f9fafb] disabled:cursor-not-allowed disabled:opacity-50";
const publishButtonClass = "inline-flex h-12 w-full items-center justify-center gap-2 rounded-full bg-[#ff6b6b] px-5 text-sm font-extrabold text-white transition hover:bg-[#ff5252] disabled:cursor-not-allowed disabled:opacity-50";
const dangerButtonClass = "inline-flex h-11 items-center justify-center gap-2 rounded-full border border-[#fda29b] bg-white px-5 text-sm font-extrabold text-[#b42318] transition hover:bg-[#fff5f5] disabled:opacity-50";
const smallButtonClass = "inline-flex h-9 items-center justify-center gap-1.5 rounded-full border border-[#d0d5dd] bg-white px-4 text-xs font-extrabold text-[#344054] transition hover:bg-[#f9fafb]";
const detailsClass = "rounded-[20px] border border-[#e1e5eb] bg-[#fbfcfd] p-4 open:bg-[#f8fafc]";
const summaryClass = "cursor-pointer list-none text-sm font-extrabold text-[#344054] marker:hidden";
