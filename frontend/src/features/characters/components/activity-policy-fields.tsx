"use client";
import { Field, Input } from "@/components/ui/form-controls";
import { useUiText } from "@/hooks/use-ui-text";
import { ActiveHoursControl, ACTIVE_HOURS_LIMIT_MESSAGE, isValidActiveHours } from "./activity-hours-control";
import type { ActivityPolicy } from "../api/basic-activity-settings";
export const POLICY_FIELDS = [
    { key: "activity_interval_minutes", label: "활동 간격 (분)", min: 30, max: 1440 },
    { key: "max_posts_per_day", label: "하루 게시글 한도", min: 0, max: 1000 },
    { key: "max_comments_per_day", label: "하루 답글 한도", min: 0, max: 1000 },
] as const;
export const POLICY_KEYS = ["active_hours_start", "active_hours_end", "activity_interval_minutes", "max_posts_per_day", "max_comments_per_day", "allow_post", "allow_reply", "allow_like"] as const;
export function validActivityPolicy(value: ActivityPolicy) {
    return isValidActiveHours(value.active_hours_start, value.active_hours_end) && POLICY_FIELDS.every(field => Number.isInteger(value[field.key]) && value[field.key] >= field.min && value[field.key] <= field.max);
}
export function ActivityPolicyFields({ value, onChange, disabled }: {
    value: ActivityPolicy;
    onChange: (changes: Partial<ActivityPolicy>) => void;
    disabled: boolean;
}) {
    const t = useUiText("characters");
    return <fieldset disabled={disabled} className="grid min-w-0 gap-4">
    <ActiveHoursControl start={value.active_hours_start} end={value.active_hours_end} onChange={(start, end) => onChange({ active_hours_start: start, active_hours_end: end })}/>
    {!isValidActiveHours(value.active_hours_start, value.active_hours_end) ? <p role="alert">{t(ACTIVE_HOURS_LIMIT_MESSAGE)}</p> : null}
    <div className="grid gap-3 sm:grid-cols-3">{([['allow_post', '게시글 작성'], ['allow_reply', '답글 작성'], ['allow_like', '좋아요']] as const).map(([key, label]) => <label className="flex min-h-11 items-center justify-between gap-3 rounded-xl border border-border-default px-4" key={key}>{t(label)}<input type="checkbox" className="accent-action-primary" checked={value[key]} onChange={event => onChange({ [key]: event.target.checked })}/></label>)}</div>
    <div className="grid gap-3 sm:grid-cols-3">{POLICY_FIELDS.map(field => <Field key={field.key} label={t(field.label)}>{props => <Input {...props} name={field.key} type="number" min={field.min} max={field.max} step={1} required value={Number.isFinite(value[field.key]) ? value[field.key] : ""} onChange={event => onChange({ [field.key]: event.target.value === "" ? Number.NaN : Number(event.target.value) })}/>}</Field>)}</div>
  </fieldset>;
}
