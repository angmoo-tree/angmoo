import type { Metadata } from "next";

import { AuthProvider } from "@/composition/providers/auth-provider";
import { DesktopWindowBridge } from "@/composition/providers/desktop-window-bridge";
import { StaticNavigationBridge } from "@/composition/providers/static-navigation-bridge";
import "./static-globals.css";

export const metadata: Metadata = {
  title: "Angmoo Local",
  description: "Angmoo Tauri local product shell",
  icons: [{ rel: "icon", url: "/icon.svg" }],
};

export default function StaticRootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko" data-angmoo-runtime-profile="tauri-static">
      <body className="antialiased">
        <AuthProvider>
          <DesktopWindowBridge />
          <StaticNavigationBridge />
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
