"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { isStaticFrontendProfile } from "@/shared/runtime/public";

import { isStaticLocalProductRouteSupported } from "../model/device-navigation";

import styles from "./local-product-link.module.css";

export type LocalProductLinkProps = {
  ariaLabel?: string;
  children: ReactNode;
  className?: string;
  href: string;
  rel?: string;
  target?: "_blank";
  title?: string;
};

/**
 * Product-aware link boundary. Hosted Next routes stay available in Browser
 * mode; static/Tauri renders unsupported destinations as inert presentation
 * instead of a control that can only end in StaticNotFound.
 */
export function LocalProductLink({
  ariaLabel,
  children,
  className,
  href,
  rel,
  target,
  title,
}: LocalProductLinkProps) {
  const unavailable =
    isStaticFrontendProfile() && !isStaticLocalProductRouteSupported(href);

  if (unavailable) {
    return (
      <span
        aria-disabled="true"
        aria-label={ariaLabel}
        className={[className, styles.unavailable].filter(Boolean).join(" ")}
        data-product-route-unavailable="true"
        onClick={(event) => {
          // A disabled destination can live inside a clickable feed row. Keep
          // that parent action from turning this unavailable control into a
          // different, surprising navigation target.
          event.preventDefault();
          event.stopPropagation();
        }}
        role="link"
        title={title ?? "현재 앱에서는 열 수 없는 화면입니다."}
      >
        {children}
      </span>
    );
  }

  return (
    <Link
      aria-label={ariaLabel}
      className={className}
      href={href}
      rel={rel}
      target={target}
      title={title}
    >
      {children}
    </Link>
  );
}
