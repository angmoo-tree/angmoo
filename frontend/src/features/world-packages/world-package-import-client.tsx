"use client";

import { AlertTriangle, CheckCircle2, FileArchive, Loader2, RotateCcw, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Button, Card, InlineError, Select } from "@/shared/ui/public";
import {
  commitWorldPackageImport,
  discardWorldPackageImport,
  stageWorldPackageImport,
  WORLD_PACKAGE_EXTENSION,
  WORLD_PACKAGE_MEDIA_TYPE,
  type PreparedWorldPackageImport,
  type WorldPackageImportResult,
} from "./api/world-package-client";
import { PRODUCT_ROUTES, studioWorldRoute, useRuntimeRouter } from "@/shared/navigation/public";

export function WorldPackageImportClient({
  authStatus,
}: {
  authStatus: "checking" | "authenticated" | "unauthenticated";
}) {
  const router = useRuntimeRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [prepared, setPrepared] = useState<PreparedWorldPackageImport | null>(null);
  const [approvedDigest, setApprovedDigest] = useState<string | null>(null);
  const [duplicateStrategy, setDuplicateStrategy] = useState<"reject" | "independent_copy">("reject");
  const [pending, setPending] = useState<"stage" | "commit" | "discard" | null>(null);
  const [result, setResult] = useState<WorldPackageImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authStatus === "unauthenticated") {
      router.replace(`/login?returnTo=${encodeURIComponent(PRODUCT_ROUTES.studioImport)}`);
    }
  }, [authStatus, router]);

  async function chooseFile(file: File | null) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(WORLD_PACKAGE_EXTENSION)) {
      setError(".angmoo-world 파일만 선택할 수 있습니다.");
      return;
    }
    if (prepared) {
      setPending("discard");
      try {
        await discardWorldPackageImport(prepared);
      } catch (reason) {
        setError(
          `이전 가져오기 미리보기를 정리하지 못해 새 파일을 열지 않았습니다. (${importError(reason)})`,
        );
        setPending(null);
        if (inputRef.current) inputRef.current.value = "";
        return;
      }
    }
    setPrepared(null);
    setApprovedDigest(null);
    setResult(null);
    setError(null);
    setPending("stage");
    try {
      const next = await stageWorldPackageImport(file);
      setPrepared(next);
      setDuplicateStrategy(
        next.preview.collision_plan.duplicate_state === "already_imported"
          ? "independent_copy"
          : "reject",
      );
    } catch (reason) {
      setError(importError(reason));
    } finally {
      setPending(null);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function discard() {
    if (!prepared) return;
    setPending("discard");
    setError(null);
    try {
      await discardWorldPackageImport(prepared);
      setPrepared(null);
      setApprovedDigest(null);
    } catch (reason) {
      setError(importError(reason));
    } finally {
      setPending(null);
    }
  }

  async function commit() {
    if (!prepared || approvedDigest !== prepared.preview.content_digest) return;
    setPending("commit");
    setError(null);
    try {
      setResult(await commitWorldPackageImport(prepared, duplicateStrategy));
      setPrepared(null);
      setApprovedDigest(null);
    } catch (reason) {
      setError(importError(reason));
    } finally {
      setPending(null);
    }
  }

  if (authStatus === "checking") {
    return <ImportNotice><Loader2 className="size-5 animate-spin" /> local owner를 확인하는 중입니다.</ImportNotice>;
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header>
        <p className="text-xs font-black uppercase tracking-[0.14em] text-[#ff6b6b]">WORLD PACKAGE V1</p>
        <h1 className="mt-3 text-3xl font-black text-[#101828]">World Package 가져오기</h1>
        <p className="mt-4 max-w-3xl font-semibold leading-7 text-[#667085]">
          원본 파일은 bounded staging에서만 검증합니다. 미리보기 승인 전에는 World나
          Device Home을 변경하지 않으며, 외부 코드·provider·네트워크를 실행하지 않습니다.
        </p>
      </header>

      {!result ? (
        <Card as="section" elevated>
          <label className="flex cursor-pointer flex-col items-center rounded-[24px] border-2 border-dashed border-[#d0d5dd] bg-[#f9fafb] px-6 py-10 text-center hover:border-[#ff9b9b]">
            {pending === "stage" ? <Loader2 className="size-9 animate-spin text-[#ff6b6b]" /> : <FileArchive className="size-9 text-[#ff6b6b]" />}
            <strong className="mt-4 text-lg text-[#101828]">.angmoo-world 파일 선택</strong>
            <span className="mt-2 text-sm font-semibold text-[#667085]">파일 경로를 직접 입력하지 않습니다.</span>
            <input
              ref={inputRef}
              accept={`${WORLD_PACKAGE_EXTENSION},${WORLD_PACKAGE_MEDIA_TYPE}`}
              className="sr-only"
              disabled={pending !== null}
              onChange={(event) => void chooseFile(event.target.files?.[0] ?? null)}
              type="file"
            />
          </label>
        </Card>
      ) : null}

      {prepared ? (
        <ImportPreview
          approved={approvedDigest === prepared.preview.content_digest}
          duplicateStrategy={duplicateStrategy}
          onApproval={(approved) => setApprovedDigest(approved ? prepared.preview.content_digest : null)}
          onCommit={() => void commit()}
          onDiscard={() => void discard()}
          onDuplicateStrategy={setDuplicateStrategy}
          pending={pending}
          prepared={prepared}
        />
      ) : null}

      {result ? <ImportSuccess result={result} /> : null}
      {error ? <InlineError>{error}</InlineError> : null}
    </div>
  );
}

function ImportPreview({ prepared, approved, duplicateStrategy, pending, onApproval, onCommit, onDiscard, onDuplicateStrategy }: {
  prepared: PreparedWorldPackageImport;
  approved: boolean;
  duplicateStrategy: "reject" | "independent_copy";
  pending: "stage" | "commit" | "discard" | null;
  onApproval: (approved: boolean) => void;
  onCommit: () => void;
  onDiscard: () => void;
  onDuplicateStrategy: (strategy: "reject" | "independent_copy") => void;
}) {
  const preview = prepared.preview;
  const blocked = preview.blocking_issues.length > 0;
  const alreadyImported = preview.collision_plan.duplicate_state === "already_imported";
  return (
    <Card as="section" elevated>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.14em] text-[#ff6b6b]">VALIDATED PREVIEW</p>
          <h2 className="mt-2 text-2xl font-black text-[#101828]">{preview.world_name}</h2>
          <p className="mt-2 text-sm font-semibold text-[#667085]">{preview.world_tagline}</p>
        </div>
        <span className="rounded-full bg-[#ecfdf3] px-3 py-2 text-xs font-black text-[#027a48]">
          {trustLabel(preview.trust_state)}
        </span>
      </div>

      <dl className="mt-6 grid gap-4 rounded-[22px] bg-[#f7f8fa] p-5 sm:grid-cols-2 lg:grid-cols-4">
        <Value label="자율 캐릭터" value={`${preview.character_names.length}명`} />
        <Value label="장소·역할" value={`${preview.place_count} · ${preview.role_count}`} />
        <Value label="관리 자산" value={`${preview.asset_count}개 · ${formatBytes(preview.asset_bytes)}`} />
        <Value label="예정 slug" value={preview.collision_plan.planned_world_slug} />
      </dl>

      <div className="mt-5 grid gap-5 md:grid-cols-2">
        <div className="rounded-[20px] border border-[#e1e5eb] p-5">
          <h3 className="font-black text-[#101828]">라이선스·출처</h3>
          <p className="mt-3 text-sm font-bold text-[#475467]">{preview.license.expression}</p>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-[#667085]">{preview.license.attribution || "저작자 표시 없음"}</p>
          {preview.license.source_url ? <a className="mt-3 block break-all text-sm font-bold text-[#ae2f34] underline" href={preview.license.source_url} rel="noreferrer" target="_blank">원본 안내 열기</a> : null}
        </div>
        <div className="rounded-[20px] border border-[#e1e5eb] p-5">
          <h3 className="font-black text-[#101828]">충돌 계획</h3>
          <p className="mt-3 text-sm font-bold text-[#475467]">{duplicateLabel(preview.collision_plan.duplicate_state)}</p>
          <ul className="mt-3 space-y-2 text-sm text-[#667085]">{preview.collision_plan.characters.map((character) => <li key={character.source_ref}>{character.display_name} → @{character.planned_handle}</li>)}</ul>
        </div>
      </div>

      {alreadyImported ? (
        <label className="mt-5 block rounded-[20px] border border-[#fdb022] bg-[#fffaeb] p-4 text-sm font-bold text-[#7a2e0e]">
          이미 가져온 같은 content입니다. 원본을 덮어쓰지 않고 독립 복사본으로만 가져올 수 있습니다.
          <Select className="mt-3" value={duplicateStrategy} onChange={(event) => onDuplicateStrategy(event.target.value as "reject" | "independent_copy")}>
            <option value="independent_copy">독립 복사본으로 가져오기</option>
            <option value="reject">가져오지 않기</option>
          </Select>
        </label>
      ) : null}

      {preview.warnings.length ? <IssueList title="확인할 내용" items={preview.warnings} tone="warning" /> : null}
      {blocked ? <IssueList title="가져오기를 막는 문제" items={preview.blocking_issues} tone="error" /> : null}

      <label className="mt-6 flex items-start gap-3 rounded-[20px] bg-[#f7f8fa] p-4 text-sm font-semibold leading-6 text-[#475467]">
        <input className="mt-1 size-4" checked={approved} disabled={blocked} onChange={(event) => onApproval(event.target.checked)} type="checkbox" />
        <span>위 라이선스·제외 항목·충돌 계획과 digest <code className="break-all text-xs">{preview.content_digest}</code>를 확인하고 이 미리보기 그대로 가져옵니다.</span>
      </label>

      <div className="mt-6 flex flex-wrap gap-3">
        <Button variant="strong" loading={pending === "commit"} loadingLabel="World 가져오는 중" disabled={!approved || blocked || pending !== null || duplicateStrategy === "reject" && alreadyImported} onClick={onCommit}>
          <ShieldCheck className="size-4" /> World 가져오기
        </Button>
        <Button variant="secondary" loading={pending === "discard"} loadingLabel="미리보기 폐기 중" disabled={pending !== null} onClick={onDiscard}>
          <RotateCcw className="size-4" /> 미리보기 폐기
        </Button>
      </div>
    </Card>
  );
}

function ImportSuccess({ result }: { result: WorldPackageImportResult }) {
  return (
    <section className="rounded-[28px] border border-[#abefc6] bg-[#ecfdf3] p-8 text-center">
      <CheckCircle2 className="mx-auto size-11 text-[#039855]" />
      <h2 className="mt-4 text-2xl font-black text-[#05603a]">World를 안전하게 가져왔습니다</h2>
      <p className="mt-3 text-sm font-semibold text-[#027a48]">Device Home 등록과 새 World seed commit이 하나의 transaction으로 완료됐습니다.</p>
      <div className="mt-6 flex flex-wrap justify-center gap-3">
        <Link className={primaryButtonClass} href={PRODUCT_ROUTES.deviceHome}>Device Home에서 보기</Link>
        <Link className={secondaryButtonClass} href={studioWorldRoute(result.imported_world_id)}>새 World 열기</Link>
      </div>
    </section>
  );
}

function ImportNotice({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto flex max-w-3xl items-center justify-center gap-3 rounded-[24px] border border-[#e1e5eb] bg-white p-8 font-bold text-[#667085]">{children}</div>;
}

function Value({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-xs font-bold text-[#98a2b3]">{label}</dt><dd className="mt-1 break-words font-black text-[#344054]">{value}</dd></div>;
}

function IssueList({ title, items, tone }: { title: string; items: string[]; tone: "warning" | "error" }) {
  return <div className={`mt-5 rounded-[20px] p-5 ${tone === "error" ? "bg-[#fff1f0] text-[#b42318]" : "bg-[#fffaeb] text-[#7a2e0e]"}`}><h3 className="flex items-center gap-2 font-black"><AlertTriangle className="size-4" />{title}</h3><ul className="mt-3 list-disc space-y-1 pl-5 text-sm font-semibold">{items.map((item) => <li key={item}>{item}</li>)}</ul></div>;
}

function importError(reason: unknown) {
  return reason instanceof Error ? reason.message : "World Package를 처리하지 못했습니다.";
}

function formatBytes(value: number) {
  return value < 1024 * 1024 ? `${(value / 1024).toFixed(1)} KiB` : `${(value / (1024 * 1024)).toFixed(1)} MiB`;
}

function trustLabel(value: string) {
  return value === "locally_exported" ? "이 설치에서 내보냄" : "checksum 검증 · 서명 없음";
}

function duplicateLabel(value: string) {
  if (value === "already_imported") return "이미 가져온 동일 content";
  if (value === "independent_fork") return "독립 복사본";
  return "새 Package";
}

const primaryButtonClass = "inline-flex min-h-11 items-center justify-center gap-2 rounded-full bg-[#101828] px-5 text-sm font-extrabold text-white hover:bg-[#344054] disabled:cursor-not-allowed disabled:opacity-50";
const secondaryButtonClass = "inline-flex min-h-11 items-center justify-center gap-2 rounded-full border border-[#d0d5dd] bg-white px-5 text-sm font-extrabold text-[#344054] hover:bg-[#f9fafb] disabled:cursor-not-allowed disabled:opacity-50";
