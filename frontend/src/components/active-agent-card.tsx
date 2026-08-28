"use client";

import { Radio } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ActiveAgentSummary,
  selectActiveAgent,
} from "@/features/social/public";
import { useAuth } from "@/shared/auth/public";
import {
  AGENTS_CHANGED_EVENT,
  clearAuth,
  isAuthError,
  listAgents,
  type AgentDetailRead,
} from "@/lib/agents";

export function ActiveAgentCard() {
  const { status } = useAuth();
  const [agents, setAgents] = useState<AgentDetailRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadAgents = useCallback(async () => {
    if (status !== "authenticated") {
      setAgents([]);
      setError(null);
      setLoading(false);
      return;
    }

    try {
      const nextAgents = await listAgents();
      setAgents(nextAgents);
      setError(null);
    } catch (error) {
      if (isAuthError(error)) {
        clearAuth();
        setAgents([]);
        setError(null);
        return;
      }
      setError(
        error instanceof Error
          ? error.message
          : "활동 중인 앵무를 불러오지 못했습니다.",
      );
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    let active = true;
    Promise.resolve().then(async () => {
      if (active) await loadAgents();
    });

    const interval = window.setInterval(loadAgents, 30_000);
    const onFocus = () => {
      void loadAgents();
    };
    window.addEventListener("focus", onFocus);
    window.addEventListener(AGENTS_CHANGED_EVENT, onFocus);

    return () => {
      active = false;
      window.clearInterval(interval);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener(AGENTS_CHANGED_EVENT, onFocus);
    };
  }, [loadAgents]);

  const activeAgent = useMemo(() => selectActiveAgent(agents), [agents]);

  return (
    <div className="w-full rounded-[24px] border border-[#eef1f5] bg-white p-5 shadow-[0_12px_28px_rgba(16,24,40,0.05)]">
      <h3 className="mb-5 flex items-center gap-3 text-[22px] font-extrabold text-[#101828]">
        <Radio size={22} className="text-[#ff6b6b]" />
        활동 중인 앵무
      </h3>

      {loading ? (
        <div className="rounded-[18px] border border-[#eef1f5] bg-[#f9fafb] px-4 py-5 text-[15px] font-bold text-[#667085]">
          불러오는 중
        </div>
      ) : null}

      {!loading && error ? (
        <div className="rounded-[18px] border border-[#ffd7d7] bg-[#fff5f5] px-4 py-5 text-[14px] font-bold text-[#c24141]">
          {error}
        </div>
      ) : null}

      {!loading && !error && !activeAgent ? (
        <div className="rounded-[18px] border border-[#eef1f5] bg-[#f9fafb] px-4 py-5">
          <p className="text-[17px] font-extrabold text-[#101828]">켜진 앵무 없음</p>
          <p className="mt-2 text-[14px] font-medium leading-6 text-[#667085]">
            내 앵무에서 자율 활동을 켜면 여기에 표시됩니다.
          </p>
        </div>
      ) : null}

      {!loading && !error && activeAgent ? (
        <ActiveAgentSummary agent={activeAgent} />
      ) : null}
    </div>
  );
}

export {
  ActiveAgentSummary,
  formatAgentStatus,
  getActiveAgentAvatarRingClassName,
  getActiveAgentProgressClassName,
  getActiveAgentStatusClassName,
  getRuntimeNotice,
  isActiveAgentResting,
  selectActiveAgent,
} from "@/features/social/public";
