#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{env, fs, thread, time::Duration};

fn main() {
    if let Some(marker) = env::var_os("ANGMOO_DEFENDER_MATRIX_MARKER") {
        fs::write(marker, b"stub-started\n").expect("matrix marker write failed");
    }
    thread::sleep(Duration::from_secs(5));
}
