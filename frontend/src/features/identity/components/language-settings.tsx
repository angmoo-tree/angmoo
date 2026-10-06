"use client";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/hooks/use-auth";
import { useUserEnvironment } from "@/hooks/use-user-environment";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/surfaces";
import { InlineError } from "@/components/ui/feedback";
import { storeUser } from "@/lib/auth/browser-session";
import { saveUiLanguage } from "@/features/identity/api/environment";
import type { UiLanguage } from "@/types/user-environment";

export function LanguageSettings() {
  const { t, i18n } = useTranslation("identity");
  const { status, user: currentUser } = useAuth();
  const { environment, ready, errorCode } = useUserEnvironment();
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);
  async function select(language: UiLanguage) {
    if (saving) return;
    setSaving(true); setFailed(false);
    try { const user = await saveUiLanguage(language, currentUser?.ui_preference_revision ?? 0); storeUser(user); await i18n.changeLanguage(language); }
    catch { setFailed(true); }
    finally { setSaving(false); }
  }
  return <Card as="section" data-language-settings="true">
    <h2>{t("languageTitle")}</h2>
    <p>{t("languageHelp")}</p>
    <div role="group" aria-label={t("languageTitle")}>
      <Button type="button" disabled={saving || status !== "authenticated"} aria-pressed={i18n.language === "ko"} onClick={() => void select("ko")}>{t("korean")}</Button>
      <Button type="button" disabled={saving || status !== "authenticated"} aria-pressed={i18n.language === "en"} onClick={() => void select("en")}>{t("english")}</Button>
    </div>
    {saving ? <p role="status">{t("saving")}</p> : null}
    {failed ? <InlineError>{t("languageSaveFailed")}</InlineError> : null}
    {errorCode ? <InlineError>{t("detectionFailed")}</InlineError> : null}
    {ready && environment ? <><p>{t("detectedLanguage", { language: environment.memory_search_locale })}</p><p>{t("detectedTimezone", { zone: environment.timezone })}</p></> : <p>{t("detectionPending")}</p>}
    <p>{t("detectionHelp")}</p>
  </Card>;
}
