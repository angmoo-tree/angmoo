"use client";
import { useUiText } from "@/hooks/use-ui-text";
import { useUiNumberFormatter } from "@/hooks/use-ui-number-formatter";
import { formatWorldPackageFailure, type WorldPackageFailure } from "@/features/world-packages/utils/error-presentation";


import { CheckCircle2, Download, PackageOpen, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/surfaces";
import { InlineError } from "@/components/ui/feedback";
import { Input, Select } from "@/components/ui/form-controls";

import { acknowledgeNativeWorldPackageDelivery, discardPreparedWorldPackageExport, downloadPreparedWorldPackage, prepareWorldPackageExport, previewWorldPackageExport } from "@/features/world-packages/api/world-package-client";
import { triggerBrowserWorldPackageDownload } from "@/features/world-packages/api/browser-delivery";
import { type PreparedWorldPackageExport, type WorldPackageExportPreview, type WorldPackageExportRequest } from "@/features/world-packages/types/world-package";

import { discardNativeWorldPackageDestination, selectNativeWorldPackageDestination, supportsNativeWorldPackageSaveAs, writeNativeWorldPackageDestination } from "@/features/world-packages/api/native-delivery";

type ConfirmationKey = "rights" | "license" | "exclusions";

export function WorldPackageExportPanel({ worldId }: { worldId: string }) {
  const uiText = useUiText("world-packages");
  const formatNumber = useUiNumberFormatter();
  const [licenseExpression, setLicenseExpression] = useState("CC-BY-4.0");
  const [attribution, setAttribution] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [confirmations, setConfirmations] = useState<Record<ConfirmationKey, boolean>>({
    rights: false,
    license: false,
    exclusions: false,
  });
  const [preview, setPreview] = useState<WorldPackageExportPreview | null>(null);
  const [pending, setPending] = useState<"preview" | "delivery" | "ack" | "cleanup" | null>(null);
  const [pendingAcknowledgement, setPendingAcknowledgement] =
    useState<PreparedWorldPackageExport | null>(null);
  const [pendingCleanup, setPendingCleanup] =
    useState<PreparedWorldPackageExport | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<WorldPackageFailure | null>(null);

  const allConfirmed = useMemo(
    () => Object.values(confirmations).every(Boolean),
    [confirmations],
  );

  function request(): WorldPackageExportRequest {
    return {
      license_expression: licenseExpression,
      attribution: attribution.trim(),
      source_url: sourceUrl.trim() || null,
      license_text: null,
      confirm_export_rights: true,
      confirm_license: true,
      confirm_exclusions: true,
    };
  }

  function invalidatePreview() {
    setPreview(null);
    setPendingAcknowledgement(null);
    setMessage(null);
  }

  async function handlePreview() {
    setPending("preview");
    setError(null);
    setMessage(null);
    try {
      setPreview(await previewWorldPackageExport(worldId, request()));
    } catch (reason) {
      setError({ kind: "request", reason });
    } finally {
      setPending(null);
    }
  }

  async function handleDelivery() {
    if (!preview) return;
    setPending("delivery");
    setError(null);
    setMessage(null);
    let destinationToken: string | null = null;
    let prepared: PreparedWorldPackageExport | null = null;
    let nativeWriteCompleted = false;
    try {
      if (supportsNativeWorldPackageSaveAs()) {
        const selection = await selectNativeWorldPackageDestination(
          preview.recommended_filename,
        );
        if (selection.cancelled || !selection.destinationToken) {
          setMessage(uiText("내보내기를 취소했습니다. 파일과 성공 이력은 생성되지 않았습니다."));
          return;
        }
        destinationToken = selection.destinationToken;
      }

      prepared = await prepareWorldPackageExport(worldId, request());
      if (destinationToken) {
        const downloaded = await downloadPreparedWorldPackage(prepared, "tauri_save_as");
        await writeNativeWorldPackageDestination(
          destinationToken,
          new Uint8Array(await downloaded.blob.arrayBuffer()),
        );
        nativeWriteCompleted = true;
        destinationToken = null;
        await acknowledgeNativeWorldPackageDelivery(prepared);
      } else {
        const downloaded = await downloadPreparedWorldPackage(prepared, "browser_download");
        triggerBrowserWorldPackageDownload(downloaded.blob, downloaded.filename);
      }
      setPendingAcknowledgement(null);
      setMessage(
        uiText("World Package v{{value0}}을 내보냈습니다. ({{value1}})", {value0: prepared.preview.package_version, value1: formatBytes(prepared.archive_bytes)}),
      );
    } catch (reason) {
      if (prepared && nativeWriteCompleted) {
        setPendingAcknowledgement(prepared);
        setError({ kind: "local", message: "파일은 저장됐지만 Angmoo의 전달 확인이 끝나지 않았습니다. 아래에서 확인을 다시 시도해 주세요." });
      } else {
        if (prepared) {
          try {
            await discardPreparedWorldPackageExport(prepared);
          } catch {
            setPendingCleanup(prepared);
            setError({ kind: "local", message: "내보내기 전달과 실패 작업 정리가 모두 끝나지 않았습니다. 같은 World를 다시 내보내기 전에 아래에서 정리를 재시도해 주세요." });
            return;
          }
        }
        setPendingCleanup(null);
        setError({ kind: "request", reason });
      }
    } finally {
      if (destinationToken) {
        await discardNativeWorldPackageDestination(destinationToken).catch(() => undefined);
      }
      setPending(null);
    }
  }

  async function retryCleanup() {
    if (!pendingCleanup) return;
    setPending("cleanup");
    setError(null);
    try {
      await discardPreparedWorldPackageExport(pendingCleanup);
      setPendingCleanup(null);
      setMessage(uiText("완료되지 않은 내보내기 작업을 정리했습니다. 다시 내보낼 수 있습니다."));
    } catch (reason) {
      setError({ kind: "request", reason,
        context: "완료되지 않은 내보내기 작업을 아직 정리하지 못했습니다. ({{value0}})" });
    } finally {
      setPending(null);
    }
  }

  async function retryAcknowledgement() {
    if (!pendingAcknowledgement) return;
    setPending("ack");
    setError(null);
    try {
      await acknowledgeNativeWorldPackageDelivery(pendingAcknowledgement);
      setMessage(uiText("저장된 World Package의 전달 확인을 완료했습니다."));
      setPendingAcknowledgement(null);
    } catch (reason) {
      setError({ kind: "request", reason });
    } finally {
      setPending(null);
    }
  }

  return (
    <Card as="section" elevated>
      <div className="flex items-start gap-3">
        <PackageOpen className="mt-1 size-6 shrink-0 text-[#ff6b6b]" />
        <div>
          <h2 className="text-xl font-black text-[#101828]">{uiText("Package 내보내기")}</h2>
          <p className="mt-2 text-sm font-medium leading-6 text-[#667085]">
            {uiText("자율 캐릭터와 관리된 미디어만 포함합니다. owner-controlled 프로필, 세션, credential, P2~P4 실행 기록과 관계 projection은 제외합니다. 캐릭터는 최종 편집한 설정과 표시 이미지를 공유하며, 가져온 카드 원본은 포함하지 않습니다.")}</p>
        </div>
      </div>

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <label className="text-sm font-extrabold text-[#344054]">
          {uiText("라이선스")}<Select
            className="mt-2"
            value={licenseExpression}
            onChange={(event) => {
              setLicenseExpression(event.target.value);
              invalidatePreview();
            }}
          >
            <option value="CC-BY-4.0">CC BY 4.0</option>
            <option value="CC0-1.0">CC0 1.0</option>
          </Select>
        </label>
        <label className="text-sm font-extrabold text-[#344054]">
          {uiText("저작자 표시")}<Input
            className="mt-2"
            maxLength={1000}
            value={attribution}
            onChange={(event) => {
              setAttribution(event.target.value);
              invalidatePreview();
            }}
            placeholder={uiText("예: Angmoo creator")}
          />
        </label>
      </div>
      <label className="mt-4 block text-sm font-extrabold text-[#344054]">
        {uiText("원본 안내 URL (선택)")}<Input
          className="mt-2"
          maxLength={2048}
          type="url"
          value={sourceUrl}
          onChange={(event) => {
            setSourceUrl(event.target.value);
            invalidatePreview();
          }}
          placeholder="https://..."
        />
      </label>

      <fieldset className="mt-5 space-y-3 rounded-[20px] bg-[#f7f8fa] p-4">
        <legend className="px-1 text-sm font-black text-[#344054]">{uiText("내보내기 확인")}</legend>
        <Confirmation
          checked={confirmations.rights}
          label={uiText("이 World와 포함 자산을 배포할 권리가 있습니다.")}
          onChange={(checked) => setConfirmations((value) => ({ ...value, rights: checked }))}
        />
        <Confirmation
          checked={confirmations.license}
          label={uiText("선택한 라이선스와 저작자 표시를 확인했습니다.")}
          onChange={(checked) => setConfirmations((value) => ({ ...value, license: checked }))}
        />
        <Confirmation
          checked={confirmations.exclusions}
          label={uiText("개인 프로필·runtime 기록·외부 URL 자산이 제외됨을 확인했습니다.")}
          onChange={(checked) => setConfirmations((value) => ({ ...value, exclusions: checked }))}
        />
      </fieldset>

      <div className="mt-5 flex flex-wrap gap-3">
        <Button
          variant="secondary"
          loading={pending === "preview"}
          loadingLabel={uiText("포함 내용 확인 중")}
          disabled={!allConfirmed || pending !== null}
          onClick={() => void handlePreview()}
          type="button"
        >
          <ShieldCheck className="size-4" />
          {uiText("포함 내용 확인")}</Button>
        <Button
          variant="strong"
          loading={pending === "delivery"}
          loadingLabel={uiText("Package 준비 중")}
          disabled={
            !preview ||
            pending !== null ||
            Boolean(pendingAcknowledgement) ||
            Boolean(pendingCleanup)
          }
          onClick={() => void handleDelivery()}
          type="button"
        >
          <Download className="size-4" />
          {supportsNativeWorldPackageSaveAs() ? uiText("다른 이름으로 저장") : uiText("Package 다운로드")}
        </Button>
      </div>

      {preview ? <ExportPreviewCard preview={preview} /> : null}
      {pendingAcknowledgement ? (
        <Button
          className="mt-4"
          variant="secondary"
          loading={pending === "ack"}
          loadingLabel={uiText("전달 확인 중")}
          disabled={pending !== null}
          onClick={() => void retryAcknowledgement()}
          type="button"
        >
          <CheckCircle2 className="size-4" />
          {uiText("전달 확인 다시 시도")}</Button>
      ) : null}
      {pendingCleanup ? (
        <Button
          variant="secondary"
          loading={pending === "cleanup"}
          loadingLabel={uiText("실패 작업 정리 중")}
          disabled={pending !== null}
          onClick={() => void retryCleanup()}
          type="button"
        >
          <ShieldCheck className="size-4" />
          {uiText("실패 작업 정리 후 다시 시도")}</Button>
      ) : null}
      {error ? <InlineError className="mt-4">{formatWorldPackageFailure(error, "export", uiText, formatNumber)}</InlineError> : null}
      {message ? <p className="mt-4 rounded-[18px] bg-[#ecfdf3] p-4 text-sm font-bold text-[#027a48]" role="status">{message}</p> : null}
    </Card>
  );
}

function Confirmation({ checked, label, onChange }: { checked: boolean; label: string; onChange: (checked: boolean) => void }) {
  return <label className="flex items-start gap-3 text-sm font-semibold leading-6 text-[#475467]"><input className="mt-1 size-4" type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />{label}</label>;
}

function ExportPreviewCard({ preview }: { preview: WorldPackageExportPreview }) {
  const uiText = useUiText("world-packages");
  return (
    <div className="mt-5 rounded-[22px] border border-[#d0d5dd] p-5" aria-live="polite">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <strong className="text-[#101828]">{preview.recommended_filename}</strong>
        <span className="rounded-full bg-[#f2f4f7] px-3 py-1 text-xs font-black text-[#475467]">v{preview.package_version}</span>
      </div>
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
        <PreviewValue label={uiText("포함 자율 캐릭터")} value={uiText("{{value0}}명", {value0: preview.included_autonomous_characters})} />
        <PreviewValue label={uiText("포함 관리 자산")} value={uiText("{{value0}}개", {value0: preview.included_assets})} />
        <PreviewValue label={uiText("제외 owner-controlled")} value={uiText("{{value0}}명", {value0: preview.excluded_owner_controlled_characters})} />
        <PreviewValue label={uiText("제외 외부 자산")} value={uiText("{{value0}}개", {value0: preview.excluded_external_assets})} />
      </dl>
      <p className="mt-4 break-all font-mono text-[11px] leading-5 text-[#667085]">seed {preview.seed_digest}</p>
      {preview.warnings.length ? <ul className="mt-3 list-disc pl-5 text-xs font-bold leading-5 text-[#b54708]">{preview.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : null}
    </div>
  );
}

function PreviewValue({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-xs font-bold text-[#98a2b3]">{label}</dt><dd className="mt-1 font-black text-[#344054]">{value}</dd></div>;
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MiB`;
}
