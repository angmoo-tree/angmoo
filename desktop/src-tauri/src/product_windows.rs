use serde::Serialize;
use std::path::PathBuf;
use tauri::{AppHandle, Manager, WebviewUrl, WebviewWindow, WebviewWindowBuilder};
use tauri_plugin_shell::ShellExt;

use crate::product_paths::ProductDataPaths;

const WINDOW_KIND_QUERY: &str = "__angmoo_window_kind";
const WINDOW_ROUTE_QUERY: &str = "__angmoo_window_route";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum ProductWindowKind {
    Memory,
    Phone,
    Studio,
    RelationshipGraph,
}

impl ProductWindowKind {
    pub fn parse(value: &str) -> Result<Self, String> {
        match value {
            "memory" => Ok(Self::Memory),
            "phone" => Ok(Self::Phone),
            "studio" => Ok(Self::Studio),
            "relationship-graph" => Ok(Self::RelationshipGraph),
            _ => Err("unsupported_product_window_kind".to_owned()),
        }
    }

    fn label(self) -> &'static str {
        match self {
            Self::Memory => "memory",
            Self::Phone => "main",
            Self::Studio => "studio",
            Self::RelationshipGraph => "relationship-graph",
        }
    }

    fn title(self) -> &'static str {
        match self {
            Self::Memory => "Angmoo Memory",
            Self::Phone => "Angmoo",
            Self::Studio => "Angmoo Creator Studio",
            Self::RelationshipGraph => "Angmoo Relationship Graph",
        }
    }

    fn bootstrap_kind(self) -> &'static str {
        match self {
            Self::Memory => "memory",
            Self::Phone => "phone",
            Self::Studio => "studio",
            Self::RelationshipGraph => "relationship-graph",
        }
    }
}

pub fn validate_product_route(kind: ProductWindowKind, route: &str) -> Result<String, String> {
    if route.len() > 1024
        || !route.starts_with('/')
        || route.contains(['\\', '\0'])
        || route.starts_with("//")
        || route.chars().any(char::is_control)
    {
        return Err("invalid_product_route".to_owned());
    }
    let raw_path = route.split(['?', '#']).next().unwrap_or("");
    for segment in raw_path.split('/') {
        let decoded = decode_route_segment(segment)?;
        if decoded == "."
            || decoded == ".."
            || decoded.contains(['/', '\\'])
            || decoded.chars().any(char::is_control)
        {
            return Err("invalid_product_route_segment".to_owned());
        }
    }
    if route.contains("__angmoo_") {
        return Err("private_product_route".to_owned());
    }
    let parsed = tauri::Url::parse(&format!("http://angmoo.local{route}"))
        .map_err(|_| "invalid_product_route".to_owned())?;
    if parsed.fragment().is_some() {
        return Err("product_route_fragment_not_allowed".to_owned());
    }
    for (key, _) in parsed.query_pairs() {
        let lower = key.to_ascii_lowercase();
        let compact = lower.replace(['_', '-'], "");
        if lower.starts_with("__angmoo_")
            || matches!(compact.as_str(), "apikey" | "launchtoken" | "accesstoken")
        {
            return Err("private_product_route".to_owned());
        }
    }
    let path = parsed.path();
    let segments = path
        .split('/')
        .filter(|segment| !segment.is_empty())
        .collect::<Vec<_>>();
    let path_matches = match kind {
        ProductWindowKind::Memory => memory_path_matches(&segments),
        ProductWindowKind::Phone => phone_path_matches(&segments),
        ProductWindowKind::Studio => studio_path_matches(&segments),
        ProductWindowKind::RelationshipGraph => relationship_path_matches(&segments),
    };
    if !path_matches {
        return Err("product_route_outside_window_boundary".to_owned());
    }
    if kind == ProductWindowKind::Memory && !memory_query_matches(&parsed) {
        return Err("invalid_memory_query".to_owned());
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

fn memory_path_matches(segments: &[&str]) -> bool {
    matches!(segments, ["memory"])
}

fn memory_query_matches(parsed: &tauri::Url) -> bool {
    let mut world = false;
    let mut subject = false;
    let mut memory = false;
    for (key, value) in parsed.query_pairs() {
        if !safe_decoded_segment(value.as_ref()) {
            return false;
        }
        match key.as_ref() {
            "world" if !world => world = true,
            "subject" if !subject => subject = true,
            "memory" if !memory => memory = true,
            _ => return false,
        }
    }
    (!subject || world) && (!memory || subject)
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
        ["worlds", world_id, "characters", world_character_id] => {
            safe_world_id(world_id) && safe_segment(world_character_id)
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

fn decode_route_segment(value: &str) -> Result<String, String> {
    let mut decoded = Vec::with_capacity(value.len());
    let bytes = value.as_bytes();
    let mut offset = 0;
    while offset < bytes.len() {
        if bytes[offset] == b'%' {
            let hex = |byte: u8| (byte as char).to_digit(16).map(|value| value as u8);
            if offset + 2 >= bytes.len() {
                return Err("invalid_product_route_segment".to_owned());
            }
            let high = hex(bytes[offset + 1]).ok_or("invalid_product_route_segment")?;
            let low = hex(bytes[offset + 2]).ok_or("invalid_product_route_segment")?;
            decoded.push((high << 4) | low);
            offset += 3;
        } else {
            decoded.push(bytes[offset]);
            offset += 1;
        }
    }
    String::from_utf8(decoded).map_err(|_| "invalid_product_route_segment".to_owned())
}

fn safe_world_id(value: &str) -> bool {
    decode_route_segment(value)
        .is_ok_and(|decoded| decoded != "new" && safe_decoded_segment(&decoded))
}

fn safe_decoded_segment(value: &str) -> bool {
    !value.is_empty()
        && value.chars().count() <= 255
        && value != "."
        && value != ".."
        && !value.contains(['/', '\\'])
        && !value.chars().any(char::is_control)
}

fn safe_segment(value: &str) -> bool {
    decode_route_segment(value).is_ok_and(|decoded| safe_decoded_segment(&decoded))
}

fn initial_state_script(kind: ProductWindowKind, route: &str) -> Result<String, String> {
    let kind = serde_json::to_string(&kind).map_err(|_| "window_state_encode_failed")?;
    let route = serde_json::to_string(route).map_err(|_| "window_state_encode_failed")?;
    Ok(format!(
        "window.__ANGMOO_DESKTOP_WINDOW__={{kind:{kind},route:{route}}};"
    ))
}

fn navigation_script(_kind: ProductWindowKind, route: &str) -> Result<String, String> {
    let route = serde_json::to_string(route).map_err(|_| "window_state_encode_failed")?;
    Ok(format!(
        "window.dispatchEvent(new CustomEvent('angmoo:desktop-navigate',{{detail:{{route:{route},native:true}}}}));"
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
        ProductWindowKind::Memory => builder
            .inner_size(1180.0, 780.0)
            .min_inner_size(480.0, 480.0),
        ProductWindowKind::Studio => builder
            .inner_size(1280.0, 820.0)
            .min_inner_size(480.0, 480.0),
        ProductWindowKind::RelationshipGraph => builder
            .inner_size(1180.0, 780.0)
            .min_inner_size(480.0, 480.0),
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
    .inner_size(
        crate::window_policy::MAIN_INITIAL_WIDTH,
        crate::window_policy::MAIN_INITIAL_HEIGHT,
    )
    .decorations(true)
    .transparent(false)
    .resizable(true)
    .maximizable(true)
    .shadow(true)
    .visible(false)
    .initialization_script(initial_state_script(ProductWindowKind::Phone, "/")?);
    configure_product_document_boundary(
        configure_product_webview_data_directory(builder, paths),
        app,
        ProductWindowKind::Phone,
    )?
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
        .decorations(true)
        .resizable(true)
        .maximizable(true)
        .shadow(true)
        .visible(false)
        .initialization_script(initial_state_script(kind, &route)?);
    let builder = configure_product_webview_data_directory(builder, &product_paths);
    let window =
        configure_product_document_boundary(configure_wide_window(builder, kind), &app, kind)?
            .build()
            .map_err(|error| error.to_string())?;
    let (width, height) = match kind {
        ProductWindowKind::Studio => (1280.0, 820.0),
        _ => (1180.0, 780.0),
    };
    crate::window_policy::apply_product_window_policy(&window, width, height)
        .map_err(|error| error.to_string())?;
    window.show().map_err(|error| error.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn validate_product_navigation(kind: String, route: String) -> Result<String, String> {
    validate_product_route(ProductWindowKind::parse(&kind)?, &route)
}

pub fn validate_external_product_link(value: &str) -> Result<tauri::Url, String> {
    let url = tauri::Url::parse(value).map_err(|_| "invalid_external_product_link")?;
    if value.len() > 4096
        || !matches!(url.scheme(), "http" | "https")
        || url.host_str().is_none()
        || !url.username().is_empty()
        || url.password().is_some()
    {
        return Err("invalid_external_product_link".to_owned());
    }
    Ok(url)
}

#[tauri::command]
pub fn open_external_product_link(window: WebviewWindow, url: String) -> Result<(), String> {
    if !matches!(
        window.label(),
        "main" | "memory" | "studio" | "relationship-graph"
    ) {
        return Err("invalid_product_window".to_owned());
    }
    let url = validate_external_product_link(&url)?;
    #[allow(deprecated)]
    window
        .app_handle()
        .shell()
        .open(url.as_str(), None)
        .map_err(|_| "external_product_link_failed".to_owned())
}

fn product_document_allowed(kind: ProductWindowKind, url: &tauri::Url, origin: &str) -> bool {
    let Ok(expected) = tauri::Url::parse(origin) else {
        return false;
    };
    if url.scheme() != expected.scheme()
        || url.host_str() != expected.host_str()
        || url.port_or_known_default() != expected.port_or_known_default()
        || !url.username().is_empty()
        || url.password().is_some()
        || url.fragment().is_some()
    {
        return false;
    }
    if url.path() == "/index.html" {
        let query: std::collections::HashMap<_, _> = url.query_pairs().into_owned().collect();
        return url.query_pairs().count() == 2
            && query.len() == 2
            && query
                .get(WINDOW_KIND_QUERY)
                .is_some_and(|value| value == kind.bootstrap_kind())
            && query
                .get(WINDOW_ROUTE_QUERY)
                .is_some_and(|value| validate_product_route(kind, value).is_ok());
    }
    let route = format!(
        "{}{}",
        url.path(),
        url.query()
            .map(|value| format!("?{value}"))
            .unwrap_or_default()
    );
    validate_product_route(kind, &route).is_ok()
}

fn configure_product_document_boundary<'a>(
    builder: WebviewWindowBuilder<'a, tauri::Wry, AppHandle<tauri::Wry>>,
    app: &AppHandle,
    kind: ProductWindowKind,
) -> Result<WebviewWindowBuilder<'a, tauri::Wry, AppHandle<tauri::Wry>>, String> {
    let origin = if tauri::is_dev() {
        app.config()
            .build
            .dev_url
            .as_ref()
            .ok_or("tauri_dev_url_missing")?
            .origin()
            .ascii_serialization()
    } else if cfg!(windows) || cfg!(target_os = "android") {
        "http://tauri.localhost".to_owned()
    } else {
        "tauri://localhost".to_owned()
    };
    Ok(builder
        .on_navigation(move |url| product_document_allowed(kind, url, &origin))
        .on_new_window(|_, _| tauri::webview::NewWindowResponse::Deny))
}

pub fn current_window(window: &WebviewWindow) -> &WebviewWindow {
    window
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn encoded_segments_and_private_query_keys_are_checked_before_navigation() {
        for route in [
            "//example.org/agents",
            "/agents/%",
            "/agents/%GG",
            "/agents/%FF",
            "/agents/%2e%2e",
            "/agents/a%2fb",
            "/agents/a%5cb",
            "/agents/a%00b",
            "/worlds/%6eew/feed",
            "/settings?%61pi_key=secret",
            "/settings?ACCESS-TOKEN=secret",
            "/settings?%5f%5fangmoo_window_route=/",
        ] {
            assert!(
                validate_product_route(ProductWindowKind::Phone, route).is_err(),
                "{route}"
            );
        }
        assert!(validate_product_route(ProductWindowKind::Phone, "/agents/hello%20world").is_ok());
        assert!(
            validate_product_route(
                ProductWindowKind::Phone,
                "/worlds/world-1/posts/post-1?returnTo=%2Fposts"
            )
            .is_ok()
        );
    }

    #[test]
    fn product_documents_require_the_exact_origin_kind_and_bootstrap() {
        let allowed = |kind, value: &str, origin| {
            product_document_allowed(kind, &tauri::Url::parse(value).unwrap(), origin)
        };
        assert!(allowed(
            ProductWindowKind::Phone,
            "http://127.0.0.1:3300/agents",
            "http://127.0.0.1:3300"
        ));
        assert!(allowed(
            ProductWindowKind::Memory,
            "tauri://localhost/memory?world=world-1",
            "tauri://localhost"
        ));
        assert!(allowed(
            ProductWindowKind::Phone,
            "http://tauri.localhost/index.html?__angmoo_window_kind=phone&__angmoo_window_route=%2Fagents",
            "http://tauri.localhost"
        ));
        for value in [
            "https://example.org/agents",
            "http://127.0.0.1:3301/agents",
            "http://127.0.0.1:3300/memory",
            "http://127.0.0.1:3300/agents#fragment",
            "http://user@127.0.0.1:3300/agents",
        ] {
            assert!(
                !allowed(ProductWindowKind::Phone, value, "http://127.0.0.1:3300"),
                "{value}"
            );
        }
        assert!(!allowed(
            ProductWindowKind::Phone,
            "http://tauri.localhost/index.html?__angmoo_window_kind=phone&__angmoo_window_route=%2Fagents&__angmoo_window_route=%2Fsettings",
            "http://tauri.localhost"
        ));
    }

    #[test]
    fn external_opener_accepts_only_credential_free_http_links() {
        for value in [
            "https://example.org/document",
            "http://example.org/path?q=1",
        ] {
            assert!(validate_external_product_link(value).is_ok());
        }
        for value in [
            "javascript:alert(1)",
            "file:///forbidden-document",
            "data:text/html,test",
            "https://user:password@example.org",
            "//example.org",
            "tauri://localhost",
        ] {
            assert!(validate_external_product_link(value).is_err(), "{value}");
        }
    }

    #[test]
    fn product_routes_stay_inside_their_window_boundaries() {
        assert!(validate_product_route(ProductWindowKind::Memory, "/memory").is_ok());
        assert!(
            validate_product_route(
                ProductWindowKind::Memory,
                "/memory?world=world-1&subject=wc-1&memory=memory-1"
            )
            .is_ok()
        );
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
                "/worlds/world-1/characters/world-character-1"
            )
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
        assert!(validate_product_route(ProductWindowKind::Phone, "/memory").is_err());
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
    fn memory_window_rejects_unscoped_or_unsafe_query_parameters() {
        for route in [
            "/memory?subject=wc-1",
            "/memory?world=world-1&memory=memory-1",
            "/memory?world=world-1&debug=true",
            "/memory?world=world-1&world=world-2",
            "/memory?world=..%2Fsettings",
        ] {
            assert_eq!(
                validate_product_route(ProductWindowKind::Memory, route),
                Err("invalid_memory_query".to_owned())
            );
        }
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
