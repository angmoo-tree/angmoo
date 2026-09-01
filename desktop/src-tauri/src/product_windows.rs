use serde::Serialize;
use std::path::PathBuf;
use tauri::{AppHandle, Manager, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

use crate::product_paths::ProductDataPaths;

const WINDOW_KIND_QUERY: &str = "__angmoo_window_kind";
const WINDOW_ROUTE_QUERY: &str = "__angmoo_window_route";

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

    fn bootstrap_kind(self) -> &'static str {
        match self {
            Self::Phone => "phone",
            Self::Studio => "studio",
            Self::RelationshipGraph => "relationship-graph",
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
            if key != "provider" || value != "ladybug" {
                return Err("invalid_relationship_graph_query".to_owned());
            }
        }
    }
    Ok(route.to_owned())
}

fn phone_path_matches(segments: &[&str]) -> bool {
    match segments {
        [] => true,
        ["settings"] | ["login"] | ["posts"] | ["agents"] => true,
        ["posts", id] | ["agents", id] => safe_segment(id),
        ["worlds", world_id] => safe_world_id(world_id),
        ["worlds", world_id, section] => {
            safe_world_id(world_id)
                && matches!(*section, "feed" | "chat" | "characters" | "relationships")
        }
        ["worlds", world_id, "chat", thread_id] => {
            safe_world_id(world_id) && safe_segment(thread_id)
        }
        ["worlds", world_id, "posts", post_id] => safe_world_id(world_id) && safe_segment(post_id),
        [
            "characters",
            character_id,
            "worlds",
            world_id,
            "autonomy-setup",
        ] => safe_segment(character_id) && safe_world_id(world_id),
        _ => false,
    }
}

fn studio_path_matches(segments: &[&str]) -> bool {
    match segments {
        ["studio"] | ["studio", "import"] | ["studio", "worlds", "new"] => true,
        ["studio", "worlds", world_id] => safe_world_id(world_id),
        _ => false,
    }
}

fn relationship_path_matches(segments: &[&str]) -> bool {
    matches!(
        segments,
        ["characters", character_id, "worlds", world_id, "relationship-graph"]
            if safe_segment(character_id) && safe_world_id(world_id)
    )
}

fn safe_world_id(value: &str) -> bool {
    value != "new" && safe_segment(value)
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

fn static_window_path(kind: ProductWindowKind, route: &str) -> Result<PathBuf, String> {
    let mut bootstrap = tauri::Url::parse("http://angmoo.local/index.html")
        .map_err(|_| "window_bootstrap_url_invalid".to_owned())?;
    bootstrap
        .query_pairs_mut()
        .append_pair(WINDOW_KIND_QUERY, kind.bootstrap_kind())
        .append_pair(WINDOW_ROUTE_QUERY, route);
    let query = bootstrap
        .query()
        .ok_or_else(|| "window_bootstrap_query_missing".to_owned())?;
    Ok(format!("index.html?{query}").into())
}

fn window_url(app: &AppHandle, kind: ProductWindowKind, route: &str) -> Result<WebviewUrl, String> {
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
        // The initialization script is the primary document-start contract.
        // Keep an encoded copy in the app URL as a recovery channel because a
        // real WebView can hydrate before that global becomes observable.
        Ok(WebviewUrl::App(static_window_path(kind, route)?))
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

fn configure_product_webview_data_directory<'a>(
    builder: WebviewWindowBuilder<'a, tauri::Wry, AppHandle<tauri::Wry>>,
    paths: &ProductDataPaths,
) -> WebviewWindowBuilder<'a, tauri::Wry, AppHandle<tauri::Wry>> {
    #[cfg(windows)]
    {
        builder.data_directory(paths.webview.clone())
    }
    #[cfg(not(windows))]
    {
        let _ = paths;
        builder
    }
}

pub fn create_phone_window(
    app: &AppHandle,
    paths: &ProductDataPaths,
) -> Result<WebviewWindow, String> {
    let builder = WebviewWindowBuilder::new(
        app,
        ProductWindowKind::Phone.label(),
        window_url(app, ProductWindowKind::Phone, "/")?,
    )
    .title(ProductWindowKind::Phone.title())
    .inner_size(468.0, 916.0)
    .decorations(false)
    .transparent(true)
    .resizable(true)
    .maximizable(false)
    .shadow(false)
    .center()
    .initialization_script(initial_state_script(ProductWindowKind::Phone, "/")?);
    configure_product_webview_data_directory(builder, paths)
        .build()
        .map_err(|error| error.to_string())
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

    let product_paths = ProductDataPaths::resolve(&app)?;

    let builder = WebviewWindowBuilder::new(&app, kind.label(), window_url(&app, kind, &route)?)
        .title(kind.title())
        .decorations(false)
        .resizable(true)
        .maximizable(true)
        .shadow(true)
        .center()
        .initialization_script(initial_state_script(kind, &route)?);
    let builder = configure_product_webview_data_directory(builder, &product_paths);
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
        assert!(validate_product_route(ProductWindowKind::Phone, "/agents").is_ok());
        assert!(validate_product_route(ProductWindowKind::Phone, "/worlds/world-1/feed").is_ok());
        assert!(
            validate_product_route(ProductWindowKind::Phone, "/worlds/world-1/chat/thread-1")
                .is_ok()
        );
        assert!(
            validate_product_route(
                ProductWindowKind::Phone,
                "/worlds/world-1/posts/post-1?returnTo=%2Fworlds%2Fworld-1%2Ffeed"
            )
            .is_ok()
        );
        assert!(
            validate_product_route(ProductWindowKind::Studio, "/studio/worlds/world-1").is_ok()
        );
        assert!(
            validate_product_route(
                ProductWindowKind::Studio,
                "/studio/worlds/world-1?createdCharacterId=char-1"
            )
            .is_ok()
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
                ProductWindowKind::Phone,
                "/characters/mango/worlds/arcana/relationship-graph?provider=ladybug"
            )
            .is_err()
        );
        assert!(
            validate_product_route(
                ProductWindowKind::RelationshipGraph,
                "/characters/mango/worlds/arcana/relationship-graph?provider=remote"
            )
            .is_err()
        );
    }

    #[test]
    fn world_creation_alias_never_becomes_a_phone_world_id() {
        for route in [
            "/worlds/new",
            "/worlds/new/feed",
            "/worlds/new/posts/post-1",
            "/worlds/new/chat/thread-1",
            "/characters/mango/worlds/new/autonomy-setup",
        ] {
            assert!(validate_product_route(ProductWindowKind::Phone, route).is_err());
        }

        assert!(validate_product_route(ProductWindowKind::Studio, "/studio/worlds/new").is_ok());
        assert!(
            validate_product_route(
                ProductWindowKind::RelationshipGraph,
                "/characters/mango/worlds/new/relationship-graph?provider=ladybug"
            )
            .is_err()
        );
    }

    #[test]
    fn relationship_graph_provider_is_ladybug_only() {
        let route = "/characters/mango/worlds/arcana/relationship-graph";
        assert!(validate_product_route(ProductWindowKind::RelationshipGraph, route).is_ok());
        assert!(
            validate_product_route(
                ProductWindowKind::RelationshipGraph,
                &format!("{route}?provider=ladybug")
            )
            .is_ok()
        );

        for provider in ["neo4j", "remote"] {
            assert_eq!(
                validate_product_route(
                    ProductWindowKind::RelationshipGraph,
                    &format!("{route}?provider={provider}")
                ),
                Err("invalid_relationship_graph_query".to_owned())
            );
        }
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

    #[test]
    fn static_window_path_carries_the_exact_kind_and_route() {
        let path = static_window_path(
            ProductWindowKind::RelationshipGraph,
            "/characters/mango/worlds/arcana/relationship-graph?provider=ladybug",
        )
        .expect("static window path");
        let parsed = tauri::Url::parse(&format!("http://angmoo.local/{}", path.to_string_lossy()))
            .expect("parse static window path");
        let query = parsed
            .query_pairs()
            .collect::<std::collections::HashMap<_, _>>();

        assert_eq!(
            query.get(WINDOW_KIND_QUERY).map(|value| value.as_ref()),
            Some("relationship-graph")
        );
        assert_eq!(
            query.get(WINDOW_ROUTE_QUERY).map(|value| value.as_ref()),
            Some("/characters/mango/worlds/arcana/relationship-graph?provider=ladybug")
        );
    }

    #[test]
    fn phone_static_window_bootstraps_the_logical_phone_home() {
        let path =
            static_window_path(ProductWindowKind::Phone, "/").expect("phone static window path");
        let parsed = tauri::Url::parse(&format!("http://angmoo.local/{}", path.to_string_lossy()))
            .expect("parse phone static window path");
        let query = parsed
            .query_pairs()
            .collect::<std::collections::HashMap<_, _>>();

        assert_eq!(
            query.get(WINDOW_KIND_QUERY).map(|value| value.as_ref()),
            Some("phone")
        );
        assert_eq!(
            query.get(WINDOW_ROUTE_QUERY).map(|value| value.as_ref()),
            Some("/")
        );
    }
}
