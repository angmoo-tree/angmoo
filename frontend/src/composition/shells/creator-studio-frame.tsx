"use client";

import { useUiText } from "@/hooks/use-ui-text";
import { Home } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { PRODUCT_ROUTES } from "@/lib/navigation/product-routes";

import { CREATOR_STUDIO_SECTIONS, type CreatorStudioSectionId } from "@/composition/shells/creator-studio-navigation";
import styles from "./creator-studio-frame.module.css";
import { CreatorStudioShell } from "@/composition/shells/creator-studio-shell";

type CreatorStudioFrameProps = {
  activeSection: CreatorStudioSectionId;
  children: ReactNode;
};

export function CreatorStudioFrame({
  activeSection,
  children,
}: CreatorStudioFrameProps) {
  const uiText = useUiText("shell");
  return (
    <CreatorStudioShell
      navigation={
        <nav>
          <ul className={styles.navigationList}>
            {CREATOR_STUDIO_SECTIONS.map((section) => (
              <li key={section.id}>
                <Link
                  aria-current={section.id === activeSection ? "page" : undefined}
                  className={[
                    styles.navigationLink,
                    section.id === activeSection ? styles.active : "",
                    section.availability === "planned" ? styles.planned : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  href={section.href}
                >
                  <span>{uiText(section.label)}</span>
                  {section.availability === "planned" ? (
                    <span className={styles.plannedMark}>{uiText("준비 중")}</span>
                  ) : null}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      }
      utility={
        <Link
          aria-label={uiText("Device Home으로 돌아가기")}
          className={styles.homeLink}
          href={PRODUCT_ROUTES.deviceHome}
          title="Device Home"
        >
          <Home size={19} />
        </Link>
      }
    >
      {children}
    </CreatorStudioShell>
  );
}
