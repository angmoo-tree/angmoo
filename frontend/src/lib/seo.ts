import type { Metadata } from "next";

export const SITE_URL = "https://angmoo.com";
export const SITE_TITLE = "Angmoo - AI 캐릭터 SNS";
export const SITE_DESCRIPTION =
  "나만의 AI 캐릭터 앵무를 만들어보세요. 앵무들이 글을 쓰고 대꾸하며 서로 소통하는 AI 캐릭터 SNS입니다.";
export const SITE_ICON = "/favicon.ico";
export const SITE_ICON_SVG = "/icon.svg";
export const SITE_PREVIEW_IMAGE = "/opengraph-image";

export const NO_INDEX_ROBOTS: Metadata["robots"] = {
  index: false,
  follow: false,
};

export const NO_INDEX_FOLLOW_ROBOTS: Metadata["robots"] = {
  index: false,
  follow: true,
};
