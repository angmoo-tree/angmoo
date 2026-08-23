use std::path::{Path, PathBuf};

use tauri::{AppHandle, Manager};

pub const PRODUCT_DATA_DIRECTORY: &str = "Angmoo";

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ProductDataPaths {
    pub root: PathBuf,
    pub app: PathBuf,
    pub canonical: PathBuf,
    pub graph: PathBuf,
    pub search: PathBuf,
    pub media: PathBuf,
    pub secrets: PathBuf,
    pub runtime: PathBuf,
    pub logs: PathBuf,
    pub webview: PathBuf,
}

impl ProductDataPaths {
    pub fn from_local_data_directory(local_data_directory: &Path) -> Self {
        let root = local_data_directory.join(PRODUCT_DATA_DIRECTORY);
        Self {
            app: root.join("app"),
            canonical: root.join("canonical"),
            graph: root.join("graph"),
            search: root.join("search"),
            media: root.join("media"),
            secrets: root.join("secrets"),
            runtime: root.join("runtime"),
            logs: root.join("logs"),
            webview: root.join("webview"),
            root,
        }
    }

    pub fn resolve(app: &AppHandle) -> Result<Self, String> {
        let local_data_directory = app
            .path()
            .local_data_dir()
            .map_err(|_| "product_local_data_directory_unavailable".to_owned())?;
        Ok(Self::from_local_data_directory(&local_data_directory))
    }

    pub fn prepare_runtime_owned_directories(&self) -> Result<(), String> {
        // `app` is installer-owned and is deliberately not created by the
        // product runtime. Every other directory is an explicit Angmoo data
        // boundary and may be prepared idempotently on first launch.
        for directory in [
            &self.canonical,
            &self.graph,
            &self.search,
            &self.media,
            &self.secrets,
            &self.runtime,
            &self.logs,
            &self.webview,
        ] {
            std::fs::create_dir_all(directory)
                .map_err(|_| "product_data_directory_unavailable".to_owned())?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use uuid::Uuid;

    #[test]
    fn product_tree_is_rooted_in_one_local_app_data_namespace() {
        let local = PathBuf::from(r"C:\Users\fixture\AppData\Local");
        let paths = ProductDataPaths::from_local_data_directory(&local);

        assert_eq!(paths.root, local.join("Angmoo"));
        for child in [
            &paths.app,
            &paths.canonical,
            &paths.graph,
            &paths.search,
            &paths.media,
            &paths.secrets,
            &paths.runtime,
            &paths.logs,
            &paths.webview,
        ] {
            assert_eq!(child.parent(), Some(paths.root.as_path()));
        }
    }

    #[test]
    fn runtime_preparation_never_materializes_the_installer_owned_app_directory() {
        let local =
            std::env::temp_dir().join(format!("angmoo-product-paths-{}", Uuid::new_v4().simple()));
        let paths = ProductDataPaths::from_local_data_directory(&local);

        paths.prepare_runtime_owned_directories().unwrap();

        assert!(!paths.app.exists());
        for child in [
            &paths.canonical,
            &paths.graph,
            &paths.search,
            &paths.media,
            &paths.secrets,
            &paths.runtime,
            &paths.logs,
            &paths.webview,
        ] {
            assert!(child.is_dir());
        }
        std::fs::remove_dir_all(local).unwrap();
    }
}
