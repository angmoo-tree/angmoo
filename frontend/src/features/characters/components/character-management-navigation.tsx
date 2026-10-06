"use client";

import { formatHandle } from "@/utils/profile-presentation";
import { useUiText } from "@/hooks/use-ui-text";
import type { WorldCharacterManagementView } from "../types/world-character-management";
import styles from "./character-management-navigation.module.css";

const VIEWS: { key: WorldCharacterManagementView; label: string }[] = [
  { key: "profile", label: "프로필" }, { key: "status", label: "상태" }, { key: "settings", label: "설정" },
];

export function CharacterManagementIdentity({ name, handle, role, badge }: { name: string; handle: string | null; role: string; badge: string }) {
  return <div className={styles.identity}><p className={styles.role}>{role}</p><h1>{name}</h1>
    {handle ? <p className={styles.handle}>{formatHandle(handle)}</p> : null}<span className={styles.badge}>{badge}</span>
  </div>;
}

export function CharacterManagementTabs({ activeView, onViewChange, label, panelId }: { activeView: WorldCharacterManagementView; onViewChange: (view: WorldCharacterManagementView) => void; label: string; panelId?: (view: WorldCharacterManagementView) => string }) {
  const uiText = useUiText("characters");
  return <nav className={styles.tabs} role="tablist" aria-label={label}>
    {VIEWS.map((view, index) => <button type="button" role="tab" aria-selected={view.key === activeView} aria-controls={panelId?.(view.key)}
      id={panelId ? `${panelId(view.key)}-tab` : undefined} key={view.key} tabIndex={view.key === activeView ? 0 : -1}
      onClick={() => onViewChange(view.key)} onKeyDown={(event) => {
        const next = event.key === "ArrowRight" ? (index + 1) % VIEWS.length : event.key === "ArrowLeft" ? (index + VIEWS.length - 1) % VIEWS.length : event.key === "Home" ? 0 : event.key === "End" ? VIEWS.length - 1 : null;
        if (next === null) return;
        event.preventDefault(); onViewChange(VIEWS[next].key);
        (event.currentTarget.parentElement?.children[next] as HTMLElement | undefined)?.focus();
      }}>{uiText(view.label)}</button>)}
  </nav>;
}
