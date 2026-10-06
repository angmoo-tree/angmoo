import type { ReactNode } from "react";

/** Extra panels are supplied by the product screen; Chat owns their selection and lifecycle inputs. */
export type WorldChatViewSlots = {
  renderMemorySummary: (input: {subjectWorldCharacterId: string; worldId: string}) => ReactNode;
  renderEvidenceInspector: (input: {onOpenChange: (open: boolean) => void; open: boolean; requestId: string | null; threadId: string; worldId: string}) => ReactNode;
  renderImagePicker?: (input: { threadId: string; disabled: boolean; value: { id: string; url: string; allowed: boolean } | null; onChange: (value: { id: string; url: string; allowed: boolean } | null) => void; onBusyChange: (busy: boolean) => void; renderLayout: (slots: { trigger: ReactNode; preview: ReactNode; feedback: ReactNode }) => ReactNode }) => ReactNode;
};
