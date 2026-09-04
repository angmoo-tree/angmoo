import type { HTMLAttributes, ReactNode } from "react";

import { classNames } from "./class-names";
import styles from "@/components/ui/semantic-foundation.module.css";

export type CardProps = HTMLAttributes<HTMLElement> & {
  as?: "div" | "section" | "article";
  elevated?: boolean;
};

export function Card({ as: Component = "div", className, elevated = false, ...props }: CardProps) {
  return (
    <Component
      {...props}
      data-ui-primitive="card"
      className={classNames(styles.card, elevated && styles.cardElevated, className)}
    />
  );
}

export type ListRowProps = Omit<HTMLAttributes<HTMLDivElement>, "children"> & {
  children: ReactNode;
};

export function ListRow({ children, className, ...props }: ListRowProps) {
  return (
    <div
      {...props}
      data-ui-primitive="list-row"
      className={classNames(styles.listRow, className)}
    >
      {children}
    </div>
  );
}
