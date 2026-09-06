import type { UserRead } from "@/lib/auth/browser-session";

export type LocalOwnerCandidateRead = {
  user_id: string;
  display_name: string;
  character_count: number;
  world_count: number;
  credential_count: number;
  suggested: boolean;
};

export type LocalBootstrapRead = {
  state: "unclaimed" | "claimed" | "recovery_required";
  installation_id: string | null;
  local_label: string | null;
  owner: UserRead | null;
  candidates: LocalOwnerCandidateRead[];
};

export type GoogleLoginRead = {
  user: UserRead | null;
  profile_setup_required: boolean;
  signup_required: boolean;
  expires_at: string | null;
  email: string | null;
};

export type PendingGoogleSignup = {
  expires_at: string;
  email: string;
};

/** User-profile input supplied by its route; no Social feature dependency. */
export type UserProfileRead = {
  profile: { profile_type: "user" | "character"; id: string; display_name: string; handle: string | null; avatar_url: string | null; banner_url: string | null };
  following_count: number;
};
