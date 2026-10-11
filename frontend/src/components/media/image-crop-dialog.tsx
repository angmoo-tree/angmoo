"use client";
import { useEffect, useRef, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { drawCroppedImage, type CropState, type CropSpec } from "@/utils/image-crop";

type Labels = { title: string; close: string; zoom: string; horizontal: string; vertical: string; apply: string; cancel: string; applying: string };
export function ImageCropDialog({ bitmap, spec, crop, onCrop, onApply, onCancel, busy, disabled = false, error, labels, recoveryAction }: {
  bitmap: ImageBitmap; spec: CropSpec; crop: CropState; onCrop: (value: CropState) => void;
  onApply: () => void; onCancel: () => void; busy: boolean; disabled?: boolean; error?: string | null; labels: Labels; recoveryAction?: ReactNode;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const node = canvas.current;
    if (!node) return;
    node.width = spec.width; node.height = spec.height;
    const context = node.getContext("2d");
    if (context) drawCroppedImage(context, bitmap, bitmap, spec, crop);
    return () => { node.width = 0; node.height = 0; };
  }, [bitmap, spec, crop]);
  return <Dialog open title={labels.title} closeLabel={labels.close} closeOnBackdrop={false} closeOnEscape={!busy}
    closeButtonAttributes={{ disabled: busy }} onOpenChange={open => { if (!open && !busy) onCancel(); }}>
    <div className="relative mx-auto w-full overflow-hidden rounded-[var(--radius-control)] bg-surface-muted" style={{ aspectRatio: `${spec.width}/${spec.height}`, maxWidth: spec.width === spec.height ? 360 : undefined }}>
      <canvas ref={canvas} aria-hidden="true" className="h-full w-full" />
    </div>
    <div className="mt-5 grid gap-4">
      {([['scale', labels.zoom, 1, 3, 0.05], ['offsetX', labels.horizontal, -45, 45, 1], ['offsetY', labels.vertical, -45, 45, 1]] as const).map(([key, label, min, max, step]) =>
        <label className="grid gap-2" key={key}><span className="text-[13px] font-extrabold text-text-secondary">{label}</span>
          <input type="range" min={min} max={max} step={step} value={crop[key]} disabled={busy} className="min-h-11 w-full accent-action-primary"
            onChange={event => onCrop({ ...crop, [key]: Number(event.target.value) })} />
        </label>)}
    </div>
    {error ? <p role="alert" className="mt-3 text-text-danger">{error}</p> : null}
    <div className="mt-5 flex flex-wrap justify-end gap-2">
      {recoveryAction}
      <Button type="button" variant="secondary" onClick={onCancel} disabled={busy}>{labels.cancel}</Button>
      <Button type="button" onClick={onApply} loading={busy} loadingLabel={labels.applying} disabled={disabled}>{labels.apply}</Button>
    </div>
  </Dialog>;
}
