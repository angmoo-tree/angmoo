#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{env, process::Command, thread, time::Duration};

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let stub_path =
                env::var_os("ANGMOO_DEFENDER_MATRIX_STUB").ok_or("matrix_stub_path_missing")?;
            Command::new(stub_path)
                .spawn()
                .map_err(|error| format!("matrix_stub_spawn_failed: {error}"))?;

            let handle = app.handle().clone();
            thread::spawn(move || {
                thread::sleep(Duration::from_secs(8));
                handle.exit(0);
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("ER6 Defender stub-host matrix failed");
}
