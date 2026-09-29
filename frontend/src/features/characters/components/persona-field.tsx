"use client";

import { useEffect, useRef, useState } from "react";
import { Field, Textarea } from "@/components/ui/form-controls";
import { personaLengthError, personaTextLength } from "@/features/characters/utils/persona-limits";

type Props = {
  label: string;
  name?: string;
  value?: string;
  defaultValue?: string;
  onChange?: (value: string) => void;
  limit: number;
  required?: boolean;
  disabled?: boolean;
  placeholder?: string;
  description?: string;
};

export function PersonaField({ label, name, value, defaultValue = "", onChange, limit, required, disabled, placeholder, description }: Props) {
  const [draft, setDraft] = useState(defaultValue);
  const current = value ?? draft;
  const error = personaLengthError(current, limit);
  // LOCAL: creation and editing share backend-bound name guidance, never a rendered form value.
  const helper = description ?? ((name === "worldview" || label === "캐릭터 설명")
    ? "{{user}}는 활동할 때 이 World의 내 프로필 이름으로, {{char}}는 이 캐릭터 이름으로 적용됩니다. 예: 동료: {{user}}. 카드의 별도 대화 예시에서는 사용자 역할을 ‘대화 상대’로 유지합니다."
    : undefined);
  const control = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { control.current?.setCustomValidity(error ?? ""); }, [error]);
  return (
    <Field className="mb-4" label={label} required={required} error={error}
      helperText={`${personaTextLength(current).toLocaleString()} / ${limit.toLocaleString()}자${helper ? ` · ${helper}` : ""}`}>
      {(props) => <Textarea {...props} ref={control} name={name} rows={4} value={current}
        disabled={disabled} placeholder={placeholder} onChange={(event) => {
          setDraft(event.target.value);
          onChange?.(event.target.value);
        }} />}
    </Field>
  );
}
