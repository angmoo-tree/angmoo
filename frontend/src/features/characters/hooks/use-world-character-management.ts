"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/hooks/use-auth";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { ApiRequestError } from "@/lib/http/api-request";
import { DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT } from "@/lib/runtime/runtime-config";
import { getWorldCharacterManagement, getWorldCharacterSettings } from "../api/world-character-management-client";
import type { WorldCharacterManagementRead, WorldCharacterSettingsRead } from "../types/world-character-management";

export function useWorldCharacterManagement(worldId: string, worldCharacterId: string) {
  const { status, user } = useAuth();
  const [read, setRead] = useState<WorldCharacterManagementRead | null>(null);
  const [settings, setSettings] = useState<WorldCharacterSettingsRead | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [settingsError, setSettingsError] = useState<Error | null>(null);
  const [pending, setPending] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const generation = useRef(0);
  const mutationRevision = useRef(0);
  const requests = useRef(new Set<AbortController>());
  const operations = useRef(new Set<string>());
  const [readScope, setReadScope] = useState<ReturnType<typeof captureAuthRequestScope> | null>(null);

  const invalidate = useCallback(() => {
    generation.current += 1;
    requests.current.forEach(controller => controller.abort());
    operations.current.clear();
    setRead(null); setSettings(null); setError(null); setSettingsError(null); setPending(new Set()); setLoading(true);
  }, []);

  const load = useCallback(async () => {
    if (status !== "authenticated") return;
    const currentGeneration = generation.current, currentMutation = mutationRevision.current;
    const scope = captureAuthRequestScope(), controller = new AbortController();
    requests.current.add(controller);
    const current = () => !controller.signal.aborted && currentGeneration === generation.current && isCurrentAuthRequestScope(scope);
    try {
      const result = await getWorldCharacterManagement(worldId, worldCharacterId, { signal: controller.signal });
      if (!current() || currentMutation !== mutationRevision.current) return;
      setReadScope(scope);
      setRead(previous => previous && previous.item.revision > result.item.revision ? previous : result);
      if (!result.can_manage || !result.item.capabilities.can_edit_settings) setSettings(null);
      setError(null); setLoading(false);
      return result;
    } catch (reason) {
      if (!current() || currentMutation !== mutationRevision.current) return;
      setError(reason instanceof Error ? reason : new Error("world_character_management_unavailable"));
      if (isAccessFailure(reason)) { setRead(null); setSettings(null); }
      setLoading(false);
    } finally { requests.current.delete(controller); }
  }, [status, worldId, worldCharacterId]);

  useEffect(() => {
    let active = true;
    const currentRequests = requests.current;
    generation.current += 1;
    requests.current.forEach(controller => controller.abort());
    queueMicrotask(() => { if (active) { invalidate(); void load(); } });
    const runtimeChanged = () => { invalidate(); void load(); };
    window.addEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, runtimeChanged);
    return () => {
      active = false; generation.current += 1;
      currentRequests.forEach(controller => controller.abort());
      window.removeEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, runtimeChanged);
    };
  }, [invalidate, load, user?.id]);

  const loadSettings = useCallback(async () => {
    if (!read?.can_manage || !read.item.capabilities.can_edit_settings || operations.current.has("settings-read")) return;
    operations.current.add("settings-read"); setPending(new Set(operations.current));
    const currentGeneration = generation.current, currentMutation = mutationRevision.current;
    const scope = captureAuthRequestScope(), controller = new AbortController(); requests.current.add(controller);
    const current = () => !controller.signal.aborted && currentGeneration === generation.current && isCurrentAuthRequestScope(scope);
    try {
      const result = await getWorldCharacterSettings(worldId, worldCharacterId, { signal: controller.signal });
      if (!current() || currentMutation !== mutationRevision.current) return;
      setSettings(result); setSettingsError(null);
    } catch (reason) {
      if (!current() || currentMutation !== mutationRevision.current) return;
      setSettingsError(reason instanceof Error ? reason : new Error("world_character_settings_unavailable"));
      if (isAccessFailure(reason)) { setSettings(null); setRead(null); setError(reason as Error); }
    } finally {
      requests.current.delete(controller);
      if (currentGeneration === generation.current) { operations.current.delete("settings-read"); setPending(new Set(operations.current)); }
    }
  }, [read, worldCharacterId, worldId]);

  async function mutate<T>(key: string, request: (signal: AbortSignal) => Promise<T>, accept: (result: T) => void): Promise<T | null> {
    if (!read || status !== "authenticated" || operations.current.has(key)) return null;
    operations.current.add(key); setPending(new Set(operations.current)); setError(null);
    const currentGeneration = generation.current, scope = captureAuthRequestScope(), controller = new AbortController(); requests.current.add(controller);
    const current = () => !controller.signal.aborted && currentGeneration === generation.current && isCurrentAuthRequestScope(scope);
    try {
      const result = await request(controller.signal);
      if (!current()) return null;
      mutationRevision.current += 1; accept(result); return result;
    } catch (reason) {
      if (!current()) return null;
      setError(reason instanceof Error ? reason : new Error("world_character_operation_failed"));
      if (isAccessFailure(reason)) { setRead(null); setSettings(null); }
      return null;
    } finally {
      requests.current.delete(controller);
      if (currentGeneration === generation.current) { operations.current.delete(key); setPending(new Set(operations.current)); }
    }
  }

  function acceptManagement(result: WorldCharacterManagementRead) {
    setRead(previous => previous && previous.item.revision > result.item.revision ? previous : result);
  }

  function acceptSettings(result: WorldCharacterSettingsRead) {
    setSettings(result);
    setRead(previous => previous && previous.item.revision <= result.revision ? { ...previous, item: { ...previous.item, revision: result.revision,
      profile: { ...previous.item.profile, ...result.profile }, settings: previous.item.settings ? { ...previous.item.settings,
        active_hours_start: result.settings.active_hours_start, active_hours_end: result.settings.active_hours_end,
        activity_interval_minutes: result.settings.activity_interval_minutes, max_posts_per_day: result.settings.max_posts_per_day,
        max_comments_per_day: result.settings.max_comments_per_day,
      } : null } } : previous);
  }

  const currentScope = captureAuthRequestScope();
  const scopedRead = status === "authenticated" && readScope && readScope.userId === user?.id
    && readScope.apiBaseUrl === currentScope.apiBaseUrl && readScope.launchToken === currentScope.launchToken
    && read?.world_id === worldId && read.world_character_id === worldCharacterId ? read : null;
  return { read: scopedRead, settings: scopedRead?.can_manage ? settings : null, loading, error, settingsError, pending, load, loadSettings, mutate, acceptManagement, acceptSettings };
}

function isAccessFailure(reason: unknown) {
  return reason instanceof ApiRequestError && [401, 403, 404].includes(reason.status);
}
