"use client";

import { LocalProductLink } from "@/components/navigation/local-product-link";
import { ProfileAvatar } from "@/components/ui/profile-avatar";
import styles from "@/features/characters/components/world-character-profile.module.css";
import { worldCharacterProfileRoute } from "@/lib/navigation/product-routes";
import { formatHandle } from "@/utils/profile-presentation";
import { RotateCcw,Users } from "lucide-react";
import { useCallback,useEffect,useState } from "react";
import { listWorldCharacterProfiles, WorldCharacterProfileApiError } from "@/features/characters/api/world-character-profile-client";
import type { WorldCharacterProfileListRead } from "@/features/characters/types/world-character-profile";

type LoadState = "loading" | "ready" | "error";

export function WorldCharacterDirectory({ worldId }: { worldId: string }) {
  const [read, setRead] = useState<WorldCharacterProfileListRead | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState<Error | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    void listWorldCharacterProfiles(worldId, { signal: controller.signal })
      .then((result) => {
        setRead(result);
        setState("ready");
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setRead(null);
        setError(reason instanceof Error ? reason : new Error("world_character_profiles_unavailable"));
        setState("error");
      });
    return () => controller.abort();
  }, [attempt, worldId]);

  const retry = useCallback(() => {
    setState("loading");
    setError(null);
    setAttempt((value) => value + 1);
  }, []);

  if (state === "loading") {
    return <ProfileStatus title="Character 목록을 불러오는 중" />;
  }
  if (state === "error" || !read) {
    return <ProfileError error={error} onRetry={retry} />;
  }

  return (
    <section className={styles.directory} data-world-character-surface="list">
      <header className={styles.directoryHeading}>
        <span className={styles.headingIcon} data-world-character-directory-icon>
          <Users aria-hidden="true" size={21} />
        </span>
        <div>
          <p>WORLD CHARACTERS</p>
          <h2>이 World의 앵무</h2>
          <span className={styles.directoryMeta}>
            현재 참여 중인 Character {read.items.length}명
          </span>
        </div>
      </header>
      {read.items.length === 0 ? (
        <div className={styles.empty}>
          <Users aria-hidden="true" size={28} />
          <h3>현재 참여 중인 Character가 없어요</h3>
          <p>active membership이 확인된 Character만 여기에 표시됩니다.</p>
        </div>
      ) : (
        <ol className={styles.profileList} aria-label="World Character 목록">
          {read.items.map((profile) => (
            <li key={profile.world_character_id}>
              <LocalProductLink
                ariaLabel={`${profile.display_name}의 World 프로필 열기`}
                className={styles.profileListLink}
                href={worldCharacterProfileRoute(worldId, profile.world_character_id)}
              >
                <ProfileAvatar
                  avatarUrl={profile.avatar_url}
                  name={profile.display_name}
                  sizeClassName={styles.listAvatar}
                  textClassName={styles.listAvatarText}
                />
                <span className={styles.listIdentity}>
                  <strong>{profile.display_name}</strong>
                  {profile.handle ? <span>{formatHandle(profile.handle)}</span> : null}
                  {profile.intro ? <small>{profile.intro}</small> : null}
                </span>
              </LocalProductLink>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

export function ProfileStatus({ title }: { title: string }) {
  return (
    <section aria-live="polite" className={styles.status} role="status">
      <Users aria-hidden="true" size={27} />
      <h2>{title}</h2>
      <p>현재 World의 identity와 capability를 확인하고 있어요.</p>
    </section>
  );
}

export function ProfileError({
  error,
  onRetry,
}: {
  error: Error | null;
  onRetry: () => void;
}) {
  const unavailable =
    error instanceof WorldCharacterProfileApiError && [403, 404].includes(error.status);
  return (
    <section className={styles.status} role="alert">
      <Users aria-hidden="true" size={27} />
      <h2>{unavailable ? "이 프로필을 열 수 없어요" : "프로필을 불러오지 못했어요"}</h2>
      <p>
        {unavailable
          ? "다른 World, 떠난 Character 또는 허용되지 않은 identity로 이동하지 않습니다."
          : "로컬 runtime 상태를 확인한 뒤 다시 시도해주세요."}
      </p>
      {!unavailable ? (
        <button onClick={onRetry} type="button">
          <RotateCcw aria-hidden="true" size={17} />
          다시 시도
        </button>
      ) : null}
    </section>
  );
}
