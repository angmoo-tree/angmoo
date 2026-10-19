"use client";
import { useEffect, useState } from "react";
import { useUiText } from "@/hooks/use-ui-text";
import { useRuntimeRouter } from "@/hooks/use-runtime-navigation";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/surfaces";
import { useLocalEntry } from "../controllers/local-entry-context";
import { safeLoginReturnTo } from "@/utils/safe-navigation";
import styles from "./local-owner-client.module.css";

export function LocalOwnerClient({ returnTo = null, embedded = false }: { logoutLocallyOnly?: boolean; returnTo?: string | null; embedded?: boolean }) {
  const text = useUiText("identity");
  const router = useRuntimeRouter();
  const { controller, snapshot } = useLocalEntry();
  const [pending, setPending] = useState(false);
  useEffect(() => {
    if (snapshot.phase === "authenticated" && !embedded) router.replace(safeLoginReturnTo(returnTo) ?? "/");
  }, [snapshot.phase, embedded, router, returnTo]);
  const act = async (work: () => Promise<void>) => {
    if (pending) return;
    setPending(true);
    try { await work(); } finally { setPending(false); }
  };
  if (snapshot.phase === "authenticated") return null;
  const stopped = snapshot.phase === "stopped";
  const unconfirmed = snapshot.phase === "end_unconfirmed";
  const preparing = ["checking", "preparing", "ending"].includes(snapshot.phase);
  const title = stopped ? text("세션을 종료했어요.") : unconfirmed ? text("세션 종료를 확인하지 못했어요.")
    : snapshot.phase === "selection_required" ? text("기존 사용자를 선택해 주세요.")
      : snapshot.phase === "recovery_required" ? text("기존 데이터 연결을 확인해야 해요.")
        : preparing ? text("Angmoo를 준비하고 있어요.") : text("Angmoo를 준비하지 못했어요.");
  return <section className={embedded ? undefined : styles.page} data-local-owner-state={snapshot.phase} aria-live="polite">
    <Card as="section" className={styles.stateCard}>
      <h2>{title}</h2>
      {stopped || unconfirmed ? <p>{text("사용자와 저장된 데이터는 그대로 유지됩니다.")}</p> : null}
      {snapshot.errorCode === "local_auth_contract_mismatch" ? <p>{text("앱과 서버의 버전이 맞지 않아요. 같은 버전으로 다시 실행해 주세요.")}</p> : null}
      {snapshot.errorCode?.startsWith("local_connection_storage") ? <p>{text("이 브라우저의 연결 상태를 저장하지 못했어요. 저장소 사용을 허용한 뒤 다시 시도해 주세요.")}</p> : null}
      {stopped ? <Button disabled={pending} onClick={() => void act(controller.resume)}>{text("다시 시작하기")}</Button> : null}
      {unconfirmed ? <Button disabled={pending} onClick={() => void act(controller.stop)}>{text("세션 종료 다시 시도")}</Button> : null}
      {snapshot.phase === "selection_required" ? snapshot.bootstrap?.candidates.map(candidate =>
        <Button key={candidate.user_id} disabled={pending} onClick={() => void act(() => controller.selectOwner(candidate.user_id))}>{candidate.display_name}</Button>) : null}
      {!preparing && !stopped ? <Button variant="secondary" disabled={pending} onClick={() => void act(controller.refresh)}>{text("다시 확인")}</Button> : null}
    </Card>
  </section>;
}
