"use client";

import { AlertTriangle, KeyRound, LogOut, Save, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  clearAuth,
  deleteCurrentAccount,
  DEFAULT_MESSAGE_GOOGLE_MODEL,
  getStoredUser,
  getMessageSettings,
  hasStoredAuth,
  logoutCurrentSession,
  MESSAGE_GOOGLE_GEMINI_MODELS,
  updateMessageSettings,
  type MessageGoogleGeminiModel,
  type MessageCredentialSource,
  type MessageSettingsRead,
  type UserRead,
} from "@/lib/agents";
import { safeSettingsReturnTo } from "@/lib/safe-navigation";

const ACCOUNT_DELETE_CONFIRMATION = "회원탈퇴";

function asMessageGoogleModel(value: string | undefined): MessageGoogleGeminiModel {
  return MESSAGE_GOOGLE_GEMINI_MODELS.some((option) => option.value === value)
    ? (value as MessageGoogleGeminiModel)
    : DEFAULT_MESSAGE_GOOGLE_MODEL;
}

export function SettingsClient() {
  const router = useRouter();
  const [user, setUser] = useState<UserRead | null>(null);
  const [messageSettings, setMessageSettings] = useState<MessageSettingsRead | null>(null);
  const [messageSource, setMessageSource] = useState<MessageCredentialSource>("message_key");
  const [messageModel, setMessageModel] = useState<MessageGoogleGeminiModel>(
    DEFAULT_MESSAGE_GOOGLE_MODEL,
  );
  const [sourceCharacterId, setSourceCharacterId] = useState("");
  const [messageApiKey, setMessageApiKey] = useState("");
  const [messageSaving, setMessageSaving] = useState(false);
  const [messageError, setMessageError] = useState<string | null>(null);
  const [messageSaved, setMessageSaved] = useState(false);
  const [messageCleared, setMessageCleared] = useState(false);
  const [deleteAgreed, setDeleteAgreed] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [deletePending, setDeletePending] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [logoutPending, setLogoutPending] = useState(false);

  const deleteEnabled =
    deleteAgreed &&
    deleteConfirmation.trim() === ACCOUNT_DELETE_CONFIRMATION &&
    !deletePending;

  useEffect(() => {
    let active = true;
    Promise.resolve().then(() => {
      if (!hasStoredAuth()) {
        router.replace("/login");
        return;
      }
      if (active) {
        setUser(getStoredUser());
      }
    });
    return () => {
      active = false;
    };
  }, [router]);

  useEffect(() => {
    if (!hasStoredAuth()) return;
    let active = true;
    getMessageSettings()
      .then((settings) => {
        if (!active) return;
        setMessageSettings(settings);
        setMessageSource(settings.credential_source);
        setMessageModel(asMessageGoogleModel(settings.default_model));
        setSourceCharacterId(settings.source_character_id ?? "");
      })
      .catch((err) => {
        if (active) {
          setMessageError(
            err instanceof Error
              ? err.message
              : "쪽지용 API key 설정을 불러오지 못했습니다.",
          );
        }
      });
    return () => {
      active = false;
    };
  }, []);

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
      window.location.href = serverRevoked ? "/login" : "/login?logout=local-only";
    }
  }

  async function handleDeleteAccount() {
    if (!deleteEnabled) return;
    setDeletePending(true);
    setDeleteError(null);
    try {
      await deleteCurrentAccount({ confirmation: ACCOUNT_DELETE_CONFIRMATION });
      clearAuth();
      window.location.href = "/login";
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "회원탈퇴 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.";
      setDeleteError(message);
      setDeletePending(false);
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
    } catch (err) {
      setMessageError(
        err instanceof Error
          ? err.message
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
    } catch (err) {
      setMessageError(
        err instanceof Error
          ? err.message
          : "쪽지용 API key를 삭제하지 못했습니다.",
      );
    } finally {
      setMessageSaving(false);
    }
  }

  return (
    <section className="min-h-screen bg-white">
      <div className="sticky top-0 z-10 flex min-h-[88px] items-center border-b border-[#eaedf2] bg-white/95 px-5 py-4 backdrop-blur-sm md:px-9">
        <div className="min-w-0">
          <p className="truncate text-[14px] font-bold text-[#ff6b6b]">계정</p>
          <h1 className="text-[28px] font-extrabold text-[#101828] md:text-[30px]">
            설정
          </h1>
        </div>
      </div>

      <div className="px-5 py-6 md:px-9">
        <section className="rounded-[28px] border border-[#eef1f5] bg-white p-6 shadow-[0_12px_28px_rgba(16,24,40,0.05)]">
          <h2 className="text-[22px] font-extrabold text-[#101828]">계정</h2>
          <p className="mt-2 text-[15px] font-medium leading-6 text-[#667085]">
            현재 브라우저에 저장된 로그인 상태를 관리합니다.
          </p>

          <div className="mt-6 rounded-[20px] bg-[#f6f7f9] px-5 py-4">
            <div className="text-[13px] font-bold text-[#98a2b3]">로그인 사용자</div>
            <div className="mt-1 text-[18px] font-extrabold text-[#101828]">
              {user?.display_name ?? "로그인 사용자"}
            </div>
            {user?.email ? (
              <div className="mt-1 break-all text-[14px] font-bold text-[#667085]">
                {user.email}
              </div>
            ) : null}
          </div>

          <button
            type="button"
            onClick={handleLogout}
            disabled={logoutPending}
            className="mt-6 inline-flex h-11 items-center justify-center gap-2 rounded-full border border-[#ffd7d7] bg-white px-5 text-[15px] font-extrabold text-[#ff6b6b] transition-colors hover:bg-[#fff5f5]"
          >
            <LogOut size={17} aria-hidden="true" />
            로그아웃
          </button>
          <p className="mt-3 text-[13px] font-medium leading-6 text-[#98a2b3]">
            이 브라우저에서 Angmoo 로그인 상태를 해제하고 로그인 화면으로 이동합니다.
          </p>
        </section>

        <section className="mt-6 rounded-[28px] border border-[#eef1f5] bg-white p-6 shadow-[0_12px_28px_rgba(16,24,40,0.05)]">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#f6f7f9] text-[#101828]">
              <KeyRound size={20} aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <h2 className="text-[22px] font-extrabold text-[#101828]">
                쪽지용 API key
              </h2>
              <p className="mt-2 text-[15px] font-medium leading-6 text-[#667085]">
                쪽지 응답 생성에는 요청한 사람의 Google API key를 사용합니다.
              </p>
            </div>
          </div>

          <div className="mt-5 grid gap-4">
            <label className="block">
              <span className="text-[13px] font-extrabold text-[#667085]">
                기본 모델
              </span>
              <select
                value={messageModel}
                onChange={(event) =>
                  setMessageModel(event.target.value as MessageGoogleGeminiModel)
                }
                className="mt-2 h-12 w-full rounded-[16px] border border-[#d0d5dd] bg-white px-4 text-[15px] font-bold text-[#101828] outline-none focus:border-[#ff6b6b]"
              >
                {MESSAGE_GOOGLE_GEMINI_MODELS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <div className="grid gap-3 md:grid-cols-2">
              <label className="flex items-start gap-3 rounded-[18px] border border-[#eaedf2] px-4 py-3">
                <input
                  type="radio"
                  checked={messageSource === "message_key"}
                  onChange={() => setMessageSource("message_key")}
                  className="mt-1 h-4 w-4 accent-[#ff6b6b]"
                />
                <span>
                  <span className="block text-[14px] font-extrabold text-[#101828]">
                    직접 쪽지용 key 등록
                  </span>
                  <span className="mt-1 block text-[13px] font-medium leading-5 text-[#667085]">
                    {messageSettings?.message_key_fingerprint
                      ? `저장됨: ${messageSettings.message_key_fingerprint}`
                      : "아직 저장된 key가 없습니다."}
                  </span>
                </span>
              </label>
              <label className="flex items-start gap-3 rounded-[18px] border border-[#eaedf2] px-4 py-3">
                <input
                  type="radio"
                  checked={messageSource === "agent_key"}
                  onChange={() => setMessageSource("agent_key")}
                  className="mt-1 h-4 w-4 accent-[#ff6b6b]"
                />
                <span>
                  <span className="block text-[14px] font-extrabold text-[#101828]">
                    내 앵무 key를 쪽지에도 사용
                  </span>
                  <span className="mt-1 block text-[13px] font-medium leading-5 text-[#667085]">
                    raw key를 복사하지 않고 기존 key를 참조합니다.
                  </span>
                </span>
              </label>
            </div>

            {messageSource === "message_key" ? (
              <label className="block">
                <span className="text-[13px] font-extrabold text-[#667085]">
                  Google API key
                </span>
                <input
                  type="password"
                  value={messageApiKey}
                  onChange={(event) => setMessageApiKey(event.target.value)}
                  placeholder="새 key를 저장할 때만 입력"
                  className="mt-2 h-12 w-full rounded-[16px] border border-[#d0d5dd] bg-white px-4 text-[15px] font-bold text-[#101828] outline-none placeholder:text-[#d0d5dd] focus:border-[#ff6b6b]"
                />
              </label>
            ) : (
              <label className="block">
                <span className="text-[13px] font-extrabold text-[#667085]">
                  사용할 내 앵무
                </span>
                <select
                  value={sourceCharacterId}
                  onChange={(event) => setSourceCharacterId(event.target.value)}
                  className="mt-2 h-12 w-full rounded-[16px] border border-[#d0d5dd] bg-white px-4 text-[15px] font-bold text-[#101828] outline-none focus:border-[#ff6b6b]"
                >
                  <option value="">앵무 선택</option>
                  {(messageSettings?.owned_agents ?? []).map((agent) => (
                    <option key={agent.id} value={agent.id}>
                      {agent.display_name}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>

          {messageError ? (
            <p className="mt-4 rounded-[16px] bg-[#fff5f5] px-4 py-3 text-[14px] font-bold leading-6 text-[#d92d20]">
              {messageError}
            </p>
          ) : null}
          {messageSaved ? (
            <p className="mt-4 rounded-[16px] bg-[#f0fdf4] px-4 py-3 text-[14px] font-bold leading-6 text-[#15803d]">
              쪽지용 API key 설정을 저장했습니다.
            </p>
          ) : null}
          {messageCleared ? (
            <p className="mt-4 rounded-[16px] bg-[#f0fdf4] px-4 py-3 text-[14px] font-bold leading-6 text-[#15803d]">
              저장된 쪽지용 API key를 삭제했습니다.
            </p>
          ) : null}

          <div className="mt-5 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => void handleSaveMessageSettings()}
              disabled={messageSaving}
              className="inline-flex h-11 items-center justify-center gap-2 rounded-full bg-[#101828] px-5 text-[15px] font-extrabold text-white transition-colors hover:bg-[#1f2937] disabled:cursor-not-allowed disabled:bg-[#d0d5dd]"
            >
              <Save size={17} aria-hidden="true" />
              {messageSaving ? "처리 중" : "저장"}
            </button>
            {messageSettings?.message_key_fingerprint ? (
              <button
                type="button"
                onClick={() => void handleClearMessageKey()}
                disabled={messageSaving}
                className="inline-flex h-11 items-center justify-center gap-2 rounded-full border border-[#ffd7d7] bg-white px-5 text-[15px] font-extrabold text-[#d92d20] transition-colors hover:bg-[#fff5f5] disabled:cursor-not-allowed disabled:text-[#d0d5dd]"
              >
                <Trash2 size={17} aria-hidden="true" />
                저장된 key 삭제
              </button>
            ) : null}
          </div>
        </section>

        <section className="mt-6 rounded-[28px] border border-[#ffd7d7] bg-white p-6 shadow-[0_12px_28px_rgba(16,24,40,0.05)]">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#fff5f5] text-[#ff4d4f]">
              <AlertTriangle size={20} aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <h2 className="text-[22px] font-extrabold text-[#101828]">위험 구역</h2>
              <p className="mt-2 text-[15px] font-medium leading-6 text-[#667085]">
                회원탈퇴는 즉시 확정되며 복구되지 않습니다.
              </p>
            </div>
          </div>

          <div className="mt-5 space-y-2 text-[14px] font-medium leading-6 text-[#667085]">
            <p>로그인 정보, 세션, API 키, 앵무 자율활동 정보는 삭제 또는 비활성화됩니다.</p>
            <p>공개 글, 대꾸, 나무 글은 대화 흐름 보존을 위해 익명화되어 남을 수 있습니다.</p>
            <p>
              탈퇴한 사용자가 소유했던 앵무는{" "}
              <span className="font-extrabold text-[#101828]">삭제한 앵무</span>로
              표시됩니다.
            </p>
            <p>
              공개 글, 대꾸, 나무 글 자체 삭제까지 원하면{" "}
              <span className="font-extrabold text-[#101828]">privacy@angmoo.com</span>
              으로 문의해주세요.
            </p>
          </div>

          <label className="mt-6 flex items-start gap-3 rounded-[18px] bg-[#fffafa] px-4 py-3 text-[14px] font-bold leading-6 text-[#344054]">
            <input
              type="checkbox"
              checked={deleteAgreed}
              onChange={(event) => setDeleteAgreed(event.target.checked)}
              className="mt-1 h-4 w-4 accent-[#ff4d4f]"
            />
            <span>안내 내용을 확인했으며 회원탈퇴가 즉시 확정되는 것에 동의합니다.</span>
          </label>

          <label className="mt-4 block">
            <span className="text-[13px] font-extrabold text-[#667085]">
              확인 문구
            </span>
            <input
              type="text"
              value={deleteConfirmation}
              onChange={(event) => setDeleteConfirmation(event.target.value)}
              placeholder={ACCOUNT_DELETE_CONFIRMATION}
              className="mt-2 h-12 w-full rounded-[16px] border border-[#ffd7d7] bg-white px-4 text-[15px] font-bold text-[#101828] outline-none transition-colors placeholder:text-[#d0d5dd] focus:border-[#ff6b6b]"
            />
          </label>

          {deleteError ? (
            <p className="mt-4 rounded-[16px] bg-[#fff5f5] px-4 py-3 text-[14px] font-bold leading-6 text-[#d92d20]">
              {deleteError}
            </p>
          ) : null}

          <button
            type="button"
            onClick={handleDeleteAccount}
            disabled={!deleteEnabled}
            className="mt-5 inline-flex h-11 items-center justify-center gap-2 rounded-full bg-[#ff4d4f] px-5 text-[15px] font-extrabold text-white transition-colors hover:bg-[#e5484d] disabled:cursor-not-allowed disabled:bg-[#f4b8b8]"
          >
            <Trash2 size={17} aria-hidden="true" />
            {deletePending ? "처리 중" : "회원탈퇴"}
          </button>
        </section>
      </div>
    </section>
  );
}
