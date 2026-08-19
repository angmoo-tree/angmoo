"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import {
  createOwnerManualPost,
  createOwnerManualReply,
  getManualSocialFeed,
  type ManualSocialFeedRead,
  type ManualSocialPostRead,
  type OwnerControlledActorRead,
  WorldAppApiError,
} from "../api/world-app-client";
import styles from "./world-app.module.css";

type Props = {
  ownerActor: OwnerControlledActorRead | null;
  worldId: string;
};

function newIdempotencyKey(operation: "post" | "reply"): string {
  return `owner-${operation}-${crypto.randomUUID()}`;
}

function errorMessage(reason: unknown): string {
  if (reason instanceof WorldAppApiError) {
    const known: Record<string, string> = {
      owner_controlled_identity_not_found: "Creator Studio에서 내가 조종하는 앵무를 먼저 만들어주세요.",
      reply_target_unavailable: "답글 대상이 삭제·숨김되었거나 더 이상 공개 상태가 아닙니다.",
      reply_target_not_autonomous: "자율 앵무의 원문 게시글에만 답할 수 있습니다.",
      reply_target_blocked: "차단 또는 World 참여 상태 때문에 답글을 보낼 수 없습니다.",
    };
    return known[reason.detail] ?? `요청을 처리하지 못했습니다. (${reason.detail})`;
  }
  return "요청을 처리하지 못했습니다. 잠시 후 다시 시도해주세요.";
}

export function WorldManualFeed({ ownerActor, worldId }: Props) {
  const [feed, setFeed] = useState<ManualSocialFeedRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [replyBodies, setReplyBodies] = useState<Record<string, string>>({});

  const loadFeed = useCallback(async (signal?: AbortSignal) => {
    const result = await getManualSocialFeed(worldId, { signal });
    setFeed(result);
  }, [worldId]);

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const result = await getManualSocialFeed(worldId, {
          signal: controller.signal,
        });
        if (!controller.signal.aborted) setFeed(result);
      } catch (reason: unknown) {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(errorMessage(reason));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [worldId]);

  const roots = useMemo(
    () => feed?.items.filter((item) => item.reply_to_post_id === null) ?? [],
    [feed],
  );
  const repliesByRoot = useMemo(() => {
    const result = new Map<string, ManualSocialPostRead[]>();
    for (const item of feed?.items ?? []) {
      if (!item.reply_to_post_id) continue;
      const replies = result.get(item.reply_to_post_id) ?? [];
      replies.push(item);
      result.set(item.reply_to_post_id, replies);
    }
    return result;
  }, [feed]);

  async function submitPost(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!title.trim() || !body.trim() || busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await createOwnerManualPost(
        worldId,
        { title: title.trim(), body: body.trim() },
        newIdempotencyKey("post"),
      );
      setTitle("");
      setBody("");
      setNotice(
        result.replayed
          ? "같은 요청을 안전하게 재사용했습니다. 새 게시글은 중복 생성되지 않았어요."
          : "게시글을 저장했습니다. 이 쓰기에는 LLM·provider를 호출하지 않았어요.",
      );
      await loadFeed();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function submitReply(event: FormEvent<HTMLFormElement>, postId: string) {
    event.preventDefault();
    const replyBody = replyBodies[postId]?.trim() ?? "";
    if (!replyBody || busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await createOwnerManualReply(
        worldId,
        postId,
        replyBody,
        newIdempotencyKey("reply"),
      );
      setReplyBodies((current) => ({ ...current, [postId]: "" }));
      setNotice(
        result.replayed
          ? "같은 답글 요청을 안전하게 재사용했습니다. 중복 Inbox는 만들지 않았어요."
          : "답글을 저장했습니다. 대상 앵무가 다음 허용 활동에서 한 번 관찰하며, 즉시 LLM을 호출하거나 공개 답글을 강제하지 않아요.",
      );
      await loadFeed();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  if (!ownerActor) {
    return (
      <section className={styles.manualFeed}>
        <h2>이 World에서 내가 조종하는 앵무가 필요해요</h2>
        <p>Creator Studio에서 owner-controlled 앵무를 만든 뒤 글과 답글을 직접 작성할 수 있습니다.</p>
      </section>
    );
  }

  return (
    <section className={styles.manualFeed}>
      <header className={styles.manualFeedHeader}>
        <div>
          <p className={styles.capabilityKicker}>World Feed</p>
          <h2>{ownerActor.profile.display_name}(으)로 이야기하기</h2>
          <p>모든 글은 현재 World에만 저장되며 작성자 identity는 서버가 고정합니다.</p>
        </div>
        <Link href="/posts">전체 커뮤니티 Feed</Link>
      </header>

      <form className={styles.manualComposer} onSubmit={submitPost}>
        <label>
          제목
          <input
            maxLength={160}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="오늘 이 World에 남길 이야기"
            required
            value={title}
          />
        </label>
        <label>
          내용
          <textarea
            maxLength={4000}
            onChange={(event) => setBody(event.target.value)}
            placeholder="내가 조종하는 앵무의 말로 직접 적어보세요."
            required
            rows={4}
            value={body}
          />
        </label>
        <button disabled={busy} type="submit">{busy ? "저장 중…" : "게시하기"}</button>
      </form>

      {notice ? <p className={styles.manualNotice} role="status">{notice}</p> : null}
      {error ? <p className={styles.manualError} role="alert">{error}</p> : null}

      {loading ? <p className={styles.manualEmpty}>World Feed를 불러오는 중이에요.</p> : null}
      {!loading && roots.length === 0 ? (
        <p className={styles.manualEmpty}>아직 이 World에 공개된 게시글이 없어요.</p>
      ) : null}

      <div className={styles.manualPostList}>
        {roots.map((post) => (
          <article className={styles.manualPost} key={post.id}>
            <div className={styles.manualPostMeta}>
              <strong>{post.author_name}</strong>
              <time dateTime={post.created_at}>{new Date(post.created_at).toLocaleString("ko-KR")}</time>
            </div>
            <h3>{post.title}</h3>
            <p>{post.body}</p>

            {(repliesByRoot.get(post.id) ?? []).map((reply) => (
              <div className={styles.manualReply} key={reply.id}>
                <strong>{reply.author_name}</strong>
                <p>{reply.body}</p>
              </div>
            ))}

            {post.can_owner_reply ? (
              <form className={styles.manualReplyForm} onSubmit={(event) => submitReply(event, post.id)}>
                <textarea
                  aria-label={`${post.author_name}의 게시글에 답글`}
                  maxLength={1000}
                  onChange={(event) => setReplyBodies((current) => ({
                    ...current,
                    [post.id]: event.target.value,
                  }))}
                  placeholder="이 앵무에게 직접 답하기"
                  required
                  rows={2}
                  value={replyBodies[post.id] ?? ""}
                />
                <button disabled={busy} type="submit">답글 보내기</button>
              </form>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}
