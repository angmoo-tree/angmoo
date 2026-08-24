mod desktop_runtime;
mod launch_mode;
mod phone_resize;
mod product_paths;
mod product_windows;
mod window_policy;

use product_windows::{
    ProductWindowKind, create_phone_window, current_window, open_product_window_impl,
};
use tauri::{Manager, WebviewWindow, Window};
use tauri_runtime::ResizeDirection;

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
fn minimize_product_window(window: WebviewWindow) -> Result<(), String> {
    current_window(&window)
        .minimize()
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn close_product_window(window: WebviewWindow) -> Result<(), String> {
    current_window(&window)
        .close()
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn start_product_window_drag(window: WebviewWindow) -> Result<(), String> {
    current_window(&window)
        .start_dragging()
        .map_err(|error| error.to_string())
}

fn parse_phone_resize_direction(value: &str) -> Result<ResizeDirection, String> {
    match value {
        "east" => Ok(ResizeDirection::East),
        "north" => Ok(ResizeDirection::North),
        "north-east" => Ok(ResizeDirection::NorthEast),
        "north-west" => Ok(ResizeDirection::NorthWest),
        "south" => Ok(ResizeDirection::South),
        "south-east" => Ok(ResizeDirection::SouthEast),
        "south-west" => Ok(ResizeDirection::SouthWest),
        "west" => Ok(ResizeDirection::West),
        _ => Err("unsupported_phone_resize_direction".to_owned()),
    }
}

#[tauri::command]
fn start_product_window_resize(window: Window, direction: String) -> Result<(), String> {
    if window.label() != "main" {
        return Err("phone_resize_only".to_owned());
    }
    window
        .start_resize_dragging(parse_phone_resize_direction(&direction)?)
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
        .manage(launch_mode)
        .manage(desktop_runtime::DesktopRuntimeState::default())
        .setup(|app| {
            let launch_mode = *app.state::<launch_mode::DesktopLaunchMode>();
            let product_paths = product_paths::ProductDataPaths::resolve(app.handle())?;
            if launch_mode.is_contributor_docker_bridge() {
                product_paths.prepare_contributor_bridge_directory()?;
            } else {
                product_paths.prepare_runtime_owned_directories()?;
            }
            let phone = create_phone_window(app.handle(), &product_paths)?;
            window_policy::apply_phone_window_policy(&phone)?;
            phone_resize::install_phone_aspect_ratio_lock(&phone)?;
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
            minimize_product_window,
            close_product_window,
            start_product_window_drag,
            start_product_window_resize,
            desktop_runtime_status,
            retry_desktop_runtime,
        ])
        .build(tauri::generate_context!())
        .expect("error while building Angmoo Tauri product shell")
        .run(|app, event| {
            if matches!(
                event,
                tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit
            ) {
                desktop_runtime::shutdown(&app.state::<desktop_runtime::DesktopRuntimeState>());
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn phone_resize_command_accepts_only_the_eight_native_directions() {
        let accepted = [
            ("east", ResizeDirection::East),
            ("north", ResizeDirection::North),
            ("north-east", ResizeDirection::NorthEast),
            ("north-west", ResizeDirection::NorthWest),
            ("south", ResizeDirection::South),
            ("south-east", ResizeDirection::SouthEast),
            ("south-west", ResizeDirection::SouthWest),
            ("west", ResizeDirection::West),
        ];
        for (value, expected) in accepted {
            assert_eq!(parse_phone_resize_direction(value), Ok(expected));
        }
        assert_eq!(
            parse_phone_resize_direction("maximize"),
            Err("unsupported_phone_resize_direction".to_owned())
        );
    }
}
