"use client";
import { useProductLeaveGuard } from "@/hooks/use-product-leave-guard";
import { useUiText } from "@/hooks/use-ui-text";
import { buildReplyTree } from "../utils/reply-tree";
import { SocialReplyTree } from "./social-reply-tree";
import { useOwnerReactions } from "../hooks/use-owner-reactions";
import { applyConfirmedReaction } from "../utils/confirmed-reactions";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { useUiDateFormatter } from "@/hooks/use-ui-date-formatter";


import { ArrowLeft, RefreshCw, Send } from "lucide-react";
import Link from "next/link";
import {
  type ComponentType,
  type FormEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { useElementVisibility } from "@/hooks/use-element-visibility";
import { useReadAnchor } from "@/hooks/use-read-anchor";
import { useMobilePullToRefresh } from "@/hooks/use-mobile-pull-to-refresh";
import { worldAppRoute, worldPostDetailRoute, worldCharacterProfileRoute } from "@/lib/navigation/product-routes";
import { Button, IconButton } from "@/components/ui/button";
import { formatHandle } from "@/utils/profile-presentation";
import { DegradedPanel, EmptyState, InlineError, Toast } from "@/components/ui/feedback";
import { Field, Input, Textarea } from "@/components/ui/form-controls";
import { ProfileAvatar } from "@/components/ui/profile-avatar";
import { createOwnerManualPost, createOwnerManualReply, getManualSocialPostSummary, getManualSocialFeed, getManualSocialPostThread, SocialWriteApiError } from "@/features/social/api/social-write-client";
import type { SocialPostActionPresentation, SocialPostPresentation } from "@/features/social/types/social-presentation-contract";
import type { ManualSocialFeedRead, ManualSocialThreadRead, ManualSocialPostRead, SocialOwnerActor } from "@/features/social/types/social-write-contract";
import { SocialPostRow } from "@/features/social/components/social-post-row";
import styles from "./world-social-feed.module.css";

type Props = {
  ownerActor: SocialOwnerActor | null;
  postId?: string;
  worldId: string;
  feedHeader?: ReactNode;
  renderImagePicker?: (input: { disabled: boolean; value: { id: string; url: string; allowed: boolean } | null; onChange: (value: { id: string; url: string; allowed: boolean } | null) => void; onBusyChange: (busy: boolean) => void; renderLayout: (slots: { trigger: ReactNode; preview: ReactNode; feedback: ReactNode }) => ReactNode }) => ReactNode;
  imageStatus?: ComponentType<{ worldId: string; postId: string; hasResult?: boolean; onCompleted: () => void }>;
};

type PendingPost = {
  idempotencyKey: string;
  title: string;
  body: string;
  assetId?: string;
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
  | { key: string; status: "ready"; feed: ManualSocialFeedRead | ManualSocialThreadRead }
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

function presentManualPost(post: ManualSocialPostRead, formatDate: (value: string) => string): SocialPostPresentation {
  return {
    id: post.id,
    authorAvatarUrl: post.author_avatar_url,
    authorHandle: post.author_handle,
    authorName: post.author_name,
    authorDeleted: post.author_deleted,
    createdAt: post.created_at,
    timeLabel: formatDate(post.created_at),
    title: post.post_type === "reply" ? "" : post.title,
    body: post.body,
    media: post.media,
  };
}

function aggregateManualPostActions(
  post: ManualSocialPostRead,
  replyHref?: string,
  pending = false,
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
    interaction: post.can_owner_like && post.reaction_world_id && post.reaction_owner_world_character_id && post.viewer_like_state !== "unavailable" && post.viewer_like_state !== undefined ? "button" : "metric",
    label: "좋아요",
    count: post.like_count,
    accent: post.viewer_like_state === "liked",
    disabled: pending,
  });
  return actions;
}

export function WorldSocialFeed({ ownerActor, postId, worldId, feedHeader, renderImagePicker, imageStatus: ImageStatus }: Props) {
  const formatDate = useUiDateFormatter();
  const uiText = useUiText("social");
  const routeKey = `${worldId}:${postId ?? "feed"}:${ownerActor?.world_character_id ?? "none"}`;
  const [loadState, setLoadState] = useState<FeedLoadState>({
    key: routeKey,
    status: "loading",
  });
  const [busy, setBusy] = useState(false);
  const [readBusy, setReadBusy] = useState(false);
  const [readFailure, setReadFailure] = useState<{kind: "refresh" | "append" | "summary"; id?: string} | null>(null);
  const reads = useRef(new Set<AbortController>());
  const pageFlight = useRef<AbortController | null>(null);
  const summaryVersions = useRef(new Map<string, number>());
  const mutationReads = useRef(0);
  const surfaceRef = useRef<HTMLElement>(null);
  const { remember: rememberAnchor } = useReadAnchor(surfaceRef, "[data-social-post-row]", "data-social-post-row", routeKey);
  const { ref: moreRef, visible: moreVisible } = useElementVisibility<HTMLDivElement>({ margin: 600 });
  const moreArmed = useRef(true);
  const [writeError, setWriteError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [attachment, setAttachment] = useState<{ id: string; url: string; allowed: boolean } | null>(null);
  const [imageBusy, setImageBusy] = useState(false);
  const [replyBody, setReplyBody] = useState("");
  useProductLeaveGuard(Boolean(title.trim() || body.trim() || replyBody.trim() || attachment || imageBusy || busy));
  const pendingPostRef = useRef<PendingPost | null>(null);
  const pendingRepliesRef = useRef(new Map<string, PendingReply>());
  const requestGenerationRef = useRef(0);
  const mutationGenerationRef = useRef(0);
  const replyTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const reactions = useOwnerReactions(routeKey, change => {
    setLoadState(current => {
      if (current.key !== routeKey || current.status !== "ready") return current;
      const feed = current.feed;
      return { ...current, feed: "selected_post" in feed
        ? { ...feed, selected_post: applyConfirmedReaction(feed.selected_post, change), replies: feed.replies.map(post => applyConfirmedReaction(post, change)) }
        : { ...feed, items: feed.items.map(post => applyConfirmedReaction(post, change)) } };
    });
  }, worldId);
  const { captureReadRevision, reconcilePost } = reactions;

  const currentState = useMemo<FeedLoadState>(
    () =>
      loadState.key === routeKey
        ? loadState
        : { key: routeKey, status: "loading" },
    [loadState, routeKey],
  );

  const loadFeed = useCallback(
    async (signal?: AbortSignal, offset?: number, cursor?: string) => {
      if (!ownerActor || (pageFlight.current && !pageFlight.current.signal.aborted)) return;
      const controller = new AbortController();
      pageFlight.current = controller;
      reads.current.add(controller);
      const abort = () => controller.abort();
      signal?.addEventListener("abort", abort, { once: true });
      if (signal?.aborted) controller.abort();
      setReadBusy(true); setReadFailure(null);
      const mutationAtStart = mutationReads.current;
      const summariesAtStart = new Map(summaryVersions.current);
      const generation = ++requestGenerationRef.current;
      const authScope = captureAuthRequestScope();
      const readRevision = captureReadRevision();
      setLoadState(current => current.key === routeKey && current.status === "ready" ? current : { key: routeKey, status: "loading" });
      try {
        const result = postId
          ? await getManualSocialPostThread(worldId, postId, {
              ownerWorldCharacterId: ownerActor.world_character_id,
              signal: controller.signal,
              offset,
            })
          : await getManualSocialFeed(worldId, {
              ownerWorldCharacterId: ownerActor.world_character_id,
              signal: controller.signal, cursor,
            });
        if (generation !== requestGenerationRef.current || controller.signal.aborted || !isCurrentAuthRequestScope(authScope)) return;
        const feed = "selected_post" in result
          ? { ...result, selected_post: reconcilePost(result.selected_post, readRevision), replies: result.replies.map(post => reconcilePost(post, readRevision)) }
          : { ...result, items: result.items.map(post => reconcilePost(post, readRevision)) };
        rememberAnchor();
        setLoadState(current => {
          if (current.key === routeKey && current.status === "ready" && !("selected_post" in current.feed) && !("selected_post" in feed)) {
            const incoming = new Map(feed.items.map(p => [p.id, p]));
            if (cursor) {
              const merged = current.feed.items.map(p => summaryVersions.current.get(p.id) !== summariesAtStart.get(p.id) ? p : incoming.get(p.id) ?? p);
              const ids = new Set(merged.map(p => p.id));
              return { key: routeKey, status: "ready", feed: { ...feed, items: [...merged, ...feed.items.filter(p => !ids.has(p.id))] } };
            }
            // A successful local write/summary arriving during refresh wins.
            if (mutationReads.current !== mutationAtStart) return current;
          }
          return { key: routeKey, status: "ready", feed };
        });
      } catch (reason: unknown) {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        if (generation !== requestGenerationRef.current || controller.signal.aborted || !isCurrentAuthRequestScope(authScope)) return;
        setReadFailure({ kind: cursor ? "append" : "refresh" });
        setLoadState(current => current.key === routeKey && current.status === "ready" ? current : { key: routeKey, status: "error", failure: feedFailure(reason) });
      } finally {
        signal?.removeEventListener("abort", abort);
        reads.current.delete(controller); if (pageFlight.current === controller) pageFlight.current = null;
        if (generation === requestGenerationRef.current) setReadBusy(false);
      }
    },
    [ownerActor, postId, routeKey, worldId, captureReadRevision, reconcilePost, rememberAnchor],
  );

  useEffect(() => {
    if (!ownerActor) return;
    const controller = new AbortController();
    const ownedReads = reads.current, ownedVersions = summaryVersions.current;
    const startTimer = window.setTimeout(() => {
      void loadFeed(controller.signal);
    }, 0);
    return () => {
      window.clearTimeout(startTimer);
      requestGenerationRef.current += 1;
      controller.abort();
      for (const read of ownedReads) read.abort();
      ownedReads.clear(); ownedVersions.clear();
    };
  }, [loadFeed, ownerActor]);

  useEffect(() => {
    const ownedGeneration = ++mutationGenerationRef.current;
    return () => {
      mutationGenerationRef.current = ownedGeneration + 1;
    };
  }, [routeKey]);

  useMobilePullToRefresh({
    enabled: Boolean(ownerActor),
    refreshing: readBusy,
    onRefresh: loadFeed,
  });

  const items = useMemo(
    () => (currentState.status === "ready" ? "selected_post" in currentState.feed ? [currentState.feed.selected_post, ...currentState.feed.replies] : currentState.feed.items : []),
    [currentState],
  );
  const roots = useMemo(
    () => items.filter((item) => item.reply_to_post_id === null),
    [items],
  );
  const detailPage = postId && currentState.status === "ready" && "selected_post" in currentState.feed ? currentState.feed : null;
  const detailRoot = detailPage?.selected_post ?? null;
  const detailReplies = detailRoot ? items.slice(1) : [];

  useEffect(() => {
    if (!postId || currentState.status !== "ready") return;
    document.getElementById(`world-reply-${postId}`)?.scrollIntoView({ block: "center" });
  }, [postId, currentState]);

  const page = currentState.status === "ready" && !("selected_post" in currentState.feed) ? currentState.feed : null;
  useEffect(() => {
    if (!moreVisible) { moreArmed.current = true; return; }
    if (moreArmed.current && page?.has_more && !readBusy && !readFailure) {
      moreArmed.current = false;
      void loadFeed(undefined, undefined, page.next_cursor!);
    }
  }, [moreVisible, page, readBusy, readFailure, loadFeed]);

  async function refreshPost(id: string) {
    if (!ownerActor) return;
    if (postId) { await loadFeed(undefined, currentState.status === "ready" && "selected_post" in currentState.feed ? currentState.feed.page_offset : 0); return; }
    const controller = new AbortController(), auth = captureAuthRequestScope();
    reads.current.add(controller);
    const version = (summaryVersions.current.get(id) ?? 0) + 1;
    summaryVersions.current.set(id, version);
    const revision = captureReadRevision();
    try {
      const result = reconcilePost(await getManualSocialPostSummary(worldId, id, { signal: controller.signal, ownerWorldCharacterId: ownerActor.world_character_id }), revision);
      if (controller.signal.aborted || !isCurrentAuthRequestScope(auth) || summaryVersions.current.get(id) !== version) return;
      ++mutationReads.current; rememberAnchor();
      setLoadState(current => {
        if (current.key !== routeKey || current.status !== "ready" || "selected_post" in current.feed) return current;
        const exists = current.feed.items.some(p => p.id === id);
        return { ...current, feed: { ...current.feed, items: exists ? current.feed.items.map(p => p.id === id ? result : p) : [result, ...current.feed.items] } };
      });
      setReadFailure(null);
    } catch {
      if (!controller.signal.aborted && isCurrentAuthRequestScope(auth)) setReadFailure({ kind: "summary", id });
    } finally { reads.current.delete(controller); }
  }

  async function submitPost(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ownerActor) return;
    const nextTitle = title.trim();
    const nextBody = body.trim();
    if (!nextTitle || !nextBody || busy || imageBusy) return;
    const generation = mutationGenerationRef.current;
    const authScope = captureAuthRequestScope();
    const previous = pendingPostRef.current;
    const pending =
      previous?.title === nextTitle && previous.body === nextBody && previous.assetId === attachment?.id
        ? previous
        : {
            idempotencyKey: newIdempotencyKey("post"),
            title: nextTitle,
            body: nextBody,
            assetId: attachment?.id,
          };
    pendingPostRef.current = pending;
    setBusy(true);
    setWriteError(null);
    setNotice(null);
    try {
      const result = await createOwnerManualPost(
        worldId,
        { title: pending.title, body: pending.body, ...(pending.assetId ? { attachment_asset_id: pending.assetId } : {}) },
        pending.idempotencyKey,
        ownerActor.world_character_id,
      );
      if (generation !== mutationGenerationRef.current || !isCurrentAuthRequestScope(authScope)) return;
      pendingPostRef.current = null;
      setTitle("");
      setBody("");
      setAttachment(null);
      setNotice(
        result.replayed
          ? uiText("같은 요청을 안전하게 재사용했습니다. 게시글은 중복 생성되지 않았어요.")
          : uiText("게시글을 저장했습니다."),
      );
      await refreshPost(result.post.reply_to_post_id ?? result.post.id);
    } catch (reason) {
      if (generation === mutationGenerationRef.current && isCurrentAuthRequestScope(authScope)) setWriteError(writeErrorMessage(reason));
    } finally {
      if (generation === mutationGenerationRef.current && isCurrentAuthRequestScope(authScope)) setBusy(false);
    }
  }

  async function submitReply(event: FormEvent<HTMLFormElement>, rootPostId: string) {
    event.preventDefault();
    if (!ownerActor) return;
    const nextBody = replyBody.trim();
    if (!nextBody || busy) return;
    const generation = mutationGenerationRef.current;
    const authScope = captureAuthRequestScope();
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
      if (generation !== mutationGenerationRef.current || !isCurrentAuthRequestScope(authScope)) return;
      pendingRepliesRef.current.delete(rootPostId);
      setReplyBody("");
      setNotice(
        result.replayed
          ? uiText("같은 답글 요청을 안전하게 재사용했습니다. 중복 Inbox는 만들지 않았어요.")
          : uiText("답글을 저장했습니다. 대상 앵무는 다음 허용 활동에서 관찰하며, 공개 반응은 강제되지 않아요."),
      );
      await refreshPost(result.post.reply_to_post_id ?? result.post.id);
      window.requestAnimationFrame(() => replyTextareaRef.current?.focus());
    } catch (reason) {
      if (generation === mutationGenerationRef.current && isCurrentAuthRequestScope(authScope)) setWriteError(writeErrorMessage(reason));
    } finally {
      if (generation === mutationGenerationRef.current && isCurrentAuthRequestScope(authScope)) setBusy(false);
    }
  }

  const publishButton = (
    <IconButton className={styles.publishButton} type="submit" variant="primary"
      label={uiText("게시하기")} title={busy ? uiText("저장 중") : uiText("게시하기")}
      loading={busy} loadingLabel={uiText("저장 중")}
      disabled={!title.trim() || !body.trim() || imageBusy}>
      <Send size={22} aria-hidden="true" />
    </IconButton>
  );

  if (!ownerActor) {
    return (
      <section className={styles.manualFeed}>
        {!postId ? <div className={styles.feedHeader}>{feedHeader}</div> : null}
        <EmptyState
          description={uiText("Creator Studio에서 owner-controlled 앵무를 만든 뒤 이 World에 글과 답글을 남길 수 있습니다.")}
          title={uiText("이 World에서 내가 조종할 앵무가 필요해요")}
        />
      </section>
    );
  }

  return (
    <section
      className={styles.manualFeed}
      ref={surfaceRef}
      data-world-social-surface={postId ? "detail" : "feed"}
    >
      {!postId ? <div className={styles.feedHeader}>{feedHeader}</div> : (
      <header className={styles.contextHeader}>
        <div className={styles.headerStart}>
        <Link aria-label={uiText("피드로 돌아가기")} className={styles.backLink} href={`${worldAppRoute(worldId)}/feed`}>
          <ArrowLeft aria-hidden="true" size={22} />
        </Link>
        <div className={styles.contextCopy}>
          <h2>{uiText("게시글")}</h2>
        </div>
        </div>
        <div className={styles.headerActions}>
          <IconButton label={uiText("새로고침")} onClick={() => void loadFeed()} disabled={readBusy}>
            <RefreshCw aria-hidden="true" size={22} />
          </IconButton>
        </div>
      </header>
      )}

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
              {ownerActor.profile.handle ? <span>{formatHandle(ownerActor.profile.handle)}</span> : null}
            </div>
            <label className={styles.visuallyHidden} htmlFor="world-owner-post-title">
              {uiText("제목")}</label>
            <Input
              className={styles.composerTitle}
              id="world-owner-post-title"
              maxLength={160}
              onChange={(event) => setTitle(event.target.value)}
              placeholder={uiText("오늘 이 World에 남길 이야기의 제목을 적어주세요")}
              required
              readOnly={busy}
              value={title}
            />
            <label className={styles.visuallyHidden} htmlFor="world-owner-post-body">
              {uiText("내용")}</label>
            <Textarea
              className={styles.composerBody}
              id="world-owner-post-body"
              maxLength={4000}
              onChange={(event) => setBody(event.target.value)}
              placeholder={uiText("본문을 적어주세요")}
              required
              readOnly={busy}
              rows={3}
              value={body}
            />
            {renderImagePicker ? renderImagePicker({
              value: attachment, disabled: busy, onChange: setAttachment, onBusyChange: setImageBusy,
              renderLayout: ({ trigger, preview, feedback }) => (
                <>
                  {preview}
                  {feedback}
                  <div className={styles.composerActions}>
                    {trigger}
                    {publishButton}
                  </div>
                </>
              ),
            }) : <div className={`${styles.composerActions} ${styles.submitOnly}`}>{publishButton}</div>}
          </div>
        </form>
      ) : null}

      {notice ? <Toast tone="success">{notice}</Toast> : null}
      {writeError ? <InlineError>{writeError}</InlineError> : null}
      {readFailure && currentState.status === "ready" ? <InlineError>
        {uiText("조회하지 못했습니다. 저장된 내용은 유지됩니다.")}
        <Button variant="ghost" onClick={() => readFailure.kind === "summary" ? void refreshPost(readFailure.id!) : void loadFeed(undefined, undefined, readFailure.kind === "append" ? page?.next_cursor ?? undefined : undefined)}>{uiText("조회 다시 시도")}</Button>
      </InlineError> : null}
      {reactions.error ? <InlineError>{uiText("좋아요를 저장하지 못했습니다. 다시 시도해 주세요.")}</InlineError> : null}

      {currentState.status === "loading" ? <WorldFeedLoading /> : null}
      {currentState.status === "error" ? (
        <WorldFeedFailure
          failure={currentState.failure}
          onRetry={() => void loadFeed()}
        />
      ) : null}

      {currentState.status === "ready" && items.length === 0 ? (
        <EmptyState
          description={
            postId
              ? uiText("게시글이 제거됐거나 이 World에서 더 이상 공개되지 않습니다.")
              : uiText("자율 앵무 또는 내가 조종하는 앵무의 첫 이야기를 기다리고 있어요.")
          }
          title={postId ? uiText("게시글을 찾을 수 없어요") : uiText("아직 공개된 게시글이 없어요")}
        />
      ) : null}

      {currentState.status === "ready" && !postId ? (
        <div className={styles.socialStream} data-social-stream="world">
          {roots.map((post) => {
            const detailHref = worldPostDetailRoute(worldId, post.id);
            const authorHref =
              post.author_profile_capability === "available"
                ? worldCharacterProfileRoute(worldId, post.author_world_character_id)
                : undefined;
            return (
              <VisibleFeedItem key={post.id} status={ImageStatus} worldId={worldId} post={post} onCompleted={() => void refreshPost(post.id)}><SocialPostRow
                deferMedia
                actions={aggregateManualPostActions(post, detailHref, reactions.likeAction(post).disabled)}
                onAction={() => void reactions.setReaction(post)}
                authorHref={authorHref}
                href={detailHref}
                key={post.id}
                post={presentManualPost(post, formatDate)}
              /></VisibleFeedItem>
            );
          })}
        </div>
      ) : null}

      {!postId && page ? <div ref={moreRef}>
        {page.has_more ? <Button variant="ghost" disabled={readBusy} onClick={() => void loadFeed(undefined, undefined, page.next_cursor!)}>{uiText(readBusy ? "게시글을 불러오는 중…" : "게시글 더 보기")}</Button> : page.items.length ? <p>{uiText("모든 게시글을 확인했습니다.")}</p> : null}
      </div> : null}
      {currentState.status === "ready" && detailRoot ? (
        <div className={styles.detailSurface}>
          <SocialPostRow
            actions={aggregateManualPostActions(
              detailRoot,
              worldPostDetailRoute(worldId, detailRoot.id),
              reactions.likeAction(detailRoot).disabled,
            )}
            onAction={() => void reactions.setReaction(detailRoot)}
            authorHref={
              detailRoot.author_profile_capability === "available"
                ? worldCharacterProfileRoute(
                    worldId,
                    detailRoot.author_world_character_id,
                  )
                : undefined
            }
            post={presentManualPost(detailRoot, formatDate)}
            variant="detail"
          />
          {ImageStatus && (!detailRoot.media?.length || detailRoot.media.some(item => item.source_kind === "generated")) ? <ImageStatus worldId={worldId} postId={detailRoot.id} hasResult={Boolean(detailRoot.media?.length)} onCompleted={() => void loadFeed(undefined, currentState.status === "ready" && "selected_post" in currentState.feed ? detailPage?.page_offset ?? 0 : 0)} /> : null}
          {detailRoot.reply_to_post_id && currentState.feed.schema_version === "owner-manual-social-thread-v2" ? (
            currentState.feed.parent?.state === "available" ? <Link className={styles.parentReply} href={worldPostDetailRoute(worldId, detailRoot.reply_to_post_id)}>{uiText("부모 게시글 보기")}</Link> : <p className={styles.parentReply}>{uiText("부모 게시글을 볼 수 없습니다.")}</p>
          ) : null}
          <section aria-labelledby="world-reply-heading" className={styles.replySection}>
            <h3 id="world-reply-heading">{uiText("답글 {{count}}", { count: detailRoot.reply_count })}</h3>
            {detailReplies.length > 0 ? (
              <div className={styles.replyList}>
                <SocialReplyTree nodes={buildReplyTree(detailReplies, detailRoot.id)} renderRow={reply => (
                  <article key={reply.id} id={`world-reply-${reply.id}`} tabIndex={-1}
                    className={reply.id === postId ? styles.targetReply : undefined}
                    aria-label={reply.id === postId ? uiText("근거가 가리키는 답글") : undefined}>
                    {reply.reply_to_post_id !== detailRoot.id ? (
                      currentState.feed.schema_version === "owner-manual-social-thread-v2" && currentState.feed.parent_references.find(parent => parent.post_id === reply.reply_to_post_id)?.state === "unavailable" ?
                      <p className={styles.parentReply}>{uiText("부모 게시글을 볼 수 없습니다.")}</p> :
                      <Link className={styles.parentReply} href={worldPostDetailRoute(worldId, reply.reply_to_post_id!)}>
                        {uiText("부모 게시글 보기")}</Link>
                    ) : null}
                  <SocialPostRow
                    actions={aggregateManualPostActions(reply, worldPostDetailRoute(worldId, reply.id), reactions.likeAction(reply).disabled)}
                    onAction={() => void reactions.setReaction(reply)}
                    href={worldPostDetailRoute(worldId, reply.id)}
                    authorHref={
                      reply.author_profile_capability === "available"
                        ? worldCharacterProfileRoute(
                            worldId,
                            reply.author_world_character_id,
                          )
                        : undefined
                    }
                    key={reply.id}
                    post={presentManualPost(reply, formatDate)}
                    variant="reply"
                  />
                  </article>
                )} />
              </div>
            ) : (
              <p className={styles.noReplies}>{uiText("아직 공개된 답글이 없어요.")}</p>
            )}
            <div className={styles.threadPages}>
              {(detailPage?.page_offset ?? 0) > 0 ? (
                <Button onClick={() => void loadFeed(undefined, Math.max(0, (detailPage?.page_offset ?? 0) - 50))}>{uiText("이전 답글")}</Button>
              ) : null}
              {detailPage?.next_offset != null ? (
                <Button onClick={() => void loadFeed(undefined, detailPage?.next_offset ?? undefined)}>{uiText("다음 답글")}</Button>
              ) : null}
            </div>
          </section>
          {detailRoot.can_owner_reply ? (
            <form className={`${styles.replyComposer} ${styles.manualComposer}`} onSubmit={(event) => submitReply(event, detailRoot.id)}>
              <ProfileAvatar avatarUrl={ownerActor.profile.avatar_url} name={ownerActor.profile.display_name} sizeClassName={styles.composerAvatar} textClassName={styles.composerAvatarText} />
              <div className={styles.composerContent}>
                <div className={styles.composerHeading}><strong>{ownerActor.profile.display_name}</strong>{ownerActor.profile.handle ? <span>{formatHandle(ownerActor.profile.handle)}</span> : null}</div>
                <Field label={uiText("답글")} labelVisibility="sr-only" required>
                  {(fieldProps) => <Textarea {...fieldProps} maxLength={1000} onChange={event => setReplyBody(event.target.value)} ref={replyTextareaRef} rows={3} value={replyBody} readOnly={busy} />}
                </Field>
                <div className={styles.composerActions}><IconButton type="submit" variant="primary" className={styles.publishButton} label={uiText("답글 보내기")} title={uiText("답글 보내기")} loading={busy} loadingLabel={uiText("전송 중")} disabled={!replyBody.trim()}><Send size={22} aria-hidden="true" /></IconButton></div>
              </div>
            </form>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function WorldFeedLoading() {
  const uiText = useUiText("social");
  return (
    <div aria-live="polite" className={styles.loadingState} data-social-feed-loading>
      <span>{uiText("World Feed를 불러오는 중")}</span>
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
  const uiText = useUiText("social");
  const action = failure.retryable ? (
    <Button onClick={onRetry} variant="secondary">
      {uiText("다시 시도")}</Button>
  ) : undefined;
  if (failure.kind === "offline" || failure.kind === "scope_mismatch") {
    return (
      <DegradedPanel
        action={action}
        description={failure.message}
        title={
          failure.kind === "offline"
            ? uiText("로컬 runtime에 연결할 수 없어요")
            : uiText("World 경계를 확인했어요")
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
          ? uiText("이 Feed를 볼 권한이 없어요")
          : failure.kind === "not_found"
            ? uiText("게시글을 찾을 수 없어요")
            : uiText("World Feed를 열지 못했어요")
      }
    />
  );
}

// LOCAL: visibility owns only the status reader, never the server generation job.
function VisibleFeedItem({ children, status: Status, worldId, post, onCompleted }: {
  children: ReactNode; status: Props["imageStatus"]; worldId: string; post: ManualSocialPostRead; onCompleted: () => void;
}) {
  const { ref, visible } = useElementVisibility<HTMLDivElement>({ margin: 600 });
  return <div ref={ref}>{children}{visible && Status && (!post.media?.length || post.media.some(m => m.source_kind === "generated")) ?
    <Status worldId={worldId} postId={post.id} hasResult={Boolean(post.media?.length)} onCompleted={onCompleted} /> : null}</div>;
}
