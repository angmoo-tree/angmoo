import type { Metadata } from "next";

import { SemanticFoundationFixture } from "@/features/ui-foundation/components/semantic-foundation-fixture";

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
