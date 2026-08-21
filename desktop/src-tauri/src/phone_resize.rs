use tauri::WebviewWindow;

use crate::window_policy::PHONE_ASPECT_RATIO;

const PHONE_CORNER_RADIUS_MIN_LOGICAL: f64 = 26.0;
const PHONE_CORNER_RADIUS_MAX_LOGICAL: f64 = 42.0;
const PHONE_CORNER_RADIUS_WIDTH_RATIO: f64 = 0.0725;
const PHONE_RESIZE_HIT_THICKNESS_LOGICAL: f64 = 8.0;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum SizingEdge {
    Left,
    Right,
    Top,
    Bottom,
    TopLeft,
    TopRight,
    BottomLeft,
    BottomRight,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct ResizeRect {
    left: i32,
    top: i32,
    right: i32,
    bottom: i32,
}

impl ResizeRect {
    fn width(self) -> i32 {
        self.right - self.left
    }

    fn height(self) -> i32 {
        self.bottom - self.top
    }
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
struct NonClientInsets {
    horizontal: i32,
    vertical: i32,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct WindowPoint {
    x: i32,
    y: i32,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct WindowSize {
    width: i32,
    height: i32,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct PhoneRegionGeometry {
    offset_x: i32,
    offset_y: i32,
    width: i32,
    height: i32,
    radius: i32,
    resize_hit_thickness: i32,
}

fn phone_region_geometry(
    outer_size: WindowSize,
    client_origin: WindowPoint,
    client_size: WindowSize,
    dpi: u32,
) -> Option<PhoneRegionGeometry> {
    if outer_size.width <= 0
        || outer_size.height <= 0
        || client_origin.x < 0
        || client_origin.y < 0
        || client_size.width <= 0
        || client_size.height <= 0
        || client_origin.x + client_size.width > outer_size.width
        || client_origin.y + client_size.height > outer_size.height
    {
        return None;
    }
    let safe_dpi = if dpi == 0 { 96 } else { dpi };
    let dpi_scale = safe_dpi as f64 / 96.0;
    let logical_client_width = client_size.width as f64 / dpi_scale;
    let logical_radius = (logical_client_width * PHONE_CORNER_RADIUS_WIDTH_RATIO).clamp(
        PHONE_CORNER_RADIUS_MIN_LOGICAL,
        PHONE_CORNER_RADIUS_MAX_LOGICAL,
    );
    let radius = (logical_radius * dpi_scale)
        .round()
        .max(1.0)
        .min((client_size.width / 2) as f64)
        .min((client_size.height / 2) as f64) as i32;
    let resize_hit_thickness = (PHONE_RESIZE_HIT_THICKNESS_LOGICAL * dpi_scale)
        .round()
        .max(1.0)
        .min(radius as f64) as i32;
    Some(PhoneRegionGeometry {
        offset_x: client_origin.x,
        offset_y: client_origin.y,
        width: client_size.width,
        height: client_size.height,
        radius,
        resize_hit_thickness,
    })
}

fn phone_resize_hit_test(point: WindowPoint, geometry: PhoneRegionGeometry) -> Option<SizingEdge> {
    let point = WindowPoint {
        x: point.x - geometry.offset_x,
        y: point.y - geometry.offset_y,
    };
    if point.x < 0 || point.y < 0 || point.x >= geometry.width || point.y >= geometry.height {
        return None;
    }

    let radius = geometry.radius.max(1);
    let thickness = geometry.resize_hit_thickness.clamp(1, radius);
    let inner_radius = (radius - thickness).max(0);
    let corner_band = |center_x: i32, center_y: i32| {
        let dx = i64::from(point.x - center_x);
        let dy = i64::from(point.y - center_y);
        let distance_squared = dx * dx + dy * dy;
        distance_squared >= i64::from(inner_radius) * i64::from(inner_radius)
            && distance_squared <= i64::from(radius) * i64::from(radius)
    };

    let right_corner_start = geometry.width - radius;
    let bottom_corner_start = geometry.height - radius;
    if point.x < radius && point.y < radius {
        return corner_band(radius, radius).then_some(SizingEdge::TopLeft);
    }
    if point.x >= right_corner_start && point.y < radius {
        return corner_band(right_corner_start, radius).then_some(SizingEdge::TopRight);
    }
    if point.x < radius && point.y >= bottom_corner_start {
        return corner_band(radius, bottom_corner_start).then_some(SizingEdge::BottomLeft);
    }
    if point.x >= right_corner_start && point.y >= bottom_corner_start {
        return corner_band(right_corner_start, bottom_corner_start)
            .then_some(SizingEdge::BottomRight);
    }

    if point.y < thickness {
        return Some(SizingEdge::Top);
    }
    if point.y >= geometry.height - thickness {
        return Some(SizingEdge::Bottom);
    }
    if point.x < thickness {
        return Some(SizingEdge::Left);
    }
    if point.x >= geometry.width - thickness {
        return Some(SizingEdge::Right);
    }
    None
}

fn phone_contains_point(point: WindowPoint, geometry: PhoneRegionGeometry) -> bool {
    let point = WindowPoint {
        x: point.x - geometry.offset_x,
        y: point.y - geometry.offset_y,
    };
    if point.x < 0 || point.y < 0 || point.x >= geometry.width || point.y >= geometry.height {
        return false;
    }

    let radius = geometry
        .radius
        .clamp(1, geometry.width.min(geometry.height) / 2);
    let right_corner_start = geometry.width - radius;
    let bottom_corner_start = geometry.height - radius;
    let inside_corner = |center_x: i32, center_y: i32| {
        let dx = i64::from(point.x - center_x);
        let dy = i64::from(point.y - center_y);
        dx * dx + dy * dy <= i64::from(radius) * i64::from(radius)
    };

    if point.x < radius && point.y < radius {
        return inside_corner(radius, radius);
    }
    if point.x >= right_corner_start && point.y < radius {
        return inside_corner(right_corner_start, radius);
    }
    if point.x < radius && point.y >= bottom_corner_start {
        return inside_corner(radius, bottom_corner_start);
    }
    if point.x >= right_corner_start && point.y >= bottom_corner_start {
        return inside_corner(right_corner_start, bottom_corner_start);
    }
    true
}

fn ratio_locked_rect(
    proposed: ResizeRect,
    edge: SizingEdge,
    insets: NonClientInsets,
) -> ResizeRect {
    let outer_width = proposed.width().max(insets.horizontal + 1);
    let outer_height = proposed.height().max(insets.vertical + 1);
    let client_width = (outer_width - insets.horizontal).max(1);
    let client_height = (outer_height - insets.vertical).max(1);
    let width_driven_height =
        ((client_width as f64 / PHONE_ASPECT_RATIO).round() as i32 + insets.vertical).max(1);
    let height_driven_width =
        ((client_height as f64 * PHONE_ASPECT_RATIO).round() as i32 + insets.horizontal).max(1);

    let (locked_width, locked_height) = match edge {
        SizingEdge::Left | SizingEdge::Right => (outer_width, width_driven_height),
        SizingEdge::Top | SizingEdge::Bottom => (height_driven_width, outer_height),
        SizingEdge::TopLeft
        | SizingEdge::TopRight
        | SizingEdge::BottomLeft
        | SizingEdge::BottomRight => {
            if (width_driven_height - outer_height).abs()
                <= (height_driven_width - outer_width).abs()
            {
                (outer_width, width_driven_height)
            } else {
                (height_driven_width, outer_height)
            }
        }
    };

    let center_x = proposed.left + outer_width / 2;
    let center_y = proposed.top + outer_height / 2;
    match edge {
        SizingEdge::Left => ResizeRect {
            left: proposed.right - locked_width,
            right: proposed.right,
            top: center_y - locked_height / 2,
            bottom: center_y - locked_height / 2 + locked_height,
        },
        SizingEdge::Right => ResizeRect {
            left: proposed.left,
            right: proposed.left + locked_width,
            top: center_y - locked_height / 2,
            bottom: center_y - locked_height / 2 + locked_height,
        },
        SizingEdge::Top => ResizeRect {
            left: center_x - locked_width / 2,
            right: center_x - locked_width / 2 + locked_width,
            top: proposed.bottom - locked_height,
            bottom: proposed.bottom,
        },
        SizingEdge::Bottom => ResizeRect {
            left: center_x - locked_width / 2,
            right: center_x - locked_width / 2 + locked_width,
            top: proposed.top,
            bottom: proposed.top + locked_height,
        },
        SizingEdge::TopLeft => ResizeRect {
            left: proposed.right - locked_width,
            top: proposed.bottom - locked_height,
            right: proposed.right,
            bottom: proposed.bottom,
        },
        SizingEdge::TopRight => ResizeRect {
            left: proposed.left,
            top: proposed.bottom - locked_height,
            right: proposed.left + locked_width,
            bottom: proposed.bottom,
        },
        SizingEdge::BottomLeft => ResizeRect {
            left: proposed.right - locked_width,
            top: proposed.top,
            right: proposed.right,
            bottom: proposed.top + locked_height,
        },
        SizingEdge::BottomRight => ResizeRect {
            left: proposed.left,
            top: proposed.top,
            right: proposed.left + locked_width,
            bottom: proposed.top + locked_height,
        },
    }
}

#[cfg(windows)]
mod windows {
    use super::{
        NonClientInsets, PhoneRegionGeometry, ResizeRect, SizingEdge, WindowPoint, WindowSize,
        phone_contains_point, phone_region_geometry, phone_resize_hit_test, ratio_locked_rect,
    };
    use std::{ffi::c_void, mem::size_of};
    use windows::Win32::{
        Foundation::{HWND, LPARAM, LRESULT, POINT, RECT, WPARAM},
        Graphics::{
            Dwm::{
                DWMWA_BORDER_COLOR, DWMWA_COLOR_NONE, DWMWA_WINDOW_CORNER_PREFERENCE,
                DwmSetWindowAttribute,
            },
            Gdi::ClientToScreen,
        },
        UI::{
            HiDpi::GetDpiForWindow,
            Shell::{DefSubclassProc, GetWindowSubclass, RemoveWindowSubclass, SetWindowSubclass},
            WindowsAndMessaging::{
                GetClientRect, GetWindowRect, HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT, HTLEFT,
                HTNOWHERE, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT, WM_NCDESTROY, WM_NCHITTEST,
                WM_SIZING, WMSZ_BOTTOM, WMSZ_BOTTOMLEFT, WMSZ_BOTTOMRIGHT, WMSZ_LEFT, WMSZ_RIGHT,
                WMSZ_TOP, WMSZ_TOPLEFT, WMSZ_TOPRIGHT,
            },
        },
    };

    const PHONE_ASPECT_SUBCLASS_ID: usize = 0x414E_474D_4F4F;
    const DWMWCP_ROUND_VALUE: u32 = 2;

    struct PhoneWindowSubclassState;

    enum NativePhoneHit {
        Resize(SizingEdge),
        OutsideSilhouette,
    }

    pub fn install(window: &tauri::WebviewWindow) -> Result<(), String> {
        let hwnd = window.hwnd().map_err(|error| error.to_string())?;
        let mut existing_ref_data = 0;
        let already_attached = unsafe {
            GetWindowSubclass(
                hwnd,
                Some(phone_aspect_subclass),
                PHONE_ASPECT_SUBCLASS_ID,
                Some(&mut existing_ref_data),
            )
        };
        if already_attached.as_bool() {
            return Ok(());
        }

        let state = Box::new(PhoneWindowSubclassState);
        let state_ptr = Box::into_raw(state);
        let attached = unsafe {
            SetWindowSubclass(
                hwnd,
                Some(phone_aspect_subclass),
                PHONE_ASPECT_SUBCLASS_ID,
                state_ptr as usize,
            )
        };
        if !attached.as_bool() {
            unsafe { drop(Box::from_raw(state_ptr)) };
            return Err(windows::core::Error::from_win32().to_string());
        }

        // Do not clip this window with an HRGN. Region edges are integer-pixel masks
        // and visibly staircase at the Phone's large radius. The transparent
        // WebView and CSS frame own the antialiased silhouette; native code only
        // suppresses the rectangular DWM border and owns hit testing.
        suppress_native_border(hwnd);
        request_compositor_rounding(hwnd);
        Ok(())
    }

    unsafe extern "system" fn phone_aspect_subclass(
        hwnd: HWND,
        message: u32,
        wparam: WPARAM,
        lparam: LPARAM,
        _: usize,
        ref_data: usize,
    ) -> LRESULT {
        if message == WM_SIZING {
            if let Some(edge) = sizing_edge(wparam.0 as u32) {
                let rect_ptr = lparam.0 as *mut RECT;
                if let Some(rect) = unsafe { rect_ptr.as_mut() } {
                    let proposed = ResizeRect {
                        left: rect.left,
                        top: rect.top,
                        right: rect.right,
                        bottom: rect.bottom,
                    };
                    let locked = ratio_locked_rect(proposed, edge, non_client_insets(hwnd));
                    rect.left = locked.left;
                    rect.top = locked.top;
                    rect.right = locked.right;
                    rect.bottom = locked.bottom;
                    return LRESULT(1);
                }
            }
        } else if message == WM_NCHITTEST {
            if let Some(hit) = native_phone_hit(hwnd, lparam) {
                return match hit {
                    NativePhoneHit::Resize(edge) => LRESULT(resize_hit_code(edge)),
                    NativePhoneHit::OutsideSilhouette => LRESULT(HTNOWHERE as isize),
                };
            }
        } else if message == WM_NCDESTROY {
            let _ = unsafe {
                RemoveWindowSubclass(hwnd, Some(phone_aspect_subclass), PHONE_ASPECT_SUBCLASS_ID)
            };
            let result = unsafe { DefSubclassProc(hwnd, message, wparam, lparam) };
            if ref_data != 0 {
                unsafe { drop(Box::from_raw(ref_data as *mut PhoneWindowSubclassState)) };
            }
            return result;
        }

        unsafe { DefSubclassProc(hwnd, message, wparam, lparam) }
    }

    fn suppress_native_border(hwnd: HWND) {
        let border_color = DWMWA_COLOR_NONE;
        let _ = unsafe {
            DwmSetWindowAttribute(
                hwnd,
                DWMWA_BORDER_COLOR,
                (&border_color as *const u32).cast::<c_void>(),
                size_of::<u32>() as u32,
            )
        };
    }

    fn request_compositor_rounding(hwnd: HWND) {
        let preference = DWMWCP_ROUND_VALUE;
        let _ = unsafe {
            DwmSetWindowAttribute(
                hwnd,
                DWMWA_WINDOW_CORNER_PREFERENCE,
                (&preference as *const u32).cast::<c_void>(),
                size_of::<u32>() as u32,
            )
        };
    }

    fn current_region_geometry(hwnd: HWND) -> Result<PhoneRegionGeometry, String> {
        let mut window_rect = RECT::default();
        let mut client_rect = RECT::default();
        unsafe { GetWindowRect(hwnd, &mut window_rect) }.map_err(|error| error.to_string())?;
        unsafe { GetClientRect(hwnd, &mut client_rect) }.map_err(|error| error.to_string())?;
        let outer_size = WindowSize {
            width: window_rect.right - window_rect.left,
            height: window_rect.bottom - window_rect.top,
        };
        let mut client_origin = POINT::default();
        if !unsafe { ClientToScreen(hwnd, &mut client_origin) }.as_bool() {
            return Err(windows::core::Error::from_win32().to_string());
        }
        let client_origin = WindowPoint {
            x: client_origin.x - window_rect.left,
            y: client_origin.y - window_rect.top,
        };
        let client_size = WindowSize {
            width: client_rect.right - client_rect.left,
            height: client_rect.bottom - client_rect.top,
        };
        let dpi = unsafe { GetDpiForWindow(hwnd) };
        phone_region_geometry(outer_size, client_origin, client_size, dpi)
            .ok_or_else(|| "phone window has invalid region geometry".to_owned())
    }

    fn native_phone_hit(hwnd: HWND, lparam: LPARAM) -> Option<NativePhoneHit> {
        let geometry = current_region_geometry(hwnd).ok()?;
        let mut window_rect = RECT::default();
        unsafe { GetWindowRect(hwnd, &mut window_rect) }.ok()?;
        let screen_x = (lparam.0 & 0xffff) as u16 as i16 as i32;
        let screen_y = ((lparam.0 >> 16) & 0xffff) as u16 as i16 as i32;
        let point = WindowPoint {
            x: screen_x - window_rect.left,
            y: screen_y - window_rect.top,
        };
        if let Some(edge) = phone_resize_hit_test(point, geometry) {
            return Some(NativePhoneHit::Resize(edge));
        }
        (!phone_contains_point(point, geometry)).then_some(NativePhoneHit::OutsideSilhouette)
    }

    fn resize_hit_code(edge: SizingEdge) -> isize {
        match edge {
            SizingEdge::Left => HTLEFT as isize,
            SizingEdge::Right => HTRIGHT as isize,
            SizingEdge::Top => HTTOP as isize,
            SizingEdge::Bottom => HTBOTTOM as isize,
            SizingEdge::TopLeft => HTTOPLEFT as isize,
            SizingEdge::TopRight => HTTOPRIGHT as isize,
            SizingEdge::BottomLeft => HTBOTTOMLEFT as isize,
            SizingEdge::BottomRight => HTBOTTOMRIGHT as isize,
        }
    }

    fn non_client_insets(hwnd: HWND) -> NonClientInsets {
        let mut window_rect = RECT::default();
        let mut client_rect = RECT::default();
        let window_ok = unsafe { GetWindowRect(hwnd, &mut window_rect) }.is_ok();
        let client_ok = unsafe { GetClientRect(hwnd, &mut client_rect) }.is_ok();
        if !window_ok || !client_ok {
            return NonClientInsets::default();
        }
        NonClientInsets {
            horizontal: ((window_rect.right - window_rect.left)
                - (client_rect.right - client_rect.left))
                .max(0),
            vertical: ((window_rect.bottom - window_rect.top)
                - (client_rect.bottom - client_rect.top))
                .max(0),
        }
    }

    fn sizing_edge(value: u32) -> Option<SizingEdge> {
        match value {
            WMSZ_LEFT => Some(SizingEdge::Left),
            WMSZ_RIGHT => Some(SizingEdge::Right),
            WMSZ_TOP => Some(SizingEdge::Top),
            WMSZ_BOTTOM => Some(SizingEdge::Bottom),
            WMSZ_TOPLEFT => Some(SizingEdge::TopLeft),
            WMSZ_TOPRIGHT => Some(SizingEdge::TopRight),
            WMSZ_BOTTOMLEFT => Some(SizingEdge::BottomLeft),
            WMSZ_BOTTOMRIGHT => Some(SizingEdge::BottomRight),
            _ => None,
        }
    }
}

#[cfg(windows)]
pub fn install_phone_aspect_ratio_lock(window: &WebviewWindow) -> Result<(), String> {
    windows::install(window)
}

#[cfg(not(windows))]
pub fn install_phone_aspect_ratio_lock(window: &WebviewWindow) -> Result<(), String> {
    let _ = window;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn assert_phone_client_ratio(rect: ResizeRect, insets: NonClientInsets) {
        let client_width = rect.width() - insets.horizontal;
        let client_height = rect.height() - insets.vertical;
        let expected_height = client_width as f64 / PHONE_ASPECT_RATIO;
        assert!((client_height as f64 - expected_height).abs() <= 1.0);
    }

    #[test]
    fn locks_all_eight_native_resize_directions() {
        let proposed = ResizeRect {
            left: 100,
            top: 80,
            right: 620,
            bottom: 980,
        };
        let insets = NonClientInsets {
            horizontal: 8,
            vertical: 8,
        };
        for edge in [
            SizingEdge::Left,
            SizingEdge::Right,
            SizingEdge::Top,
            SizingEdge::Bottom,
            SizingEdge::TopLeft,
            SizingEdge::TopRight,
            SizingEdge::BottomLeft,
            SizingEdge::BottomRight,
        ] {
            assert_phone_client_ratio(ratio_locked_rect(proposed, edge, insets), insets);
        }
    }

    #[test]
    fn horizontal_edges_keep_the_opposite_edge_and_vertical_center() {
        let proposed = ResizeRect {
            left: 100,
            top: 100,
            right: 568,
            bottom: 916,
        };
        let locked_left = ratio_locked_rect(proposed, SizingEdge::Left, Default::default());
        let locked_right = ratio_locked_rect(proposed, SizingEdge::Right, Default::default());
        assert_eq!(locked_left.right, proposed.right);
        assert_eq!(locked_right.left, proposed.left);
        assert_eq!(
            locked_left.top + locked_left.bottom,
            proposed.top + proposed.bottom
        );
        assert_eq!(
            locked_right.top + locked_right.bottom,
            proposed.top + proposed.bottom
        );
    }

    #[test]
    fn corner_resize_keeps_the_opposite_corner_fixed() {
        let proposed = ResizeRect {
            left: 100,
            top: 100,
            right: 568,
            bottom: 916,
        };
        let top_left = ratio_locked_rect(proposed, SizingEdge::TopLeft, Default::default());
        let bottom_right = ratio_locked_rect(proposed, SizingEdge::BottomRight, Default::default());
        assert_eq!(
            (top_left.right, top_left.bottom),
            (proposed.right, proposed.bottom)
        );
        assert_eq!(
            (bottom_right.left, bottom_right.top),
            (proposed.left, proposed.top)
        );
    }

    #[test]
    fn phone_region_radius_matches_the_css_clamp_at_common_scales() {
        let base = phone_region_geometry(
            WindowSize {
                width: 482,
                height: 924,
            },
            WindowPoint { x: 7, y: 0 },
            WindowSize {
                width: 468,
                height: 916,
            },
            96,
        )
        .expect("base geometry");
        let minimum = phone_region_geometry(
            WindowSize {
                width: 365,
                height: 695,
            },
            WindowPoint { x: 7, y: 0 },
            WindowSize {
                width: 351,
                height: 687,
            },
            96,
        )
        .expect("minimum geometry");
        let scaled = phone_region_geometry(
            WindowSize {
                width: 603,
                height: 1155,
            },
            WindowPoint { x: 9, y: 0 },
            WindowSize {
                width: 585,
                height: 1145,
            },
            120,
        )
        .expect("scaled geometry");
        assert_eq!(base.radius, 34);
        assert_eq!(minimum.radius, 26);
        assert_eq!(scaled.radius, 42);
        assert_eq!(scaled.resize_hit_thickness, 10);
        assert_eq!((base.offset_x, base.offset_y), (7, 0));
    }

    #[test]
    fn rounded_bezel_hit_test_covers_all_eight_resize_directions() {
        let geometry = PhoneRegionGeometry {
            offset_x: 7,
            offset_y: 4,
            width: 468,
            height: 916,
            radius: 34,
            resize_hit_thickness: 8,
        };
        for (point, expected) in [
            (WindowPoint { x: 9, y: 462 }, SizingEdge::Left),
            (WindowPoint { x: 472, y: 462 }, SizingEdge::Right),
            (WindowPoint { x: 241, y: 6 }, SizingEdge::Top),
            (WindowPoint { x: 241, y: 917 }, SizingEdge::Bottom),
            (WindowPoint { x: 17, y: 18 }, SizingEdge::TopLeft),
            (WindowPoint { x: 464, y: 18 }, SizingEdge::TopRight),
            (WindowPoint { x: 17, y: 905 }, SizingEdge::BottomLeft),
            (WindowPoint { x: 464, y: 905 }, SizingEdge::BottomRight),
        ] {
            assert_eq!(phone_resize_hit_test(point, geometry), Some(expected));
        }
    }

    #[test]
    fn rounded_bezel_hit_test_leaves_controls_and_clipped_corners_alone() {
        let geometry = PhoneRegionGeometry {
            offset_x: 7,
            offset_y: 4,
            width: 468,
            height: 916,
            radius: 34,
            resize_hit_thickness: 8,
        };
        assert_eq!(
            phone_resize_hit_test(WindowPoint { x: 457, y: 36 }, geometry),
            None
        );
        assert_eq!(
            phone_resize_hit_test(WindowPoint { x: 9, y: 6 }, geometry),
            None
        );
        assert_eq!(
            phone_resize_hit_test(WindowPoint { x: 241, y: 462 }, geometry),
            None
        );
    }

    #[test]
    fn compositor_silhouette_excludes_only_the_rounded_corner_cutouts() {
        let geometry = PhoneRegionGeometry {
            offset_x: 7,
            offset_y: 4,
            width: 468,
            height: 916,
            radius: 34,
            resize_hit_thickness: 8,
        };
        for point in [
            WindowPoint { x: 7, y: 4 },
            WindowPoint { x: 474, y: 4 },
            WindowPoint { x: 7, y: 919 },
            WindowPoint { x: 474, y: 919 },
        ] {
            assert!(!phone_contains_point(point, geometry));
        }
        for point in [
            WindowPoint { x: 41, y: 4 },
            WindowPoint { x: 241, y: 4 },
            WindowPoint { x: 7, y: 38 },
            WindowPoint { x: 241, y: 462 },
        ] {
            assert!(phone_contains_point(point, geometry));
        }
    }
}
