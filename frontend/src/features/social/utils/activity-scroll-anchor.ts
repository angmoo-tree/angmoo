/** Keep an adjacent, surviving row stable when canonical likes membership changes. */
export function captureActivityAnchor(container: HTMLElement | null, nextIds: ReadonlySet<string>): (() => void) | null {
  if (!container) return null;
  const rows = [...container.querySelectorAll<HTMLElement>("[data-social-post-row]")];
  const focused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  const focusedIndex = rows.findIndex(row => focused && row.contains(focused));
  const candidates = focusedIndex >= 0
    ? [...rows.slice(focusedIndex), ...rows.slice(0, focusedIndex).reverse()]
    : rows;
  const scrollOwner = container.closest<HTMLElement>('[data-device-scroll-owner="true"]');
  const viewport = scrollOwner?.getBoundingClientRect() ?? { top: 0, bottom: window.innerHeight };
  const row = candidates.find(candidate => nextIds.has(candidate.dataset.socialPostRow ?? "")
    && (focusedIndex >= 0 || (candidate.getBoundingClientRect().bottom > viewport.top && candidate.getBoundingClientRect().top < viewport.bottom)));
  if (!row) return null;
  const id = row.dataset.socialPostRow;
  const top = row.getBoundingClientRect().top;
  const restoreFocus = focusedIndex >= 0 && !nextIds.has(rows[focusedIndex].dataset.socialPostRow ?? "");
  return () => {
    const current = [...container.querySelectorAll<HTMLElement>("[data-social-post-row]")].find(candidate => candidate.dataset.socialPostRow === id);
    if (!current) return;
    if (restoreFocus) current.querySelector<HTMLElement>("a, button")?.focus({ preventScroll: true });
    const delta = current.getBoundingClientRect().top - top;
    if (scrollOwner) scrollOwner.scrollTop += delta;
    else window.scrollBy(0, delta);
  };
}
