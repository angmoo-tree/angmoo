import type { ReactNode } from "react";
import { LocalProductLink } from "@/components/navigation/local-product-link";
import { Badge } from "@/components/ui/status";

export type ActivityTimelineItem = {
  id: string | number;
  icon: ReactNode;
  actionLabel: string;
  occurredAt: string;
  displayedTime: string;
  timeTitle: string;
  headline: string;
  detail?: ReactNode;
  link?: { href: string; label: string; title?: string };
};

export function ActivityTimeline({ items, timezone, timezoneLabel, empty }: {
  items: ActivityTimelineItem[]; timezone: string; timezoneLabel: string; empty: ReactNode;
}) {
  if (!items.length) return empty;
  return <div className="flex flex-col border-t border-border-default">
    <p className="sticky top-0 z-10 border-b border-border-default bg-surface-subtle px-4 py-2 text-xs font-bold text-text-secondary" data-activity-log-timezone={timezone}>{timezoneLabel}{timezone}</p>
    {items.map(item => <article key={item.id} className="border-b border-border-default bg-surface py-5">
      <div className="flex gap-4">
        <div className="flex size-11 shrink-0 items-center justify-center rounded-full bg-surface-muted text-text-secondary">{item.icon}</div>
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Badge>{item.actionLabel}</Badge>
            <time dateTime={item.occurredAt} className="text-[14px] font-medium text-text-secondary" title={item.timeTitle}>{item.displayedTime}</time>
          </div>
          <p className="break-words text-[17px] font-extrabold leading-7 text-text-strong">{item.headline}</p>
          {item.detail ? <p className="mt-1 break-words text-[15px] font-medium leading-6 text-text-secondary">{item.detail}</p> : null}
          {item.link ? <LocalProductLink href={item.link.href} title={item.link.title} className="mt-3 inline-flex min-h-11 items-center rounded-full border border-border-control bg-surface px-4 py-2 text-[13px] font-extrabold text-text-strong transition-colors hover:border-brand-soft-border hover:bg-surface-subtle focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]">{item.link.label}</LocalProductLink> : null}
        </div>
      </div>
    </article>)}
  </div>;
}
