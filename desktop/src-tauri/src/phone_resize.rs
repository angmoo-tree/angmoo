use tauri::WebviewWindow;

use crate::window_policy::PHONE_ASPECT_RATIO;

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
    use super::{NonClientInsets, ResizeRect, SizingEdge, ratio_locked_rect};
    use windows::Win32::{
        Foundation::{HWND, LPARAM, LRESULT, RECT, WPARAM},
        UI::{
            Shell::{DefSubclassProc, RemoveWindowSubclass, SetWindowSubclass},
            WindowsAndMessaging::{
                GetClientRect, GetWindowRect, WM_NCDESTROY, WM_SIZING, WMSZ_BOTTOM,
                WMSZ_BOTTOMLEFT, WMSZ_BOTTOMRIGHT, WMSZ_LEFT, WMSZ_RIGHT, WMSZ_TOP, WMSZ_TOPLEFT,
                WMSZ_TOPRIGHT,
            },
        },
    };

    const PHONE_ASPECT_SUBCLASS_ID: usize = 0x414E_474D_4F4F;

    pub fn install(window: &tauri::WebviewWindow) -> Result<(), String> {
        let hwnd = window.hwnd().map_err(|error| error.to_string())?;
        let attached = unsafe {
            SetWindowSubclass(
                hwnd,
                Some(phone_aspect_subclass),
                PHONE_ASPECT_SUBCLASS_ID,
                0,
            )
        };
        if attached.as_bool() {
            Ok(())
        } else {
            Err(windows::core::Error::from_win32().to_string())
        }
    }

    unsafe extern "system" fn phone_aspect_subclass(
        hwnd: HWND,
        message: u32,
        wparam: WPARAM,
        lparam: LPARAM,
        _: usize,
        _: usize,
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
        } else if message == WM_NCDESTROY {
            let _ = unsafe {
                RemoveWindowSubclass(hwnd, Some(phone_aspect_subclass), PHONE_ASPECT_SUBCLASS_ID)
            };
        }

        unsafe { DefSubclassProc(hwnd, message, wparam, lparam) }
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
}
