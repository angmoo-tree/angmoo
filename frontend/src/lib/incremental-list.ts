"use client";

import { useEffect, useState } from "react";
import type { UIEvent } from "react";

const DEFAULT_STEP = 5;

type IncrementState = {
  initialCount: number;
  resetKey: unknown;
  step: number;
  visibleCount: number;
};

export function usePageIncrementalCount(
  total: number,
  resetKey: unknown,
  step = DEFAULT_STEP,
) {
  const [state, setState] = useState<IncrementState>({
    initialCount: step,
    resetKey,
    step,
    visibleCount: step,
  });
  const visibleCount = resolveVisibleCount(state, resetKey, step, step);

  useEffect(() => {
    if (visibleCount >= total) return;

    function handleScroll() {
      const element = document.documentElement;
      const nearBottom = window.innerHeight + window.scrollY >= element.scrollHeight - 360;
      if (!nearBottom) return;
      setState((current) => ({
        initialCount: step,
        resetKey,
        step,
        visibleCount: Math.min(
          total,
          resolveVisibleCount(current, resetKey, step, step) + step,
        ),
      }));
    }

    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [resetKey, step, total, visibleCount]);

  return Math.min(total, visibleCount);
}

export function useContainerIncrementalCount(
  total: number,
  resetKey: unknown,
  step = DEFAULT_STEP,
  initialCount = step,
) {
  const resolvedInitialCount = Math.max(step, initialCount);
  const [state, setState] = useState<IncrementState>({
    initialCount: resolvedInitialCount,
    resetKey,
    step,
    visibleCount: resolvedInitialCount,
  });
  const visibleCount = resolveVisibleCount(
    state,
    resetKey,
    step,
    resolvedInitialCount,
  );

  function handleScroll(event: UIEvent<HTMLElement>) {
    if (visibleCount >= total) return;
    const element = event.currentTarget;
    const nearBottom =
      element.scrollTop + element.clientHeight >= element.scrollHeight - 180;
    if (!nearBottom) return;
    setState((current) => ({
      resetKey,
      step,
      initialCount: resolvedInitialCount,
      visibleCount: Math.min(
        total,
        resolveVisibleCount(current, resetKey, step, resolvedInitialCount) + step,
      ),
    }));
  }

  return {
    visibleCount: Math.min(total, visibleCount),
    handleScroll,
  };
}

function resolveVisibleCount(
  state: IncrementState,
  resetKey: unknown,
  step: number,
  initialCount: number,
) {
  return Object.is(state.resetKey, resetKey) &&
    state.step === step &&
    state.initialCount === initialCount
    ? state.visibleCount
    : initialCount;
}
