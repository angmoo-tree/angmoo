use std::{env, fs, path::PathBuf};

fn main() {
    let target = env::var("TARGET").unwrap_or_else(|_| "unknown-target".to_owned());
    let manifest_dir =
        PathBuf::from(env::var("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR is required"));
    let hash_path = manifest_dir
        .join("binaries")
        .join(format!("angmoo-sidecar-{target}.exe.sha256"));
    println!("cargo:rerun-if-changed={}", hash_path.display());
    let expected = fs::read_to_string(hash_path)
        .map(|value| value.trim().to_ascii_lowercase())
        .unwrap_or_else(|_| "missing-sidecar-hash".to_owned());
    println!("cargo:rustc-env=ANGMOO_SIDECAR_SHA256={expected}");
    println!("cargo:rustc-env=ANGMOO_TARGET_TRIPLE={target}");
    tauri_build::build()
}
