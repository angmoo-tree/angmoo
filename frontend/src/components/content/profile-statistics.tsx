import type { HTMLAttributes } from "react";
import styles from "./profile-statistics.module.css";

export function ProfileStatistics({ statistics, className = "", ...props }: HTMLAttributes<HTMLDListElement> & { statistics: { label: string; value: string | number }[] }) {
  return <dl {...props} className={`${styles.statistics} ${className}`}>
    {statistics.map((stat) => <div key={stat.label}><dt>{stat.label}</dt><dd>{stat.value}</dd></div>)}
  </dl>;
}
