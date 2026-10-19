"use client";
import { createContext, useContext } from "react";
import type { createLocalEntryController } from "./local-entry-controller";
import type { LocalEntrySnapshot } from "../types/local-entry";

export type LocalEntryController = ReturnType<typeof createLocalEntryController>;
export const LocalEntryContext = createContext<{ controller: LocalEntryController; snapshot: LocalEntrySnapshot } | null>(null);
export function useLocalEntry() {
  const value = useContext(LocalEntryContext);
  if (!value) throw new Error("LocalEntryContext missing");
  return value;
}
