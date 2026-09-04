"use client";

import { CircleAlert } from "lucide-react";
import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

import { classNames } from "./class-names";
import styles from "@/components/ui/semantic-foundation.module.css";

function hasInvalidState(value: unknown): boolean {
  return value === true || value === "true" || value === "grammar" || value === "spelling";
}

type FieldControlProps = {
  "aria-describedby"?: string;
  "aria-invalid"?: true;
  id: string;
  required?: true;
};

export type FieldProps = {
  children: (props: FieldControlProps) => ReactNode;
  className?: string;
  error?: string;
  helperText?: string;
  id?: string;
  label: string;
  required?: boolean;
};

export function Field({
  children,
  className,
  error,
  helperText,
  id,
  label,
  required = false,
}: FieldProps) {
  const generatedId = useId();
  const controlId = id ?? `field-${generatedId.replaceAll(":", "")}`;
  const hintId = helperText ? `${controlId}-hint` : undefined;
  const errorId = error ? `${controlId}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className={classNames(styles.field, className)} data-ui-primitive="field">
      <div className={styles.fieldHeader}>
        <label className={styles.fieldLabel} htmlFor={controlId}>
          {label}
          {required ? (
            <span className={styles.requiredMark} aria-hidden="true">
              *
            </span>
          ) : null}
        </label>
      </div>
      {children({
        id: controlId,
        "aria-describedby": describedBy,
        "aria-invalid": error ? true : undefined,
        required: required ? true : undefined,
      })}
      {helperText ? (
        <p className={styles.fieldHint} id={hintId}>
          {helperText}
        </p>
      ) : null}
      {error ? (
        <p className={styles.fieldError} id={errorId} role="alert">
          <CircleAlert size={15} aria-hidden="true" />
          <span>{error}</span>
        </p>
      ) : null}
    </div>
  );
}

export type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  invalid?: boolean;
  loading?: boolean;
};

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, disabled, invalid = false, loading = false, readOnly, ...props },
  ref,
) {
  const visuallyInvalid = invalid || hasInvalidState(props["aria-invalid"]);
  return (
    <input
      {...props}
      ref={ref}
      aria-busy={loading || undefined}
      aria-invalid={invalid ? true : props["aria-invalid"]}
      data-ui-primitive="input"
      disabled={disabled}
      readOnly={readOnly || loading}
      className={classNames(
        styles.control,
        visuallyInvalid && styles.controlInvalid,
        className,
      )}
    />
  );
});

export type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  invalid?: boolean;
  loading?: boolean;
};

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { className, disabled, invalid = false, loading = false, readOnly, ...props },
  ref,
) {
  const visuallyInvalid = invalid || hasInvalidState(props["aria-invalid"]);
  return (
    <textarea
      {...props}
      ref={ref}
      aria-busy={loading || undefined}
      aria-invalid={invalid ? true : props["aria-invalid"]}
      data-ui-primitive="textarea"
      disabled={disabled}
      readOnly={readOnly || loading}
      className={classNames(
        styles.control,
        styles.textarea,
        visuallyInvalid && styles.controlInvalid,
        className,
      )}
    />
  );
});

export type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & {
  invalid?: boolean;
  loading?: boolean;
};

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className, disabled, invalid = false, loading = false, ...props },
  ref,
) {
  const visuallyInvalid = invalid || hasInvalidState(props["aria-invalid"]);
  return (
    <select
      {...props}
      ref={ref}
      aria-busy={loading || undefined}
      aria-invalid={invalid ? true : props["aria-invalid"]}
      data-ui-primitive="select"
      disabled={disabled || loading}
      className={classNames(
        styles.control,
        styles.select,
        visuallyInvalid && styles.controlInvalid,
        className,
      )}
    />
  );
});
