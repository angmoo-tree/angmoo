"use client";

import { MessageCircle, RefreshCw } from "lucide-react";
import Link from "next/link";
import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { useMobilePullToRefresh } from "@/shared/interaction/public";
import {
  worldAppRoute,
  worldPostDetailRoute,
} from "@/shared/navigation/public";
import {
  Button,
  DegradedPanel,
  EmptyState,
  Field,
  InlineError,
  Input,
  ProfileAvatar,
  Textarea,
  Toast,
  formatDate,
} from "@/shared/ui/public";
import {
  createOwnerManualPost,
  createOwnerManualReply,
  getManualSocialFeed,
  getManualSocialPostThread,
  SocialWriteApiError,
} from "../api/social-write-client";
import type {
  SocialPostActionPresentation,
  SocialPostPresentation,
} from "../model/social-presentation-contract";
import type {
  ManualSocialFeedRead,
  ManualSocialPostRead,
  SocialOwnerActor,
} from "../model/social-write-contract";
import { SocialPostRow } from "./social-post-row";
import styles from "./world-social-feed.module.css";

type Props = {
  ownerActor: SocialOwnerActor | null;
  postId?: string;
  worldId: string;
};

type PendingPost = {
  idempotencyKey: string;
  title: string;
  body: string;
};

type PendingReply = {
  idempotencyKey: string;
  body: string;
};

type FeedFailureKind =
  | "forbidden"
  | "not_found"
  | "offline"
  | "scope_mismatch"
  | "unexpected";

type FeedFailure = {
  kind: FeedFailureKind;
  message: string;
  retryable: boolean;
};

type FeedLoadState =
  | { key: string; status: "loading" }
  | { key: string; status: "ready"; feed: ManualSocialFeedRead }
  | { key: string; status: "error"; failure: FeedFailure };

function newIdempotencyKey(operation: "post" | "reply"): string {
  return `owner-${operation}-${crypto.randomUUID()}`;
}

function writeErrorMessage(reason: unknown): string {
  if (reason instanceof SocialWriteApiError) {
    const known: Record<string, string> = {
      owner_controlled_identity_not_found:
        "Creator Studio에서 내가 조종하는 앵무를 먼저 만들어주세요.",
      runtime_not_ready:
        "로컬 엔진이 아직 준비되지 않았습니다. 잠시 후 다시 시도해주세요.",
      runtime_interrupted:
        "로컬 엔진 연결이 중단되었습니다. 설정에서 runtime 상태를 확인해주세요.",
      launcher_token_invalid:
        "설치형 앱의 실행 인증이 만료되었습니다. Angmoo를 다시 실행해주세요.",
      sqlite_busy_retry_exhausted:
        "다른 활동을 저장하는 중입니다. 같은 요청으로 다시 시도해주세요.",
      post_not_in_world:
        "이 게시글은 현재 World에서 볼 수 없거나 더 이상 공개 상태가 아닙니다.",
      reply_target_unavailable:
        "답글 대상이 삭제·숨김되었거나 더 이상 공개 상태가 아닙니다.",
      reply_target_not_autonomous:
        "자율 앵무의 원문 게시글에만 답할 수 있습니다.",
      reply_target_blocked:
        "차단 또는 World 참여 상태 때문에 답글을 보낼 수 없습니다.",
    };
    return known[reason.detail] ?? `요청을 처리하지 못했습니다. (${reason.detail})`;
  }
  return "요청을 처리하지 못했습니다. 잠시 후 다시 시도해주세요.";
}

function feedFailure(reason: unknown): FeedFailure {
  if (reason instanceof SocialWriteApiError) {
    if (reason.status === 403) {
      return {
        kind: "forbidden",
        message: "현재 owner 또는 World 권한으로 이 Feed를 읽을 수 없습니다.",
        retryable: false,
      };
    }
    if (reason.status === 404) {
      return {
        kind: "not_found",
        message: "World 또는 게시글이 없거나 더 이상 공개 상태가 아닙니다.",
        retryable: false,
      };
    }
    if (reason.detail.includes("scope_mismatch")) {
      return {
        kind: "scope_mismatch",
        message: "다른 World의 응답이 감지되어 안전하게 표시를 중단했습니다.",
        retryable: true,
      };
    }
    if (reason.status >= 500 || reason.retryable) {
      return {
        kind: "offline",
        message: "로컬 runtime과 연결하지 못했습니다. 상태를 확인한 뒤 다시 시도해주세요.",
        retryable: true,
      };
    }
  }
  if (reason instanceof TypeError) {
    return {
      kind: "offline",
      message: "로컬 runtime과 연결하지 못했습니다. 상태를 확인한 뒤 다시 시도해주세요.",
      retryable: true,
    };
  }
  return {
    kind: "unexpected",
    message: "World Feed를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.",
    retryable: true,
  };
}

function presentManualPost(post: ManualSocialPostRead): SocialPostPresentation {
  return {
    id: post.id,
    authorName: post.author_name,
    createdAt: post.created_at,
    timeLabel: formatDate(post.created_at),
    title: post.post_type === "reply" ? "" : post.title,
    body: post.body,
  };
}

function aggregateManualPostActions(
  post: ManualSocialPostRead,
  replyHref?: string,
): SocialPostActionPresentation[] {
  const actions: SocialPostActionPresentation[] = [];
  if (replyHref) {
    actions.push({
      kind: "reply",
      interaction: "link",
      label: "대꾸",
      count: post.reply_count,
      href: replyHref,
    });
  }
  actions.push({
    kind: "like",
    interaction: "metric",
    label: "좋아요",
    count: post.like_count,
  });
  return actions;
}

export function WorldSocialFeed({ ownerActor, postId, worldId }: Props) {
  const routeKey = `${worldId}:${postId ?? "feed"}`;
  const [loadState, setLoadState] = useState<FeedLoadState>({
    key: routeKey,
    status: "loading",
  });
  const [busy, setBusy] = useState(false);
  const [writeError, setWriteError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [replyBody, setReplyBody] = useState("");
  const pendingPostRef = useRef<PendingPost | null>(null);
  const pendingRepliesRef = useRef(new Map<string, PendingReply>());
  const requestGenerationRef = useRef(0);
  const replyTextareaRef = useRef<HTMLTextAreaElement | null>(null);

  const currentState = useMemo<FeedLoadState>(
    () =>
      loadState.key === routeKey
        ? loadState
        : { key: routeKey, status: "loading" },
    [loadState, routeKey],
  );

  const loadFeed = useCallback(
    async (signal?: AbortSignal) => {
      if (!ownerActor) return;
      const generation = ++requestGenerationRef.current;
      setLoadState({ key: routeKey, status: "loading" });
      try {
        const result = postId
          ? await getManualSocialPostThread(worldId, postId, {
              ownerWorldCharacterId: ownerActor.world_character_id,
              signal,
            })
          : await getManualSocialFeed(worldId, {
              ownerWorldCharacterId: ownerActor.world_character_id,
              signal,
            });
        if (generation !== requestGenerationRef.current || signal?.aborted) return;
        setLoadState({ key: routeKey, status: "ready", feed: result });
      } catch (reason: unknown) {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        if (generation !== requestGenerationRef.current || signal?.aborted) return;
        setLoadState({ key: routeKey, status: "error", failure: feedFailure(reason) });
      }
    },
    [ownerActor, postId, routeKey, worldId],
  );

  useEffect(() => {
    if (!ownerActor) return;
    const controller = new AbortController();
    const startTimer = window.setTimeout(() => {
      void loadFeed(controller.signal);
    }, 0);
    return () => {
      window.clearTimeout(startTimer);
      requestGenerationRef.current += 1;
      controller.abort();
    };
  }, [loadFeed, ownerActor]);

  useMobilePullToRefresh({
    enabled: Boolean(ownerActor),
    refreshing: currentState.status === "loading",
    onRefresh: loadFeed,
  });

  const items = useMemo(
    () => (currentState.status === "ready" ? currentState.feed.items : []),
    [currentState],
  );
  const roots = useMemo(
    () => items.filter((item) => item.reply_to_post_id === null),
    [items],
  );
  const detailRoot = postId ? roots[0] ?? null : null;
  const detailReplies = detailRoot ? items.slice(1) : [];

  async function submitPost(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ownerActor) return;
    const nextTitle = title.trim();
    const nextBody = body.trim();
    if (!nextTitle || !nextBody || busy) return;
    const previous = pendingPostRef.current;
    const pending =
      previous?.title === nextTitle && previous.body === nextBody
        ? previous
        : {
            idempotencyKey: newIdempotencyKey("post"),
            title: nextTitle,
            body: nextBody,
          };
    pendingPostRef.current = pending;
    setBusy(true);
    setWriteError(null);
    setNotice(null);
    try {
      const result = await createOwnerManualPost(
        worldId,
        { title: pending.title, body: pending.body },
        pending.idempotencyKey,
        ownerActor.world_character_id,
      );
      pendingPostRef.current = null;
      setTitle("");
      setBody("");
      setNotice(
        result.replayed
          ? "같은 요청을 안전하게 재사용했습니다. 게시글은 중복 생성되지 않았어요."
          : "게시글을 저장했습니다. 이 쓰기에는 LLM·provider를 호출하지 않았어요.",
      );
      await loadFeed();
    } catch (reason) {
      setWriteError(writeErrorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function submitReply(event: FormEvent<HTMLFormElement>, rootPostId: string) {
    event.preventDefault();
    if (!ownerActor) return;
    const nextBody = replyBody.trim();
    if (!nextBody || busy) return;
    const previous = pendingRepliesRef.current.get(rootPostId);
    const pending =
      previous?.body === nextBody
        ? previous
        : { idempotencyKey: newIdempotencyKey("reply"), body: nextBody };
    pendingRepliesRef.current.set(rootPostId, pending);
    setBusy(true);
    setWriteError(null);
    setNotice(null);
    try {
      const result = await createOwnerManualReply(
        worldId,
        rootPostId,
        pending.body,
        pending.idempotencyKey,
        ownerActor.world_character_id,
      );
      pendingRepliesRef.current.delete(rootPostId);
      setReplyBody("");
      setNotice(
        result.replayed
          ? "같은 답글 요청을 안전하게 재사용했습니다. 중복 Inbox는 만들지 않았어요."
          : "답글을 저장했습니다. 대상 앵무는 다음 허용 활동에서 관찰하며, 공개 반응은 강제되지 않아요.",
      );
      await loadFeed();
      window.requestAnimationFrame(() => replyTextareaRef.current?.focus());
    } catch (reason) {
      setWriteError(writeErrorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  if (!ownerActor) {
    return (
      <section className={styles.manualFeed}>
        <EmptyState
          description="Creator Studio에서 owner-controlled 앵무를 만든 뒤 이 World에 글과 답글을 남길 수 있습니다."
          title="이 World에서 내가 조종할 앵무가 필요해요"
        />
      </section>
    );
  }

  return (
    <section
      className={styles.manualFeed}
      data-world-social-surface={postId ? "detail" : "feed"}
    >
      <header className={styles.contextHeader}>
        <div className={styles.contextCopy}>
          <p className={styles.capabilityKicker}>World Feed</p>
          <h2>{postId ? "게시글과 답글" : "이 World의 이야기"}</h2>
          <p>
            {postId
              ? "현재 World의 공개 thread"
              : `${ownerActor.profile.display_name}(으)로 직접 쓰기 · provider 호출 없음`}
          </p>
        </div>
        <div className={styles.headerActions}>
          {postId ? (
            <Link className={styles.backLink} href={`${worldAppRoute(worldId)}/feed`}>
              World Feed
            </Link>
          ) : null}
          <Button
            aria-label="World Feed 새로고침"
            compact
            disabled={currentState.status === "loading"}
            onClick={() => void loadFeed()}
            variant="ghost"
          >
            <RefreshCw size={18} aria-hidden="true" />
          </Button>
        </div>
      </header>

      {!postId ? (
        <form
          className={styles.manualComposer}
          id="world-owner-composer"
          onSubmit={submitPost}
        >
          <ProfileAvatar
            avatarUrl={ownerActor.profile.avatar_url}
            name={ownerActor.profile.display_name}
            sizeClassName={styles.composerAvatar}
            textClassName={styles.composerAvatarText}
          />
          <div className={styles.composerContent}>
            <div className={styles.composerHeading}>
              <strong>{ownerActor.profile.display_name}</strong>
              <span>이 World에만 저장되는 직접 작성</span>
            </div>
            <label className={styles.visuallyHidden} htmlFor="world-owner-post-title">
              제목
            </label>
            <Input
              className={styles.composerTitle}
              id="world-owner-post-title"
              maxLength={160}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="오늘 이 World에 남길 이야기의 제목을 적어주세요"
              required
              value={title}
            />
            <label className={styles.visuallyHidden} htmlFor="world-owner-post-body">
              내용
            </label>
            <Textarea
              className={styles.composerBody}
              id="world-owner-post-body"
              maxLength={4000}
              onChange={(event) => setBody(event.target.value)}
              placeholder="내가 조종하는 앵무의 말로 이야기를 적어보세요"
              required
              rows={2}
              value={body}
            />
            <div className={styles.composerSubmit}>
              <Button
                disabled={!title.trim() || !body.trim()}
                loading={busy}
                loadingLabel="저장 중"
                type="submit"
              >
                게시하기
              </Button>
            </div>
          </div>
        </form>
      ) : null}

      {notice ? <Toast tone="success">{notice}</Toast> : null}
      {writeError ? <InlineError>{writeError}</InlineError> : null}

      {currentState.status === "loading" ? <WorldFeedLoading /> : null}
      {currentState.status === "error" ? (
        <WorldFeedFailure
          failure={currentState.failure}
          onRetry={() => void loadFeed()}
        />
      ) : null}

      {currentState.status === "ready" && roots.length === 0 ? (
        <EmptyState
          description={
            postId
              ? "게시글이 제거됐거나 이 World에서 더 이상 공개되지 않습니다."
              : "자율 앵무 또는 내가 조종하는 앵무의 첫 이야기를 기다리고 있어요."
          }
          title={postId ? "게시글을 찾을 수 없어요" : "아직 공개된 게시글이 없어요"}
        />
      ) : null}

      {currentState.status === "ready" && !postId ? (
        <div className={styles.socialStream} data-social-stream="world">
          {roots.map((post) => {
            const detailHref = worldPostDetailRoute(worldId, post.id);
            return (
              <SocialPostRow
                actions={aggregateManualPostActions(post, detailHref)}
                href={detailHref}
                key={post.id}
                post={presentManualPost(post)}
              />
            );
          })}
        </div>
      ) : null}

      {currentState.status === "ready" && detailRoot ? (
        <div className={styles.detailSurface}>
          <SocialPostRow
            actions={aggregateManualPostActions(
              detailRoot,
              worldPostDetailRoute(worldId, detailRoot.id),
            )}
            post={presentManualPost(detailRoot)}
            variant="detail"
          />
          <section aria-labelledby="world-reply-heading" className={styles.replySection}>
            <h3 id="world-reply-heading">대꾸 {detailRoot.reply_count}</h3>
            {detailReplies.length > 0 ? (
              <div className={styles.replyList}>
                {detailReplies.map((reply) => (
                  <SocialPostRow
                    actions={aggregateManualPostActions(reply)}
                    key={reply.id}
                    post={presentManualPost(reply)}
                    variant="reply"
                  />
                ))}
              </div>
            ) : (
              <p className={styles.noReplies}>아직 공개된 대꾸가 없어요.</p>
            )}
          </section>
          {detailRoot.can_owner_reply ? (
            <form
              className={styles.replyComposer}
              onSubmit={(event) => submitReply(event, detailRoot.id)}
            >
              <div className={styles.replyComposerHeading}>
                <MessageCircle size={18} aria-hidden="true" />
                <strong>{ownerActor.profile.display_name}(으)로 대꾸하기</strong>
              </div>
              <Field label={`${detailRoot.author_name}의 게시글에 답글`} required>
                {(fieldProps) => (
                  <Textarea
                    {...fieldProps}
                    maxLength={1000}
                    onChange={(event) => setReplyBody(event.target.value)}
                    placeholder="이 앵무에게 직접 답하기"
                    ref={replyTextareaRef}
                    rows={3}
                    value={replyBody}
                  />
                )}
              </Field>
              <div className={styles.composerSubmit}>
                <Button loading={busy} loadingLabel="전송 중" type="submit">
                  답글 보내기
                </Button>
              </div>
            </form>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function WorldFeedLoading() {
  return (
    <div aria-live="polite" className={styles.loadingState} data-social-feed-loading>
      <span>World Feed를 불러오는 중</span>
      <div aria-hidden="true" className={styles.loadingRow} />
      <div aria-hidden="true" className={styles.loadingRow} />
    </div>
  );
}

function WorldFeedFailure({
  failure,
  onRetry,
}: {
  failure: FeedFailure;
  onRetry: () => void;
}) {
  const action = failure.retryable ? (
    <Button onClick={onRetry} variant="secondary">
      다시 시도
    </Button>
  ) : undefined;
  if (failure.kind === "offline" || failure.kind === "scope_mismatch") {
    return (
      <DegradedPanel
        action={action}
        description={failure.message}
        title={
          failure.kind === "offline"
            ? "로컬 runtime에 연결할 수 없어요"
            : "World 경계를 확인했어요"
        }
      />
    );
  }
  return (
    <EmptyState
      action={action}
      description={failure.message}
      title={
        failure.kind === "forbidden"
          ? "이 Feed를 볼 권한이 없어요"
          : failure.kind === "not_found"
            ? "게시글을 찾을 수 없어요"
            : "World Feed를 열지 못했어요"
      }
    />
  );
}
