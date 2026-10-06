"use client";

import { Field, Input, Select } from "@/components/ui/form-controls";
import { useUiText } from "@/hooks/use-ui-text";

export const novelDefaults = { mode: "opus_free", width: 1024, height: 1024, steps: 28, scale: 5, sampler: "k_euler_ancestral", noise_schedule: "karras", seed: -1, cfg_rescale: 0, decrisper: false, variety_boost: false, reference_strength: 1, reference_fidelity: 1, reference_type: "character&style" };

type Props = { options: Record<string, unknown>; disabled?: boolean; onChange: (value: Record<string, unknown>) => void };

/** Shared provider controls; owners decide how drafts, keys and quotas are saved. */
export function NovelOptionsEditor({ options, disabled, onChange, onModeChange }: Props & { onModeChange?: (mode: string) => void }) {
  const t = useUiText("media"), value = { ...novelDefaults, ...options };
  const free = value.mode === "opus_free";
  function setOption(name: string, next: unknown) {
    const changed: Record<string, unknown> = { ...value, [name]: next };
    if (free && (name === "width" || name === "height")) {
      const other = name === "width" ? "height" : "width";
      changed[other] = Math.min(Number(changed[other]), Math.floor(1048576 / Math.max(64, Number(next)) / 64) * 64);
    }
    onChange(changed);
  }
  return <>
    <Field label={t("비용 모드")}>{props => <Select {...props} disabled={disabled} value={String(value.mode)} onChange={event => onModeChange ? onModeChange(event.target.value) : setOption("mode", event.target.value)}>
      <option value="opus_free">{t("Anlas 사용 안 함 — Opus 전용")}</option><option value="allow_anlas">{t("Anlas 사용 허용")}</option>
    </Select>}</Field>
    <p className="text-sm text-text-secondary">{free ? t("Opus 혜택 확인 후 1장, 28 Steps 이하로 생성해요. 참조 사진은 보내지 않아요.") : t("Anlas 사용을 허용해요. 참조 사진은 이미지 1장마다 5 Anlas가 추가돼요.")}</p>
    <div className="grid gap-4 sm:grid-cols-2">
      {(["width", "height", "steps", "scale", "cfg_rescale", "seed"] as const).map(name => <Field key={name} label={{ width: t("가로"), height: t("세로"), steps: "Steps", scale: "CFG scale", cfg_rescale: "CFG rescale", seed: t("Seed (-1: 무작위)") }[name]}>{props => <Input {...props} type="number" disabled={disabled} value={Number(value[name])} min={name === "seed" ? -1 : name === "width" || name === "height" ? 64 : name === "steps" ? 1 : 0} max={name === "steps" ? free ? 28 : 50 : name === "scale" ? 10 : name === "cfg_rescale" ? 1 : undefined} step={name === "width" || name === "height" ? 64 : name === "scale" || name === "cfg_rescale" ? .1 : 1} onChange={event => setOption(name, Number(event.target.value))} />}</Field>)}
      <Field label="Sampler">{props => <Select {...props} disabled={disabled} value={String(value.sampler)} onChange={event => setOption("sampler", event.target.value)}>{["k_euler", "k_euler_ancestral", "k_dpmpp_2s_ancestral", "k_dpmpp_2m", "k_dpmpp_sde", "ddim_v3"].map(item => <option key={item}>{item}</option>)}</Select>}</Field>
      <Field label="Noise schedule">{props => <Select {...props} disabled={disabled} value={String(value.noise_schedule)} onChange={event => setOption("noise_schedule", event.target.value)}>{["native", "karras", "exponential", "polyexponential"].map(item => <option key={item}>{item}</option>)}</Select>}</Field>
    </div>
    {(["decrisper", "variety_boost"] as const).map(name => <label className="flex min-h-11 items-center gap-3" key={name}><input type="checkbox" className="accent-action-primary" disabled={disabled} checked={Boolean(value[name])} onChange={event => setOption(name, event.target.checked)} />{name === "decrisper" ? "Decrisper" : "Variety Boost"}</label>)}
  </>;
}

export function NovelReferenceEditor({ options, disabled, onChange }: Props) {
  const t = useUiText("media"), value = { ...novelDefaults, ...options };
  return <div className="grid gap-4 sm:grid-cols-2">
    <Field label={t("참조 종류")}>{props => <Select {...props} disabled={disabled} value={String(value.reference_type)} onChange={event => onChange({ ...value, reference_type: event.target.value })}>{["character", "style", "character&style"].map(item => <option key={item}>{item}</option>)}</Select>}</Field>
    {(["reference_strength", "reference_fidelity"] as const).map(name => <Field key={name} label={name === "reference_strength" ? "Strength" : "Fidelity"}>{props => <Input {...props} disabled={disabled} type="number" min={0} max={1} step={.05} value={Number(value[name])} onChange={event => onChange({ ...value, [name]: Number(event.target.value) })} />}</Field>)}
  </div>;
}
