"use client";
import { useUiText } from "@/hooks/use-ui-text";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/form-controls";
import { saveCredential } from "@/features/characters/api/agents";
import { DEFAULT_GOOGLE_GEMINI_MODEL, GOOGLE_GEMINI_MODELS, type GoogleGeminiModel } from "@/features/characters/config/model-options";

export function ActivityCredentialForm({ characterId, hasCredential, onSaved }: {
  characterId: string; hasCredential: boolean; onSaved: () => Promise<void>;
}) {
  const uiText = useUiText("characters");
  const [model, setModel] = useState<GoogleGeminiModel>(DEFAULT_GOOGLE_GEMINI_MODEL);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  return <details open={!hasCredential} className="space-y-4">
    <summary>{uiText("활동에 사용할 모델·API 키")}</summary>
    <form className="space-y-4" onSubmit={async (event) => {
      event.preventDefault(); if (busy) return;
      setBusy(true); setMessage(null);
      try { await saveCredential(characterId, { provider: "google", model, ...(key.trim() ? { api_key: key.trim() } : {}) }); setKey(""); await onSaved(); setMessage(uiText("저장했습니다. 활동 준비와 실행은 아래에서 별도로 선택해주세요.")); }
      catch (reason) { setMessage(reason instanceof Error ? uiText(reason.message) : uiText("키를 저장하지 못했습니다.")); }
      finally { setBusy(false); }
    }}>
      <Field label={uiText("모델")}>{(props) => <Select {...props} disabled={busy} value={model} onChange={(event) => setModel(event.target.value as GoogleGeminiModel)}>{GOOGLE_GEMINI_MODELS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</Select>}</Field>
      <Field label={uiText("API 키")} required={!hasCredential} helperText={hasCredential ? uiText("기존 키를 유지하려면 비워두세요.") : uiText("활동 준비에 사용할 키를 등록해주세요.")}>{(props) => <Input {...props} type="password" autoComplete="off" value={key} disabled={busy} onChange={(event) => setKey(event.target.value)} />}</Field>
      {message && <p role="status">{message}</p>}
      <Button type="submit" loading={busy}>{uiText("모델·키 저장")}</Button>
    </form>
  </details>;
}
