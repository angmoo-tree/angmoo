import { Suspense } from "react";
import { ProductViewport } from "@/composition/shells/product-viewport";
import type { Metadata } from "next";
import { AuthProvider } from "@/composition/providers/auth-provider";
import { PwaServiceWorkerLifecycle } from "@/composition/providers/pwa-service-worker-lifecycle";
import { DesktopWindowBridge } from "@/composition/providers/desktop-window-bridge";
import { BrowserNavigationGuard } from "@/composition/providers/browser-navigation-guard";
import {
  SITE_DESCRIPTION,
  SITE_ICON,
  SITE_PREVIEW_IMAGE,
  SITE_TITLE,
  SITE_URL,
} from "@/config/seo";
import "../styles/globals.css";

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
    locale: "en_US",
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
    <html lang="en">
      <body className="antialiased">
        <AuthProvider>
          <BrowserNavigationGuard />
          <Suspense fallback={null}><DesktopWindowBridge /></Suspense>
          <PwaServiceWorkerLifecycle />
          <ProductViewport>{children}</ProductViewport>
        </AuthProvider>
      </body>
    </html>
  );
}
