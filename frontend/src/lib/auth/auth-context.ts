"use client";

import { createContext } from "react";
import type { UserRead } from "@/lib/auth/browser-session";

export type AuthStatus = "checking" | "authenticated" | "unauthenticated";

export type AuthContextValue = {
  status: AuthStatus;
  user: UserRead | null;
  refresh: () => Promise<void>;
  sessionRevision?: number;
};

export const AuthContext = createContext<AuthContextValue | null>(null);

