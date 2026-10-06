"use client";
import { useEffect, useRef, useState } from "react";
import { TriangleAlert } from "lucide-react";
import { SettingsCard } from "@/components/ui/settings-card";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/form-controls";
import { useUiText } from "@/hooks/use-ui-text";
import { useProductLeaveGuard } from "@/hooks/use-product-leave-guard";
import { apiRequest } from "@/lib/http/api-request";
export function WorldCharacterDeletionCard({ worldId, actorId, name, revision, onDeleted }: { worldId: string; actorId: string; name: string; revision: number; onDeleted: () => void }) {
  const t = useUiText("characters");
  const [input, setInput] = useState(""), [consent, setConsent] = useState(false), [open, setOpen] = useState(false), [busy, setBusy] = useState(false), [failed, setFailed] = useState(false);
  const cancel = useRef<HTMLButtonElement>(null), request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  useProductLeaveGuard(busy || Boolean(input));
  async function remove() {
    if (busy || !consent || input !== name) return;
    const controller = new AbortController(); request.current = controller; setBusy(true); setFailed(false);
    try {
      const result = await apiRequest<{ world_id: string; world_character_id: string; deleted: boolean }>(`/worlds/${encodeURIComponent(worldId)}/world-characters/${encodeURIComponent(actorId)}/instance`, { signal: controller.signal, method: "DELETE", body: { expected_revision: revision, confirmed_name: input, consent: true } });
      if (!controller.signal.aborted && result.deleted && result.world_id === worldId && result.world_character_id === actorId) { setInput(""); setOpen(false); onDeleted(); }
    } catch { if (!controller.signal.aborted) setFailed(true); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <SettingsCard danger title={t("캐릭터 삭제")} description={t("현재 World의 캐릭터를 삭제하며 복구할 수 없어요.")} icon={<TriangleAlert size={20} />}>
    <p>{t("이 World의 키, 비공개 대화, 기억과 활동 준비 정보를 삭제해요. 공개 게시글·답글·첨부는 삭제된 캐릭터로 남아요.")}</p>
    <p className="text-sm text-text-secondary">{t("원본 캐릭터와 다른 World의 캐릭터·자료는 유지돼요.")}</p>
    <label className="flex min-h-11 items-center gap-3"><input type="checkbox" className="accent-action-primary" checked={consent} onChange={event => setConsent(event.target.checked)} />{t("삭제 범위와 복구할 수 없음을 확인했어요.")}</label>
    <Field label={t("삭제 확인: {{name}}", { name })}>{props => <Input {...props} value={input} onChange={event => setInput(event.target.value)} autoComplete="off" />}</Field>
    {failed ? <p role="alert">{t("삭제하지 못했어요. 진행 중인 작업과 최신 상태를 확인해주세요.")}</p> : null}
    <Button variant="danger" disabled={!consent || input !== name || busy} onClick={() => setOpen(true)}>{t("캐릭터 삭제")}</Button>
    <Dialog open={open} onOpenChange={next => { if (!busy) setOpen(next); }} title={t("이 World의 캐릭터를 삭제할까요?")} initialFocusRef={cancel} closeOnEscape={!busy} closeOnBackdrop={!busy}
      actions={<><Button ref={cancel} variant="secondary" disabled={busy} onClick={() => setOpen(false)}>{t("취소")}</Button><Button variant="danger" loading={busy} onClick={() => void remove()}>{t("삭제 확정")}</Button></>}>
      <p>{t("비공개 자료는 삭제되고, 공개 글과 다른 World의 자료는 유지돼요.")}</p>
    </Dialog>
  </SettingsCard>;
}
