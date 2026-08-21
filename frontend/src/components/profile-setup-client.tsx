"use client";

import { Check } from "lucide-react";
import { useRuntimeRouter as useRouter } from "@/shared/navigation/public";
import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";

import { useAuth } from "@/components/auth-provider";
import { TurnstileWidget } from "@/components/turnstile-widget";
import {
  clearPendingGoogleSignup,
  completeGoogleSignup,
  getPendingGoogleSignup,
  isAuthError,
  markFirstAgentWelcomePromptPending,
  storeAuth,
  storeUser,
  updateMe,
  type PendingGoogleSignup,
} from "@/lib/agents";
import { PRIVACY_POLICY_URL, TERMS_OF_SERVICE_URL } from "@/lib/policy-links";

const TURNSTILE_SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY ?? "";

export function ProfileSetupClient() {
  const router = useRouter();
  const { status: authStatus, user } = useAuth();
  const [displayName, setDisplayName] = useState("");
  const [pendingSignup] = useState<PendingGoogleSignup | null>(() =>
    getPendingGoogleSignup(),
  );
  const [privacyAgreed, setPrivacyAgreed] = useState(false);
  const [termsAgreed, setTermsAgreed] = useState(false);
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);
  const [turnstileResetKey, setTurnstileResetKey] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requiresTurnstile = Boolean(pendingSignup && TURNSTILE_SITE_KEY);

  useEffect(() => {
    if (authStatus === "checking" && !pendingSignup) return;
    if (!user && !pendingSignup) {
      router.replace("/login");
      return;
    }
    if (user?.profile_setup_completed) {
      router.replace("/agents");
      return;
    }
  }, [authStatus, pendingSignup, router, user]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nickname = displayName.trim();
    if (!nickname) {
      setError("닉네임을 입력해주세요.");
      return;
    }
    if (!privacyAgreed || !termsAgreed) {
      setError("개인정보처리방침과 이용약관에 동의해주세요.");
      return;
    }
    if (requiresTurnstile && !turnstileToken) {
      setError("보안 확인을 완료해주세요.");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      if (pendingSignup) {
        const auth = await completeGoogleSignup({
          display_name: nickname,
          privacy_policy_agreed: privacyAgreed,
          terms_agreed: termsAgreed,
          turnstile_token: turnstileToken ?? undefined,
        });
        clearPendingGoogleSignup();
        storeAuth(auth);
        markFirstAgentWelcomePromptPending();
        router.push("/agents");
        return;
      }
      const user = await updateMe({
        display_name: nickname,
        privacy_policy_agreed: privacyAgreed,
        terms_agreed: termsAgreed,
      });
      storeUser(user);
      markFirstAgentWelcomePromptPending();
      router.push("/agents");
    } catch (err) {
      if (pendingSignup && isAuthError(err)) {
        clearPendingGoogleSignup();
        router.replace("/login");
        return;
      }
      setError(err instanceof Error ? err.message : "닉네임을 저장하지 못했습니다.");
      if (requiresTurnstile) {
        setTurnstileToken(null);
        setTurnstileResetKey((value) => value + 1);
      }
    } finally {
      setSaving(false);
    }
  }

  const handleTurnstileToken = useCallback((token: string) => {
    setTurnstileToken(token);
  }, []);

  const clearTurnstileToken = useCallback(() => {
    setTurnstileToken(null);
  }, []);

  const handleTurnstileError = useCallback(() => {
    setTurnstileToken(null);
    setError("보안 확인을 다시 시도해주세요.");
  }, []);

  return (
    <section className="min-h-screen bg-white">
      <div className="sticky top-0 z-10 flex h-[72px] items-center border-b border-[#eaedf2] bg-white/95 px-5 backdrop-blur-sm md:h-[88px] md:px-9">
        <h1 className="text-[28px] font-extrabold text-[#101828] md:text-[30px]">
          닉네임 설정
        </h1>
      </div>

      <div className="flex justify-center px-5 py-8 md:px-9">
        <form
          onSubmit={handleSubmit}
          className="w-full max-w-[640px] rounded-[32px] border border-[#eef1f5] bg-white p-7 shadow-[0_18px_40px_rgba(16,24,40,0.06)]"
        >
          <div className="mx-auto w-full max-w-[460px] text-center">
            <p className="text-[20px] font-extrabold text-[#101828]">
              Angmoo에서 사용할 닉네임을 정해주세요
            </p>
            <p className="mt-2 text-[14px] font-semibold leading-5 text-[#667085]">
              Google 이름은 저장하지 않습니다. 여기서 정한 닉네임만 Angmoo에 표시됩니다.
            </p>

            <label className="mt-7 block text-left">
              <span className="mb-2 block text-[15px] font-bold text-[#344054]">
                닉네임
              </span>
              <input
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                maxLength={80}
                autoFocus
                className="h-14 w-full rounded-full border border-[#e1e5eb] bg-white px-5 text-[17px] font-medium text-[#101828] outline-none focus:border-[#ff6b6b] focus:ring-2 focus:ring-[#ffe2e2]"
              />
            </label>

            <div className="mt-5 grid gap-3 rounded-[18px] border border-[#eef1f5] bg-[#f9fafb] p-4 text-left">
              <AgreementCheckbox
                checked={privacyAgreed}
                onChange={setPrivacyAgreed}
                label="개인정보처리방침에 동의합니다"
                linkText="개인정보처리방침"
                href={PRIVACY_POLICY_URL}
              />
              <AgreementCheckbox
                checked={termsAgreed}
                onChange={setTermsAgreed}
                label="이용약관에 동의합니다"
                linkText="이용약관"
                href={TERMS_OF_SERVICE_URL}
              />
            </div>

            {requiresTurnstile ? (
              <TurnstileWidget
                key={turnstileResetKey}
                siteKey={TURNSTILE_SITE_KEY}
                onToken={handleTurnstileToken}
                onExpire={clearTurnstileToken}
                onError={handleTurnstileError}
              />
            ) : null}

            {error ? (
              <div className="mt-4 rounded-[18px] border border-[#ffd7d7] bg-[#fff5f5] px-4 py-3 text-left text-[14px] font-bold text-[#c24141]">
                {error}
              </div>
            ) : null}

            <button
              type="submit"
              disabled={
                saving ||
                !displayName.trim() ||
                !privacyAgreed ||
                !termsAgreed ||
                (requiresTurnstile && !turnstileToken)
              }
              className="mt-7 inline-flex h-14 w-full items-center justify-center gap-3 rounded-full bg-[#ff6b6b] px-6 text-[17px] font-extrabold text-white shadow-[0_12px_24px_rgba(255,104,104,0.28)] transition-colors hover:bg-[#ff5252] disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Check size={20} aria-hidden="true" />
              {saving ? "저장 중..." : "시작하기"}
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}

function AgreementCheckbox({
  checked,
  onChange,
  label,
  linkText,
  href,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  linkText: string;
  href: string;
}) {
  const [before, after] = label.split(linkText);

  return (
    <label className="flex items-start gap-3 text-[14px] font-bold leading-5 text-[#344054]">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-1 size-4 rounded border-[#d0d5dd] accent-[#ff6b6b]"
      />
      <span>
        {before}
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[#ff6b6b] underline-offset-2 hover:underline"
          onClick={(event) => event.stopPropagation()}
        >
          {linkText}
        </a>
        {after}
      </span>
    </label>
  );
}
