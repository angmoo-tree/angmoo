"use client";
import {WorldChat} from "@/features/chat/components/world-chat";
import type {WorldChatViewSlots} from "@/features/chat/types/view-slots";
import {MemoryScopeSummary, WorldChatEvidenceInspector} from "@/features/memory/public";

const renderMemorySummary: WorldChatViewSlots["renderMemorySummary"] = input => <MemoryScopeSummary {...input} />;
const renderEvidenceInspector: WorldChatViewSlots["renderEvidenceInspector"] = input => <WorldChatEvidenceInspector key={input.requestId ?? "closed"} {...input} />;

export function WorldChatScreen({threadId, worldId}: {threadId?: string; worldId: string}) {
 return <WorldChat threadId={threadId} worldId={worldId} renderMemorySummary={renderMemorySummary} renderEvidenceInspector={renderEvidenceInspector} />;
}
