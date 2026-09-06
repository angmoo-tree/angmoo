export type WorldPackageLicense = {
  expression: string;
  attribution: string;
  source_url: string | null;
  license_text_path: string | null;
};

export type WorldPackageExportRequest = {
  license_expression: string;
  attribution: string;
  source_url: string | null;
  license_text: string | null;
  confirm_export_rights: true;
  confirm_license: true;
  confirm_exclusions: true;
};

export type WorldPackageExportPreview = {
  source_world_id: string;
  package_id: string;
  package_version: number;
  seed_digest: string;
  recommended_filename: string;
  included_autonomous_characters: number;
  excluded_owner_controlled_characters: number;
  included_assets: number;
  excluded_external_assets: number;
  warnings: string[];
  license: WorldPackageLicense;
};

export type PreparedWorldPackageExport = {
  operation_id: string;
  download_token: string;
  download_path: string;
  expires_at: string;
  preview: WorldPackageExportPreview;
  manifest_digest: string;
  archive_digest: string;
  archive_bytes: number;
  replayed_request: boolean;
};

export type WorldPackageImportPreview = {
  schema_version: string;
  state: string;
  operation_id: string;
  archive_digest: string;
  content_digest: string;
  package_id: string;
  package_version: number;
  producer_name: string;
  producer_version: string;
  min_reader_version: string;
  world_contract_version: string;
  trust_state: string;
  license: WorldPackageLicense;
  world_name: string;
  world_tagline: string;
  character_names: string[];
  role_count: number;
  place_count: number;
  rule_count: number;
  glossary_count: number;
  asset_count: number;
  asset_bytes: number;
  total_decoded_pixels: number;
  excluded_owner_controlled_characters: number;
  excluded_runtime_records: number;
  collision_plan: {
    planned_world_slug: string;
    characters: Array<{
      source_ref: string;
      display_name: string;
      planned_handle: string;
    }>;
    duplicate_state: "new_package" | "already_imported" | "independent_fork";
    commit_allowed_by_default: boolean;
  };
  normalized_assets: Array<{
    source_ref: string;
    normalized_ref: string;
    normalized_sha256: string;
    normalized_bytes: number;
    width: number;
    height: number;
    alt_text: string;
  }>;
  warnings: string[];
  blocking_issues: string[];
  expires_at: string;
};

export type PreparedWorldPackageImport = {
  preview_token: string;
  preview: WorldPackageImportPreview;
};

export type WorldPackageImportResult = {
  import_id: string;
  imported_world_id: string;
  device_home_world_id: string;
  replayed: boolean;
};
