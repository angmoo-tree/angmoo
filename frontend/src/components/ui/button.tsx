import { LoaderCircle } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

import { classNames } from "@/utils/class-names";
import styles from "./semantic-foundation.module.css";

export type ButtonVariant = "primary" | "strong" | "secondary" | "ghost" | "danger";

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  compact?: boolean;
  fullWidth?: boolean;
  loading?: boolean;
  loadingLabel?: string;
  variant?: ButtonVariant;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    children,
    className,
    compact = false,
    disabled = false,
    fullWidth = false,
    loading = false,
    loadingLabel,
    type = "button",
    variant = "primary",
    ...props
  },
  ref,
) {
  return (
    <button
      {...props}
      ref={ref}
      type={type}
      aria-busy={loading || undefined}
      data-loading={loading || undefined}
      data-ui-primitive="button"
      disabled={disabled || loading}
      className={classNames(
        styles.button,
        styles[variant],
        compact && styles.compactButton,
        fullWidth && styles.fullWidth,
        className,
      )}
    >
      {loading ? (
        <LoaderCircle
          className={styles.loadingIcon}
          data-ui-part="loading-indicator"
          aria-hidden="true"
        />
      ) : null}
      <span>{loading && loadingLabel ? loadingLabel : children}</span>
    </button>
  );
});

export type IconButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "aria-label"> & {
  children: ReactNode;
  label: string;
  loading?: boolean;
  loadingLabel?: string;
  variant?: ButtonVariant;
};

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  function IconButton(
    {
      children,
      className,
      disabled = false,
      label,
      loading = false,
      loadingLabel,
      type = "button",
      variant = "ghost",
      ...props
    },
    ref,
  ) {
    return (
      <button
        {...props}
        ref={ref}
        type={type}
        aria-busy={loading || undefined}
        aria-label={loading && loadingLabel ? loadingLabel : label}
        data-loading={loading || undefined}
        data-ui-primitive="icon-button"
        disabled={disabled || loading}
        className={classNames(styles.iconButton, styles[variant], className)}
      >
        {loading ? (
          <LoaderCircle
            className={styles.loadingIcon}
            data-ui-part="loading-indicator"
            aria-hidden="true"
          />
        ) : (
          children
        )}
      </button>
    );
  },
);
