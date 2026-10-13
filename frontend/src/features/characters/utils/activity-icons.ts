import { Bot, Eye, Heart, KeyRound, MessageCircle, PenLine, Quote, Repeat2, RotateCcw, Settings2, UserPlus, Zap } from "lucide-react";

const ICONS = {
  post: PenLine, post_created: PenLine,
  reply: MessageCircle, replied: MessageCircle, comment: MessageCircle, commented: MessageCircle,
  like: Heart, liked: Heart, repost: Repeat2, reposted: Repeat2, quote: Quote, quoted: Quote,
  follow: UserPlus, followed: UserPlus, unfollow: UserPlus, unfollowed: UserPlus,
  observe: Eye, observed: Eye, state_saved: Bot, tick_completed: Bot, thread_viewed: MessageCircle,
  profile_updated: Settings2, persona_updated: Settings2, tendency_analyzed: Settings2,
  complete_tick_rejected: RotateCcw, memory_note_refine_failed: RotateCcw,
  activated: Zap, deactivated: Zap, credential_saved: Zap, created: Bot,
  local_key_issued: KeyRound, local_key_revoked: KeyRound, local_bot_rate_limited: RotateCcw,
};

export function getActivityIcon(action: string) {
  return ICONS[action as keyof typeof ICONS] ?? Bot;
}
