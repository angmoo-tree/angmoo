"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { useRuntimePathname } from "@/hooks/use-runtime-navigation";
import { useUiText } from "@/hooks/use-ui-text";
import { AUTH_CHANGED_EVENT, captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT } from "@/lib/runtime/runtime-config";
import { deleteWorldChatThread, WorldChatApiError } from "@/features/chat/api/world-chat-client";
import type { WorldChatThreadDeleteRead } from "@/features/chat/types/world-chat-contract";

type DeleteTarget = { worldId: string; threadId: string; name: string };

export function useWorldChatDelete(
  onDeleted: (result: WorldChatThreadDeleteRead) => void,
  canDelete: () => boolean = () => true,
) {
  const pathname = useRuntimePathname();
  const [target, setTarget] = useState<(DeleteTarget & { pathname: string }) | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<WorldChatApiError | Error | null>(null);
  const lifetime = useRef(0);
  const admitted = useRef<{
    target: DeleteTarget;
    pathname: string;
    lifetime: number;
    auth: ReturnType<typeof captureAuthRequestScope>;
  } | null>(null);
  const pendingRef = useRef(false);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => {
    lifetime.current += 1;
    const invalidate = () => {
      if (admitted.current && isCurrentAuthRequestScope(admitted.current.auth)) return;
      lifetime.current += 1;
      controller.current?.abort();
      admitted.current = null;
      pendingRef.current = false;
      setTarget(null);
      setError(null);
      setPending(false);
    };
    window.addEventListener(AUTH_CHANGED_EVENT, invalidate);
    window.addEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, invalidate);
    return () => {
      lifetime.current += 1;
      controller.current?.abort();
      pendingRef.current = false;
      window.removeEventListener(AUTH_CHANGED_EVENT, invalidate);
      window.removeEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, invalidate);
    };
  }, [pathname]);

  const open = useCallback((value: DeleteTarget) => {
    if (pendingRef.current) return;
    admitted.current = { target: value, pathname, lifetime: lifetime.current, auth: captureAuthRequestScope() };
    setTarget({ ...value, pathname });
    setPending(false);
    setError(null);
  }, [pathname]);

  const close = useCallback(() => {
    if (pendingRef.current) return;
    admitted.current = null;
    setTarget(null);
    setError(null);
  }, []);

  const confirm = useCallback(async () => {
    const request = admitted.current;
    if (!request || request.pathname !== pathname || pendingRef.current || request.lifetime !== lifetime.current ||
        !isCurrentAuthRequestScope(request.auth)) return;
    if (!canDelete()) {
      setError(new WorldChatApiError(409, "world_chat_response_in_flight"));
      return;
    }
    pendingRef.current = true;
    setPending(true);
    setError(null);
    const active = new AbortController();
    controller.current = active;
    const current = () => !active.signal.aborted && request === admitted.current &&
      request.lifetime === lifetime.current && isCurrentAuthRequestScope(request.auth);
    try {
      const result = await deleteWorldChatThread(request.target.worldId, request.target.threadId, { signal: active.signal });
      if (!current()) return;
      admitted.current = null;
      setTarget(null);
      onDeleted(result);
    } catch (reason) {
      if (!current()) return;
      setError(reason instanceof Error ? reason : new Error("world_chat_delete_failed"));
    } finally {
      if (controller.current === active) {
        pendingRef.current = false;
        if (request.lifetime === lifetime.current) setPending(false);
      }
    }
  }, [canDelete, onDeleted, pathname]);

  const currentTarget = target?.pathname === pathname ? target : null;
  return { target: currentTarget, pending: Boolean(currentTarget) && pending,
    error: currentTarget ? error : null, open, close, confirm };
}

export function WorldChatDeleteDialog({ deletion, hasDraft = false }: {
  deletion: ReturnType<typeof useWorldChatDelete>;
  hasDraft?: boolean;
}) {
  const uiText = useUiText("chat");
  const cancelRef = useRef<HTMLButtonElement>(null);
  const { target, pending, error } = deletion;
  const errorText = error instanceof WorldChatApiError && error.status === 409
    ? uiText("답장을 처리하고 있어요. 완료된 뒤 다시 삭제해 주세요.")
    : error instanceof WorldChatApiError && error.status === 401
      ? uiText("대화를 삭제하려면 다시 로그인해 주세요.")
      : error instanceof WorldChatApiError && (error.status === 403 || error.status === 404)
        ? uiText("이 대화에 접근할 수 없어요. 현재 World와 권한을 확인해 주세요.")
        : uiText("삭제 결과를 확인하지 못했어요. 대화는 그대로 표시하며 같은 대상을 다시 확인할 수 있어요.");
  return <Dialog open={target !== null} title={uiText("대화 삭제")}
    onOpenChange={(value) => { if (!value) deletion.close(); }} initialFocusRef={cancelRef}
    closeOnBackdrop={!pending} closeOnEscape={!pending} closeButtonAttributes={{ disabled: pending }}
    dialogAttributes={{ "data-world-chat-delete-dialog": true }}
    actions={<>
      <Button ref={cancelRef} variant="secondary" disabled={pending} onClick={deletion.close}>{uiText("취소")}</Button>
      <Button variant="danger" loading={pending} loadingLabel={uiText("대화 삭제 중")}
        onClick={() => void deletion.confirm()}>{error ? uiText("같은 대화 다시 삭제") : uiText("삭제")}</Button>
    </>}>
    <p>{uiText("{{name}}와의 대화를 삭제할까요?", { name: target?.name ?? "" })}</p>
    <p>{uiText("이 World의 대화 목록과 채팅방에서 해당 대화를 숨깁니다. 별도 기억·관계·게시글은 삭제하지 않습니다.")}</p>
    {hasDraft ? <p>{uiText("이 채팅방의 보내지 않은 글과 첨부 사진도 화면에서 사라집니다.")}</p> : null}
    {error ? <p role="alert">{errorText}</p> : null}
  </Dialog>;
}
