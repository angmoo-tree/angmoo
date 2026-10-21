"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, type RefObject } from "react";
import { scrollViewport } from "./use-element-visibility";

// LOCAL: compensate item insertion and late image size changes in the existing
// scroll owner. Capture again when the reader moves while a request is pending.
export function useReadAnchor(ref: RefObject<HTMLElement | null>, selector: string, attribute: string, identity = "") {
  const anchor = useRef<{ id: string; top: number } | null>(null);
  const remember = useCallback(() => {
    const surface = ref.current;
    if (!surface) return;
    const top = scrollViewport(surface)?.getBoundingClientRect().top ?? 0;
    const node = [...surface.querySelectorAll<HTMLElement>(selector)].find(node => node.getBoundingClientRect().bottom > top);
    anchor.current = node ? { id: node.getAttribute(attribute)!, top: node.getBoundingClientRect().top } : null;
  }, [attribute, ref, selector]);
  const restore = useCallback(() => {
    const surface = ref.current;
    if (!surface || !anchor.current) return;
    const node = [...surface.querySelectorAll<HTMLElement>(selector)].find(n => n.getAttribute(attribute) === anchor.current!.id);
    if (!node) return;
    const difference = node.getBoundingClientRect().top - anchor.current.top;
    const viewport = scrollViewport(surface);
    if (viewport) viewport.scrollTop += difference;
    else window.scrollBy(0, difference);
  }, [attribute, ref, selector]);
  useLayoutEffect(restore);
  useEffect(() => {
    const surface = ref.current;
    if (!surface) return;
    const viewport = scrollViewport(surface) ?? window;
    viewport.addEventListener("scroll", remember, { passive: true });
    let frame = 0;
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => {
      cancelAnimationFrame(frame); frame = requestAnimationFrame(restore);
    }) : null;
    observer?.observe(surface);
    return () => { viewport.removeEventListener("scroll", remember); observer?.disconnect(); cancelAnimationFrame(frame); };
  }, [ref, remember, restore, identity]);
  return { remember };
}
