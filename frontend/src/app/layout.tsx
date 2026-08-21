import type { Metadata } from "next";
import { AuthProvider } from "@/components/auth-provider";
import { PwaServiceWorkerLifecycle } from "@/features/pwa-shell/public";
import { DesktopWindowBridge } from "@/shared/desktop/public";
import {
  SITE_DESCRIPTION,
  SITE_ICON,
  SITE_PREVIEW_IMAGE,
  SITE_TITLE,
  SITE_URL,
} from "@/lib/seo";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: SITE_TITLE,
  description: SITE_DESCRIPTION,
  alternates: {
    canonical: "/",
  },
  openGraph: {
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    url: "/",
    siteName: "Angmoo",
    locale: "ko_KR",
    type: "website",
    images: [
      {
        url: SITE_PREVIEW_IMAGE,
        width: 1200,
        height: 630,
        alt: "Angmoo golden cherry parrot logo",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    images: [SITE_PREVIEW_IMAGE],
  },
  icons: {
    icon: [{ url: SITE_ICON, type: "image/x-icon" }],
    shortcut: [SITE_ICON],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body className="antialiased">
        <AuthProvider>
          <DesktopWindowBridge />
          <PwaServiceWorkerLifecycle />
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
