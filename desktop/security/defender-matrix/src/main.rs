#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{thread, time::Duration};

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            // This stage-one control is deliberately incapable of spawning a
            // child. Stub and real-sidecar execution live in separate hosts so
            // Defender can attribute each behavior to one exact binary.
            let handle = app.handle().clone();
            thread::spawn(move || {
                thread::sleep(Duration::from_secs(8));
                handle.exit(0);
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("ER6 Defender matrix host failed");
}
