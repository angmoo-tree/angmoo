import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { MessageThreadClient } from "@/components/message-thread-client";
import { NO_INDEX_ROBOTS } from "@/lib/seo";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  robots: NO_INDEX_ROBOTS,
};

type PageProps = {
  params: Promise<{
    threadId: string;
  }>;
};

export default async function MessageThreadPage({ params }: PageProps) {
  const { threadId } = await params;
  return (
    <AppShell>
      <MessageThreadClient threadId={threadId} />
    </AppShell>
  );
}
