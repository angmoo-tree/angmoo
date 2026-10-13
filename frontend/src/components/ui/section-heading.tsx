import type { ReactNode } from "react";
import styles from "./section-heading.module.css";
export function SectionHeading({ icon, title, description, level = 2 }: { icon: ReactNode; title: string; description: ReactNode; level?: 1 | 2 }) {
  const Heading = level === 1 ? 'h1' : 'h2';
  return <header className={styles.root} data-section-heading>
    <span className={styles.icon} aria-hidden="true">{icon}</span>
    <div className={styles.content}><Heading className={styles.title}>{title}</Heading><span className={styles.description}>{description}</span></div>
  </header>;
}
