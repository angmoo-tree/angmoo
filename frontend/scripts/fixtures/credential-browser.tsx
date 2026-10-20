import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { CredentialFields, type SecretMetadata, type SecretWrite } from "../../src/components/ui/credential-fields";
import { ApiRequestError } from "../../src/lib/http/error-contract";
import { connectionStore } from "../../src/features/identity/controllers/local-connection-store";
import { WorldVisionControls } from "../../src/features/media/components/world-image-policy-controls";
import { I18nextProvider } from "react-i18next";
import i18next from "i18next";
import mediaEn from "../../src/features/media/locales/en.json";
import mediaKo from "../../src/features/media/locales/ko.json";

const fixture = {
  metadata: { provider: "google", model: "model-a", thinking_level: "high", has_key: false, fingerprint: null, revision: 0, configuration_revision: 1 } as SecretMetadata,
  writes: [] as SecretWrite[], deletes: 0, reads: 0, failure: "", refresh: () => {},
  store: connectionStore, changed: 0,
};
(window as unknown as { fixture: typeof fixture }).fixture = fixture;
connectionStore.subscribe(() => fixture.changed++);
const text = { model: "Model", key: "New API key", stored: "Key saved", missing: "No key", save: "Save", remove: "Delete", confirm: "Delete?", failed: "Legacy failure", saved: "Saved", keep: "Leave blank to keep", unsupported: "Stored model", reload: "Reload", review: "Review and keep inputs", loadFailed: "Load failed", keyLoadFailed: "Key status failed", saveFailed: "Save rejected", deleteFailed: "Delete rejected", conflict: "Settings changed", unknown: "Result unknown" };
function App() {
  const [revision, setRevision] = useState(0);
  useEffect(() => { fixture.refresh = () => setRevision(value => value + 1); return () => { fixture.refresh = () => {}; }; }, []);
  return <CredentialFields scopeKey="synthetic-scope" refreshRevision={revision}
    profiles={["model-a", "model-b"].map(model => ({ provider: "google", model, thinking_level: "high", label: model }))}
    read={async () => {
      fixture.reads++;
      if (fixture.failure === "load") throw new Error("private detail never displayed");
      return { ...fixture.metadata };
    }} save={async data => {
      fixture.writes.push(data);
      if (fixture.failure === "conflict") throw new ApiRequestError("private", 409, "revision_conflict");
      if (fixture.failure === "reject") throw new ApiRequestError("private", 422, "invalid");
      if (fixture.failure === "unknown") throw new TypeError("private network information");
      fixture.metadata = { ...fixture.metadata, model: data.model, has_key: true, revision: fixture.metadata.revision+1 };
      return { ...fixture.metadata };
    }} remove={async () => { fixture.deletes++; throw new ApiRequestError("private", 422, "invalid"); }} text={text} />;
}
const vision = {
  status: "loading" as "loading" | "error" | "missing" | "saved",
  policy: { world_id: "synthetic-world", world_character_id: "synthetic-actor", revision: 1,
    vision_enabled: false, vision_limit: 10, vision_usage: 0, generation_enabled: false,
    generation_limit: 20, generation_usage: 0, generation_settings: {}, timezone: "UTC", reset_at: "" },
  updates: [] as Record<string, unknown>[], reads: 0, reloads: 0, fail: false,
  refresh: () => {},
};
(window as unknown as { vision: typeof vision }).vision = vision;
(window as unknown as { fixtureAPI: (path: string, options: {method?: string; body?: Record<string, unknown>}) => unknown }).fixtureAPI = async (path, options = {}) => {
  if (!path.endsWith("/image-policy")) throw new Error("Unexpected fixture API request");
  if (!options.method) { vision.reads++; return { ...vision.policy }; }
  vision.updates.push(options.body ?? {});
  if (vision.fail) throw new ApiRequestError("private", 422, "world_credential_key_required");
  vision.policy = { ...vision.policy, ...options.body, revision: vision.policy.revision + 1 };
  return { ...vision.policy };
};
function VisionApp() {
  const [, rerender] = useState(0);
  useEffect(() => { vision.refresh = () => rerender(value => value + 1); }, []);
  return <WorldVisionControls worldId="synthetic-world" actorId="synthetic-actor"
    keyStatus={vision.status} onReloadKey={() => vision.reloads++} />;
}
const language = new URLSearchParams(location.search).get("vision");
const i18n = i18next.createInstance();
void i18n.init({ lng: language ?? "en", fallbackLng: "en", resources: {
  en: { media: mediaEn }, ko: { media: mediaKo },
}, interpolation: { escapeValue: false } }).then(() => {
  createRoot(document.getElementById("root")!).render(
    <I18nextProvider i18n={i18n}>{language ? <VisionApp /> : <App />}</I18nextProvider>);
});
