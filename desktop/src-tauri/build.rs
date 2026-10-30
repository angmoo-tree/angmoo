use std::{env, fs, path::PathBuf};

fn main() {
    println!("cargo:rerun-if-env-changed=ANGMOO_SOURCE_SHA");
    let mut revisions=vec!["HEAD".to_owned()];
    if let Ok(result)=std::process::Command::new("git").args(["symbolic-ref","-q","HEAD"]).output() {
        if result.status.success() { revisions.push(String::from_utf8_lossy(&result.stdout).trim().to_owned()); }
    }
    for revision in revisions {
        if let Ok(result)=std::process::Command::new("git").args(["rev-parse","--git-path",&revision]).output() {
            if result.status.success() {
                println!("cargo:rerun-if-changed={}",String::from_utf8_lossy(&result.stdout).trim());
            }
        }
    }
    let source = env::var("ANGMOO_SOURCE_SHA").ok().or_else(|| {
        std::process::Command::new("git").args(["rev-parse", "HEAD"]).output().ok()
            .filter(|result| result.status.success())
            .map(|result| String::from_utf8_lossy(&result.stdout).trim().to_owned())
    }).unwrap_or_else(|| "unknown".to_owned());
    println!("cargo:rustc-env=ANGMOO_BUILD_COMMIT={source}");
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
