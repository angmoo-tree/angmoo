"use client";
import {WorldChat} from "@/features/chat/components/world-chat";
import type {WorldChatViewSlots} from "@/features/chat/types/view-slots";
import { MemoryScopeSummary } from "@/features/memory/components/memory-scope-summary";
import { WorldChatEvidenceInspector } from "@/features/memory/components/world-chat-evidence-inspector";
import { ImagePicker } from "@/features/media/components/image-picker";

const renderMemorySummary: WorldChatViewSlots["renderMemorySummary"] = input => <MemoryScopeSummary {...input} />;
const renderEvidenceInspector: WorldChatViewSlots["renderEvidenceInspector"] = input => <WorldChatEvidenceInspector key={`${input.worldId}:${input.threadId}`} {...input} />;
const renderImagePicker: WorldChatViewSlots["renderImagePicker"] = input => <ImagePicker key={input.threadId} scopeKind="thread" scopeId={input.threadId} requireRecognition value={input.value} disabled={input.disabled} onChange={input.onChange} onBusyChange={input.onBusyChange} renderLayout={input.renderLayout} />;

export function WorldChatScreen({threadId, worldId}: {threadId?: string; worldId: string}) {
 return <WorldChat threadId={threadId} worldId={worldId} renderMemorySummary={renderMemorySummary} renderEvidenceInspector={renderEvidenceInspector} renderImagePicker={renderImagePicker} />;
}
