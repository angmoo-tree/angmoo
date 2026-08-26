"use client";

import { CheckCircle2, Download, Loader2, PackageOpen, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";

import {
  acknowledgeNativeWorldPackageDelivery,
  discardPreparedWorldPackageExport,
  downloadPreparedWorldPackage,
  prepareWorldPackageExport,
  previewWorldPackageExport,
  triggerBrowserWorldPackageDownload,
  type PreparedWorldPackageExport,
  type WorldPackageExportPreview,
  type WorldPackageExportRequest,
} from "./api/world-package-client";

import {
  discardNativeWorldPackageDestination,
  selectNativeWorldPackageDestination,
  supportsNativeWorldPackageSaveAs,
  writeNativeWorldPackageDestination,
} from "./native-delivery";

type ConfirmationKey = "rights" | "license" | "exclusions";

export function WorldPackageExportPanel({ worldId }: { worldId: string }) {
  const [licenseExpression, setLicenseExpression] = useState("CC-BY-4.0");
  const [attribution, setAttribution] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [confirmations, setConfirmations] = useState<Record<ConfirmationKey, boolean>>({
    rights: false,
    license: false,
    exclusions: false,
  });
  const [preview, setPreview] = useState<WorldPackageExportPreview | null>(null);
  const [pending, setPending] = useState<"preview" | "delivery" | "ack" | null>(null);
  const [pendingAcknowledgement, setPendingAcknowledgement] =
    useState<PreparedWorldPackageExport | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
      setError(exportError(reason));
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
          setMessage("내보내기를 취소했습니다. 파일과 성공 이력은 생성되지 않았습니다.");
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
        `World Package v${prepared.preview.package_version}을 내보냈습니다. (${formatBytes(prepared.archive_bytes)})`,
      );
    } catch (reason) {
      if (prepared && nativeWriteCompleted) {
        setPendingAcknowledgement(prepared);
        setError("파일은 저장됐지만 Angmoo의 전달 확인이 끝나지 않았습니다. 아래에서 확인을 다시 시도해 주세요.");
      } else {
        if (prepared) await discardPreparedWorldPackageExport(prepared).catch(() => undefined);
        setError(exportError(reason));
      }
    } finally {
      if (destinationToken) {
        await discardNativeWorldPackageDestination(destinationToken).catch(() => undefined);
      }
      setPending(null);
    }
  }

  async function retryAcknowledgement() {
    if (!pendingAcknowledgement) return;
    setPending("ack");
    setError(null);
    try {
      await acknowledgeNativeWorldPackageDelivery(pendingAcknowledgement);
      setMessage("저장된 World Package의 전달 확인을 완료했습니다.");
      setPendingAcknowledgement(null);
    } catch (reason) {
      setError(exportError(reason));
    } finally {
      setPending(null);
    }
  }

  return (
    <section className="rounded-[28px] border border-[#e1e5eb] bg-white p-6 shadow-sm md:p-8">
      <div className="flex items-start gap-3">
        <PackageOpen className="mt-1 size-6 shrink-0 text-[#ff6b6b]" />
        <div>
          <h2 className="text-xl font-black text-[#101828]">Package 내보내기</h2>
          <p className="mt-2 text-sm font-medium leading-6 text-[#667085]">
            자율 캐릭터와 관리된 미디어만 포함합니다. owner-controlled 프로필,
            세션, credential, P2~P4 실행 기록과 관계 projection은 제외합니다.
          </p>
        </div>
      </div>

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <label className="text-sm font-extrabold text-[#344054]">
          라이선스
          <select
            className={inputClass}
            value={licenseExpression}
            onChange={(event) => {
              setLicenseExpression(event.target.value);
              invalidatePreview();
            }}
          >
            <option value="CC-BY-4.0">CC BY 4.0</option>
            <option value="CC0-1.0">CC0 1.0</option>
          </select>
        </label>
        <label className="text-sm font-extrabold text-[#344054]">
          저작자 표시
          <input
            className={inputClass}
            maxLength={1000}
            value={attribution}
            onChange={(event) => {
              setAttribution(event.target.value);
              invalidatePreview();
            }}
            placeholder="예: Angmoo creator"
          />
        </label>
      </div>
      <label className="mt-4 block text-sm font-extrabold text-[#344054]">
        원본 안내 URL (선택)
        <input
          className={inputClass}
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
        <legend className="px-1 text-sm font-black text-[#344054]">내보내기 확인</legend>
        <Confirmation
          checked={confirmations.rights}
          label="이 World와 포함 자산을 배포할 권리가 있습니다."
          onChange={(checked) => setConfirmations((value) => ({ ...value, rights: checked }))}
        />
        <Confirmation
          checked={confirmations.license}
          label="선택한 라이선스와 저작자 표시를 확인했습니다."
          onChange={(checked) => setConfirmations((value) => ({ ...value, license: checked }))}
        />
        <Confirmation
          checked={confirmations.exclusions}
          label="개인 프로필·runtime 기록·외부 URL 자산이 제외됨을 확인했습니다."
          onChange={(checked) => setConfirmations((value) => ({ ...value, exclusions: checked }))}
        />
      </fieldset>

      <div className="mt-5 flex flex-wrap gap-3">
        <button
          className={secondaryButtonClass}
          disabled={!allConfirmed || pending !== null}
          onClick={() => void handlePreview()}
          type="button"
        >
          {pending === "preview" ? <Loader2 className="size-4 animate-spin" /> : <ShieldCheck className="size-4" />}
          포함 내용 확인
        </button>
        <button
          className={primaryButtonClass}
          disabled={!preview || pending !== null || Boolean(pendingAcknowledgement)}
          onClick={() => void handleDelivery()}
          type="button"
        >
          {pending === "delivery" ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" />}
          {supportsNativeWorldPackageSaveAs() ? "다른 이름으로 저장" : "Package 다운로드"}
        </button>
      </div>

      {preview ? <ExportPreviewCard preview={preview} /> : null}
      {pendingAcknowledgement ? (
        <button
          className={`${secondaryButtonClass} mt-4`}
          disabled={pending !== null}
          onClick={() => void retryAcknowledgement()}
          type="button"
        >
          {pending === "ack" ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
          전달 확인 다시 시도
        </button>
      ) : null}
      {error ? <p className="mt-4 rounded-[18px] bg-[#fff1f0] p-4 text-sm font-bold text-[#b42318]" role="alert">{error}</p> : null}
      {message ? <p className="mt-4 rounded-[18px] bg-[#ecfdf3] p-4 text-sm font-bold text-[#027a48]" role="status">{message}</p> : null}
    </section>
  );
}

function Confirmation({ checked, label, onChange }: { checked: boolean; label: string; onChange: (checked: boolean) => void }) {
  return <label className="flex items-start gap-3 text-sm font-semibold leading-6 text-[#475467]"><input className="mt-1 size-4" type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />{label}</label>;
}

function ExportPreviewCard({ preview }: { preview: WorldPackageExportPreview }) {
  return (
    <div className="mt-5 rounded-[22px] border border-[#d0d5dd] p-5" aria-live="polite">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <strong className="text-[#101828]">{preview.recommended_filename}</strong>
        <span className="rounded-full bg-[#f2f4f7] px-3 py-1 text-xs font-black text-[#475467]">v{preview.package_version}</span>
      </div>
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
        <PreviewValue label="포함 자율 캐릭터" value={`${preview.included_autonomous_characters}명`} />
        <PreviewValue label="포함 관리 자산" value={`${preview.included_assets}개`} />
        <PreviewValue label="제외 owner-controlled" value={`${preview.excluded_owner_controlled_characters}명`} />
        <PreviewValue label="제외 외부 자산" value={`${preview.excluded_external_assets}개`} />
      </dl>
      <p className="mt-4 break-all font-mono text-[11px] leading-5 text-[#667085]">seed {preview.seed_digest}</p>
      {preview.warnings.length ? <ul className="mt-3 list-disc pl-5 text-xs font-bold leading-5 text-[#b54708]">{preview.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : null}
    </div>
  );
}

function PreviewValue({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-xs font-bold text-[#98a2b3]">{label}</dt><dd className="mt-1 font-black text-[#344054]">{value}</dd></div>;
}

function exportError(reason: unknown) {
  return reason instanceof Error ? reason.message : "World Package 내보내기를 완료하지 못했습니다.";
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MiB`;
}

const inputClass = "mt-2 h-12 w-full rounded-[16px] border border-[#d0d5dd] bg-white px-4 text-sm font-semibold text-[#101828] outline-none focus:border-[#ff6b6b] focus:ring-2 focus:ring-[#ffe2e2]";
const secondaryButtonClass = "inline-flex min-h-11 items-center justify-center gap-2 rounded-full border border-[#d0d5dd] bg-white px-5 text-sm font-extrabold text-[#344054] hover:bg-[#f9fafb] disabled:cursor-not-allowed disabled:opacity-50";
const primaryButtonClass = "inline-flex min-h-11 items-center justify-center gap-2 rounded-full bg-[#101828] px-5 text-sm font-extrabold text-white hover:bg-[#344054] disabled:cursor-not-allowed disabled:opacity-50";
