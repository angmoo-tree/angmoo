import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import i18n from "i18next";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { ProfileMediaUploader } from "../../src/features/characters/components/profile-media-uploader";
import { WorldChatEvidenceInspector } from "../../src/features/memory/components/world-chat-evidence-inspector";
import { displaySegmentsMatch } from "../../src/features/memory/utils/evidence-display";
import enCharacters from "../../src/features/characters/locales/en.json";
import koCharacters from "../../src/features/characters/locales/ko.json";
import enMemory from "../../src/features/memory/locales/en.json";
import koMemory from "../../src/features/memory/locales/ko.json";
import enShell from "../../src/composition/locales/en.json";
import koShell from "../../src/composition/locales/ko.json";

const source = '<img src=x onerror="window.injected=true"> kept source text';
const segments = [{ key: "kind", text: "오늘 SNS 활동 종류: " }, { key: null, text: "posts_authored | " },
  { key: "actor", text: "행동 주체: " }, { key: null, text: "Ian | " },
  { key: "body", text: "내용: " }, { key: null, text: source }];
const item = { reference: "synthetic:1", kind: "today_sns_activity", label: "오늘 SNS 활동", excerpt: segments.map(s => s.text).join(""),
  occurred_at: null, availability: "available", related_character: null, direction: null, canonical_href: null, display_segments: segments };
const fixture = { i18n, item, displaySegmentsMatch, source, set: (value: unknown) => { void value; }, scope: 1, uploads: 0,
  evidence: { schema_version: "world-chat-evidence.v1", request_id: "synthetic-request", route: "answer", retrieval_outcome: "complete", capability: "available", items: [item, { ...item, reference: "legacy:1", excerpt: "과거 원문 그대로", display_segments: null }] } };
(window as unknown as { fixture: typeof fixture }).fixture = fixture;
await i18n.use(initReactI18next).init({ lng: "en", fallbackLng: "en", keySeparator: false, interpolation: { escapeValue: false }, resources: {
  en: { characters: enCharacters, memory: enMemory, shell: enShell }, ko: { characters: koCharacters, memory: koMemory, shell: koShell },
} });
function App() {
  const [options, setOptions] = useState({ avatar: true, banner: false, overlay: false, evidence: false });
  useEffect(() => { fixture.set = value => setOptions(previous => ({ ...previous, ...(value as Partial<typeof options>) }));
    return () => { fixture.set = value => { void value; }; }; }, []);
  return <I18nextProvider i18n={i18n}><main style={{ margin: 24, maxWidth: 700 }}>
    <ProfileMediaUploader name="Synthetic Ian" avatarUrl={options.avatar ? "/media/avatar.svg" : ""} bannerUrl={options.banner ? "/media/avatar.svg" : ""}
      disabled={false} generationOverlay={options.overlay ? { kind: "avatar", label: "Preparing" } : null} onUpload={async () => { fixture.uploads++; }} />
    <WorldChatEvidenceInspector open={options.evidence} onOpenChange={open => setOptions(value => ({ ...value, evidence: open }))} requestId="synthetic-request" threadId="thread" worldId="world" />
  </main></I18nextProvider>;
}
createRoot(document.getElementById("root")!).render(<App />);
