"use client";

import type { ReactNode } from "react";

import { LocalProductLink } from "@/components/navigation/local-product-link";
import { ProfileAvatar } from "@/components/ui/profile-avatar";
import { ListRow } from "@/components/ui/surfaces";
import { formatHandle } from "@/utils/profile-presentation";

import styles from "./characters-dashboard.module.css";

/** Display only. Each caller owns its scope, data, capabilities and actions. */
export function CharacterManagementCard({
  identity,
  href,
  linkLabel,
  status,
  action,
  metrics,
  policy,
  notice,
  autonomyState,
  worldCharacterId,
}: {
  identity: { id: string; name: string; handle: string | null; avatarUrl: string | null; intro: string | null };
  href: string;
  linkLabel: string;
  status: ReactNode;
  action?: ReactNode;
  metrics: ReactNode;
  policy?: ReactNode;
  notice?: ReactNode;
  autonomyState: string;
  worldCharacterId?: string;
}) {
  return (
    <ListRow
      className={styles.row}
      data-character-id={identity.id}
      data-character-autonomy-state={autonomyState}
      data-world-character-id={worldCharacterId}
    >
      <LocalProductLink ariaLabel={linkLabel} className={styles.avatarLink} href={href}>
        <ProfileAvatar
          name={identity.name}
          avatarUrl={identity.avatarUrl}
          sizeClassName="size-[58px]"
          textClassName="text-[22px]"
        />
      </LocalProductLink>
      <article className={styles.rowBody}>
        <div className={styles.identityActionRow}>
          <div className={styles.identity}>
            <div className={styles.statusLine}>{status}</div>
            <LocalProductLink ariaLabel={linkLabel} className={styles.characterName} href={href}>
              {identity.name}
            </LocalProductLink>
            {identity.handle ? <p className={styles.handle}>{formatHandle(identity.handle)}</p> : null}
            {identity.intro ? <p className={styles.oneLiner}>{identity.intro}</p> : null}
          </div>
          {action}
        </div>
        <div className={styles.metrics} data-character-metrics>{metrics}</div>
        {policy ? <p className={styles.policyLine}>{policy}</p> : null}
        {notice}
      </article>
    </ListRow>
  );
}

export function CharacterManagementMetric({ label, value }: { label: string; value: ReactNode }) {
  return <div className={styles.metric}><span>{label}</span><strong>{value}</strong></div>;
}
