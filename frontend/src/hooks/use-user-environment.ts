"use client";
import { useContext } from "react";
import { EnvironmentContext } from "@/lib/i18n/environment-context";

export function useUserEnvironment() {
  return useContext(EnvironmentContext);
}
