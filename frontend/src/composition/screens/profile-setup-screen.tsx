"use client";

import { ProfileSetupClient } from "@/features/identity/components/profile-setup-client";
import { markFirstAgentWelcomePromptPending } from "@/lib/agents";

export function ProfileSetupScreen() {
  return <ProfileSetupClient onProfileReady={markFirstAgentWelcomePromptPending} />;
}
