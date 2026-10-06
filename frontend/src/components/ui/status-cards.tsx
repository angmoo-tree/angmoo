import type { ReactNode } from "react";
import { Card } from "./surfaces";
import styles from "./status-cards.module.css";

export function PersonaStatusCard({ title, sections }: { title: ReactNode; sections: { label: string; value: string }[] }) {
  return <Card as="section" className={styles.card}><h2>{title}</h2><div className={styles.stack}>
    {sections.map(section => <article className={styles.tile} key={section.label}><h3>{section.label}</h3>
      <p className={styles.body}>{section.value}</p></article>)}
  </div></Card>;
}

export function ActivitySummaryStatusCard({ title, time, metrics }: {
  title: ReactNode; time: ReactNode; metrics: { label: string; value: ReactNode }[];
}) {
  return <Card as="section" className={styles.card}><header className={styles.header}><h2>{title}</h2><div>{time}</div></header>
    <dl className={styles.metrics}>{metrics.map(metric => <div className={styles.tile} key={metric.label}>
      <dt>{metric.label}</dt><dd>{metric.value}</dd></div>)}</dl></Card>;
}
