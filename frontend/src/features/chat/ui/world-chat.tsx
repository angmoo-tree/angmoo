"use client";

import { ArrowLeft, MessageCircle, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  worldChatRoute,
  worldChatThreadRoute,
} from "@/shared/navigation/public";
import { ProfileAvatar, formatHandle } from "@/shared/ui/public";
import {
  getWorldChatThread,
  listWorldChatThreads,
  WorldChatApiError,
} from "../api/world-chat-client";
import type {
  WorldChatThreadListRead,
  WorldChatThreadRead,
} from "../model/world-chat-contract";

import styles from "./world-chat.module.css";

type WorldChatProps = {
  threadId?: string;
  worldId: string;
};

type LoadState = "loading" | "ready" | "error";

export function WorldChat({ threadId, worldId }: WorldChatProps) {
  return threadId ? (
    <WorldChatThread key={`${worldId}:${threadId}`} threadId={threadId} worldId={worldId} />
  ) : (
    <WorldChatList key={worldId} worldId={worldId} />
  );
}

function WorldChatList({ worldId }: { worldId: string }) {
  const [read, setRead] = useState<WorldChatThreadListRead | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState<Error | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    void listWorldChatThreads(worldId, { signal: controller.signal })
      .then((result) => {
        setRead(result);
        setState("ready");
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setRead(null);
        setError(reason instanceof Error ? reason : new Error("world_chat_unavailable"));
        setState("error");
      });
    return () => controller.abort();
  }, [attempt, worldId]);

  const retry = useCallback(() => {
    setState("loading");
    setError(null);
    setAttempt((value) => value + 1);
  }, []);

  if (state === "loading") {
    return <WorldChatStatus title="World Chat을 불러오는 중" />;
  }
  if (state === "error" || !read) {
    return <WorldChatError error={error} onRetry={retry} />;
  }

  return (
    <section
      className={styles.surface}
      data-world-chat-surface="list"
      data-world-id={worldId}
    >
      <header className={styles.heading}>
        <div className={styles.headingIcon}>
          <MessageCircle aria-hidden="true" size={21} />
        </div>
        <div>
          <p className={styles.kicker}>WORLD CHAT</p>
          <h2>대화</h2>
          <p>
            {read.items.length}/{read.max_threads}개의 World 대화
          </p>
        </div>
      </header>

      {read.ambiguous_legacy_count > 0 ? (
        <div className={styles.notice} role="status">
          <strong>World를 확인해야 하는 이전 대화가 있어요.</strong>
          <p>
            {read.ambiguous_legacy_count}개의 이전 대화는 임의의 World에 연결하지
            않았습니다.
          </p>
        </div>
      ) : null}

      {read.items.length === 0 ? (
        <div className={styles.empty}>
          <MessageCircle aria-hidden="true" size={28} />
          <h3>아직 시작한 대화가 없어요</h3>
          <p>같은 World의 Character와 시작한 대화가 여기에 표시됩니다.</p>
        </div>
      ) : (
        <ol className={styles.threadList} aria-label="World 대화 목록">
          {read.items.map((thread) => (
            <li key={thread.id}>
              <Link
                className={styles.threadLink}
                href={worldChatThreadRoute(worldId, thread.id)}
              >
                <ProfileAvatar
                  avatarUrl={thread.responding.avatar_url}
                  name={thread.responding.display_name}
                  sizeClassName="size-12"
                  textClassName="text-[18px]"
                />
                <div className={styles.threadBody}>
                  <div className={styles.identityLine}>
                    <strong>{thread.responding.display_name}</strong>
                    {thread.responding.handle ? (
                      <span>{formatHandle(thread.responding.handle)}</span>
                    ) : null}
                  </div>
                  <p className={styles.requesterLabel}>
                    {thread.requester.display_name}(으)로 대화
                  </p>
                  <p className={styles.preview}>
                    {thread.latest_message?.content ?? "아직 메시지가 없어요."}
                  </p>
                </div>
                <time
                  className={styles.time}
                  dateTime={thread.last_message_at ?? thread.created_at}
                >
                  {compactDate(thread.last_message_at ?? thread.created_at)}
                </time>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function WorldChatThread({
  threadId,
  worldId,
}: {
  threadId: string;
  worldId: string;
}) {
  const [thread, setThread] = useState<WorldChatThreadRead | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState<Error | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    void getWorldChatThread(worldId, threadId, { signal: controller.signal })
      .then((result) => {
        setThread(result);
        setState("ready");
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setThread(null);
        setError(reason instanceof Error ? reason : new Error("world_chat_unavailable"));
        setState("error");
      });
    return () => controller.abort();
  }, [attempt, threadId, worldId]);

  const retry = useCallback(() => {
    setState("loading");
    setError(null);
    setAttempt((value) => value + 1);
  }, []);

  if (state === "loading") {
    return <WorldChatStatus title="대화를 불러오는 중" />;
  }
  if (state === "error" || !thread) {
    return (
      <WorldChatError
        backHref={worldChatRoute(worldId)}
        error={error}
        onRetry={retry}
      />
    );
  }

  return (
    <section
      className={styles.threadSurface}
      data-thread-id={thread.id}
      data-world-chat-surface="thread"
      data-world-id={worldId}
    >
      <header className={styles.threadHeading}>
        <Link
          aria-label="World 대화 목록으로"
          className={styles.backLink}
          href={worldChatRoute(worldId)}
          title="World 대화 목록으로"
        >
          <ArrowLeft aria-hidden="true" size={20} />
        </Link>
        <ProfileAvatar
          avatarUrl={thread.responding.avatar_url}
          name={thread.responding.display_name}
          sizeClassName="size-11"
          textClassName="text-[17px]"
        />
        <div className={styles.threadTitle}>
          <h2>{thread.responding.display_name}</h2>
          <p>{thread.requester.display_name}(으)로 대화 중</p>
        </div>
      </header>

      <div className={styles.roleBoundary}>
        <span>말하는 앵무</span>
        <strong>{thread.requester.display_name}</strong>
        <span aria-hidden="true">→</span>
        <span>답하는 앵무</span>
        <strong>{thread.responding.display_name}</strong>
      </div>

      {thread.messages.length === 0 ? (
        <div className={styles.empty}>
          <MessageCircle aria-hidden="true" size={28} />
          <h3>아직 메시지가 없어요</h3>
          <p>이 대화에 저장된 메시지가 생기면 여기에 표시됩니다.</p>
        </div>
      ) : (
        <ol className={styles.messages} aria-label="대화 메시지">
          {thread.messages.map((message) => {
            const fromRequester = message.role === "user";
            return (
              <li
                className={
                  fromRequester ? styles.requesterMessage : styles.respondingMessage
                }
                key={message.id}
              >
                <div className={styles.messageMeta}>
                  <strong>
                    {fromRequester
                      ? thread.requester.display_name
                      : thread.responding.display_name}
                  </strong>
                  <time dateTime={message.created_at}>{compactDate(message.created_at)}</time>
                </div>
                <p>
                  {message.status === "ok"
                    ? message.content
                    : "이 응답은 완료되지 않았어요."}
                </p>
              </li>
            );
          })}
        </ol>
      )}

      <div className={styles.readOnlyNotice} role="status">
        저장된 World 대화를 안전하게 표시하고 있어요.
      </div>
    </section>
  );
}

function WorldChatStatus({ title }: { title: string }) {
  return (
    <section className={styles.status} aria-live="polite" role="status">
      <MessageCircle aria-hidden="true" size={26} />
      <h2>{title}</h2>
      <p>현재 World 경계를 확인하고 있어요.</p>
    </section>
  );
}

function WorldChatError({
  backHref,
  error,
  onRetry,
}: {
  backHref?: string;
  error: Error | null;
  onRetry: () => void;
}) {
  const status = error instanceof WorldChatApiError ? error.status : 500;
  const scopeMismatch =
    error instanceof WorldChatApiError && error.detail === "world_chat_scope_mismatch";
  const denied = status === 403;
  const missing = status === 404;
  const retryable = !denied && !missing && !scopeMismatch;
  const title = scopeMismatch
    ? "World 경계를 확인했어요"
    : denied
      ? "이 대화를 볼 권한이 없어요"
      : missing
        ? "대화를 찾을 수 없어요"
        : "World Chat을 불러오지 못했어요";
  const description = scopeMismatch
    ? "다른 World의 응답은 표시하지 않았습니다."
    : denied || missing
      ? "다른 World나 대화로 자동 이동하지 않습니다."
      : "로컬 runtime 상태를 확인한 뒤 다시 시도해주세요.";

  return (
    <section className={styles.status} role="alert">
      <MessageCircle aria-hidden="true" size={26} />
      <h2>{title}</h2>
      <p>{description}</p>
      <div className={styles.statusActions}>
        {backHref ? <Link href={backHref}>대화 목록으로</Link> : null}
        {retryable ? (
          <button onClick={onRetry} type="button">
            <RotateCcw aria-hidden="true" size={17} />
            다시 시도
          </button>
        ) : null}
      </div>
    </section>
  );
}

function compactDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("ko-KR", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "2-digit",
  }).format(date);
}
