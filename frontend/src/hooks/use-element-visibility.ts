"use client";

import { useCallback, useEffect, useState } from "react";

export function scrollViewport(element: HTMLElement): HTMLElement | null {
  for (let parent = element.parentElement; parent; parent = parent.parentElement) {
    if (/(auto|scroll)/.test(getComputedStyle(parent).overflowY)) return parent;
  }
  return null;
}

// Product-neutral observer: use the real nearest scrolling viewport. Callers
// decide whether visibility should pause work or latch a media download.
export function useElementVisibility<T extends HTMLElement>({ margin = 0, once = false, identity = "" } = {}) {
  const [element, setElement] = useState<T | null>(null);
  const ref = useCallback((next: T | null) => { setElement(next); }, []);
  const [state, setState] = useState({ identity, visible: false });
  useEffect(() => {
    if (!element) return;
    if (typeof IntersectionObserver === "undefined") {
      // Only the already bounded rendered page is admitted by this fallback.
      const timer = setTimeout(() => setState({ identity, visible: true }), 0);
      return () => clearTimeout(timer);
    }
    const observer = new IntersectionObserver(entries => {
      const visible = Boolean(entries[0]?.isIntersecting);
      setState(previous => ({ identity, visible: visible || (once && previous.identity === identity && previous.visible) }));
      if (once && visible) observer.disconnect();
    }, { root: scrollViewport(element), rootMargin: `${margin}px 0px` });
    observer.observe(element);
    return () => observer.disconnect();
  }, [element, identity, margin, once]);
  return { ref, visible: state.identity === identity && state.visible };
}
