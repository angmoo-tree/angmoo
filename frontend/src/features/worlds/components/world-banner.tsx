"use client";
import Image from "next/image";
import { useState } from "react";
import { useRuntimeMediaUrl } from "@/hooks/use-runtime-media-url";
import { useUiText } from "@/hooks/use-ui-text";
import { safeSameOriginMediaUrl } from "@/lib/media/safe-media-url";
import styles from "./world-introduction.module.css";
const DEFAULT_BANNER = "/world-default-banner.svg";

export function WorldBanner({ source, alt }: { source: string | null; alt: string }) {
  const uiText = useUiText("worlds");
  const resolved = useRuntimeMediaUrl(safeSameOriginMediaUrl(source));
  const [failed, setFailed] = useState<string | null>(null);
  const actual = Boolean(resolved && resolved !== failed);
  return <div className={styles.banner} data-world-banner={actual ? "registered" : "default"}>
    <Image src={actual ? resolved! : DEFAULT_BANNER} alt={actual ? alt : uiText("World 기본 배너")} fill unoptimized priority sizes="(max-width: 960px) 100vw, 960px" onError={() => { if (actual) setFailed(resolved); }} />
  </div>;
}
