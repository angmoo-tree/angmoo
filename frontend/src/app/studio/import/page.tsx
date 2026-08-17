import type { Metadata } from "next";

import { CreatorStudioFrame } from "@/features/creator-studio/public";
import { NO_INDEX_ROBOTS } from "@/lib/seo";

export const metadata: Metadata = {
  title: "World Import · Creator Studio · Angmoo",
  robots: NO_INDEX_ROBOTS,
};

export default function StudioImportPage() {
  return (
    <CreatorStudioFrame activeSection="import">
      <section className="mx-auto max-w-3xl rounded-[28px] border border-[#e1e5eb] bg-white p-8 shadow-sm md:p-12">
        <p className="text-xs font-black uppercase tracking-[0.14em] text-[#ff6b6b]">L3.5 CAPABILITY</p>
        <h1 className="mt-3 text-3xl font-black text-[#101828]">World 가져오기는 준비 중입니다</h1>
        <p className="mt-4 font-semibold leading-7 text-[#667085]">
          서명된 World Package 검증·충돌 preview·rollback 계약이 준비되기 전에는 파일을 읽거나 적용하지 않습니다.
        </p>
      </section>
    </CreatorStudioFrame>
  );
}
