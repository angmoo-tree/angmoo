import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/seo";

const lastModified = new Date("2026-06-25T00:00:00.000Z");

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: SITE_URL,
      lastModified,
      changeFrequency: "daily",
      priority: 1,
    },
    {
      url: `${SITE_URL}/tree`,
      lastModified,
      changeFrequency: "weekly",
      priority: 0.6,
    },
    {
      url: `${SITE_URL}/angmoo-api`,
      lastModified,
      changeFrequency: "monthly",
      priority: 0.4,
    },
    {
      url: `${SITE_URL}/licenses`,
      lastModified,
      changeFrequency: "yearly",
      priority: 0.2,
    },
  ];
}
