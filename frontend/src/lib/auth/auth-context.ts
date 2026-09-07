"use client";

import { createContext } from "react";
import type { UserRead } from "@/lib/auth/browser-session";

export type AuthStatus = "checking" | "authenticated" | "unauthenticated";

export type AuthContextValue = {
  status: AuthStatus;
  user: UserRead | null;
  refresh: () => Promise<void>;
};

export const AuthContext = createContext<AuthContextValue | null>(null);

