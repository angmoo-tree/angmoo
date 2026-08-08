"use client";

import { LogIn } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";

import {
  googleLogin,
  login,
  storeAuth,
  storePendingGoogleSignup,
} from "@/lib/agents";

const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ?? "";
const GOOGLE_SCRIPT_SRC = "https://accounts.google.com/gsi/client";

type GoogleCredentialResponse = {
  credential?: string;
};

type GoogleIdentityServices = {
  accounts: {
    id: {
      initialize: (config: {
        client_id: string;
        callback: (response: GoogleCredentialResponse) => void;
        ux_mode?: "popup" | "redirect";
      }) => void;
      renderButton: (
        parent: HTMLElement,
        options: {
          type?: "standard" | "icon";
          theme?: "outline" | "filled_blue" | "filled_black";
          size?: "large" | "medium" | "small";
          text?: "signin_with" | "signup_with" | "continue_with" | "signin";
          shape?: "pill" | "rectangular" | "circle" | "square";
          logo_alignment?: "left" | "center";
          width?: number;
        },
      ) => void;
    };
  };
};

declare global {
  interface Window {
    google?: GoogleIdentityServices;
  }
}

let googleScriptPromise: Promise<void> | null = null;

function loadGoogleScript() {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("Google 로그인을 사용할 수 없습니다."));
  }
  if (window.google?.accounts.id) {
    return Promise.resolve();
  }
  if (googleScriptPromise) {
    return googleScriptPromise;
  }
  googleScriptPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(
      `script[src="${GOOGLE_SCRIPT_SRC}"]`,
    );
    if (existing) {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener(
        "error",
        () => reject(new Error("Google 로그인 스크립트를 불러오지 못했습니다.")),
        { once: true },
      );
      return;
    }

    const script = document.createElement("script");
    script.src = GOOGLE_SCRIPT_SRC;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () =>
      reject(new Error("Google 로그인 스크립트를 불러오지 못했습니다."));
    document.head.appendChild(script);
  });
  return googleScriptPromise;
}

type LoginClientProps = {
  emailLoginEnabled?: boolean;
  logoutLocallyOnly?: boolean;
  returnTo?: string | null;
};

export function LoginClient({
  emailLoginEnabled = false,
  logoutLocallyOnly = false,
  returnTo = null,
}: LoginClientProps) {
  const router = useRouter();
  const googleButtonRef = useRef<HTMLDivElement | null>(null);
  const googleSavingRef = useRef(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [emailSaving, setEmailSaving] = useState(false);
  const [googleSaving, setGoogleSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleGoogleCredential = useCallback(
    async (response: GoogleCredentialResponse) => {
      if (googleSavingRef.current) return;
      if (!response.credential) {
        setError("Google 로그인 정보를 확인하지 못했습니다.");
        return;
      }

      googleSavingRef.current = true;
      setGoogleSaving(true);
      setError(null);
      try {
        const auth = await googleLogin({ credential: response.credential });
        if (auth.signup_required) {
          storePendingGoogleSignup(auth);
          router.push("/profile/setup");
          return;
        }
        if (!auth.user) {
          throw new Error("Google 로그인 응답을 확인하지 못했습니다.");
        }
        storeAuth({
          user: auth.user,
          profile_setup_required: auth.profile_setup_required,
        });
        router.push(
          auth.profile_setup_required || !auth.user.profile_setup_completed
            ? "/profile/setup"
            : returnTo ?? "/agents",
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : "Google 로그인에 실패했습니다.");
      } finally {
        googleSavingRef.current = false;
        setGoogleSaving(false);
      }
    },
    [returnTo, router],
  );

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return;
    let cancelled = false;

    loadGoogleScript()
      .then(() => {
        if (cancelled) return;
        const buttonRoot = googleButtonRef.current;
        const google = window.google;
        if (!buttonRoot || !google?.accounts.id) return;

        buttonRoot.innerHTML = "";
        google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: handleGoogleCredential,
          ux_mode: "popup",
        });
        google.accounts.id.renderButton(buttonRoot, {
          type: "standard",
          theme: "outline",
          size: "large",
          text: "signin_with",
          shape: "pill",
          logo_alignment: "left",
          width: Math.min(buttonRoot.clientWidth || 360, 400),
        });
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Google 로그인에 실패했습니다.");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [handleGoogleCredential]);

  async function handleEmailSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setEmailSaving(true);
    setError(null);

    try {
      const auth = await login({ email, password });
      storeAuth(auth);
      router.push(
        auth.profile_setup_required || !auth.user.profile_setup_completed
          ? "/profile/setup"
          : returnTo ?? "/agents",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "로그인에 실패했습니다.");
    } finally {
      setEmailSaving(false);
    }
  }

  return (
    <section className="min-h-screen bg-white">
      <div className="sticky top-0 z-10 flex h-[72px] items-center border-b border-[#eaedf2] bg-white/95 px-5 backdrop-blur-sm md:h-[88px] md:px-9">
        <h1 className="text-[28px] font-extrabold text-[#101828] md:text-[30px]">
          로그인
        </h1>
      </div>

      {error ? (
        <div className="mx-5 mt-6 rounded-[24px] border border-[#ffd7d7] bg-[#fff5f5] px-5 py-4 text-[15px] font-medium text-[#c24141] md:mx-9">
          {error}
        </div>
      ) : null}

      {logoutLocallyOnly ? (
        <div className="mx-5 mt-6 rounded-[24px] border border-[#f9df9b] bg-[#fffaf0] px-5 py-4 text-[15px] font-medium text-[#8a5a00] md:mx-9">
          이 브라우저의 로그인 정보는 지웠지만 서버 세션 폐기를 확인하지 못했습니다.
          다시 로그인한 뒤 로그아웃을 재시도해 주세요.
        </div>
      ) : null}

      <div className="flex justify-center px-5 py-8 md:px-9">
        <div className="w-full max-w-[720px] rounded-[32px] border border-[#eef1f5] bg-white p-7 shadow-[0_18px_40px_rgba(16,24,40,0.06)]">
          <div className="mx-auto flex w-full max-w-[480px] flex-col items-center space-y-4 text-center">
            <div>
              <p className="text-[18px] font-extrabold text-[#101828]">
                Google 계정으로 시작
              </p>
              <p className="mx-auto mt-3 max-w-[420px] text-[13px] font-semibold leading-5 text-[#667085]">
                Google은 계정 인증에만 사용됩니다. Angmoo는 Google 프로필 사진을 저장하지 않으며,
                닉네임은 로그인 후 직접 설정합니다.
              </p>
            </div>

            {GOOGLE_CLIENT_ID ? (
              <div
                ref={googleButtonRef}
                className={`flex min-h-11 w-full justify-center [&>div]:mx-auto ${googleSaving ? "pointer-events-none opacity-60" : ""}`}
              />
            ) : (
              <div className="flex h-11 w-full items-center justify-center rounded-full border border-[#e1e5eb] bg-[#f9fafb] px-5 text-[15px] font-bold text-[#98a2b3]">
                Google 로그인 설정이 필요합니다.
              </div>
            )}

            {googleSaving ? (
              <p className="text-[14px] font-bold text-[#667085]">
                Google 로그인 확인 중...
              </p>
            ) : null}
          </div>

          {emailLoginEnabled ? (
            <>
              <div className="my-7 h-px bg-[#eef1f5]" />
              <form onSubmit={handleEmailSubmit} className="mx-auto w-full max-w-[480px]">
                <p className="mb-5 text-center text-[18px] font-extrabold text-[#101828]">
                  이메일 로그인
                </p>
                <div className="space-y-5">
                  <Field label="이메일">
                    <input
                      type="email"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      className="h-14 w-full rounded-full border border-[#e1e5eb] bg-white px-5 text-[17px] font-medium text-[#101828] outline-none focus:border-[#ff6b6b] focus:ring-2 focus:ring-[#ffe2e2]"
                    />
                  </Field>
                  <Field label="비밀번호">
                    <input
                      type="password"
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      className="h-14 w-full rounded-full border border-[#e1e5eb] bg-white px-5 text-[17px] font-medium text-[#101828] outline-none focus:border-[#ff6b6b] focus:ring-2 focus:ring-[#ffe2e2]"
                    />
                  </Field>
                </div>

                <button
                  type="submit"
                  disabled={emailSaving || !email.trim() || !password.trim()}
                  className="mt-7 inline-flex h-14 w-full items-center justify-center gap-3 rounded-full bg-[#ff6b6b] px-6 text-[17px] font-extrabold text-white shadow-[0_12px_24px_rgba(255,104,104,0.28)] transition-colors hover:bg-[#ff5252] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <LogIn size={20} aria-hidden="true" />
                  {emailSaving ? "로그인 중..." : "이메일 로그인"}
                </button>
              </form>
            </>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-[15px] font-bold text-[#344054]">{label}</span>
      {children}
    </label>
  );
}
