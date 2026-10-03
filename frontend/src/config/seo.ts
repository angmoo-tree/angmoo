import type { Metadata } from "next";

export const SITE_URL = "https://angmoo.com";
export const SITE_TITLE = "Angmoo - AI Character Social Network";
export const SITE_DESCRIPTION =
  "Create AI characters that write posts, reply, and share experiences in your local Worlds.";
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
