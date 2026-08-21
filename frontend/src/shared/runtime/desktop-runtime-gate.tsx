"use client";

import { useEffect, useState, type ReactNode } from "react";

import {
  getDesktopRuntimeStatus,
  isTauriDesktopRuntime,
  retryDesktopRuntime,
  type AngmooDesktopRuntimeStatus,
} from "@/shared/desktop/public";
import {
  clearDesktopRuntimeConfig,
  installDesktopRuntimeConfig,
  isStaticFrontendProfile,
} from "./runtime-config";

type GateState =
  | { kind: "checking" }
  | { kind: "bypass" }
  | { kind: "ready" }
  | { kind: "waiting"; status: AngmooDesktopRuntimeStatus };

export function DesktopRuntimeGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<GateState>({ kind: "checking" });

  useEffect(() => {
    if (!isStaticFrontendProfile() || !isTauriDesktopRuntime()) {
      const bypassTimer = setTimeout(() => {
        setState({ kind: "bypass" });
      }, 0);
      return () => clearTimeout(bypassTimer);
    }
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function refresh() {
      try {
        const status = await getDesktopRuntimeStatus();
        if (!active || !status) return;
        if (
          status.phase === "ready" &&
          status.apiBaseUrl &&
          status.launchToken
        ) {
          installDesktopRuntimeConfig(status.apiBaseUrl, status.launchToken);
          setState({ kind: "ready" });
          timer = setTimeout(refresh, 2_000);
          return;
        }
        clearDesktopRuntimeConfig();
        setState({ kind: "waiting", status });
        timer = setTimeout(refresh, status.phase === "starting" ? 250 : 1_000);
      } catch {
        clearDesktopRuntimeConfig();
        setState({
          kind: "waiting",
          status: {
            phase: "crashed",
            diagnosticCode: "desktop_runtime_unreachable",
          },
        });
        timer = setTimeout(refresh, 1_000);
      }
    }

    void refresh();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, []);

  if (state.kind === "ready" || state.kind === "bypass") return children;
  const crashed =
    state.kind === "waiting" && state.status.phase === "crashed";
  return (
    <main
      className="flex min-h-screen w-full items-center justify-center bg-[#fff8f7] px-8 text-[#251818]"
      aria-live="polite"
      data-desktop-runtime-state={crashed ? "crashed" : "starting"}
    >
      <section className="w-full min-w-0 max-w-sm text-center">
        <p className="text-xs font-bold uppercase tracking-[0.22em] text-[#9c6d68]">
          Local Device
        </p>
        <h1 className="mt-3 text-3xl font-bold">Angmoo</h1>
        {crashed ? (
          <>
            <p className="mt-6 break-keep text-base leading-7 text-[#765f5c]">
              로컬 엔진 연결이 중단되었습니다. 데이터는 보존되어 있으며 다시
              시작할 수 있습니다.
            </p>
            <p className="mt-2 break-all text-xs text-[#9c6d68]">
              진단 코드: {state.status.diagnosticCode ?? "sidecar_stopped"}
            </p>
            <button
              className="mt-6 rounded-full bg-[#aa453c] px-6 py-3 font-bold text-white"
              onClick={() => {
                setState({
                  kind: "waiting",
                  status: { phase: "starting" },
                });
                void retryDesktopRuntime();
              }}
              type="button"
            >
              로컬 엔진 다시 시작
            </button>
          </>
        ) : (
          <>
            <div
              className="mx-auto mt-8 h-9 w-9 animate-pulse rounded-full bg-[#e8b6b0]"
              aria-hidden="true"
            />
            <p className="mt-5 text-base text-[#765f5c]">
              로컬 엔진과 저장된 World를 준비하고 있습니다.
            </p>
          </>
        )}
      </section>
    </main>
  );
}
