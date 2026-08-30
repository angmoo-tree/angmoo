"use client";

import { Bird, Database, LockKeyhole } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { useRuntimeRouter as useRouter } from "@/shared/navigation/public";
import {
  Button,
  Card,
  DegradedPanel,
  Field,
  InlineError,
  Input,
  PageHeader,
  StatusChip,
  Toast,
} from "@/shared/ui/public";
import {
  claimLocalOwner,
  createLocalBootstrapChallenge,
  getLocalBootstrapStatus,
  issueLocalSession,
  storeAuth,
  type LocalBootstrapRead,
} from "@/lib/agents";

import styles from "./local-owner-client.module.css";

type LocalOwnerClientProps = {
  logoutLocallyOnly?: boolean;
  returnTo?: string | null;
};

export function LocalOwnerClient({
  logoutLocallyOnly = false,
  returnTo = null,
}: LocalOwnerClientProps) {
  const router = useRouter();
  const [bootstrap, setBootstrap] = useState<LocalBootstrapRead | null>(null);
  const [selectedOwnerId, setSelectedOwnerId] = useState<string>("");
  const [displayName, setDisplayName] = useState("");
  const [localLabel, setLocalLabel] = useState("");
  const [privacyAcknowledged, setPrivacyAcknowledged] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadRevision, setLoadRevision] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getLocalBootstrapStatus()
      .then(async (status) => {
        if (cancelled) return;
        if (status.state === "claimed") {
          const auth = await issueLocalSession();
          if (cancelled) return;
          storeAuth(auth);
          router.replace(returnTo ?? "/");
          return;
        }
        setBootstrap(status);
        setLocalLabel(status.local_label ?? "");
        const suggested = status.candidates.find((candidate) => candidate.suggested);
        setSelectedOwnerId(suggested?.user_id ?? "");
      })
      .catch((reason) => {
        if (!cancelled) {
          setBootstrap(null);
          setError(
            reason instanceof Error
              ? reason.message
              : "이 설치의 owner 준비 상태를 확인하지 못했습니다.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [loadRevision, returnTo, router]);

  const selectedCandidate = useMemo(
    () =>
      bootstrap?.candidates.find(
        (candidate) => candidate.user_id === selectedOwnerId,
      ) ?? null,
    [bootstrap, selectedOwnerId],
  );

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!bootstrap || bootstrap.state !== "unclaimed") return;
    setSaving(true);
    setError(null);
    try {
      await createLocalBootstrapChallenge();
      const auth = await claimLocalOwner({
        owner_user_id: selectedOwnerId || null,
        display_name: selectedOwnerId ? null : displayName,
        local_label: localLabel || null,
        privacy_acknowledged: privacyAcknowledged,
      });
      storeAuth(auth);
      router.replace(returnTo ?? "/");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "이 설치의 local owner를 준비하지 못했습니다.",
      );
      try {
        setBootstrap(await getLocalBootstrapStatus());
      } catch {
        // Keep the original actionable error.
      }
    } finally {
      setSaving(false);
    }
  }

  function retryBootstrap() {
    setError(null);
    setLoadRevision((value) => value + 1);
  }

  if (!bootstrap && !error) {
    return (
      <LocalOwnerStateSurface>
        <StatusChip label="설치 확인 중" tone="waiting" />
        <p>이 설치에 연결된 Angmoo owner와 로컬 세션을 확인하고 있습니다.</p>
      </LocalOwnerStateSurface>
    );
  }

  if (bootstrap?.state === "recovery_required") {
    return (
      <LocalOwnerStateSurface>
        <DegradedPanel
          title="owner 복구가 필요합니다"
          description="기존 owner principal을 찾을 수 없습니다. 데이터는 변경하지 않았으며 새 owner를 만들지 않습니다."
          action={
            <Button variant="secondary" onClick={retryBootstrap}>
              다시 확인
            </Button>
          }
        />
      </LocalOwnerStateSurface>
    );
  }

  if (!bootstrap) {
    return (
      <LocalOwnerStateSurface>
        <InlineError>
          <div className={styles.feedbackStack}>
            <span>{localErrorMessage(error ?? "owner_state_unavailable")}</span>
            <Button variant="secondary" onClick={retryBootstrap}>
              다시 확인
            </Button>
          </div>
        </InlineError>
      </LocalOwnerStateSurface>
    );
  }

  return (
    <section className={styles.page} data-local-owner-state={bootstrap.state}>
      <PageHeader title="이 장치의 owner 준비" subtitle="Local Angmoo · 한 설치 · 한 owner" />

      <div className={styles.content}>
        <Card as="section" className={styles.introCard}>
          <div className={styles.introHeading}>
            <span className={styles.brandIcon} aria-hidden="true">
              <Bird />
            </span>
            <div>
              <h2>이 설치의 데이터 owner를 연결합니다</h2>
              <p>
                외부 계정 가입 없이 이 PC의 한 사용자를 Angmoo 데이터 owner로 연결합니다.
                owner는 한 번만 정해지며 다른 설치의 사용자와 자동으로 합쳐지지 않습니다.
              </p>
            </div>
          </div>
          <dl className={styles.installationSummary}>
            <div>
              <dt>설치 식별자</dt>
              <dd>{bootstrap.installation_id ?? "준비 중"}</dd>
            </div>
            <div>
              <dt>설치 이름</dt>
              <dd>{bootstrap.local_label?.trim() || "아직 정하지 않음"}</dd>
            </div>
          </dl>
        </Card>

        {logoutLocallyOnly ? (
          <Toast>
            이전 로컬 세션은 이 설치에서 정리됐습니다. owner 데이터는 그대로이며 새
            local session을 준비합니다.
          </Toast>
        ) : null}
        {error ? <InlineError>{localErrorMessage(error)}</InlineError> : null}

        <form onSubmit={handleSubmit} className={styles.form}>
          {bootstrap.candidates.length ? (
            <fieldset className={styles.ownerFieldset}>
              <legend>기존 데이터 owner 선택</legend>
              <p>
                Character·World·credential이 이미 연결된 사용자를 확인하고 직접
                선택하세요. 선택하지 않으면 새 owner를 만듭니다.
              </p>
              <div className={styles.ownerChoices}>
                {bootstrap.candidates.map((candidate) => {
                  const selected = selectedOwnerId === candidate.user_id;
                  return (
                    <label
                      key={candidate.user_id}
                      className={styles.ownerChoice}
                      data-selected={selected || undefined}
                    >
                      <input
                        type="radio"
                        name="owner"
                        value={candidate.user_id}
                        checked={selected}
                        onChange={() => setSelectedOwnerId(candidate.user_id)}
                      />
                      <span>
                        <strong>
                          {candidate.display_name}
                          {candidate.suggested ? " · 기존 데이터 후보" : ""}
                        </strong>
                        <small>
                          앵무 {candidate.character_count} · World {candidate.world_count} ·
                          credential {candidate.credential_count}
                        </small>
                      </span>
                    </label>
                  );
                })}
                <label
                  className={styles.ownerChoice}
                  data-selected={!selectedOwnerId || undefined}
                >
                  <input
                    type="radio"
                    name="owner"
                    value=""
                    checked={!selectedOwnerId}
                    onChange={() => setSelectedOwnerId("")}
                  />
                  <span>
                    <strong>새 local owner 만들기</strong>
                    <small>기존 후보와 합치지 않고 이 설치에 새 owner를 만듭니다.</small>
                  </span>
                </label>
              </div>
            </fieldset>
          ) : null}

          {!selectedCandidate ? (
            <Field id="local-owner-display-name" label="owner 표시 이름" required>
              {(controlProps) => (
                <Input
                  {...controlProps}
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  maxLength={80}
                  autoComplete="name"
                  placeholder="예: 내 Angmoo"
                />
              )}
            </Field>
          ) : null}

          <Field
            id="local-installation-label"
            label="이 설치의 이름"
            helperText="선택 사항이며 다른 설치를 구분하기 위한 로컬 표시 이름입니다."
          >
            {(controlProps) => (
              <Input
                {...controlProps}
                value={localLabel}
                onChange={(event) => setLocalLabel(event.target.value)}
                maxLength={80}
                placeholder="예: 작업실 PC"
              />
            )}
          </Field>

          <label className={styles.privacyChoice}>
            <input
              type="checkbox"
              checked={privacyAcknowledged}
              onChange={(event) => setPrivacyAcknowledged(event.target.checked)}
            />
            <span>
              SQLite 데이터와 local secret은 이 장치에 보존되고, owner claim은 한 번만
              가능하다는 점을 확인했습니다.
            </span>
          </label>

          <div className={styles.localFacts} aria-label="로컬 저장 계약">
            <span>
              <Database aria-hidden="true" />
              기존 row·FK 보존
            </span>
            <span>
              <LockKeyhole aria-hidden="true" />
              opaque local session
            </span>
          </div>

          <Button
            type="submit"
            fullWidth
            loading={saving}
            loadingLabel="owner를 연결하는 중"
            disabled={
              !privacyAcknowledged ||
              (!selectedOwnerId && !displayName.trim())
            }
          >
            이 owner로 Angmoo 시작
          </Button>
        </form>
      </div>
    </section>
  );
}

function LocalOwnerStateSurface({ children }: { children: React.ReactNode }) {
  return (
    <section className={styles.page} data-local-owner-state="checking">
      <PageHeader title="이 장치의 owner 준비" subtitle="Local Angmoo" />
      <div className={styles.stateContent}>
        <Card as="section" className={styles.stateCard}>
          {children}
        </Card>
      </div>
    </section>
  );
}

function localErrorMessage(code: string) {
  if (code.includes("bootstrap_race_lost") || code.includes("bootstrap_closed")) {
    return "다른 owner claim이 먼저 완료되었습니다. local session을 다시 확인합니다.";
  }
  if (code.includes("bootstrap_challenge_invalid")) {
    return "owner 확인 시간이 만료되었습니다. 다시 시도해 주세요.";
  }
  if (code.includes("local_owner_candidate_invalid")) {
    return "선택한 기존 owner를 사용할 수 없습니다. 목록을 다시 확인해 주세요.";
  }
  return code;
}
