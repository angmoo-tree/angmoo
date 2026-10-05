"use client";

import { ArrowLeft, Play, Power, PowerOff, RefreshCw } from "lucide-react";
import { useEffect, useId, useState, type ReactNode } from "react";
import { Button, IconButton } from "@/components/ui/button";
import { InlineError } from "@/components/ui/feedback";
import { useUiText } from "@/hooks/use-ui-text";
import { setWorldCharacterAutonomy } from "../api/world-character-dashboard-client";
import { runWorldCharacterNow, updateWorldCharacterProfile, updateWorldCharacterSettings, uploadWorldCharacterProfileMedia } from "../api/world-character-management-client";
import { useWorldCharacterManagement } from "../hooks/use-world-character-management";
import type { WorldCharacterManagementRead, WorldCharacterManagementView } from "../types/world-character-management";
import { worldCharacterRestrictionMessage } from "../utils/world-character-dashboard-presentation";
import { CharacterManagementIdentity, CharacterManagementTabs } from "./character-management-navigation";
import { ProfileError, ProfileStatus, WorldCharacterManagementItem, worldCharacterOperationError } from "./world-character-directory";
import { WorldCharacterProfileEditor } from "./world-character-profile-editor";
import { WorldCharacterSettingsForm } from "./world-character-settings-form";
import styles from "./world-character-management.module.css";

export function WorldCharacterManagement({ worldId, worldCharacterId, activeView, onViewChange, onBack, renderProfile }: {
  worldId: string; worldCharacterId: string; activeView: WorldCharacterManagementView;
  onViewChange: (view: WorldCharacterManagementView) => void; onBack: () => void;
  renderProfile: (input: { read: WorldCharacterManagementRead; onEditProfile?: () => void }) => ReactNode;
}) {
  const uiText = useUiText("characters");
  const controller = useWorldCharacterManagement(worldId, worldCharacterId);
  const { read, settings, loading, error, settingsError, pending, load, loadSettings, mutate, acceptManagement, acceptSettings } = controller;
  const [visited, setVisited] = useState<Set<WorldCharacterManagementView>>(new Set([activeView]));
  const [editing, setEditing] = useState(false);
  const [editorVisited, setEditorVisited] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [runPending, setRunPending] = useState(false);
  const id = useId().replaceAll(":", "");
  const panelId = (view: WorldCharacterManagementView) => `world-character-${id}-${view}`;
  const busy = [...pending].some(operation => operation !== "settings-read");

  useEffect(() => {
    queueMicrotask(() => setVisited(current => current.has(activeView) ? current : new Set([...current, activeView])));
  }, [activeView]);
  useEffect(() => {
    if (activeView === "settings" && read?.item.capabilities.can_edit_settings && !settings && !settingsError && !pending.has("settings-read")) void loadSettings();
  }, [activeView, read, settings, settingsError, pending, loadSettings]);
  useEffect(() => {
    if (!read) queueMicrotask(() => { setEditing(false); setEditorVisited(false); setMessage(null); setRunPending(false); });
  }, [read]);

  if (!read) return loading && !error ? <ProfileStatus title={uiText("World 캐릭터 관리 정보를 불러오는 중")} /> : <ProfileError error={error} onRetry={() => void load()} />;
  const item = read.item, profile = item.profile, capabilities = item.capabilities;
  const isUser = profile.control_mode === "owner_controlled";
  const toggleAllowed = item.autonomous_enabled ? capabilities.can_deactivate : capabilities.can_activate;
  const edit = read.can_manage && capabilities.can_edit_profile ? () => { setEditorVisited(true); setEditing(true); } : undefined;

  const refresh = () => { void load(); if (activeView === "settings" && settings) void loadSettings(); };
  async function toggle() {
    if (!read || !toggleAllowed || busy) return;
    await mutate("autonomy", signal => setWorldCharacterAutonomy(worldId, worldCharacterId, !item.autonomous_enabled, item.revision, { signal }), result => {
      const updated = result.items.find(entry => entry.profile.world_character_id === worldCharacterId);
      if (updated) acceptManagement({ ...read, item: updated });
    });
  }
  async function runNow() {
    if (!read || !capabilities.can_run_now || busy || runPending) return;
    const result = await mutate("run-now", signal => runWorldCharacterNow(worldId, worldCharacterId, profile.character_id, item.revision, { signal }), result => {
      const active = ["accepted", "queued", "running", "pending", "processing"].includes(result.run.status);
      setRunPending(active);
      setMessage(active ? "이 World의 활동 요청을 접수했어요." : ["completed", "ok", "success", "succeeded"].includes(result.run.status) ? "이 World의 활동이 완료되었어요." : "이 World의 활동 결과를 확인해주세요.");
    });
    if (result) {
      const latest = await load();
      if (latest?.item.capabilities.can_run_now) setRunPending(false);
    }
  }

  return <section className={styles.management} data-world-character-management data-world-id={worldId} data-world-character-id={worldCharacterId}>
    <header className={styles.header}>
      <div className={styles.headerIdentity}>
        <IconButton label={uiText("World 캐릭터 목록으로 돌아가기")} onClick={onBack}><ArrowLeft aria-hidden="true" size={20} /></IconButton>
        <CharacterManagementIdentity name={profile.display_name} handle={profile.handle} role={uiText(isUser ? "사용자" : "캐릭터")}
          badge={uiText(isUser ? "사용자" : "이 World의 캐릭터")} />
      </div>
      <div className={styles.headerActions}>
        <IconButton label={uiText("관리 상태 새로고침")} title={uiText("관리 상태 새로고침")} disabled={busy} onClick={refresh}><RefreshCw aria-hidden="true" size={20} /></IconButton>
        {!isUser && read.can_manage ? <>
          <Button variant={item.autonomous_enabled ? "strong" : "primary"} loading={pending.has("autonomy")} disabled={busy || !toggleAllowed}
            title={!toggleAllowed ? uiText(worldCharacterRestrictionMessage(capabilities.reason)) : undefined} onClick={() => void toggle()}>
            {item.autonomous_enabled ? <PowerOff aria-hidden="true" size={16} /> : <Power aria-hidden="true" size={16} />}{uiText(item.autonomous_enabled ? "자율 활동 끄기" : "자율 활동 켜기")}
          </Button>
          {capabilities.can_run_now ? <Button variant="secondary" loading={pending.has("run-now")} disabled={busy || runPending} onClick={() => void runNow()}>
            <Play aria-hidden="true" size={16} />{uiText("지금 한 번 활동")}</Button> : null}
        </> : null}
      </div>
    </header>
    <CharacterManagementTabs activeView={activeView} onViewChange={onViewChange} label={uiText("World 캐릭터 관리 탭")} panelId={panelId} />
    {error ? <InlineError className={styles.feedback}><p>{uiText(worldCharacterOperationError(error))}</p><Button variant="secondary" onClick={refresh}>{uiText("최신 상태 확인")}</Button></InlineError> : null}
    {message ? <p className={styles.readonly} role="status">{uiText(message)}</p> : null}
    {(visited.has("profile") || activeView === "profile") ? <div className={styles.pane} hidden={activeView !== "profile"} role="tabpanel" id={panelId("profile")} aria-labelledby={`${panelId("profile")}-tab`}>
      {renderProfile({ read, onEditProfile: edit })}
    </div> : null}
    {(visited.has("status") || activeView === "status") ? <div className={styles.pane} hidden={activeView !== "status"} role="tabpanel" id={panelId("status")} aria-labelledby={`${panelId("status")}-tab`}>
      <p className={styles.readonly}>{uiText("이 World에서만 적용되는 활동 상태예요.")}</p>
      <WorldCharacterManagementItem item={item} />
      {!read.can_manage ? <p className={styles.readonly}>{uiText("이 World 캐릭터의 관리 권한이 없어요.")}</p> : null}
    </div> : null}
    {(visited.has("settings") || activeView === "settings") ? <div className={styles.pane} hidden={activeView !== "settings"} role="tabpanel" id={panelId("settings")} aria-labelledby={`${panelId("settings")}-tab`}>
      {!read.can_manage ? <p className={styles.readonly}>{uiText("이 World 캐릭터의 관리 권한이 없어요.")}</p>
        : isUser ? <div className={styles.readonly}><p>{uiText("직접 작성하는 사용자 프로필이에요. 자율활동을 사용하지 않아요.")}</p>{edit ? <Button variant="secondary" onClick={edit}>{uiText("내 프로필 편집")}</Button> : null}</div>
        : !capabilities.can_edit_settings ? <p className={styles.readonly}>{uiText(worldCharacterRestrictionMessage(capabilities.reason))}</p>
        : settings ? <WorldCharacterSettingsForm initial={settings} pending={busy}
          onSave={(revision, values) => mutate("settings-save", signal => updateWorldCharacterSettings(worldId, worldCharacterId, revision, values, { signal }), acceptSettings)} />
        : settingsError ? <InlineError className={styles.feedback}><p>{uiText(worldCharacterOperationError(settingsError))}</p><Button variant="secondary" onClick={() => void loadSettings()}>{uiText("다시 시도")}</Button></InlineError>
        : <ProfileStatus title={uiText("World 설정을 불러오는 중")} />}
    </div> : null}
    {editorVisited && edit ? <WorldCharacterProfileEditor profile={profile} initialRevision={item.revision} open={editing} pending={busy} onOpenChange={setEditing}
      onSave={(revision, values) => mutate("profile-save", signal => updateWorldCharacterProfile(worldId, worldCharacterId, revision, values, { signal }), acceptManagement)}
      onUpload={(revision, media) => mutate("profile-media", signal => uploadWorldCharacterProfileMedia(worldId, worldCharacterId, revision, media, { signal }), acceptManagement)} /> : null}
  </section>;
}
