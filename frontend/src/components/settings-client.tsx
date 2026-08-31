"use client";

import {
  AlertTriangle,
  Database,
  KeyRound,
  LogOut,
  Save,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/shared/auth/public";
import { useRuntimeRouter as useRouter } from "@/shared/navigation/public";
import {
  Button,
  Card,
  Field,
  InlineError,
  Input,
  PageHeader,
  Select,
  StatusChip,
  Toast,
} from "@/shared/ui/public";
import {
  DEFAULT_MESSAGE_GOOGLE_MODEL,
  getMessageSettings,
  MESSAGE_GOOGLE_GEMINI_MODELS,
  updateMessageSettings,
  type MessageCredentialSource,
  type MessageGoogleGeminiModel,
  type MessageSettingsRead,
} from "@/features/chat/public";
import {
  clearAuth,
  getLocalBootstrapStatus,
  logoutCurrentSession,
  type LocalBootstrapRead,
} from "@/lib/agents";
import { safeSettingsReturnTo } from "@/lib/safe-navigation";

import styles from "./settings-client.module.css";

function asMessageGoogleModel(value: string | undefined): MessageGoogleGeminiModel {
  return MESSAGE_GOOGLE_GEMINI_MODELS.some((option) => option.value === value)
    ? (value as MessageGoogleGeminiModel)
    : DEFAULT_MESSAGE_GOOGLE_MODEL;
}

export function SettingsClient() {
  const router = useRouter();
  const { status: authStatus, user } = useAuth();
  const [installation, setInstallation] = useState<LocalBootstrapRead | null>(null);
  const [installationLoading, setInstallationLoading] = useState(true);
  const [installationError, setInstallationError] = useState<string | null>(null);
  const [messageSettings, setMessageSettings] = useState<MessageSettingsRead | null>(null);
  const [messageSource, setMessageSource] = useState<MessageCredentialSource>("message_key");
  const [messageModel, setMessageModel] = useState<MessageGoogleGeminiModel>(
    DEFAULT_MESSAGE_GOOGLE_MODEL,
  );
  const [sourceCharacterId, setSourceCharacterId] = useState("");
  const [messageApiKey, setMessageApiKey] = useState("");
  const [messageLoading, setMessageLoading] = useState(true);
  const [messageSaving, setMessageSaving] = useState(false);
  const [messageError, setMessageError] = useState<string | null>(null);
  const [messageSaved, setMessageSaved] = useState(false);
  const [messageCleared, setMessageCleared] = useState(false);
  const [logoutPending, setLogoutPending] = useState(false);

  const installationStatus = installationLoading
    ? { label: "설치 확인 중", tone: "waiting" as const }
    : installationError
      ? { label: "설치 확인 실패", tone: "degraded" as const }
      : installation?.state === "claimed" && installation.owner
        ? { label: "로컬 세션 연결됨", tone: "healthy" as const }
        : { label: "owner 연결 확인 필요", tone: "degraded" as const };

  const loadInstallation = useCallback(async () => {
    setInstallationLoading(true);
    setInstallationError(null);
    try {
      setInstallation(await getLocalBootstrapStatus());
    } catch (error) {
      setInstallation(null);
      setInstallationError(
        error instanceof Error
          ? error.message
          : "현재 설치의 owner 연결 상태를 확인하지 못했습니다.",
      );
    } finally {
      setInstallationLoading(false);
    }
  }, []);

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
            ? error.message
            : "현재 설치의 owner 연결 상태를 확인하지 못했습니다.",
        );
      })
      .finally(() => {
        if (active) setInstallationLoading(false);
      });
    return () => {
      active = false;
    };
  }, [authStatus]);

  useEffect(() => {
    if (authStatus !== "authenticated") return;
    let active = true;
    getMessageSettings()
      .then((settings) => {
        if (!active) return;
        setMessageSettings(settings);
        setMessageSource(settings.credential_source);
        setMessageModel(asMessageGoogleModel(settings.default_model));
        setSourceCharacterId(settings.source_character_id ?? "");
      })
      .catch((error) => {
        if (active) {
          setMessageError(
            error instanceof Error
              ? error.message
              : "쪽지용 API key 설정을 불러오지 못했습니다.",
          );
        }
      })
      .finally(() => {
        if (active) setMessageLoading(false);
      });
    return () => {
      active = false;
    };
  }, [authStatus]);

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

  async function handleSaveMessageSettings() {
    setMessageSaving(true);
    setMessageError(null);
    setMessageSaved(false);
    setMessageCleared(false);
    try {
      const next = await updateMessageSettings({
        credential_source: messageSource,
        source_character_id: messageSource === "agent_key" ? sourceCharacterId : null,
        default_model: messageModel,
        api_key: messageApiKey.trim() || undefined,
      });
      setMessageSettings(next);
      setMessageSource(next.credential_source);
      setMessageModel(asMessageGoogleModel(next.default_model));
      setSourceCharacterId(next.source_character_id ?? "");
      setMessageApiKey("");
      setMessageSaved(true);
      const params =
        typeof window !== "undefined"
          ? new URLSearchParams(window.location.search)
          : new URLSearchParams();
      const returnTo = safeSettingsReturnTo(params.get("returnTo"));
      if (params.get("messageKey") === "1" && returnTo && next.has_usable_key) {
        router.push(returnTo);
      }
    } catch (error) {
      setMessageError(
        error instanceof Error
          ? error.message
          : "쪽지용 API key 설정을 저장하지 못했습니다.",
      );
    } finally {
      setMessageSaving(false);
    }
  }

  async function handleClearMessageKey() {
    setMessageSaving(true);
    setMessageError(null);
    setMessageSaved(false);
    setMessageCleared(false);
    try {
      const next = await updateMessageSettings({ clear_message_key: true });
      setMessageSettings(next);
      setMessageSource(next.credential_source);
      setMessageModel(asMessageGoogleModel(next.default_model));
      setSourceCharacterId(next.source_character_id ?? "");
      setMessageApiKey("");
      setMessageCleared(true);
    } catch (error) {
      setMessageError(
        error instanceof Error
          ? error.message
          : "쪽지용 API key를 삭제하지 못했습니다.",
      );
    } finally {
      setMessageSaving(false);
    }
  }

  return (
    <section className={styles.page} data-local-settings-surface="true">
      <PageHeader title="설정" subtitle="현재 설치 · 로컬 세션 · API key" />

      <div className={styles.content}>
        <Card as="section" className={styles.sectionCard}>
          <div className={styles.sectionHeading}>
            <span className={styles.sectionIcon} aria-hidden="true">
              <Database />
            </span>
            <div>
              <h2>현재 설치와 로컬 세션</h2>
              <p>
                이 설치의 owner 연결과 현재 세션을 보여줍니다. 다른 PC나 외부 계정과
                자동으로 합쳐지지 않습니다.
              </p>
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
                  다시 확인
                </Button>
              </div>
            </InlineError>
          ) : null}

          <dl className={styles.detailGrid}>
            <div>
              <dt>설치 이름</dt>
              <dd>{installation?.local_label?.trim() || "이 장치"}</dd>
            </div>
            <div>
              <dt>현재 owner</dt>
              <dd>{user?.display_name ?? installation?.owner?.display_name ?? "확인 중"}</dd>
            </div>
            {installation?.installation_id ? (
              <div className={styles.detailWide}>
                <dt>설치 식별자</dt>
                <dd className={styles.identifier}>{installation.installation_id}</dd>
              </div>
            ) : null}
            {user?.email ? (
              <div className={styles.detailWide}>
                <dt>연결된 이메일</dt>
                <dd className={styles.identifier}>{user.email}</dd>
              </div>
            ) : null}
          </dl>

          <div className={styles.actionBlock}>
            <Button
              variant="strong"
              onClick={() => void handleLogout()}
              loading={logoutPending}
              loadingLabel="로컬 세션 종료 중"
            >
              <LogOut size={17} aria-hidden="true" />
              로컬 세션 끝내기
            </Button>
            <p>
              owner 데이터는 지우지 않습니다. 현재 세션만 끝내고 이 설치의 owner를
              다시 확인합니다.
            </p>
          </div>
        </Card>

        <Card as="section" className={styles.sectionCard}>
          <div className={styles.sectionHeading}>
            <span className={styles.sectionIcon} aria-hidden="true">
              <KeyRound />
            </span>
            <div>
              <h2>쪽지용 API key</h2>
              <p>
                이 설치에서 현재 owner의 쪽지 응답을 생성할 때 사용할 Google API key를
                선택합니다.
              </p>
            </div>
          </div>

          {messageLoading ? (
            <div className={styles.statusLine} role="status">
              <StatusChip label="API key 설정 확인 중" tone="waiting" />
            </div>
          ) : null}

          <div className={styles.formStack}>
            <Field id="message-default-model" label="기본 모델">
              {(controlProps) => (
                <Select
                  {...controlProps}
                  value={messageModel}
                  disabled={messageLoading || messageSaving}
                  onChange={(event) =>
                    setMessageModel(event.target.value as MessageGoogleGeminiModel)
                  }
                >
                  {MESSAGE_GOOGLE_GEMINI_MODELS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              )}
            </Field>

            <fieldset className={styles.choiceFieldset}>
              <legend>API key 출처</legend>
              <div className={styles.choiceGrid}>
                <label
                  className={styles.choiceCard}
                  data-selected={messageSource === "message_key" || undefined}
                >
                  <input
                    type="radio"
                    name="message-credential-source"
                    checked={messageSource === "message_key"}
                    disabled={messageLoading || messageSaving}
                    onChange={() => setMessageSource("message_key")}
                  />
                  <span>
                    <strong>쪽지 전용 key 사용</strong>
                    <small>
                      {messageSettings?.message_key_fingerprint
                        ? `저장됨: ${messageSettings.message_key_fingerprint}`
                        : "아직 저장된 key가 없습니다."}
                    </small>
                  </span>
                </label>
                <label
                  className={styles.choiceCard}
                  data-selected={messageSource === "agent_key" || undefined}
                >
                  <input
                    type="radio"
                    name="message-credential-source"
                    checked={messageSource === "agent_key"}
                    disabled={messageLoading || messageSaving}
                    onChange={() => setMessageSource("agent_key")}
                  />
                  <span>
                    <strong>내 앵무 key 참조</strong>
                    <small>raw key를 복제하지 않고 이 설치의 기존 credential을 참조합니다.</small>
                  </span>
                </label>
              </div>
            </fieldset>

            {messageSource === "message_key" ? (
              <Field
                id="message-google-api-key"
                label="Google API key"
                helperText="새 key를 저장하거나 기존 key를 교체할 때만 입력하세요."
              >
                {(controlProps) => (
                  <Input
                    {...controlProps}
                    type="password"
                    autoComplete="off"
                    value={messageApiKey}
                    disabled={messageLoading || messageSaving}
                    onChange={(event) => setMessageApiKey(event.target.value)}
                    placeholder="새 key 입력"
                  />
                )}
              </Field>
            ) : (
              <Field id="message-source-character" label="사용할 내 앵무">
                {(controlProps) => (
                  <Select
                    {...controlProps}
                    value={sourceCharacterId}
                    disabled={messageLoading || messageSaving}
                    onChange={(event) => setSourceCharacterId(event.target.value)}
                  >
                    <option value="">앵무 선택</option>
                    {(messageSettings?.owned_agents ?? []).map((agent) => (
                      <option key={agent.id} value={agent.id}>
                        {agent.display_name}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
            )}
          </div>

          {messageError ? <InlineError className={styles.feedback}>{messageError}</InlineError> : null}
          {messageSaved ? <Toast tone="success">쪽지용 API key 설정을 저장했습니다.</Toast> : null}
          {messageCleared ? <Toast tone="success">저장된 쪽지용 API key를 삭제했습니다.</Toast> : null}

          <div className={styles.buttonRow}>
            <Button
              variant="primary"
              onClick={() => void handleSaveMessageSettings()}
              loading={messageSaving}
              loadingLabel="저장 중"
              disabled={
                messageLoading ||
                (messageSource === "agent_key" && !sourceCharacterId)
              }
            >
              <Save size={17} aria-hidden="true" />
              저장
            </Button>
            {messageSettings?.message_key_fingerprint ? (
              <Button
                variant="danger"
                onClick={() => void handleClearMessageKey()}
                disabled={messageSaving}
              >
                <Trash2 size={17} aria-hidden="true" />
                저장된 key 삭제
              </Button>
            ) : null}
          </div>
        </Card>

        <Card as="section" className={`${styles.sectionCard} ${styles.dangerCard}`}>
          <div className={styles.sectionHeading}>
            <span className={`${styles.sectionIcon} ${styles.dangerIcon}`} aria-hidden="true">
              <AlertTriangle />
            </span>
            <div>
              <h2>데이터 삭제 범위</h2>
              <p>
                삭제 작업은 대상에 따라 범위가 다릅니다. 이 Local 설정 화면은 현재
                owner 전체 삭제 capability를 제공하지 않습니다.
              </p>
            </div>
          </div>

          <StatusChip label="owner 전체 삭제 지원 안 함" tone="disabled" />

          <div className={styles.scopeList}>
            <p>
              개별 앵무 삭제는 내 앵무 관리에서 해당 Character 하나만 대상으로
              진행합니다.
            </p>
            <p>
              World에서 제거는 Creator Studio에서 해당 World 참여만 끝내며 전역
              Character identity와 과거 기록을 삭제하지 않습니다.
            </p>
            <p>
              로컬 세션 끝내기는 현재 세션만 해제하며 owner 데이터·SQLite·credential을
              삭제하지 않습니다.
            </p>
          </div>
        </Card>
      </div>
    </section>
  );
}
