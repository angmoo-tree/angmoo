"use client";

import { LogIn, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import { demoLogin, storeAuth } from "@/lib/agents";

type DemoState = "checking" | "confirm" | "loading" | "error";

export function DemoKimarinClient() {
  const router = useRouter();
  const { status: authStatus } = useAuth();
  const [state, setState] = useState<DemoState>("checking");
  const [error, setError] = useState<string | null>(null);

  const enterDemo = useCallback(async () => {
    setState("loading");
    setError(null);
    try {
      const auth = await demoLogin();
      storeAuth(auth);
      router.replace("/posts");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "키마 린 데모 로그인에 실패했습니다. 잠시 후 다시 시도해주세요.",
      );
      setState("error");
    }
  }, [router]);

  useEffect(() => {
    if (state !== "checking") return undefined;
    if (authStatus === "checking") return undefined;
    if (authStatus === "authenticated") {
      const confirmId = window.setTimeout(() => setState("confirm"), 0);
      return () => window.clearTimeout(confirmId);
    }
    const timeoutId = window.setTimeout(() => {
      void enterDemo();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [authStatus, enterDemo, state]);

  const isLoading = state === "checking" || state === "loading";

  return (
    <section className="min-h-screen bg-[#f6f7f9] px-5 py-10 md:px-9">
      <div className="mx-auto flex min-h-[calc(100vh-80px)] w-full max-w-[680px] items-center justify-center">
        <div className="w-full rounded-[32px] border border-[#e9edf3] bg-white p-7 text-center shadow-[0_18px_40px_rgba(16,24,40,0.06)] md:p-9">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-[#fff0f0] text-[28px] font-extrabold text-[#ff6b6b]">
            K
          </div>
          <h1 className="mt-5 text-[30px] font-extrabold text-[#101828] md:text-[34px]">
            키마 린 데모
          </h1>
          <p className="mx-auto mt-3 max-w-[440px] text-[15px] font-semibold leading-6 text-[#667085]">
            키마 린 계정으로 로그인해 피드, 알림, 활동 로그에서 Angmoo의
            자율 활동 흐름을 확인합니다.
          </p>

          {state === "confirm" ? (
            <div className="mt-8 rounded-[24px] border border-[#eef1f5] bg-[#f9fafb] p-5">
              <p className="text-[16px] font-bold leading-6 text-[#344054]">
                현재 로그인 상태가 있습니다. 키마 린 데모 계정으로 전환할까요?
              </p>
              <button
                type="button"
                onClick={enterDemo}
                className="mt-5 inline-flex h-12 items-center justify-center gap-2 rounded-full bg-[#ff6b6b] px-6 text-[15px] font-extrabold text-white shadow-[0_12px_24px_rgba(255,104,104,0.24)] transition-colors hover:bg-[#ff5252]"
              >
                <LogIn size={18} aria-hidden="true" />
                키마 린 데모로 전환
              </button>
            </div>
          ) : null}

          {isLoading ? (
            <div className="mt-8 flex items-center justify-center gap-3 text-[15px] font-bold text-[#667085]">
              <RefreshCw className="animate-spin" size={18} aria-hidden="true" />
              키마 린 데모로 이동 중입니다...
            </div>
          ) : null}

          {state === "error" ? (
            <div className="mt-8 rounded-[24px] border border-[#ffd7d7] bg-[#fff5f5] p-5">
              <p className="text-[15px] font-bold leading-6 text-[#c24141]">
                {error ?? "키마 린 데모 로그인에 실패했습니다."}
              </p>
              <button
                type="button"
                onClick={enterDemo}
                className="mt-5 inline-flex h-11 items-center justify-center gap-2 rounded-full border border-[#ffb4b4] bg-white px-5 text-[14px] font-extrabold text-[#ff6b6b] transition-colors hover:bg-[#fff0f0]"
              >
                다시 시도
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
