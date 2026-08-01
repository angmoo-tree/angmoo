"use client";

import { Mail, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { ProfileAvatar } from "@/components/profile-avatar";
import {
  deleteMessageThread,
  listMessageThreads,
  type MessageThreadListRead,
} from "@/lib/agents";
import { formatHandle } from "@/lib/profile";

export function MessagesClient() {
  const router = useRouter();
  const { status: authStatus } = useAuth();
  const [threads, setThreads] = useState<MessageThreadListRead | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    if (authStatus === "checking") return;
    if (authStatus !== "authenticated") {
      router.replace("/login");
      return;
    }
    let active = true;
    listMessageThreads()
      .then((result) => {
        if (active) setThreads(result);
      })
      .catch((err) => {
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : "쪽지함을 불러오지 못했습니다. 잠시 뒤 다시 시도해주세요.",
          );
        }
      });
    return () => {
      active = false;
    };
  }, [authStatus, router]);

  async function handleDelete(threadId: string) {
    setDeletingId(threadId);
    setError(null);
    try {
      await deleteMessageThread(threadId);
      setThreads((previous) =>
        previous
          ? {
              ...previous,
              items: previous.items.filter((thread) => thread.id !== threadId),
            }
          : previous,
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "쪽지 내역을 삭제하지 못했습니다. 잠시 뒤 다시 시도해주세요.",
      );
    } finally {
      setDeletingId(null);
    }
  }

  const items = threads?.items ?? [];

  return (
    <section className="min-h-screen bg-white">
      <div className="sticky top-0 z-10 flex min-h-[88px] items-center border-b border-[#eaedf2] bg-white/95 px-5 py-4 backdrop-blur-sm md:px-9">
        <div className="min-w-0">
          <p className="truncate text-[14px] font-bold text-[#ff6b6b]">쪽지</p>
          <h1 className="text-[28px] font-extrabold text-[#101828] md:text-[30px]">
            쪽지함
          </h1>
          {threads ? (
            <p className="mt-1 text-[13px] font-bold text-[#98a2b3]">
              {items.length}/{threads.max_threads}
            </p>
          ) : null}
        </div>
      </div>

      {error ? (
        <div className="mx-5 mt-5 rounded-[18px] border border-[#ffd7d7] bg-[#fff5f5] px-4 py-3 text-[14px] font-bold leading-6 text-[#d92d20] md:mx-9">
          {error}
        </div>
      ) : null}

      {!threads ? (
        <div className="p-8 text-center text-[15px] font-bold text-[#98a2b3]">
          쪽지함을 불러오는 중입니다.
        </div>
      ) : items.length === 0 ? (
        <div className="p-8 text-center text-[15px] font-bold text-[#98a2b3]">
          아직 나눈 쪽지가 없습니다.
        </div>
      ) : (
        <div className="divide-y divide-[#eaedf2]">
          {items.map((thread) => (
            <div key={thread.id} className="flex items-center gap-3 px-5 py-4 md:px-9">
              <Link
                href={`/messages/${thread.id}`}
                className="flex min-w-0 flex-1 items-center gap-3"
              >
                <ProfileAvatar
                  name={thread.character.display_name}
                  avatarUrl={thread.character.avatar_url}
                  sizeClassName="size-12"
                  textClassName="text-[18px]"
                />
                <div className="min-w-0">
                  <div className="flex min-w-0 items-baseline gap-2">
                    <span className="truncate text-[16px] font-extrabold text-[#101828]">
                      {thread.character.display_name}
                    </span>
                    {thread.character.handle ? (
                      <span className="truncate text-[13px] font-bold text-[#98a2b3]">
                        {formatHandle(thread.character.handle)}
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1 line-clamp-1 text-[14px] font-medium text-[#667085]">
                    {thread.latest_message?.content ?? "새 쪽지를 시작해보세요."}
                  </p>
                </div>
              </Link>
              <button
                type="button"
                onClick={() => void handleDelete(thread.id)}
                disabled={deletingId === thread.id}
                className="flex size-10 shrink-0 items-center justify-center rounded-full text-[#98a2b3] transition-colors hover:bg-[#fff5f5] hover:text-[#ff6b6b] disabled:opacity-50"
                aria-label="쪽지 내역 삭제"
                title="쪽지 내역 삭제"
              >
                {deletingId === thread.id ? (
                  <Mail size={18} aria-hidden="true" />
                ) : (
                  <Trash2 size={18} aria-hidden="true" />
                )}
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
