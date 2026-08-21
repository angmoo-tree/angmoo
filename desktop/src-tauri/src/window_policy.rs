use tauri::{LogicalSize, WebviewWindow};

pub const PHONE_TARGET_WIDTH: f64 = 468.0;
pub const PHONE_TARGET_HEIGHT: f64 = 916.0;
const MONITOR_EDGE_RESERVE: f64 = 64.0;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PhoneWindowSize {
    pub width: f64,
    pub height: f64,
}

pub fn phone_size_for_monitor(
    physical_width: u32,
    physical_height: u32,
    scale_factor: f64,
) -> PhoneWindowSize {
    let safe_scale = if scale_factor.is_finite() && scale_factor > 0.0 {
        scale_factor
    } else {
        1.0
    };
    let logical_width = physical_width as f64 / safe_scale;
    let logical_height = physical_height as f64 / safe_scale;
    let available_width = (logical_width - MONITOR_EDGE_RESERVE).max(1.0);
    let available_height = (logical_height - MONITOR_EDGE_RESERVE).max(1.0);
    let fit = 1.0_f64
        .min(available_width / PHONE_TARGET_WIDTH)
        .min(available_height / PHONE_TARGET_HEIGHT);
    PhoneWindowSize {
        width: (PHONE_TARGET_WIDTH * fit).round(),
        height: (PHONE_TARGET_HEIGHT * fit).round(),
    }
}

pub fn apply_phone_window_policy(window: &WebviewWindow) -> tauri::Result<PhoneWindowSize> {
    let size = if let Some(monitor) = window.current_monitor()? {
        phone_size_for_monitor(
            monitor.size().width,
            monitor.size().height,
            monitor.scale_factor(),
        )
    } else {
        PhoneWindowSize {
            width: PHONE_TARGET_WIDTH,
            height: PHONE_TARGET_HEIGHT,
        }
    };
    let logical_size = LogicalSize::new(size.width, size.height);
    window.set_resizable(false)?;
    window.set_min_size(Some(logical_size))?;
    window.set_max_size(Some(logical_size))?;
    window.set_size(logical_size)?;
    window.center()?;
    Ok(size)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn phone_policy_keeps_target_size_at_100_percent() {
        assert_eq!(
            phone_size_for_monitor(1920, 1080, 1.0),
            PhoneWindowSize {
                width: 468.0,
                height: 916.0,
            }
        );
    }

    #[test]
    fn phone_policy_fits_a_1080p_monitor_at_125_percent() {
        assert_eq!(
            phone_size_for_monitor(1920, 1080, 1.25),
            PhoneWindowSize {
                width: 409.0,
                height: 800.0,
            }
        );
    }

    #[test]
    fn phone_policy_fits_a_1080p_monitor_at_150_percent() {
        assert_eq!(
            phone_size_for_monitor(1920, 1080, 1.5),
            PhoneWindowSize {
                width: 335.0,
                height: 656.0,
            }
        );
    }

    #[test]
    fn invalid_scale_falls_back_to_100_percent() {
        assert_eq!(
            phone_size_for_monitor(1920, 1080, 0.0),
            phone_size_for_monitor(1920, 1080, 1.0)
        );
    }
}
