"use client";

import { ProfileSetupClient } from "@/features/identity/components/profile-setup-client";
import { markFirstAgentWelcomePromptPending } from "@/features/characters/stores/agent-session";

export function ProfileSetupScreen() {
  return <ProfileSetupClient onProfileReady={markFirstAgentWelcomePromptPending} />;
}
