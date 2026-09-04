use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::{Read, Write},
    net::{SocketAddr, TcpStream},
    path::PathBuf,
    process,
    sync::Mutex,
    time::Duration,
};
use tauri::{AppHandle, Manager};
use tauri_plugin_shell::{
    ShellExt,
    process::{CommandChild, CommandEvent},
};
use uuid::Uuid;

use crate::product_paths::ProductDataPaths;

const DESKTOP_ORIGIN: &str = "http://tauri.localhost";
const PRODUCT_GRAPH_PROVIDER: &str = "ladybug";
const HEALTH_FAILURE_LIMIT: u8 = 15;
// A cold PyInstaller one-file sidecar must unpack and import the full FastAPI
// graph before it can publish its endpoint.  On Windows with real-time
// Defender enabled that took about 20 seconds on the ER6 user machine, so the
// previous 12-second budget falsely declared a healthy sidecar crashed.
const ENDPOINT_READY_ATTEMPTS: usize = 600;

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct DesktopRuntimeStatus {
    phase: &'static str,
    runtime_mode: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    api_base_url: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    graph_provider: Option<&'static str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    launch_token: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    diagnostic_code: Option<&'static str>,
}

impl DesktopRuntimeStatus {
    fn starting() -> Self {
        Self {
            phase: "starting",
            runtime_mode: "installed-sidecar",
            api_base_url: None,
            graph_provider: None,
            launch_token: None,
            diagnostic_code: None,
        }
    }

    fn ready(port: u16, launch_token: String) -> Self {
        Self {
            phase: "ready",
            runtime_mode: "installed-sidecar",
            api_base_url: Some(format!("http://127.0.0.1:{port}")),
            graph_provider: Some(PRODUCT_GRAPH_PROVIDER),
            launch_token: Some(launch_token),
            diagnostic_code: None,
        }
    }

    fn crashed(code: &'static str) -> Self {
        Self {
            phase: "crashed",
            runtime_mode: "installed-sidecar",
            api_base_url: None,
            graph_provider: None,
            launch_token: None,
            diagnostic_code: Some(code),
        }
    }

    fn stopped() -> Self {
        Self {
            phase: "stopped",
            runtime_mode: "installed-sidecar",
            api_base_url: None,
            graph_provider: None,
            launch_token: None,
            diagnostic_code: None,
        }
    }

    fn contributor_bridge_ready() -> Self {
        Self {
            phase: "ready",
            runtime_mode: "contributor-docker-bridge",
            api_base_url: None,
            graph_provider: Some(PRODUCT_GRAPH_PROVIDER),
            launch_token: None,
            diagnostic_code: None,
        }
    }
}

struct PrivateRuntime {
    status: DesktopRuntimeStatus,
    child: Option<CommandChild>,
    generation: u64,
    runtime_root: Option<PathBuf>,
}

pub struct DesktopRuntimeState(Mutex<PrivateRuntime>);

impl Default for DesktopRuntimeState {
    fn default() -> Self {
        Self(Mutex::new(PrivateRuntime {
            status: DesktopRuntimeStatus::stopped(),
            child: None,
            generation: 0,
            runtime_root: None,
        }))
    }
}

#[derive(Debug, Deserialize, PartialEq, Eq)]
struct EndpointMetadata {
    schema_version: u8,
    logical_sidecar_pid: u32,
    host: String,
    dynamic_port: u16,
    generation: String,
}

#[derive(Debug, Deserialize)]
struct SidecarProcessEvent {
    event: String,
    code: String,
}

fn stable_sidecar_fatal_code(bytes: &[u8]) -> Option<&'static str> {
    let event: SidecarProcessEvent = serde_json::from_slice(bytes).ok()?;
    if event.event != "fatal" {
        return None;
    }
    match event.code.as_str() {
        "desktop_sidecar_schema_unsupported" => Some("desktop_sidecar_schema_unsupported"),
        "desktop_sidecar_already_owned" => Some("desktop_sidecar_already_owned"),
        "desktop_sidecar_data_migration_failed" => Some("desktop_sidecar_data_migration_failed"),
        "desktop_sidecar_startup_failed" => Some("desktop_sidecar_startup_failed"),
        _ => None,
    }
}

fn read_endpoint_metadata(
    endpoint_path: &std::path::Path,
    expected_generation: &str,
) -> Result<Option<EndpointMetadata>, &'static str> {
    let contents = match fs::read_to_string(endpoint_path) {
        Ok(contents) => contents,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(_) => return Err("desktop_sidecar_endpoint_unavailable"),
    };
    let endpoint: EndpointMetadata =
        serde_json::from_str(&contents).map_err(|_| "desktop_sidecar_endpoint_invalid")?;
    // A previous abnormal exit may leave valid metadata for an older launch.
    // It is not an invalid endpoint for the new child; wait for the current
    // generation to atomically replace it.  The launcher token health check
    // below still prevents a stale process from becoming ready.
    if endpoint.generation != expected_generation {
        return Ok(None);
    }
    if endpoint.schema_version != 1
        || endpoint.logical_sidecar_pid == 0
        || endpoint.host != "127.0.0.1"
        || endpoint.dynamic_port == 0
    {
        return Err("desktop_sidecar_endpoint_invalid");
    }
    Ok(Some(endpoint))
}

pub fn status(state: &DesktopRuntimeState) -> Result<DesktopRuntimeStatus, String> {
    state
        .0
        .lock()
        .map(|runtime| runtime.status.clone())
        .map_err(|_| "desktop_runtime_state_poisoned".to_owned())
}

pub fn activate_contributor_bridge(state: &DesktopRuntimeState) -> Result<(), String> {
    let mut runtime = state
        .0
        .lock()
        .map_err(|_| "desktop_runtime_state_poisoned".to_owned())?;
    if runtime.child.is_some() || runtime.runtime_root.is_some() {
        return Err("contributor_bridge_host_sidecar_forbidden".to_owned());
    }
    runtime.generation += 1;
    runtime.status = DesktopRuntimeStatus::contributor_bridge_ready();
    Ok(())
}

fn verify_packaged_sidecar() -> Result<(), String> {
    let expected = env!("ANGMOO_SIDECAR_SHA256");
    if expected.len() != 64 || !expected.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err("desktop_sidecar_hash_missing".to_owned());
    }
    let file_name = if cfg!(windows) {
        "angmoo-sidecar.exe"
    } else {
        "angmoo-sidecar"
    };
    let bundled = std::env::current_exe()
        .ok()
        .and_then(|path| path.parent().map(|parent| parent.join(file_name)));
    let source = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("binaries")
        .join(format!(
            "angmoo-sidecar-{}{}",
            env!("ANGMOO_TARGET_TRIPLE"),
            if cfg!(windows) { ".exe" } else { "" }
        ));
    let path = bundled
        .filter(|candidate| candidate.is_file())
        .unwrap_or(source);
    let bytes = fs::read(path).map_err(|_| "desktop_sidecar_missing".to_owned())?;
    let actual = format!("{:x}", Sha256::digest(bytes));
    if actual != expected {
        return Err("desktop_sidecar_hash_mismatch".to_owned());
    }
    Ok(())
}

fn http_request(port: u16, method: &str, path: &str, token: &str) -> std::io::Result<String> {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let mut stream = TcpStream::connect_timeout(&address, Duration::from_secs(2))?;
    stream.set_read_timeout(Some(Duration::from_secs(2)))?;
    let request = format!(
        "{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nOrigin: {DESKTOP_ORIGIN}\r\nX-Angmoo-Launcher-Token: {token}\r\nConnection: close\r\nContent-Length: 0\r\n\r\n"
    );
    stream.write_all(request.as_bytes())?;
    let mut response = String::new();
    stream.read_to_string(&mut response)?;
    Ok(response)
}

fn response_is_ok(response: &str) -> bool {
    response
        .lines()
        .next()
        .is_some_and(|line| line.contains(" 200 "))
}

pub fn memory_shutdown_request(
    state: &DesktopRuntimeState,
    method: &str,
    path: &str,
) -> Option<serde_json::Value> {
    let (port, token) = {
        let runtime = state.0.lock().ok()?;
        let port = runtime
            .status
            .api_base_url
            .as_deref()?
            .rsplit(':')
            .next()?
            .parse::<u16>()
            .ok()?;
        (port, runtime.status.launch_token.clone()?)
    };
    let response = http_request(port, method, path, &token).ok()?;
    if !response_is_ok(&response) {
        return None;
    }
    serde_json::from_str(response.split_once("\r\n\r\n")?.1).ok()
}

fn drain_sidecar_events(
    receiver: &mut tauri::async_runtime::Receiver<CommandEvent>,
    fatal_code: &mut Option<&'static str>,
) -> bool {
    let mut terminated = false;
    while let Ok(event) = receiver.try_recv() {
        match event {
            CommandEvent::Stderr(bytes) => {
                if let Some(code) = stable_sidecar_fatal_code(&bytes) {
                    *fatal_code = Some(code);
                }
            }
            CommandEvent::Terminated(_) => terminated = true,
            _ => {}
        }
    }
    terminated
}

fn health_failure_is_terminal(consecutive_failures: u8) -> bool {
    consecutive_failures >= HEALTH_FAILURE_LIMIT
}

pub fn start(app: AppHandle, state: &DesktopRuntimeState) -> Result<(), String> {
    verify_packaged_sidecar()?;
    let generation = {
        let mut runtime = state
            .0
            .lock()
            .map_err(|_| "desktop_runtime_state_poisoned")?;
        if matches!(runtime.status.phase, "starting" | "ready") {
            return Ok(());
        }
        runtime.generation += 1;
        runtime.status = DesktopRuntimeStatus::starting();
        runtime.child = None;
        runtime.runtime_root = None;
        runtime.generation
    };

    let token = Uuid::new_v4().simple().to_string();
    let launch_id = Uuid::new_v4().simple().to_string();
    let product_paths = ProductDataPaths::resolve(&app)?;
    product_paths.prepare_runtime_owned_directories()?;
    let legacy_data_root = product_paths.legacy_preview_root;
    let data_root = product_paths.root;
    let runtime_root = product_paths.runtime;
    let parent_pid = process::id().to_string();
    let data_root_argument = data_root.to_string_lossy().into_owned();
    let legacy_data_root_argument = legacy_data_root.to_string_lossy().into_owned();
    let runtime_root_argument = runtime_root.to_string_lossy().into_owned();
    let command = app
        .shell()
        .sidecar("angmoo-sidecar")
        .map_err(|_| "desktop_sidecar_command_invalid")?
        .args([
            "--parent-pid",
            &parent_pid,
            "--data-root",
            &data_root_argument,
            "--legacy-data-root",
            &legacy_data_root_argument,
            "--runtime-root",
            &runtime_root_argument,
            "--launch-id",
            &launch_id,
            "--runtime-profile",
            ProductDataPaths::runtime_profile(),
        ])
        .env("DESKTOP_LAUNCH_TOKEN", &token)
        .env("DESKTOP_ALLOWED_ORIGIN", DESKTOP_ORIGIN);
    let (mut receiver, child) = command
        .spawn()
        .map_err(|_| "desktop_sidecar_spawn_failed")?;
    {
        let mut runtime = state
            .0
            .lock()
            .map_err(|_| "desktop_runtime_state_poisoned")?;
        runtime.child = Some(child);
        runtime.runtime_root = Some(runtime_root.clone());
    }
    let endpoint_path = runtime_root.join("sidecar.endpoint.json");
    let app_handle = app.clone();
    tauri::async_runtime::spawn(async move {
        let managed = app_handle.state::<DesktopRuntimeState>();
        let mut ready: Option<EndpointMetadata> = None;
        let mut fatal_code: Option<&'static str> = None;
        for _ in 0..ENDPOINT_READY_ATTEMPTS {
            let terminated = drain_sidecar_events(&mut receiver, &mut fatal_code);
            match read_endpoint_metadata(&endpoint_path, &launch_id) {
                Ok(Some(endpoint)) => {
                    ready = Some(endpoint);
                    break;
                }
                Ok(None) => {}
                Err(code) => {
                    mark_crashed(&managed, generation, code);
                    return;
                }
            }
            if terminated && fatal_code.is_some() {
                break;
            }
            std::thread::sleep(Duration::from_millis(100));
        }
        let Some(ready) = ready else {
            mark_crashed(
                &managed,
                generation,
                fatal_code.unwrap_or("desktop_sidecar_startup_failed"),
            );
            return;
        };
        let mut healthy = false;
        for _ in 0..60 {
            if http_request(ready.dynamic_port, "GET", "/health", &token)
                .is_ok_and(|response| response_is_ok(&response))
            {
                healthy = true;
                break;
            }
            std::thread::sleep(Duration::from_millis(100));
        }
        if !healthy {
            mark_crashed(&managed, generation, "desktop_sidecar_health_timeout");
            return;
        }
        if let Ok(mut runtime) = managed.0.lock()
            && runtime.generation == generation
        {
            runtime.status = DesktopRuntimeStatus::ready(ready.dynamic_port, token.clone());
        }

        let mut consecutive_health_failures = 0_u8;
        loop {
            std::thread::sleep(Duration::from_secs(2));
            let current = managed
                .0
                .lock()
                .ok()
                .map(|runtime| (runtime.generation, runtime.status.phase));
            if current != Some((generation, "ready")) {
                break;
            }
            // PyInstaller's one-file bootloader may finish its wrapper process after
            // spawning the real server process. Keep draining stdout/stderr events so
            // the pipe cannot fill, but use the authenticated health endpoint as the
            // runtime liveness contract instead of the wrapper's termination event.
            let _ = drain_sidecar_events(&mut receiver, &mut fatal_code);
            if http_request(ready.dynamic_port, "GET", "/health", &token)
                .is_ok_and(|response| response_is_ok(&response))
            {
                consecutive_health_failures = 0;
                continue;
            }
            consecutive_health_failures = consecutive_health_failures.saturating_add(1);
            if health_failure_is_terminal(consecutive_health_failures) {
                mark_crashed(
                    &managed,
                    generation,
                    fatal_code.unwrap_or("desktop_sidecar_health_lost"),
                );
                break;
            }
        }
    });
    Ok(())
}

fn mark_crashed(state: &DesktopRuntimeState, generation: u64, code: &'static str) {
    let cleanup = if let Ok(mut runtime) = state.0.lock()
        && runtime.generation == generation
    {
        runtime.status = DesktopRuntimeStatus::crashed(code);
        Some((runtime.child.take(), runtime.runtime_root.take()))
    } else {
        None
    };
    if let Some((child, runtime_root)) = cleanup {
        if let Some(child) = child {
            let _ = child.kill();
        }
        if let Some(runtime_root) = runtime_root {
            cleanup_runtime_metadata(&runtime_root);
        }
    }
}

pub fn shutdown(state: &DesktopRuntimeState) {
    let (port, token, child, runtime_root) = if let Ok(mut runtime) = state.0.lock() {
        let port = runtime
            .status
            .api_base_url
            .as_deref()
            .and_then(|value| value.rsplit(':').next())
            .and_then(|value| value.parse::<u16>().ok());
        let token = runtime.status.launch_token.clone();
        runtime.generation += 1;
        runtime.status = DesktopRuntimeStatus::stopped();
        (
            port,
            token,
            runtime.child.take(),
            runtime.runtime_root.take(),
        )
    } else {
        (None, None, None, None)
    };
    let graceful_requested = if let (Some(port), Some(token)) = (port, token) {
        let _ = http_request(port, "POST", "/__angmoo/desktop/shutdown", &token);
        true
    } else {
        false
    };
    if let Some(child) = child {
        if graceful_requested && let Some(runtime_root) = runtime_root.as_ref() {
            let owner_path = runtime_root.join("sidecar.owner.json");
            let endpoint_path = runtime_root.join("sidecar.endpoint.json");
            for _ in 0..80 {
                if !owner_path.exists() && !endpoint_path.exists() {
                    return;
                }
                std::thread::sleep(Duration::from_millis(100));
            }
        }
        if !graceful_requested || runtime_root.is_some() {
            let _ = child.kill();
        }
    }
    if let Some(runtime_root) = runtime_root {
        cleanup_runtime_metadata(&runtime_root);
    }
}

fn cleanup_runtime_metadata(runtime_root: &std::path::Path) {
    let _ = fs::remove_file(runtime_root.join("sidecar.owner.json"));
    let _ = fs::remove_file(runtime_root.join("sidecar.endpoint.json"));
}

pub fn retry(app: AppHandle, state: &DesktopRuntimeState) -> Result<(), String> {
    shutdown(state);
    start(app, state)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn public_status_never_contains_sidecar_path_or_arbitrary_command() {
        let status = DesktopRuntimeStatus::ready(49152, "a".repeat(32));
        let json = serde_json::to_string(&status).unwrap();
        assert!(json.contains("http://127.0.0.1:49152"));
        assert!(json.contains(r#""graphProvider":"ladybug""#));
        assert!(json.contains(r#""runtimeMode":"installed-sidecar""#));
        assert!(!json.contains("sidecar.exe"));
        assert!(!json.contains("command"));
    }

    #[test]
    fn contributor_bridge_status_has_no_host_api_or_launch_token() {
        let state = DesktopRuntimeState::default();
        activate_contributor_bridge(&state).unwrap();
        let status = status(&state).unwrap();

        assert_eq!(status.phase, "ready");
        assert_eq!(status.runtime_mode, "contributor-docker-bridge");
        assert_eq!(status.graph_provider, Some("ladybug"));
        assert!(status.api_base_url.is_none());
        assert!(status.launch_token.is_none());
        let runtime = state.0.lock().unwrap();
        assert!(runtime.child.is_none());
        assert!(runtime.runtime_root.is_none());
    }

    #[test]
    fn stopped_and_crashed_statuses_do_not_retain_launch_token() {
        for status in [
            DesktopRuntimeStatus::stopped(),
            DesktopRuntimeStatus::crashed("sidecar_stopped"),
        ] {
            assert!(status.launch_token.is_none());
            assert!(status.api_base_url.is_none());
            assert!(status.graph_provider.is_none());
        }
    }

    #[test]
    fn runtime_metadata_cleanup_removes_only_owned_runtime_files() {
        let root = std::env::temp_dir().join(format!(
            "angmoo-er5-runtime-cleanup-{}",
            Uuid::new_v4().simple()
        ));
        fs::create_dir_all(&root).unwrap();
        fs::write(root.join("sidecar.owner.json"), "{}").unwrap();
        fs::write(root.join("sidecar.endpoint.json"), "{}").unwrap();
        fs::write(root.join("keep.txt"), "keep").unwrap();

        cleanup_runtime_metadata(&root);

        assert!(!root.join("sidecar.owner.json").exists());
        assert!(!root.join("sidecar.endpoint.json").exists());
        assert!(root.join("keep.txt").exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn transient_health_failures_do_not_stop_the_sidecar() {
        assert!(!health_failure_is_terminal(1));
        assert!(!health_failure_is_terminal(HEALTH_FAILURE_LIMIT - 1));
        assert!(health_failure_is_terminal(HEALTH_FAILURE_LIMIT));
    }

    #[test]
    fn endpoint_metadata_requires_current_generation_and_loopback() {
        let root =
            std::env::temp_dir().join(format!("angmoo-er6-endpoint-{}", Uuid::new_v4().simple()));
        fs::create_dir_all(&root).unwrap();
        let path = root.join("sidecar.endpoint.json");
        fs::write(
            &path,
            r#"{"schema_version":1,"logical_sidecar_pid":42,"host":"127.0.0.1","dynamic_port":49152,"generation":"launch-a"}"#,
        )
        .unwrap();

        let endpoint = read_endpoint_metadata(&path, "launch-a").unwrap().unwrap();
        assert_eq!(endpoint.dynamic_port, 49152);
        assert_eq!(read_endpoint_metadata(&path, "launch-b"), Ok(None));
        let contents = fs::read_to_string(&path).unwrap();
        assert!(!contents.contains("launch_token"));
        assert!(!contents.contains("APP_SECRET"));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn cold_windows_sidecar_has_at_least_a_sixty_second_endpoint_budget() {
        let attempts = std::hint::black_box(ENDPOINT_READY_ATTEMPTS);
        assert!(
            attempts * 100 >= 60_000,
            "the endpoint budget must cover one-file unpack and AV import overhead"
        );
    }

    #[test]
    fn sidecar_fatal_parser_accepts_only_stable_redacted_codes() {
        assert_eq!(
            stable_sidecar_fatal_code(
                br#"{"event":"fatal","code":"desktop_sidecar_schema_unsupported"}"#
            ),
            Some("desktop_sidecar_schema_unsupported")
        );
        assert_eq!(
            stable_sidecar_fatal_code(br#"{"event":"fatal","code":"C:\\private\\angmoo.sqlite3"}"#),
            None
        );
        assert_eq!(stable_sidecar_fatal_code(b"not-json"), None);
    }
}
