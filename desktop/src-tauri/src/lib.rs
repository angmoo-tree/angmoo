mod phone_resize;
mod product_windows;
mod window_policy;

use product_windows::{ProductWindowKind, current_window, open_product_window_impl};
use tauri::{Manager, WebviewWindow};

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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let phone = app
                .get_webview_window("main")
                .ok_or("configured phone window is missing")?;
            window_policy::apply_phone_window_policy(&phone)?;
            phone_resize::install_phone_aspect_ratio_lock(&phone)?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            open_product_window,
            minimize_product_window,
            close_product_window,
            start_product_window_drag,
        ])
        .run(tauri::generate_context!())
        .expect("error while running Angmoo Tauri product shell");
}
