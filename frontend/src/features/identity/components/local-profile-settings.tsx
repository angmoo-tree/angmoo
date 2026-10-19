"use client";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form-controls";
import { SettingsCard } from "@/components/ui/settings-card";
import { InlineError } from "@/components/ui/feedback";
import { captureAuthRequestScope, isCurrentAuthRequestScope, storeUser, type UserRead } from "@/lib/auth/browser-session";
import { updateMe, updateInstallationLabel } from "../api/identity";

/** Parent keys this editor by runtime, installation and owner. Refreshes in the
 * same scope preserve drafts; leaving that scope discards them. */
export function LocalProfileSettings({ user, installationLabel, onInstallationSaved }: {
  user: UserRead; installationLabel: string | null; onInstallationSaved: (label: string | null) => void;
}) {
  const { t } = useTranslation("identity");
  const [name, setName] = useState(user.display_name);
  const [label, setLabel] = useState(installationLabel ?? "");
  const [busy, setBusy] = useState<"name" | "label" | null>(null);
  const [result, setResult] = useState<"saved" | "failed" | null>(null);
  async function save(kind: "name" | "label") {
    if (busy) return;
    const scope = captureAuthRequestScope();
    setBusy(kind); setResult(null);
    try {
      if (kind === "name") {
        const saved = await updateMe({ display_name: name });
        if (!isCurrentAuthRequestScope(scope)) return;
        setName(saved.display_name); storeUser(saved);
      } else {
        const saved = await updateInstallationLabel(label);
        if (!isCurrentAuthRequestScope(scope)) return;
        setLabel(saved.local_label ?? ""); onInstallationSaved(saved.local_label);
      }
      setResult("saved");
    } catch { if (isCurrentAuthRequestScope(scope)) setResult("failed"); }
    finally { if (isCurrentAuthRequestScope(scope)) setBusy(null); }
  }
  return <SettingsCard elevated title={t("localProfileTitle")} description={t("localProfileHelp")} icon={<UserRound size={20} />}>
    <form className="space-y-3" onSubmit={event => { event.preventDefault(); void save("name"); }}>
      <Field required label={t("accountName")}>{props => <Input {...props} value={name} maxLength={80} disabled={busy !== null} onChange={event => setName(event.target.value)} />}</Field>
      <Button type="submit" disabled={busy !== null || !name.trim() || name === user.display_name}>{t("saveAccountName")}</Button>
      {user.display_name_change_available_at && <p>{t("nameNextChange", { date: new Date(user.display_name_change_available_at).toLocaleString() })}</p>}
    </form>
    <form className="space-y-3" onSubmit={event => { event.preventDefault(); void save("label"); }}>
      <Field label={t("installationNameOptional")}>{props => <Input {...props} value={label} maxLength={80} disabled={busy !== null} onChange={event => setLabel(event.target.value)} />}</Field>
      <Button type="submit" disabled={busy !== null || label === (installationLabel ?? "")}>{t("saveInstallationName")}</Button>
    </form>
    {result === "saved" && <p role="status">{t("localProfileSaved")}</p>}
    {result === "failed" && <InlineError>{t("localProfileSaveFailed")}</InlineError>}
  </SettingsCard>;
}
