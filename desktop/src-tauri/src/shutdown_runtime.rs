//! Non-blocking whole-application exit. Child-window close is not a trigger.
use serde::Serialize;
use std::sync::{
    Mutex,
    atomic::{AtomicBool, Ordering},
};
use std::time::{Duration, Instant};
use tauri::Manager;

use crate::desktop_runtime::{self, DesktopRuntimeState};

#[derive(Clone, Serialize)]
pub struct ShutdownStatus {
    phase: &'static str,
    deferred: bool,
}

pub struct DesktopShutdownState {
    started: AtomicBool,
    finished: AtomicBool,
    skip: AtomicBool,
    status: Mutex<ShutdownStatus>,
}

impl Default for DesktopShutdownState {
    fn default() -> Self {
        Self {
            started: AtomicBool::new(false),
            finished: AtomicBool::new(false),
            skip: AtomicBool::new(false),
            status: Mutex::new(ShutdownStatus {
                phase: "RUNNING",
                deferred: false,
            }),
        }
    }
}

impl DesktopShutdownState {
    pub fn finished(&self) -> bool {
        self.finished.load(Ordering::SeqCst)
    }
    pub fn skip(&self) {
        self.skip.store(true, Ordering::SeqCst);
    }
    pub fn status(&self) -> Result<ShutdownStatus, String> {
        self.status
            .lock()
            .map(|value| value.clone())
            .map_err(|_| "desktop_shutdown_unavailable".to_owned())
    }
    fn set(&self, phase: &'static str, deferred: bool) {
        if let Ok(mut state) = self.status.lock() {
            *state = ShutdownStatus { phase, deferred };
        }
    }
}

fn safe_phase(value: Option<&str>) -> &'static str {
    match value {
        Some("QUIESCING") => "QUIESCING",
        Some("PREPARING") => "PREPARING",
        Some("CONSOLIDATING") => "CONSOLIDATING",
        Some("FINALIZING") => "FINALIZING",
        Some("EXIT_READY") => "EXIT_READY",
        _ => "PREPARING",
    }
}

pub fn request_exit(app: tauri::AppHandle) {
    let state = app.state::<DesktopShutdownState>();
    if state.started.swap(true, Ordering::SeqCst) {
        return;
    }
    state.set("QUIESCING", false);
    std::thread::spawn(move || {
        let state = app.state::<DesktopShutdownState>();
        let runtime = app.state::<DesktopRuntimeState>();
        let started = Instant::now();
        let mut response = desktop_runtime::memory_shutdown_request(
            &runtime,
            "POST",
            "/__angmoo/desktop/prepare-shutdown",
        );
        let mut skip_sent = false;
        let mut skip_at = None;
        let mut deferred = response.is_none();
        while response.is_some() && started.elapsed() < Duration::from_secs(30) {
            if state.skip.load(Ordering::SeqCst) && !skip_sent {
                desktop_runtime::memory_shutdown_request(
                    &runtime,
                    "POST",
                    "/__angmoo/desktop/skip-memory-shutdown",
                );
                skip_sent = true;
                skip_at = Some(Instant::now());
                deferred = true;
            }
            let body = response.as_ref().expect("checked response");
            let phase = safe_phase(body.get("phase").and_then(|value| value.as_str()));
            deferred |= body
                .get("deferred")
                .and_then(|value| value.as_bool())
                .unwrap_or(false);
            state.set(phase, deferred);
            if phase == "EXIT_READY"
                || skip_at.is_some_and(|at| at.elapsed() >= Duration::from_secs(2))
            {
                break;
            }
            std::thread::sleep(Duration::from_millis(200));
            response = desktop_runtime::memory_shutdown_request(
                &runtime,
                "GET",
                "/__angmoo/desktop/shutdown-status",
            );
        }
        if started.elapsed() >= Duration::from_secs(30) || response.is_none() {
            deferred = true;
            desktop_runtime::memory_shutdown_request(
                &runtime,
                "POST",
                "/__angmoo/desktop/skip-memory-shutdown",
            );
        }
        state.set("FINALIZING", deferred);
        // The old eight-second finalizer runs only AFTER memory preparation.
        // It does not kill a contributor-owned Docker backend.
        desktop_runtime::shutdown(&runtime);
        state.set("EXIT_READY", deferred);
        state.finished.store(true, Ordering::SeqCst);
        app.exit(0);
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn diagnostics_are_closed_and_initial_state_does_not_exit() {
        let state = DesktopShutdownState::default();
        assert!(!state.finished());
        assert_eq!(state.status().unwrap().phase, "RUNNING");
        assert_eq!(safe_phase(Some("provider body secret")), "PREPARING");
        assert_eq!(safe_phase(Some("EXIT_READY")), "EXIT_READY");
        state.skip();
        assert!(!state.finished());
    }
}
