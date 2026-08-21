"use client";

import { Bird, Database, LockKeyhole } from "lucide-react";
import { useRuntimeRouter as useRouter } from "@/shared/navigation/public";
import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";

import {
  claimLocalOwner,
  createLocalBootstrapChallenge,
  getLocalBootstrapStatus,
  issueLocalSession,
  storeAuth,
  type LocalBootstrapRead,
} from "@/lib/agents";

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
        const suggested = status.candidates.find((candidate) => candidate.suggested);
        if (suggested) setSelectedOwnerId(suggested.user_id);
      })
      .catch((reason) => {
        if (!cancelled) {
          setError(
            reason instanceof Error
              ? reason.message
              : "로컬 owner 준비 상태를 확인하지 못했습니다.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [returnTo, router]);

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
          : "로컬 owner를 준비하지 못했습니다.",
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

  if (!bootstrap && !error) {
    return <StatusCard message="이 장치의 Angmoo owner를 확인하고 있습니다..." />;
  }

  if (bootstrap?.state === "recovery_required") {
    return (
      <StatusCard message="기존 owner principal을 찾을 수 없습니다. 데이터는 변경하지 않았으며 복구가 필요합니다." />
    );
  }

  return (
    <section className="min-h-screen bg-[#f6f7f9] px-5 py-10 md:px-9">
      <div className="mx-auto w-full max-w-[720px] rounded-[36px] border border-[#e8ecf2] bg-white p-7 shadow-[0_22px_60px_rgba(16,24,40,0.08)] md:p-10">
        <div className="flex items-start gap-4">
          <div className="flex size-14 shrink-0 items-center justify-center rounded-full bg-[#e8f7e8] text-[#257a38]">
            <Bird size={30} aria-hidden="true" />
          </div>
          <div>
            <p className="text-[13px] font-extrabold uppercase tracking-[0.16em] text-[#667085]">
              Local Angmoo
            </p>
            <h1 className="mt-1 text-[30px] font-extrabold text-[#101828]">
              이 장치의 owner 준비
            </h1>
            <p className="mt-3 text-[15px] font-medium leading-6 text-[#667085]">
              외부 계정 가입 없이 이 PC의 한 사용자를 Angmoo 데이터 owner로 연결합니다.
              owner는 한 번만 정해지며 다른 기존 사용자를 자동으로 합치지 않습니다.
            </p>
          </div>
        </div>

        {logoutLocallyOnly ? (
          <Notice>브라우저 cookie는 정리됐습니다. 새 local session을 준비합니다.</Notice>
        ) : null}
        {error ? <ErrorNotice>{localErrorMessage(error)}</ErrorNotice> : null}

        <form onSubmit={handleSubmit} className="mt-8 space-y-7">
          {bootstrap?.candidates.length ? (
            <fieldset>
              <legend className="text-[16px] font-extrabold text-[#344054]">
                기존 데이터 owner 선택
              </legend>
              <p className="mt-2 text-[13px] font-medium leading-5 text-[#667085]">
                Character·World·credential이 이미 연결된 사용자를 확인하고 직접 선택하세요.
              </p>
              <div className="mt-4 space-y-3">
                {bootstrap.candidates.map((candidate) => (
                  <label
                    key={candidate.user_id}
                    className={`block cursor-pointer rounded-[24px] border p-4 transition-colors ${
                      selectedOwnerId === candidate.user_id
                        ? "border-[#ff7a7a] bg-[#fff6f6]"
                        : "border-[#e4e7ec] bg-white hover:bg-[#f9fafb]"
                    }`}
                  >
                    <span className="flex items-start gap-3">
                      <input
                        type="radio"
                        name="owner"
                        value={candidate.user_id}
                        checked={selectedOwnerId === candidate.user_id}
                        onChange={() => setSelectedOwnerId(candidate.user_id)}
                        className="mt-1"
                      />
                      <span>
                        <span className="font-extrabold text-[#101828]">
                          {candidate.display_name}
                          {candidate.suggested ? " · 기존 데이터 후보" : ""}
                        </span>
                        <span className="mt-1 block text-[13px] font-medium text-[#667085]">
                          앵무 {candidate.character_count} · World {candidate.world_count} · 자격 정보 {candidate.credential_count}
                        </span>
                      </span>
                    </span>
                  </label>
                ))}
                <label className="block cursor-pointer rounded-[24px] border border-[#e4e7ec] p-4 hover:bg-[#f9fafb]">
                  <span className="flex items-start gap-3">
                    <input
                      type="radio"
                      name="owner"
                      value=""
                      checked={!selectedOwnerId}
                      onChange={() => setSelectedOwnerId("")}
                      className="mt-1"
                    />
                    <span className="font-extrabold text-[#101828]">새 local owner 만들기</span>
                  </span>
                </label>
              </div>
            </fieldset>
          ) : null}

          {!selectedCandidate ? (
            <Field label="owner 표시 이름">
              <input
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                maxLength={80}
                required
                className="h-14 w-full rounded-full border border-[#d0d5dd] px-5 text-[17px] font-semibold outline-none focus:border-[#ff7a7a] focus:ring-2 focus:ring-[#ffe4e4]"
                placeholder="예: 내 Angmoo"
              />
            </Field>
          ) : null}

          <Field label="이 설치의 이름 (선택)">
            <input
              value={localLabel}
              onChange={(event) => setLocalLabel(event.target.value)}
              maxLength={80}
              className="h-14 w-full rounded-full border border-[#d0d5dd] px-5 text-[17px] font-semibold outline-none focus:border-[#ff7a7a] focus:ring-2 focus:ring-[#ffe4e4]"
              placeholder="예: 작업실 PC"
            />
          </Field>

          <label className="flex gap-3 rounded-[24px] border border-[#dce8df] bg-[#f5fbf6] p-4">
            <input
              type="checkbox"
              checked={privacyAcknowledged}
              onChange={(event) => setPrivacyAcknowledged(event.target.checked)}
              className="mt-1"
            />
            <span className="text-[14px] font-semibold leading-6 text-[#344054]">
              PostgreSQL 데이터와 local secret은 이 장치에 보존되고, owner claim은 한 번만 가능하다는 점을 확인했습니다.
            </span>
          </label>

          <div className="grid gap-3 rounded-[24px] bg-[#f9fafb] p-4 text-[13px] font-semibold text-[#667085] md:grid-cols-2">
            <span className="flex items-center gap-2"><Database size={17} />기존 row·FK 보존</span>
            <span className="flex items-center gap-2"><LockKeyhole size={17} />opaque local session</span>
          </div>

          <button
            type="submit"
            disabled={
              saving ||
              !privacyAcknowledged ||
              (!selectedOwnerId && !displayName.trim())
            }
            className="h-14 w-full rounded-full bg-[#ff6b6b] px-6 text-[17px] font-extrabold text-white shadow-[0_12px_24px_rgba(255,104,104,0.24)] hover:bg-[#ff5252] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "owner를 연결하는 중..." : "이 owner로 Angmoo 시작"}
          </button>
        </form>
      </div>
    </section>
  );
}

function StatusCard({ message }: { message: string }) {
  return (
    <section className="min-h-screen bg-[#f6f7f9] px-5 py-10">
      <div className="mx-auto max-w-[680px] rounded-[32px] border border-[#e8ecf2] bg-white p-8 text-center text-[16px] font-bold text-[#475467] shadow-sm">
        {message}
      </div>
    </section>
  );
}

function Notice({ children }: { children: ReactNode }) {
  return <div className="mt-6 rounded-[22px] bg-[#fff8e8] p-4 text-[14px] font-semibold text-[#8a5a00]">{children}</div>;
}

function ErrorNotice({ children }: { children: ReactNode }) {
  return <div className="mt-6 rounded-[22px] border border-[#ffd7d7] bg-[#fff5f5] p-4 text-[14px] font-semibold text-[#c24141]">{children}</div>;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-2 block text-[15px] font-extrabold text-[#344054]">{label}</span>
      {children}
    </label>
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
