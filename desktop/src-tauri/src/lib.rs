mod desktop_runtime;
mod phone_resize;
mod product_windows;
mod window_policy;

use product_windows::{ProductWindowKind, current_window, open_product_window_impl};
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
) -> Result<(), String> {
    desktop_runtime::retry(app, &state)
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
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _, _| {
            if let Some(phone) = app.get_webview_window("main") {
                let _ = phone.show();
                let _ = phone.set_focus();
            }
        }))
        .plugin(tauri_plugin_shell::init())
        .manage(desktop_runtime::DesktopRuntimeState::default())
        .setup(|app| {
            let phone = app
                .get_webview_window("main")
                .ok_or("configured phone window is missing")?;
            window_policy::apply_phone_window_policy(&phone)?;
            phone_resize::install_phone_aspect_ratio_lock(&phone)?;
            desktop_runtime::start(
                app.handle().clone(),
                &app.state::<desktop_runtime::DesktopRuntimeState>(),
            )?;
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
