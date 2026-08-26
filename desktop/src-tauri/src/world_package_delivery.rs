use serde::Serialize;
use std::{
    collections::HashMap,
    fs::{self, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
    sync::Mutex,
};
use tauri::AppHandle;
use tauri_plugin_dialog::DialogExt;
use uuid::Uuid;

const WORLD_PACKAGE_EXTENSION: &str = ".angmoo-world";
const MAX_WORLD_PACKAGE_BYTES: usize = 128 * 1024 * 1024;

#[derive(Default)]
pub struct WorldPackageDestinationState {
    destinations: Mutex<HashMap<String, PathBuf>>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct WorldPackageDestinationSelection {
    cancelled: bool,
    destination_token: Option<String>,
}

fn safe_recommended_filename(value: &str) -> String {
    let leaf = Path::new(value)
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("angmoo-world.angmoo-world");
    let filtered: String = leaf
        .chars()
        .filter(|character| {
            !matches!(
                character,
                '<' | '>' | ':' | '"' | '/' | '\\' | '|' | '?' | '*'
            )
        })
        .collect();
    let trimmed = filtered.trim().trim_end_matches(['.', ' ']);
    let base = if trimmed.is_empty() {
        "angmoo-world"
    } else {
        trimmed
    };
    if base.to_ascii_lowercase().ends_with(WORLD_PACKAGE_EXTENSION) {
        base.to_owned()
    } else {
        format!("{base}{WORLD_PACKAGE_EXTENSION}")
    }
}

#[tauri::command]
pub async fn select_world_package_export_destination(
    app: AppHandle,
    state: tauri::State<'_, WorldPackageDestinationState>,
    recommended_filename: String,
) -> Result<WorldPackageDestinationSelection, String> {
    let filename = safe_recommended_filename(&recommended_filename);
    let selection = app
        .dialog()
        .file()
        .set_title("Angmoo World Package 저장")
        .set_file_name(filename)
        .add_filter("Angmoo World Package", &["angmoo-world"])
        .blocking_save_file();
    let Some(path) = selection else {
        return Ok(WorldPackageDestinationSelection {
            cancelled: true,
            destination_token: None,
        });
    };
    let path = path
        .into_path()
        .map_err(|_| "world_package_destination_invalid")?;
    if !path
        .to_string_lossy()
        .to_ascii_lowercase()
        .ends_with(WORLD_PACKAGE_EXTENSION)
    {
        return Err("world_package_destination_extension_invalid".to_owned());
    }
    let token = Uuid::new_v4().to_string();
    state
        .destinations
        .lock()
        .map_err(|_| "world_package_destination_state_poisoned")?
        .insert(token.clone(), path);
    Ok(WorldPackageDestinationSelection {
        cancelled: false,
        destination_token: Some(token),
    })
}

#[tauri::command]
pub fn write_world_package_export_destination(
    state: tauri::State<'_, WorldPackageDestinationState>,
    destination_token: String,
    content: Vec<u8>,
) -> Result<(), String> {
    if content.is_empty() || content.len() > MAX_WORLD_PACKAGE_BYTES {
        return Err("world_package_delivery_size_invalid".to_owned());
    }
    let destination = state
        .destinations
        .lock()
        .map_err(|_| "world_package_destination_state_poisoned")?
        .remove(&destination_token)
        .ok_or_else(|| "world_package_destination_expired".to_owned())?;
    atomic_write(&destination, &content)
}

#[tauri::command]
pub fn discard_world_package_export_destination(
    state: tauri::State<'_, WorldPackageDestinationState>,
    destination_token: String,
) -> Result<(), String> {
    state
        .destinations
        .lock()
        .map_err(|_| "world_package_destination_state_poisoned")?
        .remove(&destination_token);
    Ok(())
}

fn atomic_write(destination: &Path, content: &[u8]) -> Result<(), String> {
    let parent = destination
        .parent()
        .filter(|path| path.is_dir())
        .ok_or_else(|| "world_package_destination_parent_invalid".to_owned())?;
    let suffix = Uuid::new_v4();
    let pending = parent.join(format!(".angmoo-world-{suffix}.pending"));
    let backup = parent.join(format!(".angmoo-world-{suffix}.backup"));
    let result = (|| {
        let mut file = OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&pending)
            .map_err(|_| "world_package_destination_write_failed")?;
        file.write_all(content)
            .and_then(|_| file.sync_all())
            .map_err(|_| "world_package_destination_write_failed")?;
        drop(file);

        let had_existing = destination.exists();
        if had_existing {
            fs::rename(destination, &backup)
                .map_err(|_| "world_package_destination_replace_failed")?;
        }
        if let Err(_error) = fs::rename(&pending, destination) {
            if had_existing {
                let _ = fs::rename(&backup, destination);
            }
            return Err("world_package_destination_commit_failed".to_owned());
        }
        if had_existing {
            let _ = fs::remove_file(&backup);
        }
        Ok(())
    })();
    let _ = fs::remove_file(&pending);
    let _ = fs::remove_file(&backup);
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn recommended_filename_is_leaf_only_and_forces_world_extension() {
        assert_eq!(
            safe_recommended_filename("../bad:world"),
            "badworld.angmoo-world"
        );
        assert_eq!(
            safe_recommended_filename("harbor-v1.angmoo-world"),
            "harbor-v1.angmoo-world"
        );
    }
}
