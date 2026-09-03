"use client";

import {
  ArrowLeft,
  LoaderCircle,
  MessageCircle,
  RotateCcw,
  Send,
  Settings,
} from "lucide-react";
import Link from "next/link";
import {
  type FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  worldChatRoute,
  worldChatThreadRoute,
  worldCharacterProfileRoute,
} from "@/shared/navigation/public";
import { LocalProductLink } from "@/features/device-shell/public";
import {
  MemoryScopeSummary,
  WorldChatEvidenceInspector,
} from "@/features/memory/public";
import { ProfileAvatar, formatHandle } from "@/shared/ui/public";
import {
  getLatestWorldChatResponseRequest,
  getWorldChatResponseRequest,
  getWorldChatThread,
  listWorldChatThreads,
  retryWorldChatResponse,
  sendWorldChatMessage,
  streamWorldChatResponse,
  updateWorldChatThreadModel,
  WorldChatApiError,
} from "../api/world-chat-client";
import {
  MESSAGE_GOOGLE_GEMINI_MODELS,
  type MessageGoogleGeminiModel,
} from "../model/chat-contract";
import type {
  WorldChatGenerationRequestRead,
  WorldChatThreadListRead,
  WorldChatThreadRead,
} from "../model/world-chat-contract";

import styles from "./world-chat.module.css";

type WorldChatProps = {
  threadId?: string;
  worldId: string;
};

type LoadState = "loading" | "ready" | "error";
type ModelSelection = "default" | MessageGoogleGeminiModel;

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
              <div className={styles.threadRow}>
                <LocalProductLink
                  ariaLabel={`${thread.responding.display_name}의 World 프로필 열기`}
                  className={styles.threadProfileLink}
                  href={worldCharacterProfileRoute(
                    worldId,
                    thread.responding.world_character_id,
                  )}
                >
                  <ProfileAvatar
                    avatarUrl={thread.responding.avatar_url}
                    name={thread.responding.display_name}
                    sizeClassName="size-12"
                    textClassName="text-[18px]"
                  />
                  <div className={styles.identityLine}>
                    <strong>{thread.responding.display_name}</strong>
                    {thread.responding.handle ? (
                      <span>{formatHandle(thread.responding.handle)}</span>
                    ) : null}
                  </div>
                </LocalProductLink>
                <Link
                  aria-label={`${thread.responding.display_name}와의 대화 열기`}
                  className={styles.threadLink}
                  href={worldChatThreadRoute(worldId, thread.id)}
                >
                  <div className={styles.threadBody}>
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
              </div>
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
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [sendFailure, setSendFailure] = useState<{
    content: string;
    idempotencyKey: string;
  } | null>(null);
  const [modelSelection, setModelSelection] = useState<ModelSelection>("default");
  const [modelUpdating, setModelUpdating] = useState(false);
  const [modelFailure, setModelFailure] = useState<ModelSelection | null>(null);
  const [evidenceRequestId, setEvidenceRequestId] = useState<string | null>(null);
  const [generation, setGeneration] = useState<{
    phase: "pending" | "streaming" | "failed";
    request: WorldChatGenerationRequestRead;
    retrying: boolean;
    text: string;
    typingVisible: boolean;
  } | null>(null);
  const streamControllerRef = useRef<AbortController | null>(null);
  const activeGenerationRef = useRef<string | null>(null);
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const modelUpdateSequenceRef = useRef(0);

  const clearTypingTimer = useCallback(() => {
    if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
    typingTimerRef.current = null;
  }, []);

  const refreshThread = useCallback(async () => {
    const result = await getWorldChatThread(worldId, threadId);
    setThread(result);
    return result;
  }, [threadId, worldId]);

  const showTerminalRequest = useCallback(
    async (request: WorldChatGenerationRequestRead) => {
      clearTypingTimer();
      activeGenerationRef.current = null;
      if (request.state === "committed") {
        await refreshThread();
        setGeneration(null);
        return;
      }
      setGeneration({
        phase: "failed",
        request,
        retrying: false,
        text: "",
        typingVisible: false,
      });
    },
    [clearTypingTimer, refreshThread],
  );

  const consumeGeneration = useCallback(
    async function consume(
      request: WorldChatGenerationRequestRead,
      reconnectAttempt = 0,
    ) {
      streamControllerRef.current?.abort();
      const controller = new AbortController();
      streamControllerRef.current = controller;
      const scope = generationScope(request);
      activeGenerationRef.current = scope;
      clearTypingTimer();
      setGeneration({
        phase: "pending",
        request,
        retrying: false,
        text: "",
        typingVisible: false,
      });
      typingTimerRef.current = setTimeout(() => {
        if (activeGenerationRef.current !== scope) return;
        setGeneration((current) =>
          current && generationScope(current.request) === scope
            ? { ...current, typingVisible: current.phase === "pending" }
            : current,
        );
      }, 300);
      try {
        await streamWorldChatResponse(
          worldId,
          threadId,
          request,
          async (event) => {
            if (activeGenerationRef.current !== scope) return;
            if (event.type === "delta") {
              clearTypingTimer();
              const text = "text" in event.payload ? event.payload.text : "";
              setGeneration((current) =>
                current && generationScope(current.request) === scope
                  ? {
                      ...current,
                      phase: "streaming",
                      text: current.text + text,
                      typingVisible: false,
                    }
                  : current,
              );
              return;
            }
            if (event.type === "failed") {
              clearTypingTimer();
              const failure = event.payload as {
                failure_class: string;
                retryable: boolean;
              };
              setGeneration({
                phase: "failed",
                request: {
                  ...request,
                  failure_class: failure.failure_class,
                  retryable: failure.retryable,
                  state: "failed",
                },
                retrying: false,
                text: "",
                typingVisible: false,
              });
              return;
            }
            if (event.type === "cancelled") {
              clearTypingTimer();
              setGeneration({
                phase: "failed",
                request: {
                  ...request,
                  failure_class: "cancelled",
                  retryable: false,
                  state: "cancelled",
                },
                retrying: false,
                text: "",
                typingVisible: false,
              });
              return;
            }
            if (event.type === "completed") {
              const status = await getWorldChatResponseRequest(
                worldId,
                threadId,
                request.request_id,
                { signal: controller.signal },
              );
              if (activeGenerationRef.current === scope) {
                await showTerminalRequest(status);
              }
            }
          },
          { signal: controller.signal },
        );
      } catch {
        if (controller.signal.aborted) return;
        try {
          let status = await getWorldChatResponseRequest(
            worldId,
            threadId,
            request.request_id,
            { signal: controller.signal },
          );
          if (activeGenerationRef.current !== scope) return;
          if (status.state === "accepted" && reconnectAttempt < 1) {
            await consume(status, reconnectAttempt + 1);
            return;
          }
          setGeneration({
            phase: "pending",
            request: status,
            retrying: false,
            text: "",
            typingVisible: true,
          });
          while (
            !controller.signal.aborted &&
            activeGenerationRef.current === scope &&
            !isTerminalState(status.state)
          ) {
            await waitFor(750, controller.signal);
            status = await getWorldChatResponseRequest(
              worldId,
              threadId,
              request.request_id,
              { signal: controller.signal },
            );
            if (status.state === "accepted" && reconnectAttempt < 1) {
              await consume(status, reconnectAttempt + 1);
              return;
            }
          }
          if (
            activeGenerationRef.current === scope &&
            isTerminalState(status.state)
          ) {
            await showTerminalRequest(status);
          }
        } catch {
          if (controller.signal.aborted) return;
          setGeneration({
            phase: "failed",
            request: {
              ...request,
              failure_class: "stream_interrupted",
              retryable: true,
              state: "failed",
            },
            retrying: false,
            text: "",
            typingVisible: false,
          });
        }
      } finally {
        clearTypingTimer();
      }
    },
    [clearTypingTimer, showTerminalRequest, threadId, worldId],
  );

  const hydrateRequest = useCallback(
    async (request: WorldChatGenerationRequestRead, signal: AbortSignal) => {
      if (request.state === "accepted") {
        await consumeGeneration(request);
        return;
      }
      if (isTerminalState(request.state)) {
        await showTerminalRequest(request);
        return;
      }
      const scope = generationScope(request);
      activeGenerationRef.current = scope;
      setGeneration({
        phase: "pending",
        request,
        retrying: false,
        text: "",
        typingVisible: true,
      });
      while (!signal.aborted && activeGenerationRef.current === scope) {
        await waitFor(750, signal);
        if (signal.aborted) return;
        const status = await getWorldChatResponseRequest(
          worldId,
          threadId,
          request.request_id,
          { signal },
        );
        if (status.state === "accepted") {
          await consumeGeneration(status);
          return;
        }
        if (isTerminalState(status.state)) {
          await showTerminalRequest(status);
          return;
        }
      }
    },
    [consumeGeneration, showTerminalRequest, threadId, worldId],
  );

  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([
      getWorldChatThread(worldId, threadId, { signal: controller.signal }),
      getLatestWorldChatResponseRequest(worldId, threadId, {
        signal: controller.signal,
      }),
    ])
      .then(async ([result, latest]) => {
        if (controller.signal.aborted) return;
        setThread(result);
        setModelSelection(threadModelSelection(result));
        setState("ready");
        if (latest.response_request) {
          await hydrateRequest(latest.response_request, controller.signal);
        }
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setThread(null);
        setError(reason instanceof Error ? reason : new Error("world_chat_unavailable"));
        setState("error");
      });
    return () => {
      controller.abort();
      streamControllerRef.current?.abort();
      activeGenerationRef.current = null;
      clearTypingTimer();
    };
  }, [attempt, clearTypingTimer, hydrateRequest, threadId, worldId]);

  const retry = useCallback(() => {
    setState("loading");
    setError(null);
    setAttempt((value) => value + 1);
  }, []);

  const appendUserMessage = useCallback(
    (message: WorldChatGenerationRequestRead["user_message"]) => {
      setThread((current) => {
        if (!current || current.messages.some((item) => item.id === message.id)) {
          return current;
        }
        return {
          ...current,
          last_message_at: message.created_at,
          latest_message: message,
          messages: [...current.messages, message],
        };
      });
    },
    [],
  );

  const submitMessage = useCallback(
    async (content: string, idempotencyKey: string) => {
      setSending(true);
      setSendFailure(null);
      try {
        const accepted = await sendWorldChatMessage(worldId, threadId, {
          content,
          idempotency_key: idempotencyKey,
        });
        appendUserMessage(accepted.user_message);
        setDraft("");
        await hydrateRequest(accepted.response_request, new AbortController().signal);
      } catch {
        setSendFailure({ content, idempotencyKey });
      } finally {
        setSending(false);
      }
    },
    [appendUserMessage, hydrateRequest, threadId, worldId],
  );

  const handleSubmit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const content = draft.trim();
      if (
        !content ||
        sending ||
        modelUpdating ||
        (generation && generation.phase !== "failed")
      ) return;
      void submitMessage(content, newIdempotencyKey("message"));
    },
    [draft, generation, modelUpdating, sending, submitMessage],
  );

  const retryResponse = useCallback(async () => {
    if (
      !generation ||
      generation.phase !== "failed" ||
      !generation.request.retryable ||
      modelUpdating
    ) {
      return;
    }
    const failed = generation.request;
    setGeneration((current) =>
      current ? { ...current, retrying: true } : current,
    );
    try {
      const accepted = await retryWorldChatResponse(worldId, threadId, {
        failed_request_id: failed.request_id,
        idempotency_key: newIdempotencyKey("retry"),
      });
      await consumeGeneration(accepted.response_request);
    } catch {
      setGeneration((current) =>
        current ? { ...current, retrying: false } : current,
      );
    }
  }, [consumeGeneration, generation, modelUpdating, threadId, worldId]);

  const updateModelSelection = useCallback(
    async (selection: ModelSelection) => {
      if (!thread) return;
      const sequence = modelUpdateSequenceRef.current + 1;
      modelUpdateSequenceRef.current = sequence;
      const confirmed = threadModelSelection(thread);
      setModelSelection(selection);
      setModelUpdating(true);
      setModelFailure(null);
      try {
        const updated = await updateWorldChatThreadModel(
          worldId,
          threadId,
          selection === "default"
            ? { mode: "default" }
            : { mode: "thread_override", selected_model: selection },
        );
        if (modelUpdateSequenceRef.current !== sequence) return;
        setThread(updated);
        setModelSelection(threadModelSelection(updated));
      } catch {
        if (modelUpdateSequenceRef.current !== sequence) return;
        setModelSelection(confirmed);
        setModelFailure(selection);
      } finally {
        if (modelUpdateSequenceRef.current === sequence) {
          setModelUpdating(false);
        }
      }
    },
    [thread, threadId, worldId],
  );

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

  const generationBusy = Boolean(
    generation &&
      (generation.phase !== "failed" || generation.retrying),
  );
  const modelControlDisabled = sending || generationBusy || modelUpdating;
  const modelControlDescription = modelControlDisabled
    ? "답장을 처리하는 동안에는 응답 모델을 변경할 수 없습니다."
    : thread.model_binding_mode === "default"
      ? `기본 모델 ${modelLabel(thread.default_model)}을 다음 답장에 사용합니다.`
      : `${modelLabel(thread.selected_model)}을 이 대화에서 고정해 사용합니다.`;

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
        <LocalProductLink
          ariaLabel={`${thread.responding.display_name}의 World 프로필 열기`}
          className={styles.headerProfileLink}
          href={worldCharacterProfileRoute(
            worldId,
            thread.responding.world_character_id,
          )}
        >
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
        </LocalProductLink>
      </header>

      <div className={styles.roleBoundary}>
        <span>말하는 앵무</span>
        <strong>{thread.requester.display_name}</strong>
        <span aria-hidden="true">→</span>
        <span>답하는 앵무</span>
        <strong>{thread.responding.display_name}</strong>
      </div>

      <MemoryScopeSummary
        subjectWorldCharacterId={thread.responding.world_character_id}
        worldId={worldId}
      />

      <div className={styles.modelControl}>
        <label htmlFor={`world-chat-model-${thread.id}`}>응답 모델</label>
        <select
          aria-describedby={`world-chat-model-help-${thread.id}`}
          disabled={modelControlDisabled}
          id={`world-chat-model-${thread.id}`}
          onChange={(event) =>
            void updateModelSelection(event.target.value as ModelSelection)
          }
          value={modelSelection}
        >
          <option value="default">
            기본 모델 사용 — 현재 {modelLabel(thread.default_model)}
          </option>
          {MESSAGE_GOOGLE_GEMINI_MODELS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label} — 이 대화에서 고정
            </option>
          ))}
        </select>
        <p id={`world-chat-model-help-${thread.id}`}>{modelControlDescription}</p>
        {modelFailure ? (
          <div className={styles.modelFailure} role="alert">
            <span>모델을 바꾸지 못했어요.</span>
            <button
              disabled={modelControlDisabled}
              onClick={() => void updateModelSelection(modelFailure)}
              type="button"
            >
              다시 시도
            </button>
          </div>
        ) : null}
      </div>

      {thread.messages.length === 0 && !generation ? (
        <div className={styles.empty}>
          <MessageCircle aria-hidden="true" size={28} />
          <h3>아직 메시지가 없어요</h3>
          <p>이 대화에 저장된 메시지가 생기면 여기에 표시됩니다.</p>
        </div>
      ) : (
        <ol className={styles.messages} aria-label="대화 메시지">
          {thread.messages.map((message) => {
            const fromRequester = message.role === "user";
            const evidence = fromRequester
              ? null
              : thread.evidence_summaries.find(
                  (summary) => summary.assistant_message_id === message.id,
                ) ?? null;
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
                {message.status === "ok" && evidence ? (
                  <button
                    className={styles.evidenceButton}
                    data-evidence-capability={evidence.capability}
                    onClick={() => setEvidenceRequestId(evidence.request_id)}
                    type="button"
                  >
                    근거 {evidence.count}개 보기
                  </button>
                ) : null}
              </li>
            );
          })}
          {generation ? (
            <li
              className={`${styles.respondingMessage} ${
                generation.phase === "failed" ? styles.failedMessage : ""
              }`}
              data-response-slot={generation.request.response_slot_id}
              key={generation.request.response_slot_id}
            >
              {generation.phase === "pending" && generation.typingVisible ? (
                <TypingPresence name={thread.responding.display_name} />
              ) : generation.phase === "streaming" ? (
                <p className={styles.streamingText} aria-live="polite">
                  {generation.text}
                </p>
              ) : generation.phase === "failed" ? (
                <GenerationFailure
                  disabled={modelUpdating}
                  failureClass={generation.request.failure_class}
                  onRetry={() => void retryResponse()}
                  retryable={generation.request.retryable}
                  retrying={generation.retrying}
                />
              ) : null}
            </li>
          ) : null}
        </ol>
      )}

      <WorldChatEvidenceInspector
        key={evidenceRequestId ?? "closed"}
        onOpenChange={(open) => {
          if (!open) setEvidenceRequestId(null);
        }}
        open={evidenceRequestId !== null}
        requestId={evidenceRequestId}
        threadId={thread.id}
        worldId={worldId}
      />

      <form className={styles.composer} onSubmit={handleSubmit}>
        <label className={styles.srOnly} htmlFor={`world-chat-${thread.id}`}>
          {thread.responding.display_name}에게 보낼 메시지
        </label>
        <textarea
          disabled={sending || modelUpdating || (!!generation && generation.phase !== "failed")}
          id={`world-chat-${thread.id}`}
          maxLength={4000}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="메시지를 입력하세요"
          rows={1}
          value={draft}
        />
        <button
          aria-label="메시지 보내기"
          disabled={
            !draft.trim() ||
            sending ||
            modelUpdating ||
            (!!generation && generation.phase !== "failed")
          }
          type="submit"
        >
          {sending ? (
            <LoaderCircle aria-hidden="true" className={styles.spin} size={19} />
          ) : (
            <Send aria-hidden="true" size={19} />
          )}
        </button>
      </form>
      {sendFailure ? (
        <div className={styles.sendFailure} role="alert">
          <span>메시지를 보내지 못했어요.</span>
          <button
            disabled={sending}
            onClick={() =>
              void submitMessage(
                sendFailure.content,
                sendFailure.idempotencyKey,
              )
            }
            type="button"
          >
            다시 보내기
          </button>
        </div>
      ) : null}
    </section>
  );
}

function TypingPresence({ name }: { name: string }) {
  return (
    <div
      aria-label={`${name}가 응답을 입력하고 있습니다.`}
      className={styles.typingPresence}
      role="status"
    >
      <span>입력 중</span>
      <span aria-hidden="true" className={styles.typingDots}>
        <i />
        <i />
        <i />
      </span>
    </div>
  );
}

function GenerationFailure({
  disabled,
  failureClass,
  onRetry,
  retryable,
  retrying,
}: {
  disabled: boolean;
  failureClass: string | null;
  onRetry: () => void;
  retryable: boolean;
  retrying: boolean;
}) {
  const settingsRequired = [
    "credential_required",
    "credential_invalid",
    "policy_denied",
  ].includes(failureClass ?? "");
  return (
    <div className={styles.failureBubble} role="alert">
      <strong>
        {settingsRequired
          ? "채팅에 사용할 AI 설정이 필요해요."
          : "답장을 만들지 못했어요."}
      </strong>
      {retryable ? (
        <button disabled={disabled || retrying} onClick={onRetry} type="button">
          {retrying ? (
            <LoaderCircle aria-hidden="true" className={styles.spin} size={16} />
          ) : (
            <RotateCcw aria-hidden="true" size={16} />
          )}
          {retrying ? "다시 시도 중" : "다시 시도"}
        </button>
      ) : settingsRequired ? (
        <Link href="/settings">
          <Settings aria-hidden="true" size={16} />
          설정 열기
        </Link>
      ) : null}
    </div>
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

function generationScope(request: WorldChatGenerationRequestRead) {
  return [
    request.request_id,
    request.request_scope_hash,
    request.generation_id,
    request.attempt_number,
  ].join(":");
}

function isTerminalState(state: WorldChatGenerationRequestRead["state"]) {
  return [
    "committed",
    "rejected",
    "cancelled",
    "timed_out",
    "failed",
    "orphaned",
  ].includes(state);
}

function newIdempotencyKey(prefix: "message" | "retry") {
  const random =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}-${random}`;
}

function waitFor(milliseconds: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, milliseconds);
    signal.addEventListener("abort", onAbort, { once: true });
  });
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

function threadModelSelection(thread: WorldChatThreadRead): ModelSelection {
  return thread.model_binding_mode === "default" ? "default" : thread.selected_model;
}

function modelLabel(model: MessageGoogleGeminiModel) {
  return (
    MESSAGE_GOOGLE_GEMINI_MODELS.find((option) => option.value === model)?.label ??
    model
  );
}
