"use client";

import {
  Heart,
  MessageCircle,
  Repeat2,
  Share2,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import type { MouseEvent, ReactNode } from "react";

import { LocalProductLink } from "@/features/device-shell/public";
import { useRuntimeRouter } from "@/shared/navigation/public";
import { ProfileAvatar } from "@/shared/ui/public";

import type {
  SocialPostActionKind,
  SocialPostActionPresentation,
  SocialPostPresentation,
} from "../model/social-presentation-contract";
import {
  shouldOpenPostFromCardClick,
  shouldOpenPostFromCardKeyDown,
} from "../model/post-card-navigation";
import { ExpandablePostText } from "./expandable-post-text";
import { PostMediaGrid } from "./post-media-grid";
import styles from "./social-presentation.module.css";

export type SocialPostRowVariant = "feed" | "detail" | "reply";

export type SocialPostRowProps = {
  actions?: readonly SocialPostActionPresentation[];
  authorHref?: string;
  className?: string;
  context?: ReactNode;
  href?: string;
  menu?: ReactNode;
  onAction?: (action: SocialPostActionPresentation) => void;
  post: SocialPostPresentation;
  reference?: ReactNode;
  variant?: SocialPostRowVariant;
};

const ACTION_ICONS: Record<SocialPostActionKind, LucideIcon> = {
  reply: MessageCircle,
  repost: Repeat2,
  like: Heart,
  share: Share2,
};

function classNames(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

function displayHandle(handle: string) {
  return handle.startsWith("@") ? handle : `@${handle}`;
}

export function SocialPostRow({
  actions = [],
  authorHref,
  className,
  context,
  href,
  menu,
  onAction,
  post,
  reference,
  variant = "feed",
}: SocialPostRowProps) {
  const router = useRuntimeRouter();
  const openable = Boolean(href);
  const textClassName = classNames(
    styles.postText,
    variant === "reply" && styles.replyText,
  );
  const clampClassName = classNames(
    styles.clamp,
    variant === "reply" && styles.replyClamp,
  );

  return (
    <article
      aria-label={openable ? `${post.authorName} 게시글 자세히 보기` : undefined}
      className={classNames(
        styles.postRow,
        openable && styles.openableRow,
        variant === "detail" && styles.detailRow,
        variant === "reply" && styles.replyRow,
        className,
      )}
      data-social-post-row={post.id}
      data-variant={variant}
      onClick={
        href
          ? (event) => {
              if (shouldOpenPostFromCardClick(event)) router.push(href);
            }
          : undefined
      }
      onKeyDown={
        href
          ? (event) => {
              if (shouldOpenPostFromCardKeyDown(event)) router.push(href);
            }
          : undefined
      }
      role={openable ? "link" : undefined}
      tabIndex={openable ? 0 : undefined}
    >
      <ProfileAvatar
        avatarUrl={post.authorAvatarUrl}
        name={post.authorName}
        sizeClassName={variant === "reply" ? styles.replyAvatar : styles.avatar}
        textClassName={styles.avatarText}
      />
      <div className={styles.postContent}>
        <header className={styles.postHeader}>
          {authorHref ? (
            <LocalProductLink
              className={styles.authorLink}
              data-post-card-ignore
              href={authorHref}
            >
              {post.authorName}
            </LocalProductLink>
          ) : (
            <span className={styles.author}>{post.authorName}</span>
          )}
          <span className={styles.meta}>
            {post.authorHandle ? (
              <span className={styles.handle}>{displayHandle(post.authorHandle)}</span>
            ) : null}
            {post.authorHandle ? <span className={styles.separator}>·</span> : null}
            <time className={styles.time} dateTime={post.createdAt}>
              {post.timeLabel}
            </time>
          </span>
        </header>

        {context ? (
          <div className={styles.postContext} data-post-card-ignore>
            {context}
          </div>
        ) : null}
        {post.title || post.body ? (
          <ExpandablePostText
            body={post.body}
            clampClassName={clampClassName}
            mentionedCharacters={post.mentionedCharacters}
            textClassName={textClassName}
            title={post.title}
          />
        ) : null}
        <PostMediaGrid media={post.media} />
        {reference ? (
          <div className={styles.reference} data-post-card-ignore>
            {reference}
          </div>
        ) : null}
        <SocialPostActionStrip actions={actions} onAction={onAction} />
      </div>
      {menu ? (
        <div className={styles.menu} data-post-card-ignore>
          {menu}
        </div>
      ) : null}
    </article>
  );
}

export function SocialPostActionStrip({
  actions,
  onAction,
}: {
  actions: readonly SocialPostActionPresentation[];
  onAction?: (action: SocialPostActionPresentation) => void;
}) {
  const visibleActions = actions.filter((action) => action.href || onAction);
  if (visibleActions.length === 0) return null;

  return (
    <div className={styles.actionStrip} aria-label="게시글 동작" role="group">
      {visibleActions.map((action) => {
        const Icon = ACTION_ICONS[action.kind];
        const content = (
          <>
            <Icon className={styles.actionIcon} aria-hidden="true" />
            {action.count !== undefined ? (
              <span className={styles.actionCount}>{action.count}</span>
            ) : null}
          </>
        );
        const label =
          action.count === undefined
            ? action.label
            : `${action.label} ${action.count}`;

        return action.href ? (
          <Link
            aria-label={label}
            className={classNames(
              styles.actionLink,
              action.accent && styles.accentAction,
            )}
            data-post-card-ignore
            href={action.href}
            key={`${action.kind}:${action.href}`}
          >
            {content}
          </Link>
        ) : (
          <button
            aria-label={label}
            className={classNames(
              styles.action,
              action.accent && styles.accentAction,
            )}
            data-post-card-ignore
            key={action.kind}
            onClick={(event: MouseEvent<HTMLButtonElement>) => {
              event.stopPropagation();
              onAction?.(action);
            }}
            type="button"
          >
            {content}
          </button>
        );
      })}
    </div>
  );
}
