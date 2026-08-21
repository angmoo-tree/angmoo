use tauri::{LogicalSize, WebviewWindow};

pub const PHONE_TARGET_WIDTH: f64 = 468.0;
pub const PHONE_TARGET_HEIGHT: f64 = 916.0;
pub const PHONE_ASPECT_RATIO: f64 = PHONE_TARGET_WIDTH / PHONE_TARGET_HEIGHT;
const PHONE_MIN_SCALE: f64 = 0.75;
const PHONE_MAX_SCALE: f64 = 1.25;
const MONITOR_EDGE_RESERVE: f64 = 64.0;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PhoneWindowSize {
    pub width: f64,
    pub height: f64,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PhoneWindowBounds {
    pub minimum: PhoneWindowSize,
    pub initial: PhoneWindowSize,
    pub maximum: PhoneWindowSize,
}

fn size_at_scale(scale: f64) -> PhoneWindowSize {
    PhoneWindowSize {
        width: (PHONE_TARGET_WIDTH * scale).round(),
        height: (PHONE_TARGET_HEIGHT * scale).round(),
    }
}

pub fn phone_bounds_for_monitor(
    physical_width: u32,
    physical_height: u32,
    scale_factor: f64,
) -> PhoneWindowBounds {
    let safe_scale = if scale_factor.is_finite() && scale_factor > 0.0 {
        scale_factor
    } else {
        1.0
    };
    let logical_width = physical_width as f64 / safe_scale;
    let logical_height = physical_height as f64 / safe_scale;
    let available_width = (logical_width - MONITOR_EDGE_RESERVE).max(1.0);
    let available_height = (logical_height - MONITOR_EDGE_RESERVE).max(1.0);
    let maximum_scale = PHONE_MAX_SCALE
        .min(available_width / PHONE_TARGET_WIDTH)
        .min(available_height / PHONE_TARGET_HEIGHT)
        .max(1.0 / PHONE_TARGET_HEIGHT);
    let minimum_scale = PHONE_MIN_SCALE.min(maximum_scale);
    let initial_scale = 1.0_f64.min(maximum_scale);
    PhoneWindowBounds {
        minimum: size_at_scale(minimum_scale),
        initial: size_at_scale(initial_scale),
        maximum: size_at_scale(maximum_scale),
    }
}

pub fn apply_phone_window_policy(window: &WebviewWindow) -> tauri::Result<PhoneWindowSize> {
    let bounds = if let Some(monitor) = window.current_monitor()? {
        phone_bounds_for_monitor(
            monitor.work_area().size.width,
            monitor.work_area().size.height,
            monitor.scale_factor(),
        )
    } else {
        PhoneWindowBounds {
            minimum: size_at_scale(PHONE_MIN_SCALE),
            initial: size_at_scale(1.0),
            maximum: size_at_scale(PHONE_MAX_SCALE),
        }
    };
    window.set_resizable(true)?;
    window.set_maximizable(false)?;
    window.set_min_size(Some(LogicalSize::new(
        bounds.minimum.width,
        bounds.minimum.height,
    )))?;
    window.set_max_size(Some(LogicalSize::new(
        bounds.maximum.width,
        bounds.maximum.height,
    )))?;
    window.set_size(LogicalSize::new(
        bounds.initial.width,
        bounds.initial.height,
    ))?;
    window.center()?;
    Ok(bounds.initial)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn phone_policy_keeps_a_continuous_75_to_125_percent_range() {
        assert_eq!(
            phone_bounds_for_monitor(2560, 1440, 1.0),
            PhoneWindowBounds {
                minimum: PhoneWindowSize {
                    width: 351.0,
                    height: 687.0,
                },
                initial: PhoneWindowSize {
                    width: 468.0,
                    height: 916.0,
                },
                maximum: PhoneWindowSize {
                    width: 585.0,
                    height: 1145.0,
                },
            }
        );
    }

    #[test]
    fn phone_policy_fits_a_1080p_monitor_at_125_percent() {
        assert_eq!(
            phone_bounds_for_monitor(1920, 1080, 1.25),
            PhoneWindowBounds {
                minimum: PhoneWindowSize {
                    width: 351.0,
                    height: 687.0,
                },
                initial: PhoneWindowSize {
                    width: 409.0,
                    height: 800.0,
                },
                maximum: PhoneWindowSize {
                    width: 409.0,
                    height: 800.0,
                },
            }
        );
    }

    #[test]
    fn phone_policy_fits_a_1080p_monitor_at_150_percent() {
        assert_eq!(
            phone_bounds_for_monitor(1920, 1080, 1.5),
            PhoneWindowBounds {
                minimum: PhoneWindowSize {
                    width: 335.0,
                    height: 656.0,
                },
                initial: PhoneWindowSize {
                    width: 335.0,
                    height: 656.0,
                },
                maximum: PhoneWindowSize {
                    width: 335.0,
                    height: 656.0,
                },
            }
        );
    }

    #[test]
    fn invalid_scale_falls_back_to_100_percent() {
        assert_eq!(
            phone_bounds_for_monitor(1920, 1080, 0.0),
            phone_bounds_for_monitor(1920, 1080, 1.0)
        );
    }

    #[test]
    fn every_bound_stays_within_one_logical_pixel_of_the_phone_ratio() {
        let bounds = phone_bounds_for_monitor(2560, 1440, 1.25);
        for size in [bounds.minimum, bounds.initial, bounds.maximum] {
            let expected_height = size.width / PHONE_ASPECT_RATIO;
            assert!((size.height - expected_height).abs() <= 1.0);
        }
    }
}
