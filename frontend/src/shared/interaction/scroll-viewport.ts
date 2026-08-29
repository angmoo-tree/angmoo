export type ScrollEventTarget = Window | HTMLElement;

export function resolveScrollEventTarget(
  scrollOwner: HTMLElement | null | undefined,
): ScrollEventTarget {
  if (scrollOwner) return scrollOwner;
  if (typeof window === "undefined") {
    throw new Error("A scroll event target can only be resolved in a browser.");
  }
  return window;
}

export function getScrollTop(target: ScrollEventTarget): number {
  if (!isWindowTarget(target)) return target.scrollTop;

  const scrollingElement = document.scrollingElement;
  return (
    target.scrollY ||
    scrollingElement?.scrollTop ||
    document.documentElement.scrollTop ||
    document.body.scrollTop ||
    0
  );
}

export function isScrollNearBottom(
  target: ScrollEventTarget,
  thresholdPx: number,
): boolean {
  const threshold = Math.max(0, thresholdPx);

  if (!isWindowTarget(target)) {
    return (
      target.clientHeight + target.scrollTop >= target.scrollHeight - threshold
    );
  }

  const documentHeight = Math.max(
    document.scrollingElement?.scrollHeight ?? 0,
    document.documentElement.scrollHeight,
    document.body.scrollHeight,
  );
  return target.innerHeight + getScrollTop(target) >= documentHeight - threshold;
}

function isWindowTarget(target: ScrollEventTarget): target is Window {
  return typeof window !== "undefined" && target === window;
}
