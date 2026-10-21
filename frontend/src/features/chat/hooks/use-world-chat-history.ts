"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { getWorldChatMessagePage } from "../api/world-chat-client";
import type { WorldChatGenerationRequestRead, WorldChatThreadRead } from "../types/world-chat-contract";

type Message = WorldChatThreadRead["messages"][number];
type Summary = WorldChatThreadRead["evidence_summaries"][number];
type Anchor = { id: string; offset: number };

function merge(current: WorldChatThreadRead, messages: Message[], evidence: Summary[] = []) {
  const items = new Map(current.messages.map(item => [item.id, item]));
  for (const item of messages) items.set(item.id, item);
  const summaries = new Map(current.evidence_summaries.map(item => [item.assistant_message_id, item]));
  for (const item of evidence) summaries.set(item.assistant_message_id, item);
  const sorted = [...items.values()].sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at) || a.id - b.id);
  return { ...current, messages: sorted, evidence_summaries: [...summaries.values()],
    latest_message: sorted.at(-1) ?? null, last_message_at: sorted.at(-1)?.created_at ?? current.last_message_at };
}

// LOCAL: one message state owner. Read cursors advance only from contiguous
// pages; a separately committed response never moves the catch-up boundary.
export function useWorldChatHistory(worldId: string, threadId: string) {
  const [thread, setThread] = useState<WorldChatThreadRead | null>(null);
  const [older, setOlder] = useState(false), [newer, setNewer] = useState(false);
  const [loading, setLoading] = useState<"before" | "after" | null>(null);
  const [error, setError] = useState<"before" | "after" | null>(null);
  const [unread, setUnread] = useState(false);
  const paneRef = useRef<HTMLDivElement>(null), topRef = useRef<HTMLDivElement>(null);
  const cursors = useRef({ before: null as string | null, after: null as string | null, overlap: null as string | null, moreAfter: false });
  const requests = useRef(new Set<AbortController>()), alive = useRef(true), ready = useRef(false);
  const following = useRef(true), anchor = useRef<Anchor | null>(null), autoArmed = useRef(true);
  const terminals = useRef(new Set<string>());
  const knownMessages = useRef(new Set<number>()), pendingAfter = useRef(false);

  const remember = useCallback(() => {
    const pane = paneRef.current;
    if (!pane) return;
    const bounds = pane.getBoundingClientRect();
    const first = [...pane.querySelectorAll<HTMLElement>("[data-message-id]")].find(node => node.getBoundingClientRect().bottom > bounds.top);
    anchor.current = first ? { id: first.dataset.messageId!, offset: first.getBoundingClientRect().top - bounds.top } : null;
  }, []);
  const restore = useCallback(() => {
    const pane = paneRef.current;
    if (!pane) return;
    if (following.current) pane.scrollTop = pane.scrollHeight;
    else if (anchor.current) {
      const node = pane.querySelector<HTMLElement>(`[data-message-id="${anchor.current.id}"]`);
      if (node) pane.scrollTop += node.getBoundingClientRect().top - pane.getBoundingClientRect().top - anchor.current.offset;
    }
  }, []);
  const onScroll = useCallback(() => {
    const pane = paneRef.current;
    if (!pane) return;
    following.current = pane.scrollHeight - pane.scrollTop - pane.clientHeight < 64;
    if (following.current) setUnread(false);
    remember();
  }, [remember]);
  const followLatest = useCallback(() => { following.current = true; setUnread(false); restore(); }, [restore]);
  const hydrate = useCallback((value: WorldChatThreadRead) => {
    const page = value.message_page;
    cursors.current = { before: page?.oldest_cursor ?? null, after: page?.newest_cursor ?? null,
      overlap: page?.oldest_cursor ?? page?.newest_cursor ?? null, moreAfter: false };
    ready.current = true;
    knownMessages.current = new Set(value.messages.map(message => message.id));
    setOlder(Boolean(page?.has_more)); setNewer(false); setError(null); setThread(value);
  }, []);
  const append = useCallback((messages: Message[], evidence: Summary[] = []) => {
    remember();
    if (!following.current && messages.some(message => !knownMessages.current.has(message.id))) setUnread(true);
    for (const message of messages) knownMessages.current.add(message.id);
    setThread(value => value ? merge(value, messages, evidence) : value);
  }, [remember]);
  const commit = useCallback((request: WorldChatGenerationRequestRead) => {
    if (request.state !== "committed" || !request.assistant_message ||
        request.user_message.thread_id !== threadId || request.assistant_message.thread_id !== threadId) throw new Error("chat_commit_projection_invalid");
    if (terminals.current.has(request.request_id)) return;
    terminals.current.add(request.request_id);
    append([request.user_message, request.assistant_message], request.evidence_summary ? [request.evidence_summary] : []);
  }, [append, threadId]);
  const cancel = useCallback(() => { pendingAfter.current = false; for (const controller of requests.current) controller.abort(); requests.current.clear(); }, []);
  const read = useCallback(async function readPages(direction: "before" | "after") {
    if (!ready.current || !alive.current) return;
    if (requests.current.size) { if (direction === "after") pendingAfter.current = true; return; }
    const controller = new AbortController(), auth = captureAuthRequestScope();
    requests.current.add(controller); setLoading(direction); setError(null);
    let cursor = direction === "before" ? cursors.current.before : cursors.current.moreAfter ? cursors.current.after : cursors.current.overlap;
    try {
      if (direction === "before" && !cursor) return;
      for (let pageNumber = 0; pageNumber < (direction === "after" ? 2 : 1); pageNumber += 1) {
        const page = await getWorldChatMessagePage(worldId, threadId, { signal: controller.signal,
          ...(cursor ? direction === "before" ? { before: cursor } : { after: cursor } : {}) });
        if (controller.signal.aborted || !alive.current || !isCurrentAuthRequestScope(auth)) return;
        remember(); // Capture where the reader is now, never the request-start position.
        if (direction === "after" && !following.current && page.items.some(message => !knownMessages.current.has(message.id))) setUnread(true);
        for (const message of page.items) knownMessages.current.add(message.id);
        setThread(value => value ? merge(value, page.items, page.evidence_summaries) : value);
        if (direction === "before") {
          cursors.current.before = page.oldest_cursor ?? cursors.current.before;
          setOlder(page.has_more);
          break;
        }
        // Only actual ordered rows advance the contiguous boundary, never a
        // separately committed response or an empty page's initial boundary.
        if (page.items.length && page.newest_cursor) cursors.current.after = page.newest_cursor;
        cursors.current.moreAfter = page.direction === "after" && page.has_more;
        setNewer(cursors.current.moreAfter);
        if (!cursors.current.moreAfter) {
          cursors.current.overlap = page.oldest_cursor ?? cursors.current.overlap;
          break;
        }
        cursor = page.next_cursor;
      }
    } catch {
      if (!controller.signal.aborted && alive.current && isCurrentAuthRequestScope(auth)) setError(direction);
    } finally {
      requests.current.delete(controller);
      if (alive.current) setLoading(null);
      if (pendingAfter.current && alive.current && !controller.signal.aborted && isCurrentAuthRequestScope(auth)) {
        pendingAfter.current = false;
        queueMicrotask(() => void readPages("after"));
      }
    }
  }, [remember, threadId, worldId]);
  useLayoutEffect(restore, [thread, restore]);
  const hasThread = thread !== null;
  useEffect(() => {
    alive.current = true;
    const refresh = () => { if (document.visibilityState === "visible") void read("after"); };
    window.addEventListener("online", refresh); window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => { alive.current = false; cancel(); window.removeEventListener("online", refresh); window.removeEventListener("focus", refresh); document.removeEventListener("visibilitychange", refresh); };
  }, [cancel, read]);
  useEffect(() => {
    const pane = paneRef.current, top = topRef.current;
    if (!pane || !top || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(entries => {
      if (!entries[0]?.isIntersecting) { autoArmed.current = true; return; }
      if (autoArmed.current && older && !error) { autoArmed.current = false; void read("before"); }
    }, { root: pane, rootMargin: "200px 0px 0px" });
    observer.observe(top);
    return () => observer.disconnect();
  }, [older, error, read, hasThread]);
  useEffect(() => {
    const pane = paneRef.current;
    if (!pane || typeof ResizeObserver === "undefined") return;
    let frame = 0;
    const observer = new ResizeObserver(() => { cancelAnimationFrame(frame); frame = requestAnimationFrame(restore); });
    observer.observe(pane);
    const list = pane.querySelector("ol"); if (list) observer.observe(list);
    return () => { observer.disconnect(); cancelAnimationFrame(frame); };
  }, [restore, hasThread]);
  return { thread, setThread, hydrate, append, commit, cancel, paneRef, topRef, onScroll,
    followLatest, restore, older, newer, loading, error, unread, read };
}
