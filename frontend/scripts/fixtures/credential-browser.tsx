import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { CredentialFields, type SecretMetadata, type SecretWrite } from "../../src/components/ui/credential-fields";
import { ApiRequestError } from "../../src/lib/http/error-contract";
import { connectionStore } from "../../src/features/identity/controllers/local-connection-store";

const fixture = {
  metadata: { provider: "google", model: "model-a", thinking_level: "high", has_key: false, fingerprint: null, revision: 0, configuration_revision: 1 } as SecretMetadata,
  writes: [] as SecretWrite[], deletes: 0, failure: "", refresh: () => {},
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
createRoot(document.getElementById("root")!).render(<App />);
