"use client";

import { X } from "lucide-react";
import {
  useEffect,
  useId,
  useRef,
  type ButtonHTMLAttributes,
  type DialogHTMLAttributes,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
  type RefObject,
} from "react";

import { classNames } from "./class-names";
import styles from "@/components/ui/semantic-foundation.module.css";

type DataAttributes = {
  [key: `data-${string}`]: string | number | boolean | undefined;
};

type ReservedDialogAttributes =
  | "open"
  | "className"
  | "role"
  | "aria-modal"
  | "aria-labelledby"
  | "aria-describedby"
  | "tabIndex"
  | "onCancel"
  | "onClose"
  | "onKeyDown"
  | "onMouseDown";

export type DialogProps = {
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  closeLabel?: string;
  closeOnBackdrop?: boolean;
  closeOnEscape?: boolean;
  closeButtonAttributes?: Omit<
    ButtonHTMLAttributes<HTMLButtonElement>,
    "aria-label" | "className" | "onClick" | "type"
  > &
    DataAttributes;
  description?: string;
  dialogAttributes?: Omit<
    DialogHTMLAttributes<HTMLDialogElement>,
    ReservedDialogAttributes
  > &
    DataAttributes;
  initialFocusRef?: RefObject<HTMLElement | null>;
  onOpenChange: (open: boolean) => void;
  open: boolean;
  title: string;
};

export function Dialog({
  actions,
  children,
  className,
  closeLabel = "대화상자 닫기",
  closeOnBackdrop = true,
  closeOnEscape = true,
  closeButtonAttributes,
  description,
  dialogAttributes,
  initialFocusRef,
  onOpenChange,
  open,
  title,
}: DialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const generatedId = useId().replaceAll(":", "");
  const titleId = `dialog-title-${generatedId}`;
  const descriptionId = description ? `dialog-description-${generatedId}` : undefined;

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (open) {
      triggerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      if (!dialog.open) dialog.showModal();
      queueMicrotask(() => (initialFocusRef?.current ?? closeRef.current)?.focus());
      return;
    }

    if (dialog.open) dialog.close();
    triggerRef.current?.focus();
  }, [initialFocusRef, open]);

  useEffect(
    () => () => {
      const dialog = dialogRef.current;
      if (dialog?.open) dialog.close();
    },
    [],
  );

  function handleBackdrop(event: MouseEvent<HTMLDialogElement>) {
    if (closeOnBackdrop && event.target === event.currentTarget) onOpenChange(false);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDialogElement>) {
    if (event.key !== "Tab") return;

    const dialog = dialogRef.current;
    if (!dialog) return;
    const focusable = Array.from(
      dialog.querySelectorAll<HTMLElement>(
        'a[href], area[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), iframe, object, embed, summary, [contenteditable]:not([contenteditable="false"]), [tabindex]:not([tabindex="-1"])',
      ),
    ).filter((element) => {
      const style = getComputedStyle(element);
      return (
        !element.hidden &&
        element.getAttribute("aria-hidden") !== "true" &&
        !element.closest("[inert]") &&
        !element.matches(":disabled") &&
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        element.getClientRects().length > 0
      );
    });
    if (focusable.length === 0) {
      event.preventDefault();
      dialog.focus();
      return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <dialog
      {...dialogAttributes}
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      data-ui-primitive="dialog"
      tabIndex={-1}
      className={classNames(styles.dialog, className)}
      onCancel={(event) => {
        event.preventDefault();
        if (closeOnEscape) onOpenChange(false);
      }}
      onClose={() => {
        if (open) onOpenChange(false);
      }}
      onMouseDown={handleBackdrop}
      onKeyDown={handleKeyDown}
    >
      <div onMouseDown={(event) => event.stopPropagation()}>
        <header className={styles.dialogHeader}>
          <div>
            <h2 className={styles.dialogTitle} id={titleId}>
              {title}
            </h2>
            {description ? (
              <p className={styles.dialogDescription} id={descriptionId}>
                {description}
              </p>
            ) : null}
          </div>
          <button
            {...closeButtonAttributes}
            ref={closeRef}
            type="button"
            aria-label={closeLabel}
            data-ui-primitive="dialog-close"
            className={styles.dialogClose}
            onClick={() => onOpenChange(false)}
          >
            <X size={20} aria-hidden="true" />
          </button>
        </header>
        <div className={styles.dialogBody}>{children}</div>
        {actions ? <footer className={styles.dialogActions}>{actions}</footer> : null}
      </div>
    </dialog>
  );
}
