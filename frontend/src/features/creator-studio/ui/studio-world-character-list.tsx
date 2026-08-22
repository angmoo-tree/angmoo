"use client";

import { Loader2, RefreshCw, UserRound } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import {
  getStudioWorldCharacters,
  StudioWorldCharacterApiError,
} from "../api/studio-world-character-client";
import type { StudioWorldCharacterRead } from "../model/studio-world-character-contract";


const SETUP_LABELS: Record<StudioWorldCharacterRead["activity_setup_state"], string> = {
  not_started: "P2 준비 전",
  generated: "P2 후보 생성됨",
  approved: "P2 승인 완료",
  unavailable_for_owner_controlled: "자동 활동 대상 아님",
};

function listErrorMessage(error: unknown) {
  if (error instanceof StudioWorldCharacterApiError) {
    if (error.detail === "creator_role_required") {
      return "World owner 또는 editor 권한이 필요합니다.";
    }
    if (error.detail === "world_not_found") {
      return "World를 찾을 수 없거나 접근할 수 없습니다.";
    }
    return error.detail;
  }
  return "이 World의 캐릭터를 불러오지 못했습니다.";
}

export function StudioWorldCharacterList({ worldId }: { worldId: string }) {
  const [reloadKey, setReloadKey] = useState(0);
  const requestKey = `${worldId}:${reloadKey}`;
  const [result, setResult] = useState<{
    key: string;
    items: StudioWorldCharacterRead[];
    error: string | null;
  }>({ key: "", items: [], error: null });
  const loading = result.key !== requestKey;
  const items = loading ? [] : result.items;
  const error = loading ? null : result.error;

  useEffect(() => {
    let active = true;
    void getStudioWorldCharacters(worldId)
      .then((result) => {
        if (active) {
          setResult({ key: requestKey, items: result.items, error: null });
        }
      })
      .catch((reason) => {
        if (active) {
          setResult({ key: requestKey, items: [], error: listErrorMessage(reason) });
        }
      });
    return () => {
      active = false;
    };
  }, [requestKey, worldId]);

  function openOwnerProfile() {
    document
      .getElementById("owner-controlled-identity")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <section className="rounded-[28px] border border-[#e1e5eb] bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-lg font-black text-[#101828]">이 World의 캐릭터</p>
          <p className="mt-1 text-sm font-medium leading-6 text-[#667085]">
            기존 WorldCharacter의 활동 준비와 상태를 확인합니다. 생성·삭제는 P10-L에서 제공합니다.
          </p>
        </div>
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-full border border-[#d0d5dd] px-4 py-2 text-xs font-extrabold text-[#344054]"
          onClick={() => setReloadKey((value) => value + 1)}
          disabled={loading}
        >
          {loading ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
          새로고침
        </button>
      </div>

      {loading ? (
        <p className="mt-5 flex items-center gap-2 text-sm font-bold text-[#667085]">
          <Loader2 className="size-4 animate-spin" /> 캐릭터를 확인하는 중입니다.
        </p>
      ) : error ? (
        <p className="mt-5 rounded-[18px] bg-[#fff1f0] px-4 py-3 text-sm font-bold text-[#b42318]">
          {error}
        </p>
      ) : items.length === 0 ? (
        <p className="mt-5 rounded-[18px] bg-[#f2f4f7] px-4 py-3 text-sm font-bold text-[#475467]">
          아직 이 World에 연결된 캐릭터가 없습니다.
        </p>
      ) : (
        <div className="mt-5 grid gap-3">
          {items.map((item) => (
            <article
              key={item.world_character_id}
              className="rounded-[22px] border border-[#eaecf0] bg-[#fcfcfd] p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="flex min-w-0 gap-3">
                  <span className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-[#f2f4f7] text-[#667085]">
                    <UserRound className="size-5" />
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-base font-black text-[#101828]">
                      {item.display_name}
                    </p>
                    <p className="mt-1 line-clamp-2 text-xs font-medium leading-5 text-[#667085]">
                      {item.intro || "소개가 아직 없습니다."}
                    </p>
                  </div>
                </div>
                {item.control_mode === "autonomous" ? (
                  <Link
                    href={`/characters/${encodeURIComponent(item.character_id)}/worlds/${encodeURIComponent(worldId)}/autonomy-setup`}
                    className="rounded-full bg-[#101828] px-4 py-2 text-xs font-extrabold text-white"
                  >
                    활동 준비·상태 보기
                  </Link>
                ) : (
                  <button
                    type="button"
                    onClick={openOwnerProfile}
                    className="rounded-full bg-[#101828] px-4 py-2 text-xs font-extrabold text-white"
                  >
                    프로필 보기
                  </button>
                )}
              </div>
              <div className="mt-3 flex flex-wrap gap-2 text-[11px] font-extrabold">
                <span className="rounded-full bg-[#eef2ff] px-3 py-1 text-[#3538cd]">
                  {item.control_mode === "autonomous" ? "AUTONOMOUS" : "OWNER CONTROLLED"}
                </span>
                <span className="rounded-full bg-[#f2f4f7] px-3 py-1 text-[#475467]">
                  {SETUP_LABELS[item.activity_setup_state]}
                </span>
                <span className="rounded-full bg-[#f2f4f7] px-3 py-1 text-[#475467]">
                  자율활동 {item.autonomous_enabled ? "ON" : "OFF"}
                </span>
                <span className="rounded-full bg-[#f2f4f7] px-3 py-1 text-[#475467]">
                  {item.status}
                </span>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
