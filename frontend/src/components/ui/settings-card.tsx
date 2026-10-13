import { useId, type HTMLAttributes, type ReactNode } from "react";
import { Card } from "./surfaces";
import styles from "./settings-card.module.css";

/** Product-neutral anatomy; consumers own titles, permissions and behavior. */
export function SettingsCard({ title, description, icon, children, danger = false, elevated = false, headingLevel = 2, iconTone = "filled", className, ...attributes }: Omit<HTMLAttributes<HTMLElement>, "title"> & {
  title: ReactNode; description?: ReactNode; icon: ReactNode; children: ReactNode; danger?: boolean; elevated?: boolean; headingLevel?: 1 | 2; iconTone?: "filled" | "soft";
}) {
  const Heading = headingLevel === 1 ? "h1" : "h2";
  const headingId = useId();
  return <Card as="section" elevated={elevated} aria-labelledby={headingId} {...attributes} className={`${styles.card} ${danger ? styles.danger : ""} ${className ?? ""}`}>
    <header className={styles.header}>
      <span className={`${styles.icon} ${iconTone === "soft" ? styles.softIcon : ""}`} aria-hidden="true">{icon}</span>
      <div><Heading id={headingId} className={styles.title}>{title}</Heading>{description ? <p className={styles.description}>{description}</p> : null}</div>
    </header>
    <div className={styles.content}>{children}</div>
  </Card>;
}
