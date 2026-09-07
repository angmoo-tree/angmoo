import type { ReactNode } from "react";

/** Extra panels are supplied by the product screen; Chat owns their selection and lifecycle inputs. */
export type WorldChatViewSlots = {
  renderMemorySummary: (input: {subjectWorldCharacterId: string; worldId: string}) => ReactNode;
  renderEvidenceInspector: (input: {onOpenChange: (open: boolean) => void; open: boolean; requestId: string | null; threadId: string; worldId: string}) => ReactNode;
};
