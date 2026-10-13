"use client";

import { useUiText } from "@/hooks/use-ui-text";
const LUCIDE_ISC_LICENSE = `ISC License

Copyright (c) 2026 Lucide Icons and Contributors

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.`;

const FEATHER_MIT_LICENSE = `MIT License

Copyright (c) 2013-present Cole Bemis

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.`;

export function LicensesContent() {
  const uiText = useUiText("support");
  return (
<div className="min-h-screen bg-white" data-product-content="licenses">
        <header className="border-b border-[#eaedf2] px-5 py-8 md:px-9 md:py-10">
          <p className="text-[14px] font-extrabold text-[#ff6b6b]">
            Angmoo notices
          </p>
          <h1 className="mt-2 text-[34px] font-extrabold leading-tight text-[#101828] md:text-[42px]">
            {uiText("라이선스")}</h1>
          <p className="mt-4 max-w-[660px] break-keep text-[16px] font-bold leading-7 text-[#667085]">
            {uiText("Angmoo application과 함께 배포되는 제3자 구성요소의 라이선스 경계를 안내합니다.")}</p>
        </header>

        <section className="px-5 py-8 md:px-9">
          <div className="mb-6 rounded-[24px] border border-[#eef1f5] bg-white p-5 shadow-[0_14px_34px_rgba(16,24,40,0.04)] md:p-6">
            <p className="text-[14px] font-extrabold text-[#ff6b6b]">
              Angmoo application
            </p>
            <h2 className="mt-1 text-[24px] font-extrabold text-[#101828]">
              GPL-3.0-only
            </h2>
            <div className="mt-4 space-y-3 break-keep text-[15px] font-medium leading-7 text-[#475467]">
              <p>
                {uiText("Angmoo application source는 GNU General Public License version 3 only 조건으로 제공됩니다.")}</p>
              <p>
                {uiText("이 조건은 Angmoo를 사용해 만든 World Package나 로컬 Runtime 데이터에 자동으로 부여되지 않습니다. 함께 배포되는 제3자 구성요소에는 각 구성요소의 라이선스가 적용됩니다.")}</p>
              <p>
                {uiText("전체 원문은 저장소의")}{" "}
                <a
                  href="https://github.com/angmoo-tree/angmoo/blob/main/LICENSE"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-extrabold text-[#ff6b6b] hover:underline"
                >
                  LICENSE
                </a>
                {uiText("에서 확인할 수 있습니다.")}</p>
            </div>
          </div>

          <div className="rounded-[24px] border border-[#eef1f5] bg-white p-5 shadow-[0_14px_34px_rgba(16,24,40,0.04)] md:p-6">
            <p className="text-[14px] font-extrabold text-[#ff6b6b]">Icons</p>
            <h2 className="mt-1 text-[24px] font-extrabold text-[#101828]">
              Lucide Icons
            </h2>
            <div className="mt-4 space-y-3 break-keep text-[15px] font-medium leading-7 text-[#475467]">
              <p>{uiText("Angmoo는 일부 UI 아이콘에 Lucide Icons를 사용합니다.")}</p>
              <p>
                {uiText("Lucide Icons는 ISC License로 제공되며, 일부 Lucide 아이콘은 Feather Icons에서 파생되어 MIT License 고지가 적용됩니다.")}</p>
              <p>
                {uiText("공식 라이선스 문서는")}{" "}
                <a
                  href="https://lucide.dev/license"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-extrabold text-[#ff6b6b] hover:underline"
                >
                  lucide.dev/license
                </a>
                {uiText("에서 확인할 수 있습니다.")}</p>
            </div>

            <LicenseBlock title="Lucide Icons - ISC License" body={LUCIDE_ISC_LICENSE} />
            <LicenseBlock title="Feather Icons - MIT License" body={FEATHER_MIT_LICENSE} />
          </div>
          <div className="mt-6 rounded-3xl border border-border-soft bg-surface p-6">
            <h2 className="text-xl font-bold">Quicksand · libheif</h2>
            <p>{uiText("홈 제목에는 로컬 Quicksand 글꼴을 사용해요. HEIF 사진 변환에는 기기에 포함된 libheif를 사용하며 외부 변환 서비스로 사진을 보내지 않아요.")}</p>
            <p>Quicksand: © 2011 The Quicksand Project Authors · Reserved Font Name: Quicksand · OFL-1.1</p>
            <p>libheif-js 1.23.5: Kiril Vatev · LGPL-3.0 · libheif: Dirk Farin and contributors · LGPL-3.0-or-later · libde265: struktur AG and contributors · LGPL-3.0</p>
            <ul>
              <li><a href="/licenses/Quicksand-OFL.txt">Quicksand — OFL-1.1</a></li>
              <li><a href="/licenses/libheif-js-LGPL-3.0.txt">libheif-js — LGPL-3.0</a></li>
              <li><a href="/licenses/libheif-LICENSE.txt">libheif — LGPL-3.0 / MIT</a></li>
              <li><a href="/licenses/libde265-LGPL.txt">libde265 — LGPL-3.0</a></li>
              <li><a href="/licenses/Angmoo-GPL-3.0.txt">GPL-3.0</a></li>
              <li><a href="https://github.com/catdad-experiments/libheif-js/tree/d8ec4bc3bc5bf8055975577bccbbc7e1d7313c2d">libheif-js 1.23.5 source</a></li>
              <li><a href="https://github.com/catdad-experiments/libheif-emscripten/tree/5c8968a44e9c68ae677e24790d77d001ed7fe7cc">libheif WASM source and build</a></li>
            </ul>
          </div>
        </section>
      </div>
  );
}

function LicenseBlock({ title, body }: { title: string; body: string }) {
  return (
    <section className="mt-6">
      <h3 className="text-[17px] font-extrabold text-[#101828]">{title}</h3>
      <pre className="mt-3 overflow-x-auto whitespace-pre-wrap rounded-[18px] bg-[#101828] p-4 text-[12px] font-medium leading-6 text-[#eef1f5]">
        {body}
      </pre>
    </section>
  );
}
