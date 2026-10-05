"use client";
import { useUiText } from "@/hooks/use-ui-text";


import { ProfileAvatar } from "@/components/ui/profile-avatar";
import styles from "@/features/characters/components/world-character-profile.module.css";
import { useRuntimeMediaUrl } from "@/hooks/use-runtime-media-url";
import { safeSameOriginMediaUrl } from "@/lib/media/safe-media-url";
import { formatHandle } from "@/utils/profile-presentation";
import { ArrowLeft } from "lucide-react";
import type { ReactNode } from "react";
import type { WorldCharacterPublicProfile } from "@/features/characters/types/world-character-profile";

export function WorldCharacterProfileCard({ profile, worldId, worldCharacterId, onBack, chatAction, chatNotice, children }: {
  profile: WorldCharacterPublicProfile; worldId: string; worldCharacterId: string; onBack?: () => void;
  chatAction: ReactNode; chatNotice: ReactNode; children: ReactNode;
}) {
  const uiText = useUiText("characters");
  return (
    <section
      className={styles.profile}
      data-world-character-id={worldCharacterId}
      data-world-character-surface="profile"
      data-world-id={worldId}
    >
      <ProfileBanner bannerUrl={profile.banner_url} />
      <div className={styles.profileBody}>
        {onBack ? <button
          aria-label={uiText("이전 화면으로")}
          className={styles.backButton}
          onClick={onBack}
          title={uiText("이전 화면으로")}
          type="button"
        >
          <ArrowLeft aria-hidden="true" size={20} />
        </button> : null}
        <div className={styles.avatarRow}>
          <span className={styles.avatarFrame}>
            <ProfileAvatar
              avatarUrl={profile.avatar_url}
              name={profile.display_name}
              sizeClassName={styles.profileAvatar}
              textClassName={styles.profileAvatarText}
            />
          </span>
          {chatAction}
        </div>
        <div className={styles.identity}>
          <h2>{profile.display_name}</h2>
          {profile.handle ? <p>{formatHandle(profile.handle)}</p> : null}
          <div className={styles.badges}>
            <span>{profile.control_mode === "owner_controlled" ? uiText("사용자 조종") : uiText("자율 앵무")}</span>
          </div>
          {profile.intro ? <div className={styles.intro}>{profile.intro}</div> : null}
          {profile.role_key ? <details className={styles.profileDetails}><summary>{uiText("World 프로필 정보")}</summary><p>{profile.role_key}</p></details> : null}
        </div>
        {chatNotice}
      </div>
      {children}
    </section>
  );
}

function ProfileBanner({ bannerUrl }: { bannerUrl: string | null }) {
  const safeUrl = safeSameOriginMediaUrl(bannerUrl);
  const resolvedUrl = useRuntimeMediaUrl(safeUrl);
  if (!resolvedUrl) return <div className={styles.banner} />;
  return (
    <div className={styles.banner}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img alt="" src={resolvedUrl} />
    </div>
  );
}
