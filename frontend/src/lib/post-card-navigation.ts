import type { KeyboardEvent, MouseEvent } from "react";

const INTERACTIVE_SELECTOR =
  'a, button, input, textarea, select, summary, [role="button"], [data-post-card-ignore]';

function hasSelectedText() {
  if (typeof window === "undefined") return false;
  const selection = window.getSelection();
  return Boolean(selection && !selection.isCollapsed && selection.toString().trim());
}

function isInteractiveEventTarget(
  target: EventTarget | null,
  currentTarget: EventTarget | null,
) {
  if (!(target instanceof Element) || !(currentTarget instanceof Element)) {
    return false;
  }
  const interactive = target.closest(INTERACTIVE_SELECTOR);
  return Boolean(interactive && currentTarget.contains(interactive));
}

export function shouldOpenPostFromCardClick(event: MouseEvent<HTMLElement>) {
  if (
    event.defaultPrevented ||
    event.button !== 0 ||
    event.metaKey ||
    event.ctrlKey ||
    event.shiftKey ||
    event.altKey ||
    hasSelectedText()
  ) {
    return false;
  }

  return !isInteractiveEventTarget(event.target, event.currentTarget);
}

export function shouldOpenPostFromCardKeyDown(event: KeyboardEvent<HTMLElement>) {
  if (
    event.defaultPrevented ||
    event.key !== "Enter" ||
    event.metaKey ||
    event.ctrlKey ||
    event.shiftKey ||
    event.altKey
  ) {
    return false;
  }

  return !isInteractiveEventTarget(event.target, event.currentTarget);
}
