use tauri::{LogicalSize, PhysicalPosition, WebviewWindow};

pub const MAIN_INITIAL_WIDTH: f64 = 480.0;
pub const MAIN_INITIAL_HEIGHT: f64 = 850.0;
pub const PRODUCT_MIN_WIDTH: f64 = 480.0;
pub const PRODUCT_MIN_HEIGHT: f64 = 480.0;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ProductWindowGeometry {
    pub initial: (f64, f64),
    pub minimum: (f64, f64),
    pub position: (i32, i32),
}

/// Work-area coordinates/insets are physical pixels; client sizes are logical.
/// This is a creation policy, never an aspect-ratio or resize-event constraint.
pub fn product_geometry_for_work_area(
    origin: (i32, i32),
    area: (u32, u32),
    scale: f64,
    outer_insets: (u32, u32),
    target: (f64, f64),
) -> ProductWindowGeometry {
    let scale = if scale.is_finite() && scale > 0.0 {
        scale
    } else {
        1.0
    };
    let available = (
        (area.0.saturating_sub(outer_insets.0) as f64 / scale).max(1.0),
        (area.1.saturating_sub(outer_insets.1) as f64 / scale).max(1.0),
    );
    let minimum = (
        PRODUCT_MIN_WIDTH.min(available.0),
        PRODUCT_MIN_HEIGHT.min(available.1),
    );
    let initial = (
        target.0.min(available.0).max(minimum.0),
        target.1.min(available.1).max(minimum.1),
    );
    let outer = (
        initial.0 * scale + outer_insets.0 as f64,
        initial.1 * scale + outer_insets.1 as f64,
    );
    ProductWindowGeometry {
        initial,
        minimum,
        position: (
            origin
                .0
                .saturating_add(((area.0 as f64 - outer.0).max(0.0) / 2.0).round() as i32),
            origin
                .1
                .saturating_add(((area.1 as f64 - outer.1).max(0.0) / 2.0).round() as i32),
        ),
    }
}

pub fn apply_product_window_policy(
    window: &WebviewWindow,
    width: f64,
    height: f64,
) -> tauri::Result<()> {
    window.set_resizable(true)?;
    window.set_maximizable(true)?;
    window.set_decorations(true)?;
    window.set_shadow(true)?;
    // Body CSS caps must never become native maxima.
    window.set_max_size(None::<LogicalSize<f64>>)?;
    let inner = window.inner_size()?;
    let outer = window.outer_size()?;
    let insets = (
        outer.width.saturating_sub(inner.width),
        outer.height.saturating_sub(inner.height),
    );
    let monitor = window.current_monitor()?.or(window.primary_monitor()?);
    let geometry = if let Some(monitor) = monitor {
        let area = monitor.work_area();
        product_geometry_for_work_area(
            (area.position.x, area.position.y),
            (area.size.width, area.size.height),
            monitor.scale_factor(),
            insets,
            (width, height),
        )
    } else {
        ProductWindowGeometry {
            initial: (width, height),
            minimum: (PRODUCT_MIN_WIDTH, PRODUCT_MIN_HEIGHT),
            position: (0, 0),
        }
    };
    window.set_min_size(Some(LogicalSize::new(
        geometry.minimum.0,
        geometry.minimum.1,
    )))?;
    window.set_size(LogicalSize::new(geometry.initial.0, geometry.initial.1))?;
    window.set_position(PhysicalPosition::new(
        geometry.position.0,
        geometry.position.1,
    ))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn initial_client_and_minimum_are_independent() {
        let g = product_geometry_for_work_area(
            (0, 0),
            (1920, 1080),
            1.0,
            (16, 39),
            (MAIN_INITIAL_WIDTH, MAIN_INITIAL_HEIGHT),
        );
        assert_eq!(g.initial, (480.0, 850.0));
        assert_eq!(g.minimum, (480.0, 480.0));
        assert_eq!(g.position, (712, 96));
    }
    #[test]
    fn high_dpi_and_negative_monitor_origin_fit_the_outer_window() {
        for scale in [1.0, 1.25, 1.5, 2.0] {
            let g = product_geometry_for_work_area(
                (-1920, -100),
                (1920, 1040),
                scale,
                (24, 60),
                (480.0, 850.0),
            );
            assert!(g.position.0 >= -1920 && g.position.1 >= -100);
            assert!(g.initial.0 * scale + 24.0 <= 1920.0);
            assert!(g.initial.1 * scale + 60.0 <= 1040.0);
            assert!(g.minimum.1 <= g.initial.1);
        }
    }
    #[test]
    fn small_work_area_reduces_each_minimum_instead_of_fixing_a_ratio() {
        let g = product_geometry_for_work_area((20, 30), (420, 400), 1.0, (16, 40), (480.0, 850.0));
        assert_eq!(g.initial, (404.0, 360.0));
        assert_eq!(g.minimum, (404.0, 360.0));
        assert_eq!(g.position, (20, 30));
    }
    #[test]
    fn invalid_scale_has_a_safe_fallback() {
        for scale in [0.0, -1.0, f64::NAN, f64::INFINITY] {
            assert_eq!(
                product_geometry_for_work_area(
                    (0, 0),
                    (1920, 1080),
                    scale,
                    (16, 40),
                    (480.0, 850.0)
                ),
                product_geometry_for_work_area((0, 0), (1920, 1080), 1.0, (16, 40), (480.0, 850.0))
            );
        }
    }
    #[test]
    fn workspace_initial_size_retains_its_own_target() {
        let g =
            product_geometry_for_work_area((0, 0), (2560, 1440), 1.0, (16, 40), (1280.0, 820.0));
        assert_eq!(g.initial, (1280.0, 820.0));
        assert_eq!(g.minimum, (480.0, 480.0));
    }
}
