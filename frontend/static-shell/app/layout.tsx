import type { Metadata } from "next";

import { AuthProvider } from "@/components/auth-provider";
import { StaticNavigationBridge } from "@/shared/navigation/public";
import "./static-globals.css";

export const metadata: Metadata = {
  title: "Angmoo Local",
  description: "Angmoo Tauri local product shell",
  icons: [{ rel: "icon", url: "/icon.svg" }],
};

export default function StaticRootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="antialiased">
        <AuthProvider>
          <StaticNavigationBridge />
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
