"use client";
import {WorldChat} from "@/features/chat/components/world-chat";
import type {WorldChatViewSlots} from "@/features/chat/types/view-slots";
import { MemoryScopeSummary } from "@/features/memory/components/memory-scope-summary";
import { WorldChatEvidenceInspector } from "@/features/memory/components/world-chat-evidence-inspector";

const renderMemorySummary: WorldChatViewSlots["renderMemorySummary"] = input => <MemoryScopeSummary {...input} />;
const renderEvidenceInspector: WorldChatViewSlots["renderEvidenceInspector"] = input => <WorldChatEvidenceInspector key={input.requestId ?? "closed"} {...input} />;

export function WorldChatScreen({threadId, worldId}: {threadId?: string; worldId: string}) {
 return <WorldChat threadId={threadId} worldId={worldId} renderMemorySummary={renderMemorySummary} renderEvidenceInspector={renderEvidenceInspector} />;
}
