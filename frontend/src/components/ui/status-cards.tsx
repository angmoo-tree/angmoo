import type { ReactNode, UIEventHandler } from "react";
import { ProfileAvatar } from "./profile-avatar";
import { Badge } from "./status";
import { Card } from "./surfaces";
import styles from "./status-cards.module.css";

export function CurrentStateStatusCard({ name, avatarUrl, badges, description, metadata }: {
  name: string;
  avatarUrl: string | null;
  badges: { label: string; tone?: "accent" | "danger" | "neutral" }[];
  description: ReactNode;
  metadata: { label: string; value: ReactNode }[];
}) {
  return <Card as="section" elevated className={styles.currentCard} aria-label={name}>
    <div className={styles.identity}>
      <ProfileAvatar name={name} avatarUrl={avatarUrl} sizeClassName="size-[62px]" textClassName="text-[26px]" />
      <div className={styles.identityBody}>
        <div className={styles.badges}>{badges.map((badge, index) => <Badge key={index} className={styles.identityBadge} data-badge-tone={badge.tone ?? "neutral"}>{badge.label}</Badge>)}</div>
        <h2 className={styles.name}>{name}</h2>
        {description ? <p className={styles.description}>{description}</p> : null}
      </div>
    </div>
    <dl className={styles.stateMetadata}>{metadata.map(item => <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}</dl>
  </Card>;
}

export function RecentActivityStatusCard({ title, children, onScroll }: {
  title: string; children: ReactNode; onScroll: UIEventHandler<HTMLDivElement>;
}) {
  return <Card as="section" elevated className={styles.recentCard}>
    <h2>{title}</h2>
    <div className={styles.activityScroll} role="region" aria-label={title} tabIndex={0} onScroll={onScroll}>{children}</div>
  </Card>;
}

export function PersonaStatusCard({ title, sections, elevated = false }: {
  title: ReactNode; sections: { label: string; value: string }[]; elevated?: boolean;
}) {
  return <Card as="section" elevated={elevated} className={styles.card}><h2>{title}</h2><div className={styles.stack}>
    {sections.map(section => <article className={styles.tile} key={section.label}><h3>{section.label}</h3>
      <p className={styles.body}>{section.value}</p></article>)}
  </div></Card>;
}

export function ActivitySummaryStatusCard({ title, time, metrics, elevated = false }: {
  title: ReactNode; time: ReactNode; metrics: { label: string; value: ReactNode }[]; elevated?: boolean;
}) {
  return <Card as="section" elevated={elevated} className={styles.card}><header className={styles.header}><h2>{title}</h2><div>{time}</div></header>
    <dl className={styles.metrics}>{metrics.map(metric => <div className={styles.tile} key={metric.label}>
      <dt>{metric.label}</dt><dd>{metric.value}</dd></div>)}</dl></Card>;
}
