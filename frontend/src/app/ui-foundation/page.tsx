import type { Metadata } from "next";

import { SemanticFoundationFixture } from "@/features/ui-foundation/public";

export const metadata: Metadata = {
  robots: {
    follow: false,
    index: false,
  },
  title: "Angmoo UI Foundation Fixture",
};

export default function UiFoundationPage() {
  return <SemanticFoundationFixture />;
}
