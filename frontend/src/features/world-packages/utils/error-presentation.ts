import type { UiText } from "@/hooks/use-ui-text";
import { WorldPackageApiError } from "@/features/world-packages/api/world-package-client";

const ERROR_MESSAGES: Record<string, string> = {
  world_package_owner_required: "Sign in as the device owner to manage World Packages.",
  world_package_world_not_exportable: "This World cannot be exported.",
  world_package_source_changed: "The World changed. Review its contents again before exporting.",
  world_package_persona_invalid: "Check the character settings' lengths.",
  world_package_upload_too_large: "The World Package file is too large.",
  world_package_archive_invalid: "The World Package file could not be read. Check its format and try again.",
  world_package_path_unsafe: "The World Package contains an unsafe file path.",
  world_package_archive_limit_exceeded: "The World Package exceeds the allowed file or size limits.",
  world_package_manifest_missing: "The World Package is missing its manifest. Export the package again from its source.",
  world_package_format_unsupported: "This World Package format is not supported.",
  world_package_app_version_unsupported: "This World Package requires a different Angmoo version.",
  world_package_contract_unsupported: "This World Package uses an unsupported contract version.",
  world_package_integrity_mismatch: "The World Package failed its integrity check. Export it again from its source.",
  world_package_license_missing: "The World Package must include license information.",
  world_package_asset_unsupported: "The World Package contains an unsupported media file.",
  world_package_asset_missing: "A required World Package media file is missing.",
  world_package_reference_invalid: "The World Package contains an invalid reference.",
  world_package_duplicate: "This World Package was already imported. Choose an independent copy to import it again.",
  world_package_tampered_version: "This World Package version conflicts with an existing package.",
  world_package_stage_expired: "The import preview expired. Select the package again.",
  world_package_stage_forbidden: "This import preview belongs to another owner.",
  world_package_preview_changed: "The import preview changed. Review it again before importing.",
  world_package_commit_conflict: "The import conflicts with an existing World. Review the package again.",
  world_package_commit_failed: "The import could not be completed. Select the package and review it again.",
  world_package_delivery_expired: "The export download expired. Prepare the export again.",
  world_package_delivery_forbidden: "This export download belongs to another owner.",
};

const FIELD_LABELS: Record<string, string> = {
  one_liner: "Short introduction", personality: "Personality", speech_style: "Speech style",
  worldview: "Background / worldview", character_background: "Character background / worldview", topic_preferences: "Preferred topics",
  safety_rules: "Actions to avoid", persona_summary: "Character summary",
};

export type WorldPackageFailure =
  | { kind: "request"; reason: unknown; context?: string }
  | { kind: "local"; message: string };

/** Translate only authored keys and sanitized parameters at render time. */
export function formatWorldPackageFailure(
  failure: WorldPackageFailure, operation: "import" | "export", uiText: UiText,
  formatNumber: (value: number) => string,
): string {
  if (failure.kind === "local") return uiText(failure.message);
  const reason = failure.reason;
  let message: string;
  if (reason instanceof WorldPackageApiError && reason.code && Object.hasOwn(ERROR_MESSAGES, reason.code)) {
    message = uiText(ERROR_MESSAGES[reason.code]);
    if (reason.code === "world_package_persona_invalid" && reason.fields.length) {
      message += " " + reason.fields.map(field => uiText("{{field}}: {{actual}} / {{limit}} characters", {
        field: uiText(FIELD_LABELS[field.field]), actual: formatNumber(field.actual), limit: formatNumber(field.limit),
      })).join(", ");
    }
  } else if (reason instanceof WorldPackageApiError && reason.status >= 500) {
    message = operation === "import"
      ? uiText("The server could not process the import. Please try again later.")
      : uiText("The server could not process the export. Please try again later.");
  } else {
    message = operation === "import"
      ? uiText("The World Package could not be imported. Check the file and try again.")
      : uiText("The World Package could not be exported. Please try again.");
  }
  return failure.context ? uiText(failure.context, { value0: message }) : message;
}
