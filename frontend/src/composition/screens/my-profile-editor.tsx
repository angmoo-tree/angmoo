"use client";
import { MyProfileEditor } from "@/features/worlds/components/my-profile-editor";
import { ProfileMediaUploader } from "@/features/characters/components/profile-media-uploader";

export function LocalMyProfileEditor({ worldId, onSaved }: { worldId: string; onSaved?: () => void }) {
  return <MyProfileEditor worldId={worldId} onSaved={onSaved} renderMedia={(props) => <ProfileMediaUploader {...props} />} />;
}
