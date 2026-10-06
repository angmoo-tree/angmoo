mod desktop_runtime;
mod launch_mode;
mod product_paths;
mod product_windows;
mod shutdown_runtime;
mod window_policy;
mod world_package_delivery;

use product_windows::{
    ProductWindowKind, create_phone_window, current_window, open_product_window_impl,
};
use tauri::{Manager, WebviewWindow};

#[tauri::command]
fn desktop_shutdown_status(
    state: tauri::State<'_, shutdown_runtime::DesktopShutdownState>,
) -> Result<shutdown_runtime::ShutdownStatus, String> {
    state.status()
}

#[tauri::command]
fn skip_memory_shutdown(state: tauri::State<'_, shutdown_runtime::DesktopShutdownState>) {
    state.skip();
}

#[tauri::command]
fn desktop_runtime_status(
    state: tauri::State<'_, desktop_runtime::DesktopRuntimeState>,
) -> Result<desktop_runtime::DesktopRuntimeStatus, String> {
    desktop_runtime::status(&state)
}

#[tauri::command]
fn retry_desktop_runtime(
    app: tauri::AppHandle,
    state: tauri::State<'_, desktop_runtime::DesktopRuntimeState>,
    mode: tauri::State<'_, launch_mode::DesktopLaunchMode>,
) -> Result<(), String> {
    if mode.is_contributor_docker_bridge() {
        desktop_runtime::activate_contributor_bridge(&state)
    } else {
        desktop_runtime::retry(app, &state)
    }
}

#[tauri::command]
async fn open_product_window(
    app: tauri::AppHandle,
    kind: String,
    route: String,
) -> Result<(), String> {
    open_product_window_impl(app, ProductWindowKind::parse(&kind)?, route).await
}

#[tauri::command]
fn close_product_window(window: WebviewWindow) -> Result<(), String> {
    current_window(&window)
        .close()
        .map_err(|error| error.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let launch_mode = launch_mode::DesktopLaunchMode::current()
        .expect("invalid Angmoo desktop compile-time launch mode");
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _, _| {
            if let Some(phone) = app.get_webview_window("main") {
                let _ = phone.show();
                let _ = phone.set_focus();
            }
        }))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(launch_mode)
        .manage(desktop_runtime::DesktopRuntimeState::default())
        .manage(shutdown_runtime::DesktopShutdownState::default())
        .manage(world_package_delivery::WorldPackageDestinationState::default())
        .setup(|app| {
            let launch_mode = *app.state::<launch_mode::DesktopLaunchMode>();
            let product_paths = product_paths::ProductDataPaths::resolve(app.handle())?;
            if launch_mode.is_contributor_docker_bridge() {
                product_paths.prepare_contributor_bridge_directory()?;
            } else {
                product_paths.prepare_runtime_owned_directories()?;
            }
            let phone = create_phone_window(app.handle(), &product_paths)?;
            window_policy::apply_product_window_policy(
                &phone,
                window_policy::MAIN_INITIAL_WIDTH,
                window_policy::MAIN_INITIAL_HEIGHT,
            )?;
            phone.show()?;
            if launch_mode.is_contributor_docker_bridge() {
                desktop_runtime::activate_contributor_bridge(
                    &app.state::<desktop_runtime::DesktopRuntimeState>(),
                )?;
            } else {
                desktop_runtime::start(
                    app.handle().clone(),
                    &app.state::<desktop_runtime::DesktopRuntimeState>(),
                )?;
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            open_product_window,
            close_product_window,
            product_windows::validate_product_navigation,
            product_windows::open_external_product_link,
            desktop_runtime_status,
            retry_desktop_runtime,
            desktop_shutdown_status,
            skip_memory_shutdown,
            world_package_delivery::select_world_package_export_destination,
            world_package_delivery::write_world_package_export_destination,
            world_package_delivery::discard_world_package_export_destination,
        ])
        .build(tauri::generate_context!())
        .expect("error while building Angmoo Tauri product shell")
        .run(|app, event| {
            let finished = app
                .state::<shutdown_runtime::DesktopShutdownState>()
                .finished();
            match event {
                tauri::RunEvent::WindowEvent {
                    label,
                    event: tauri::WindowEvent::CloseRequested { api, .. },
                    ..
                } if label == "main" && !finished => {
                    api.prevent_close();
                    shutdown_runtime::request_exit(app.clone());
                }
                tauri::RunEvent::ExitRequested { api, .. } if !finished => {
                    api.prevent_exit();
                    shutdown_runtime::request_exit(app.clone());
                }
                _ => {}
            }
        });
}
