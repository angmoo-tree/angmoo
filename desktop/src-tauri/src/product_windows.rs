use serde::Serialize;
use tauri::{AppHandle, Manager, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum ProductWindowKind {
    Phone,
    Studio,
    RelationshipGraph,
}

impl ProductWindowKind {
    pub fn parse(value: &str) -> Result<Self, String> {
        match value {
            "phone" => Ok(Self::Phone),
            "studio" => Ok(Self::Studio),
            "relationship-graph" => Ok(Self::RelationshipGraph),
            _ => Err("unsupported_product_window_kind".to_owned()),
        }
    }

    fn label(self) -> &'static str {
        match self {
            Self::Phone => "main",
            Self::Studio => "studio",
            Self::RelationshipGraph => "relationship-graph",
        }
    }

    fn title(self) -> &'static str {
        match self {
            Self::Phone => "Angmoo",
            Self::Studio => "Angmoo Creator Studio",
            Self::RelationshipGraph => "Angmoo Relationship Graph",
        }
    }
}

pub fn validate_product_route(kind: ProductWindowKind, route: &str) -> Result<String, String> {
    if route.len() > 1024 || !route.starts_with('/') || route.contains(['\\', '\0']) {
        return Err("invalid_product_route".to_owned());
    }
    let parsed = tauri::Url::parse(&format!("http://angmoo.local{route}"))
        .map_err(|_| "invalid_product_route".to_owned())?;
    if parsed.fragment().is_some() {
        return Err("product_route_fragment_not_allowed".to_owned());
    }
    let path = parsed.path();
    let segments = path
        .split('/')
        .filter(|segment| !segment.is_empty())
        .collect::<Vec<_>>();
    let path_matches = match kind {
        ProductWindowKind::Phone => phone_path_matches(&segments),
        ProductWindowKind::Studio => studio_path_matches(&segments),
        ProductWindowKind::RelationshipGraph => relationship_path_matches(&segments),
    };
    if !path_matches {
        return Err("product_route_outside_window_boundary".to_owned());
    }
    if kind == ProductWindowKind::RelationshipGraph {
        for (key, value) in parsed.query_pairs() {
            if key != "provider" || !matches!(value.as_ref(), "neo4j" | "ladybug") {
                return Err("invalid_relationship_graph_query".to_owned());
            }
        }
    }
    Ok(route.to_owned())
}

fn phone_path_matches(segments: &[&str]) -> bool {
    match segments {
        [] => true,
        ["settings"] | ["login"] | ["posts"] => true,
        ["posts", id] | ["agents", id] => safe_segment(id),
        ["worlds", world_id] => safe_segment(world_id),
        ["worlds", world_id, section] => {
            safe_segment(world_id)
                && matches!(*section, "feed" | "chat" | "characters" | "relationships")
        }
        [
            "characters",
            character_id,
            "worlds",
            world_id,
            "autonomy-setup",
        ] => safe_segment(character_id) && safe_segment(world_id),
        _ => false,
    }
}

fn studio_path_matches(segments: &[&str]) -> bool {
    match segments {
        ["studio"] | ["studio", "import"] | ["studio", "worlds", "new"] => true,
        ["studio", "worlds", world_id] => safe_segment(world_id),
        _ => false,
    }
}

fn relationship_path_matches(segments: &[&str]) -> bool {
    matches!(
        segments,
        ["characters", character_id, "worlds", world_id, "relationship-graph"]
            if safe_segment(character_id) && safe_segment(world_id)
    )
}

fn safe_segment(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 255
        && value != "."
        && value != ".."
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'%' | b'.'))
}

fn initial_state_script(kind: ProductWindowKind, route: &str) -> Result<String, String> {
    let kind = serde_json::to_string(&kind).map_err(|_| "window_state_encode_failed")?;
    let route = serde_json::to_string(route).map_err(|_| "window_state_encode_failed")?;
    Ok(format!(
        "window.__ANGMOO_DESKTOP_WINDOW__={{kind:{kind},route:{route}}};"
    ))
}

fn navigation_script(kind: ProductWindowKind, route: &str) -> Result<String, String> {
    Ok(format!(
        "{}window.dispatchEvent(new Event('angmoo:desktop-route'));",
        initial_state_script(kind, route)?
    ))
}

fn window_url(app: &AppHandle, route: &str) -> Result<WebviewUrl, String> {
    if tauri::is_dev() {
        let base = app
            .config()
            .build
            .dev_url
            .as_ref()
            .ok_or_else(|| "tauri_dev_url_missing".to_owned())?;
        let url = base
            .join(route.trim_start_matches('/'))
            .map_err(|_| "tauri_dev_route_invalid".to_owned())?;
        Ok(WebviewUrl::External(url))
    } else {
        Ok(WebviewUrl::App("index.html".into()))
    }
}

fn configure_wide_window(
    builder: WebviewWindowBuilder<'_, tauri::Wry, AppHandle<tauri::Wry>>,
    kind: ProductWindowKind,
) -> WebviewWindowBuilder<'_, tauri::Wry, AppHandle<tauri::Wry>> {
    match kind {
        ProductWindowKind::Studio => builder
            .inner_size(1280.0, 820.0)
            .min_inner_size(980.0, 680.0),
        ProductWindowKind::RelationshipGraph => builder
            .inner_size(1180.0, 780.0)
            .min_inner_size(900.0, 620.0),
        ProductWindowKind::Phone => builder,
    }
}

pub async fn open_product_window_impl(
    app: AppHandle,
    kind: ProductWindowKind,
    route: String,
) -> Result<(), String> {
    let route = validate_product_route(kind, &route)?;
    if let Some(window) = app.get_webview_window(kind.label()) {
        window
            .eval(navigation_script(kind, &route)?)
            .map_err(|error| error.to_string())?;
        window.unminimize().map_err(|error| error.to_string())?;
        window.show().map_err(|error| error.to_string())?;
        window.set_focus().map_err(|error| error.to_string())?;
        return Ok(());
    }
    if kind == ProductWindowKind::Phone {
        return Err("phone_window_missing".to_owned());
    }

    let builder = WebviewWindowBuilder::new(&app, kind.label(), window_url(&app, &route)?)
        .title(kind.title())
        .decorations(false)
        .resizable(true)
        .maximizable(true)
        .shadow(true)
        .center()
        .initialization_script(initial_state_script(kind, &route)?);
    configure_wide_window(builder, kind)
        .build()
        .map_err(|error| error.to_string())?;
    Ok(())
}

pub fn current_window(window: &WebviewWindow) -> &WebviewWindow {
    window
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn product_routes_stay_inside_their_window_boundaries() {
        assert!(validate_product_route(ProductWindowKind::Phone, "/").is_ok());
        assert!(validate_product_route(ProductWindowKind::Phone, "/worlds/world-1/feed").is_ok());
        assert!(
            validate_product_route(ProductWindowKind::Studio, "/studio/worlds/world-1").is_ok()
        );
        assert!(
            validate_product_route(
                ProductWindowKind::RelationshipGraph,
                "/characters/mango/worlds/arcana/relationship-graph?provider=ladybug"
            )
            .is_ok()
        );
        assert!(validate_product_route(ProductWindowKind::Phone, "/studio").is_err());
        assert!(validate_product_route(ProductWindowKind::Studio, "/worlds/world-1").is_err());
        assert!(
            validate_product_route(
                ProductWindowKind::RelationshipGraph,
                "/characters/mango/worlds/arcana/relationship-graph?provider=remote"
            )
            .is_err()
        );
    }

    #[test]
    fn route_validation_rejects_external_and_traversal_inputs() {
        for route in [
            "https://example.com/studio",
            "/studio/../settings",
            "/studio\\worlds\\foreign",
            "/studio#unsafe",
        ] {
            assert!(validate_product_route(ProductWindowKind::Studio, route).is_err());
        }
    }

    #[test]
    fn generated_state_script_is_json_escaped() {
        let script = initial_state_script(ProductWindowKind::Studio, "/studio/worlds/world-1")
            .expect("state script");
        assert!(script.contains("kind:\"studio\""));
        assert!(script.contains("route:\"/studio/worlds/world-1\""));
    }
}
