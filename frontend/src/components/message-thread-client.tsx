"use client";

import { ArrowLeft, Loader2, RotateCcw, Send, Trash2 } from "lucide-react";
import Link from "next/link";
import {
  useRuntimeRouter as useRouter,
  useRuntimeSearchParams as useSearchParams,
} from "@/shared/navigation/public";
import { useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { ProfileAvatar } from "@/components/profile-avatar";
import {
  DEFAULT_MESSAGE_GOOGLE_MODEL,
  MESSAGE_GOOGLE_GEMINI_MODELS,
  deleteMessageThread,
  getMessageThread,
  retryThreadMessage,
  sendThreadMessage,
  updateMessageThread,
  type MessageGoogleGeminiModel,
  type MessageMessageRead,
  type MessageThreadRead,
} from "@/lib/agents";
import { formatHandle } from "@/lib/profile";

function asMessageGoogleModel(value: string | undefined): MessageGoogleGeminiModel {
  return MESSAGE_GOOGLE_GEMINI_MODELS.some((option) => option.value === value)
    ? (value as MessageGoogleGeminiModel)
    : DEFAULT_MESSAGE_GOOGLE_MODEL;
}

export function MessageThreadClient({ threadId }: { threadId: string }) {
  const router = useRouter();
  const { status: authStatus } = useAuth();
  const searchParams = useSearchParams();
  const [thread, setThread] = useState<MessageThreadRead | null>(null);
  const [content, setContent] = useState("");
  const [pending, setPending] = useState(false);
  const [retryingMessageId, setRetryingMessageId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(
    searchParams.get("error") === "key_required"
      ? "쪽지를 시작하려면 API key를 등록해주세요."
      : null,
  );
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (authStatus === "checking") return;
    if (authStatus !== "authenticated") {
      router.replace("/login");
      return;
    }
    let active = true;
    getMessageThread(threadId)
      .then((result) => {
        if (active) setThread(result);
      })
      .catch((err) => {
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : "쪽지를 불러오지 못했습니다. 잠시 뒤 다시 시도해주세요.",
          );
        }
      });
    return () => {
      active = false;
    };
  }, [authStatus, router, threadId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [thread?.messages.length, pending, retryingMessageId]);

  const selectedModel = useMemo(
    () => asMessageGoogleModel(thread?.selected_model),
    [thread?.selected_model],
  );
  const latestMessageId =
    thread && thread.messages.length > 0
      ? thread.messages[thread.messages.length - 1]?.id
      : null;
  const busy = pending || retryingMessageId !== null;

  function canRetryMessage(message: MessageMessageRead) {
    return (
      Boolean(thread) &&
      !busy &&
      message.id === latestMessageId &&
      message.role === "assistant" &&
      message.status === "error" &&
      message.error_code === "model_busy"
    );
  }

  async function handleModelChange(model: MessageGoogleGeminiModel) {
    if (!thread || busy || model === thread.selected_model) return;
    setError(null);
    try {
      setThread(await updateMessageThread(thread.id, { selected_model: model }));
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "모델을 바꾸지 못했습니다. 잠시 뒤 다시 시도해주세요.",
      );
    }
  }

  async function handleSend() {
    const trimmed = content.trim();
    if (!thread || !trimmed || busy) return;
    if (trimmed.length > 2000) {
      setError("쪽지는 2,000자 이하로 입력해주세요.");
      return;
    }
    setPending(true);
    setError(null);
    const previous = thread;
    const optimistic = {
      id: -Date.now(),
      thread_id: thread.id,
      role: "user" as const,
      content: trimmed,
      model: thread.selected_model,
      status: "ok" as const,
      error_code: null,
      created_at: new Date().toISOString(),
    };
    setThread({ ...thread, messages: [...thread.messages, optimistic] });
    setContent("");
    try {
      const result = await sendThreadMessage(thread.id, trimmed);
      setThread(result.thread);
    } catch (err) {
      setThread(previous);
      void getMessageThread(thread.id)
        .then(setThread)
        .catch(() => {
          setError(
            err instanceof Error
              ? err.message
              : "현재 선택한 모델이 바쁘거나 응답하지 않습니다. 잠시 뒤 다시 시도하거나 다른 모델로 바꿔서 시도해주세요.",
          );
        });
    } finally {
      setPending(false);
    }
  }

  async function handleRetry(messageId: number) {
    if (!thread || busy) return;
    setRetryingMessageId(messageId);
    setError(null);
    try {
      const result = await retryThreadMessage(thread.id, messageId);
      setThread(result.thread);
    } catch (err) {
      void getMessageThread(thread.id)
        .then(setThread)
        .catch(() => {
          setError(
            err instanceof Error
              ? err.message
              : "현재 선택한 모델이 바쁘거나 응답하지 않습니다. 잠시 뒤 다시 시도하거나 다른 모델로 바꿔서 시도해주세요.",
          );
        });
    } finally {
      setRetryingMessageId(null);
    }
  }

  async function handleDelete() {
    if (!thread) return;
    await deleteMessageThread(thread.id);
    router.replace("/messages");
  }

  return (
    <section className="flex min-h-screen flex-col bg-white">
      <div className="sticky top-0 z-10 flex min-h-[80px] items-center gap-3 border-b border-[#eaedf2] bg-white/95 px-4 py-3 backdrop-blur-sm md:px-6">
        <Link
          href="/messages"
          className="flex size-10 shrink-0 items-center justify-center rounded-full text-[#667085] transition-colors hover:bg-[#f2f4f7] hover:text-[#101828]"
          aria-label="쪽지함으로"
          title="쪽지함으로"
        >
          <ArrowLeft size={21} aria-hidden="true" />
        </Link>
        {thread ? (
          <>
            <ProfileAvatar
              name={thread.character.display_name}
              avatarUrl={thread.character.avatar_url}
              sizeClassName="size-11"
              textClassName="text-[17px]"
            />
            <div className="min-w-0 flex-1">
              <h1 className="truncate text-[18px] font-extrabold text-[#101828]">
                {thread.character.display_name}
              </h1>
              {thread.character.handle ? (
                <p className="truncate text-[13px] font-bold text-[#98a2b3]">
                  {formatHandle(thread.character.handle)}
                </p>
              ) : null}
            </div>
            <button
              type="button"
              onClick={() => void handleDelete()}
              className="flex size-10 shrink-0 items-center justify-center rounded-full text-[#98a2b3] transition-colors hover:bg-[#f2f4f7] hover:text-[#667085]"
              aria-label="쪽지 내역 삭제"
              title="쪽지 내역 삭제"
            >
              <Trash2 size={18} aria-hidden="true" />
            </button>
          </>
        ) : (
          <div className="text-[15px] font-bold text-[#98a2b3]">쪽지를 불러오는 중입니다.</div>
        )}
      </div>

      <div className="flex-1 space-y-4 px-4 py-5 md:px-6">
        {thread?.messages.map((message) => {
          const isUser = message.role === "user";
          const retryable = canRetryMessage(message);
          const retrying = retryingMessageId === message.id;
          return (
            <div
              key={message.id}
              className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}
            >
              {!isUser ? (
                <ProfileAvatar
                  name={thread.character.display_name}
                  avatarUrl={thread.character.avatar_url}
                  sizeClassName="size-9"
                  textClassName="text-[14px]"
                />
              ) : null}
              <div
                className={`max-w-[78%] rounded-[22px] px-4 py-3 text-[15px] font-medium leading-6 ${
                  isUser
                    ? "bg-[#101828] text-white"
                    : message.status === "error"
                      ? "border border-[#ffd7d7] bg-[#fff5f5] text-[#c24141]"
                      : "bg-[#f6f7f9] text-[#101828]"
                }`}
              >
                <p className="whitespace-pre-wrap break-words">{message.content}</p>
                {retryable || retrying ? (
                  <button
                    type="button"
                    onClick={() => void handleRetry(message.id)}
                    disabled={busy}
                    className="mt-3 inline-flex h-8 items-center gap-1.5 rounded-full bg-white px-3 text-[13px] font-extrabold text-[#ff6b6b] ring-1 ring-[#ffd7d7] transition-colors hover:bg-[#fff0ef] disabled:cursor-not-allowed disabled:opacity-60"
                    aria-label="다시 시도"
                    title="다시 시도"
                  >
                    {retrying ? (
                      <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                    ) : (
                      <RotateCcw size={14} aria-hidden="true" />
                    )}
                    <span>{retrying ? "다시 시도 중" : "다시 시도"}</span>
                  </button>
                ) : null}
              </div>
            </div>
          );
        })}
        {pending ? (
          <div className="flex gap-3">
            {thread ? (
              <ProfileAvatar
                name={thread.character.display_name}
                avatarUrl={thread.character.avatar_url}
                sizeClassName="size-9"
                textClassName="text-[14px]"
              />
            ) : null}
            <div className="inline-flex items-center gap-2 rounded-[22px] bg-[#f6f7f9] px-4 py-3 text-[15px] font-bold text-[#98a2b3]">
              <span>답장 중</span>
              <span className="inline-flex items-center gap-1" aria-hidden="true">
                <span className="size-1.5 rounded-full bg-[#98a2b3] animate-bounce" />
                <span
                  className="size-1.5 rounded-full bg-[#98a2b3] animate-bounce"
                  style={{ animationDelay: "120ms" }}
                />
                <span
                  className="size-1.5 rounded-full bg-[#98a2b3] animate-bounce"
                  style={{ animationDelay: "240ms" }}
                />
              </span>
            </div>
          </div>
        ) : null}
        <div ref={bottomRef} />
      </div>

      <div className="sticky bottom-0 border-t border-[#eaedf2] bg-white/95 px-3 py-3 backdrop-blur-sm md:px-5">
        {error ? (
          <div className="mb-3 rounded-[16px] bg-[#fff5f5] px-4 py-3 text-[14px] font-bold leading-6 text-[#d92d20]">
            {error}
          </div>
        ) : null}
        <div className="rounded-[24px] border border-[#d0d5dd] bg-white px-3 py-2 shadow-[0_8px_24px_rgba(16,24,40,0.08)]">
          <textarea
            value={content}
            onChange={(event) => setContent(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void handleSend();
              }
            }}
            placeholder="쪽지를 입력하세요"
            disabled={!thread || busy}
            maxLength={2000}
            rows={3}
            className="max-h-36 min-h-16 w-full resize-none bg-transparent px-1 py-2 text-[15px] font-medium leading-6 text-[#101828] outline-none placeholder:text-[#98a2b3] disabled:opacity-60"
          />
          <div className="flex items-center justify-between gap-3 border-t border-[#f2f4f7] pt-2">
            <select
              value={selectedModel}
              onChange={(event) =>
                void handleModelChange(event.target.value as MessageGoogleGeminiModel)
              }
              disabled={!thread || busy}
              className="h-9 max-w-[210px] rounded-full border border-[#eaedf2] bg-[#f6f7f9] px-3 text-[13px] font-extrabold text-[#344054] outline-none transition-colors focus:border-[#d0d5dd] focus:bg-[#f6f7f9] disabled:opacity-60"
              aria-label="모델 선택"
            >
              {MESSAGE_GOOGLE_GEMINI_MODELS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => void handleSend()}
              disabled={!thread || busy || !content.trim()}
              className="flex size-10 shrink-0 items-center justify-center rounded-full bg-[#ff6b6b] text-white shadow-[0_6px_12px_rgba(255,104,104,0.18)] transition-colors hover:bg-[#ff5252] disabled:cursor-not-allowed disabled:bg-[#d0d5dd] disabled:shadow-none"
              aria-label="보내기"
              title="보내기"
            >
              <Send size={18} aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
