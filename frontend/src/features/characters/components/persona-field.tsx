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
  const control = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { control.current?.setCustomValidity(error ?? ""); }, [error]);
  return (
    <Field className="mb-4" label={label} required={required} error={error}
      helperText={`${personaTextLength(current).toLocaleString()} / ${limit.toLocaleString()}자${description ? ` · ${description}` : ""}`}>
      {(props) => <Textarea {...props} ref={control} name={name} rows={4} value={current}
        disabled={disabled} placeholder={placeholder} onChange={(event) => {
          setDraft(event.target.value);
          onChange?.(event.target.value);
        }} />}
    </Field>
  );
}
