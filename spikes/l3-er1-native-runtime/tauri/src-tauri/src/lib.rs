use serde::{Deserialize, Serialize};
use std::{
    env, fs,
    io::{Read, Write},
    net::TcpStream,
    path::PathBuf,
    process,
    time::{Duration, Instant},
};
use tauri::{Manager, RunEvent};
use tauri_plugin_shell::{ShellExt, process::CommandEvent};
use uuid::Uuid;

#[derive(Debug, Deserialize)]
struct ReadyEvent {
    event: String,
    host: String,
    port: u16,
}

#[derive(Debug, Serialize)]
struct RuntimeEvidence {
    schema_version: u8,
    status: &'static str,
    dynamic_loopback: bool,
    unauthenticated_rejected: bool,
    authenticated_health: bool,
    packaged_ladybug: bool,
    graceful_shutdown_requested: bool,
    parent_watchdog_enabled: bool,
    startup_ms: u128,
}

fn http_request(
    port: u16,
    method: &str,
    path: &str,
    token: Option<&str>,
) -> std::io::Result<String> {
    let mut stream = TcpStream::connect_timeout(
        &format!("127.0.0.1:{port}")
            .parse()
            .expect("valid loopback address"),
        Duration::from_secs(3),
    )?;
    stream.set_read_timeout(Some(Duration::from_secs(3)))?;
    let auth = token
        .map(|value| format!("X-Angmoo-Spike-Token: {value}\r\n"))
        .unwrap_or_default();
    let request = format!(
        "{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n{auth}Connection: close\r\nContent-Length: 0\r\n\r\n"
    );
    stream.write_all(request.as_bytes())?;
    let mut response = String::new();
    stream.read_to_string(&mut response)?;
    Ok(response)
}

fn status_is(response: &str, status: &str) -> bool {
    response
        .lines()
        .next()
        .is_some_and(|line| line.contains(status))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let started = Instant::now();
            let token = Uuid::new_v4().simple().to_string();
            let data_root = app.path().app_local_data_dir()?.join("한글 공백 spike");
            fs::create_dir_all(&data_root)?;
            let lock_path = data_root.join("sidecar.writer.lock");
            let graph_path = data_root.join("sidecar-graph.lbdb");
            let parent_pid = process::id().to_string();
            let lock_argument = lock_path.to_string_lossy().into_owned();
            let graph_argument = graph_path.to_string_lossy().into_owned();
            let command = app.shell().sidecar("angmoo-spike-sidecar")?.args(vec![
                "--auth-token".to_owned(),
                token.clone(),
                "--parent-pid".to_owned(),
                parent_pid,
                "--lock-file".to_owned(),
                lock_argument,
                "--graph-path".to_owned(),
                graph_argument,
            ]);
            let (mut receiver, child) = command.spawn()?;
            let app_handle = app.handle().clone();
            let evidence_path = env::var_os("ANGMOO_SPIKE_EVIDENCE").map(PathBuf::from);

            tauri::async_runtime::spawn(async move {
                let ready = loop {
                    match receiver.recv().await {
                        Some(CommandEvent::Stdout(bytes)) => {
                            let line = String::from_utf8_lossy(&bytes);
                            if let Ok(event) = serde_json::from_str::<ReadyEvent>(line.trim())
                                && event.event == "ready"
                            {
                                break Some(event);
                            }
                        }
                        Some(CommandEvent::Terminated(_)) | None => break None,
                        _ => {}
                    }
                };

                let mut evidence = RuntimeEvidence {
                    schema_version: 1,
                    status: "FAIL",
                    dynamic_loopback: false,
                    unauthenticated_rejected: false,
                    authenticated_health: false,
                    packaged_ladybug: false,
                    graceful_shutdown_requested: false,
                    parent_watchdog_enabled: true,
                    startup_ms: started.elapsed().as_millis(),
                };
                if let Some(ready) = ready {
                    evidence.dynamic_loopback = ready.host == "127.0.0.1" && ready.port != 0;
                    for _ in 0..30 {
                        if let Ok(response) =
                            http_request(ready.port, "GET", "/health", Some(&token))
                            && status_is(&response, "200")
                        {
                            evidence.authenticated_health = true;
                            break;
                        }
                        std::thread::sleep(Duration::from_millis(100));
                    }
                    if let Ok(response) = http_request(ready.port, "GET", "/health", None) {
                        evidence.unauthenticated_rejected = status_is(&response, "401");
                    }
                    if let Ok(response) =
                        http_request(ready.port, "GET", "/graph-proof", Some(&token))
                    {
                        evidence.packaged_ladybug = status_is(&response, "200")
                            && response.contains("\"embedded_graph\":true");
                    }
                    if let Ok(response) =
                        http_request(ready.port, "POST", "/shutdown", Some(&token))
                    {
                        evidence.graceful_shutdown_requested = status_is(&response, "200");
                    }
                }
                evidence.startup_ms = started.elapsed().as_millis();
                evidence.status = if evidence.dynamic_loopback
                    && evidence.unauthenticated_rejected
                    && evidence.authenticated_health
                    && evidence.packaged_ladybug
                    && evidence.graceful_shutdown_requested
                {
                    "PASS"
                } else {
                    "FAIL"
                };
                if let Some(path) = evidence_path {
                    if let Some(parent) = path.parent() {
                        let _ = fs::create_dir_all(parent);
                    }
                    if let Ok(rendered) = serde_json::to_string_pretty(&evidence) {
                        let _ = fs::write(path, format!("{rendered}\n"));
                    }
                }
                std::thread::sleep(Duration::from_millis(500));
                let _ = child.kill();
                app_handle.exit(if evidence.status == "PASS" { 0 } else { 1 });
            });
            Ok(())
        });

    builder
        .build(tauri::generate_context!())
        .expect("error while building Tauri spike")
        .run(|_app, event| {
            if let RunEvent::ExitRequested { .. } = event {
                // The sidecar also watches this process ID and exits if Tauri is
                // terminated before the authenticated shutdown completes.
            }
        });
}
