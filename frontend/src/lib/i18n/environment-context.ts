"use client";
import { createContext } from "react";
import type { UserEnvironment } from "@/types/user-environment";

export type EnvironmentContextValue = {
  environment: UserEnvironment | null;
  ready: boolean;
  errorCode: string | null;
  retry?: () => void;
};
export const EnvironmentContext = createContext<EnvironmentContextValue>({ environment: null, ready: false, errorCode: null });
