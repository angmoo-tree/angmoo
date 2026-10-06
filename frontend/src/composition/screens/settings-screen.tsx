"use client";
import { useUiText } from "@/hooks/use-ui-text";

import { LanguageSettings } from "@/features/identity/components/language-settings";

import {
  AlertTriangle,
  Database,
  LogOut,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/hooks/use-auth";
import { useRuntimeRouter as useRouter } from "@/hooks/use-runtime-navigation";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/surfaces";
import { InlineError } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/navigation";
import { StatusChip } from "@/components/ui/status";
import { clearAuth } from "@/lib/auth/browser-session";
import { getLocalBootstrapStatus, logoutCurrentSession } from "@/features/identity/api/identity";
import { type LocalBootstrapRead } from "@/features/identity/types/identity";

import styles from "./settings-client.module.css";

export function SettingsClient() {
  const uiText = useUiText("shell");
  const router = useRouter();
  const { status: authStatus, user } = useAuth();
  const [installation, setInstallation] = useState<LocalBootstrapRead | null>(null);
  const [installationLoading, setInstallationLoading] = useState(true);
  const [installationError, setInstallationError] = useState<string | null>(null);
  const [logoutPending, setLogoutPending] = useState(false);

  const installationStatus = installationLoading
    ? { label: uiText("설치 확인 중"), tone: "waiting" as const }
    : installationError
      ? { label: uiText("설치 확인 실패"), tone: "degraded" as const }
      : installation?.state === "claimed" && installation.owner
        ? { label: uiText("로컬 세션 연결됨"), tone: "healthy" as const }
        : { label: uiText("owner 연결 확인 필요"), tone: "degraded" as const };

  const loadInstallation = useCallback(async () => {
    setInstallationLoading(true);
    setInstallationError(null);
    try {
      setInstallation(await getLocalBootstrapStatus());
    } catch (error) {
      setInstallation(null);
      setInstallationError(
        error instanceof Error
          ? uiText(error.message)
          : uiText("현재 설치의 owner 연결 상태를 확인하지 못했습니다."),
      );
    } finally {
      setInstallationLoading(false);
    }
  }, [uiText]);

  useEffect(() => {
    if (authStatus === "unauthenticated") router.replace("/login");
  }, [authStatus, router]);

  useEffect(() => {
    if (authStatus !== "authenticated") return;
    let active = true;
    getLocalBootstrapStatus()
      .then((status) => {
        if (active) setInstallation(status);
      })
      .catch((error) => {
        if (!active) return;
        setInstallation(null);
        setInstallationError(
          error instanceof Error
            ? uiText(error.message)
            : uiText("현재 설치의 owner 연결 상태를 확인하지 못했습니다."),
        );
      })
      .finally(() => {
        if (active) setInstallationLoading(false);
      });
    return () => {
      active = false;
    };
  }, [authStatus, uiText]);

  async function handleLogout() {
    if (logoutPending) return;
    setLogoutPending(true);
    let serverRevoked = true;
    try {
      await logoutCurrentSession();
    } catch {
      serverRevoked = false;
    } finally {
      clearAuth();
      router.replace(serverRevoked ? "/login" : "/login?logout=local-only");
    }
  }

  return (
    <section className={styles.page} data-local-settings-surface="true">
      <PageHeader title={uiText("설정")} subtitle={uiText("현재 설치 · 로컬 세션")} />

      <div className={styles.content}>
        <LanguageSettings />
        <Card as="section" className={styles.sectionCard}>
          <div className={styles.sectionHeading}>
            <span className={styles.sectionIcon} aria-hidden="true">
              <Database />
            </span>
            <div>
              <h2>{uiText("현재 설치와 로컬 세션")}</h2>
              <p>
                {uiText("이 설치의 owner 연결과 현재 세션을 보여줍니다. 다른 PC나 외부 계정과 자동으로 합쳐지지 않습니다.")}</p>
            </div>
          </div>

          <div className={styles.statusLine} aria-live="polite">
            <StatusChip
              label={installationStatus.label}
              tone={installationStatus.tone}
            />
          </div>

          {installationError ? (
            <InlineError className={styles.feedback}>
              <div className={styles.feedbackStack}>
                <span>{installationError}</span>
                <Button variant="secondary" compact onClick={() => void loadInstallation()}>
                  {uiText("다시 확인")}</Button>
              </div>
            </InlineError>
          ) : null}

          <dl className={styles.detailGrid}>
            <div>
              <dt>{uiText("설치 이름")}</dt>
              <dd>{installation?.local_label?.trim() || uiText("이 장치")}</dd>
            </div>
            <div>
              <dt>{uiText("현재 owner")}</dt>
              <dd>{user?.display_name ?? installation?.owner?.display_name ?? uiText("확인 중")}</dd>
            </div>
            {installation?.installation_id ? (
              <div className={styles.detailWide}>
                <dt>{uiText("설치 식별자")}</dt>
                <dd className={styles.identifier}>{installation.installation_id}</dd>
              </div>
            ) : null}
            {user?.email ? (
              <div className={styles.detailWide}>
                <dt>{uiText("연결된 이메일")}</dt>
                <dd className={styles.identifier}>{user.email}</dd>
              </div>
            ) : null}
          </dl>

          <div className={styles.actionBlock}>
            <Button
              variant="strong"
              onClick={() => void handleLogout()}
              loading={logoutPending}
              loadingLabel={uiText("로컬 세션 종료 중")}
            >
              <LogOut size={17} aria-hidden="true" />
              {uiText("로컬 세션 끝내기")}</Button>
            <p>
              {uiText("owner 데이터는 지우지 않습니다. 현재 세션만 끝내고 이 설치의 owner를 다시 확인합니다.")}</p>
          </div>
        </Card>





        <Card as="section" className={`${styles.sectionCard} ${styles.dangerCard}`}>
          <div className={styles.sectionHeading}>
            <span className={`${styles.sectionIcon} ${styles.dangerIcon}`} aria-hidden="true">
              <AlertTriangle />
            </span>
            <div>
              <h2>{uiText("데이터 삭제 범위")}</h2>
              <p>
                {uiText("삭제 작업은 대상에 따라 범위가 다릅니다. 이 Local 설정 화면은 현재 owner 전체 삭제 capability를 제공하지 않습니다.")}</p>
            </div>
          </div>

          <StatusChip label={uiText("owner 전체 삭제 지원 안 함")} tone="disabled" />

          <div className={styles.scopeList}>
            <p>
              {uiText("개별 앵무 삭제는 내 앵무 관리에서 해당 Character 하나만 대상으로 진행합니다.")}</p>
            <p>
              {uiText("World에서 제거는 Creator Studio에서 해당 World 참여만 끝내며 전역 Character identity와 과거 기록을 삭제하지 않습니다.")}</p>
            <p>
              {uiText("로컬 세션 끝내기는 현재 세션만 해제하며 owner 데이터·SQLite·credential을 삭제하지 않습니다.")}</p>
          </div>
        </Card>
      </div>
    </section>
  );
}
