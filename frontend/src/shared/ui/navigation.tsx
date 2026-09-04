"use client";

import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";

import { classNames } from "./class-names";
import styles from "@/components/ui/semantic-foundation.module.css";

export type TabItem = {
  disabled?: boolean;
  id: string;
  label: string;
  panelId: string;
};

export type TabsProps = {
  ariaLabel: string;
  className?: string;
  items: TabItem[];
  onSelect: (id: string) => void;
  selectedId: string;
};

export function Tabs({ ariaLabel, className, items, onSelect, selectedId }: TabsProps) {
  const tabRefs = useRef(new Map<string, HTMLButtonElement>());

  function moveFocus(event: KeyboardEvent<HTMLButtonElement>, currentId: string) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    const enabled = items.filter((item) => !item.disabled);
    const currentIndex = enabled.findIndex((item) => item.id === currentId);
    if (currentIndex < 0 || enabled.length === 0) return;
    event.preventDefault();
    const nextIndex =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? enabled.length - 1
          : event.key === "ArrowRight"
            ? (currentIndex + 1) % enabled.length
            : (currentIndex - 1 + enabled.length) % enabled.length;
    const next = enabled[nextIndex];
    onSelect(next.id);
    tabRefs.current.get(next.id)?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      data-ui-primitive="tabs"
      className={classNames(styles.tabs, className)}
    >
      {items.map((item) => {
        const selected = item.id === selectedId;
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            id={`${item.panelId}-tab`}
            aria-controls={item.panelId}
            aria-selected={selected}
            data-ui-primitive="tab"
            disabled={item.disabled}
            tabIndex={selected ? 0 : -1}
            ref={(node) => {
              if (node) tabRefs.current.set(item.id, node);
              else tabRefs.current.delete(item.id);
            }}
            className={classNames(styles.tab, selected && styles.tabSelected)}
            onClick={() => onSelect(item.id)}
            onKeyDown={(event) => moveFocus(event, item.id)}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}

export type PageHeaderProps = {
  actions?: ReactNode;
  backAction?: ReactNode;
  className?: string;
  subtitle?: string;
  title: string;
};

export function PageHeader({
  actions,
  backAction,
  className,
  subtitle,
  title,
}: PageHeaderProps) {
  return (
    <header
      data-ui-primitive="page-header"
      className={classNames(styles.pageHeader, className)}
    >
      <div className={styles.pageHeaderSide}>{backAction}</div>
      <div className={styles.pageHeaderTitleBlock}>
        <h1 className={styles.pageHeaderTitle}>{title}</h1>
        {subtitle ? <p className={styles.pageHeaderSubtitle}>{subtitle}</p> : null}
      </div>
      <div className={classNames(styles.pageHeaderSide, styles.pageHeaderEnd)}>{actions}</div>
    </header>
  );
}

export type BottomNavigationItem = {
  disabled?: boolean;
  icon: ReactNode;
  id: string;
  label: string;
  href?: string;
};

export type BottomNavigationProps = {
  activeId: string | null;
  ariaLabel?: string;
  className?: string;
  items: BottomNavigationItem[];
  onSelect?: (id: string) => void;
};

export function BottomNavigation({
  activeId,
  ariaLabel = "주요 메뉴",
  className,
  items,
  onSelect,
}: BottomNavigationProps) {
  const activeItemRef = useRef<HTMLAnchorElement | HTMLButtonElement | null>(null);

  useEffect(() => {
    activeItemRef.current?.scrollIntoView({
      behavior: "instant",
      block: "nearest",
      inline: "nearest",
    });
  }, [activeId, items.length]);

  return (
    <nav
      aria-label={ariaLabel}
      data-ui-primitive="bottom-navigation"
      className={classNames(styles.bottomNavigation, className)}
    >
      {items.map((item) => {
        const active = item.id === activeId;
        const content = (
          <>
            <span className={styles.bottomNavigationIcon} aria-hidden="true">
              {item.icon}
            </span>
            <span>{item.label}</span>
          </>
        );
        if (item.href && !item.disabled) {
          return (
            <a
              key={item.id}
              ref={
                active
                  ? (node) => {
                      activeItemRef.current = node;
                    }
                  : undefined
              }
              href={item.href}
              aria-current={active ? "page" : undefined}
              data-ui-primitive="bottom-navigation-item"
              className={classNames(
                styles.bottomNavigationItem,
                active && styles.bottomNavigationItemActive,
              )}
              onClick={() => onSelect?.(item.id)}
            >
              {content}
            </a>
          );
        }
        return (
          <button
            key={item.id}
            ref={
              active
                ? (node) => {
                    activeItemRef.current = node;
                  }
                : undefined
            }
            type="button"
            aria-current={active ? "page" : undefined}
            data-ui-primitive="bottom-navigation-item"
            disabled={item.disabled}
            className={classNames(
              styles.bottomNavigationItem,
              active && styles.bottomNavigationItemActive,
            )}
            onClick={() => onSelect?.(item.id)}
          >
            {content}
          </button>
        );
      })}
    </nav>
  );
}
