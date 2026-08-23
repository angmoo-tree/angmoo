#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{env, process::Command, thread, time::Duration};

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let sidecar_path = env::var_os("ANGMOO_DEFENDER_MATRIX_REAL_SIDECAR")
                .ok_or("matrix_real_sidecar_path_missing")?;
            let runtime_root = env::var_os("ANGMOO_DEFENDER_MATRIX_RUNTIME_ROOT")
                .ok_or("matrix_runtime_root_missing")?;
            let parent_pid = std::process::id().to_string();
            let runtime_root = runtime_root.to_string_lossy().into_owned();
            Command::new(sidecar_path)
                .args([
                    "--parent-pid",
                    &parent_pid,
                    "--runtime-root",
                    &runtime_root,
                    "--launch-id",
                    "er6-defender-matrix",
                ])
                .env(
                    "DESKTOP_LAUNCH_TOKEN",
                    "matrix-only-token-not-a-product-credential",
                )
                .env("DESKTOP_ALLOWED_ORIGIN", "http://tauri.localhost")
                .spawn()
                .map_err(|error| format!("matrix_real_sidecar_spawn_failed: {error}"))?;

            let handle = app.handle().clone();
            thread::spawn(move || {
                thread::sleep(Duration::from_secs(8));
                handle.exit(0);
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("ER6 Defender real-sidecar-host matrix failed");
}
