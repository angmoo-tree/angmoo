"use client";
import { Globe2 } from "lucide-react";
import { useState } from "react";
import styles from "./app-icon-visual.module.css";
const BACKGROUNDS = ["var(--color-brand-soft)", "var(--color-state-running-surface)", "var(--color-state-warning-surface)", "var(--color-state-degraded-surface)"];
export function appIconBackground(id?: string): string | undefined {
  if (!id) return undefined;
  let hash = 0;
  for (const character of id) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return BACKGROUNDS[hash % BACKGROUNDS.length];
}
export function AppIconVisual({ source, name }: { source?: string | null; name: string }) {
  const [failed, setFailed] = useState<string | null>(null);
  const initial = Array.from(name.trim())[0];
  if (source && source !== failed) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={source} alt="" className={styles.image} onError={() => setFailed(source)} />;
  }
  return initial ? <span className={styles.initial}>{initial}</span> : <Globe2 size={31} strokeWidth={2.1} />;
}
