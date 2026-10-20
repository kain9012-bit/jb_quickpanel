use serde_json::{json, Value};
use std::sync::Mutex;
use tauri::{Manager, State};

#[derive(Default)]
pub struct LayoutState(Mutex<bool>);

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
#[repr(C)]
struct Rect {
    left: i32,
    top: i32,
    right: i32,
    bottom: i32,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
#[repr(C)]
struct Point {
    x: i32,
    y: i32,
}

#[derive(Clone, Copy, Debug, Default)]
#[repr(C)]
struct Placement {
    length: u32,
    flags: u32,
    show: u32,
    minimum: Point,
    maximum: Point,
    normal: Rect,
}

#[derive(Clone, Copy)]
struct SavedWindow {
    handle: usize,
    pid: u32,
    placement: Placement,
}

struct SavedLayout {
    helper: SavedWindow,
    hwp: SavedWindow,
}

fn split_rectangles(
    work: Rect,
    helper_width: i32,
    min_hwp_width: i32,
    min_height: i32,
) -> Result<(Rect, Rect), String> {
    let width = work.right - work.left;
    let height = work.bottom - work.top;
    if helper_width <= 0
        || min_hwp_width <= 0
        || height < min_height
        || width - helper_width < min_hwp_width
    {
        return Err(
            "두 창을 나란히 배치하기에는 화면이 좁습니다. 화면 해상도나 배율을 확인하세요.".into(),
        );
    }
    let divider = work.right - helper_width;
    Ok((
        Rect {
            right: divider,
            ..work
        },
        Rect {
            left: divider,
            ..work
        },
    ))
}

#[cfg(target_os = "windows")]
mod native {
    use super::*;
    use std::{
        ffi::c_void,
        time::{Duration, Instant},
    };
    type Handle = *mut c_void;
    #[repr(C)]
    struct MonitorInfo {
        size: u32,
        monitor: Rect,
        work: Rect,
        flags: u32,
    }

    #[link(name = "user32")]
    unsafe extern "system" {
        fn IsWindow(hwnd: Handle) -> i32;
        fn IsWindowVisible(hwnd: Handle) -> i32;
        fn IsWindowEnabled(hwnd: Handle) -> i32;
        fn IsIconic(hwnd: Handle) -> i32;
        fn IsZoomed(hwnd: Handle) -> i32;
        fn GetWindowThreadProcessId(hwnd: Handle, pid: *mut u32) -> u32;
        fn GetWindowRect(hwnd: Handle, rect: *mut Rect) -> i32;
        fn GetWindowPlacement(hwnd: Handle, placement: *mut Placement) -> i32;
        fn SetWindowPlacement(hwnd: Handle, placement: *const Placement) -> i32;
        fn ShowWindowAsync(hwnd: Handle, command: i32) -> i32;
        fn SetWindowPos(
            hwnd: Handle,
            after: Handle,
            x: i32,
            y: i32,
            width: i32,
            height: i32,
            flags: u32,
        ) -> i32;
        fn MonitorFromWindow(hwnd: Handle, flags: u32) -> Handle;
        fn GetMonitorInfoW(monitor: Handle, info: *mut MonitorInfo) -> i32;
    }

    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn OpenProcess(access: u32, inherit: i32, pid: u32) -> Handle;
        fn QueryFullProcessImageNameW(
            process: Handle,
            flags: u32,
            path: *mut u16,
            size: *mut u32,
        ) -> i32;
        fn CloseHandle(object: Handle) -> i32;
    }

    fn handle(value: usize) -> Handle {
        value as Handle
    }

    pub fn identity(hwnd: usize) -> Result<u32, String> {
        let mut pid = 0;
        unsafe {
            if hwnd == 0
                || IsWindow(handle(hwnd)) == 0
                || GetWindowThreadProcessId(handle(hwnd), &mut pid) == 0
            {
                return Err("배치할 창을 찾지 못했습니다.".into());
            }
        }
        Ok(pid)
    }

    pub fn visible(hwnd: usize) -> bool {
        unsafe { IsWindowVisible(handle(hwnd)) != 0 }
    }

    pub fn enabled(hwnd: usize) -> bool {
        unsafe { IsWindowEnabled(handle(hwnd)) != 0 }
    }

    pub fn is_hwp_process(pid: u32) -> bool {
        unsafe {
            let process = OpenProcess(0x1000, 0, pid);
            if process.is_null() {
                return false;
            }
            let mut path = vec![0u16; 32768];
            let mut size = path.len() as u32;
            let found = QueryFullProcessImageNameW(process, 0, path.as_mut_ptr(), &mut size) != 0;
            CloseHandle(process);
            found
                && String::from_utf16_lossy(&path[..size as usize])
                    .to_lowercase()
                    .ends_with("\\hwp.exe")
        }
    }

    pub fn rectangle(hwnd: usize) -> Result<Rect, String> {
        let mut rect = Rect::default();
        if unsafe { GetWindowRect(handle(hwnd), &mut rect) } == 0 {
            return Err("창 위치를 읽지 못했습니다.".into());
        }
        Ok(rect)
    }

    pub fn work_area(hwnd: usize) -> Result<Rect, String> {
        let mut info = MonitorInfo {
            size: std::mem::size_of::<MonitorInfo>() as u32,
            monitor: Rect::default(),
            work: Rect::default(),
            flags: 0,
        };
        unsafe {
            let monitor = MonitorFromWindow(handle(hwnd), 2);
            if monitor.is_null() || GetMonitorInfoW(monitor, &mut info) == 0 {
                return Err("한글 창이 있는 화면의 작업 영역을 읽지 못했습니다.".into());
            }
        }
        Ok(info.work)
    }

    pub fn save(hwnd: usize) -> Result<SavedWindow, String> {
        let pid = identity(hwnd)?;
        let mut placement = Placement {
            length: std::mem::size_of::<Placement>() as u32,
            ..Placement::default()
        };
        if unsafe { GetWindowPlacement(handle(hwnd), &mut placement) } == 0 {
            return Err("원래 창 배치를 보관하지 못했습니다.".into());
        }
        Ok(SavedWindow {
            handle: hwnd,
            pid,
            placement,
        })
    }

    pub fn matches(saved: SavedWindow) -> bool {
        identity(saved.handle).ok() == Some(saved.pid)
    }

    fn wait_for(mut check: impl FnMut() -> bool) -> bool {
        let deadline = Instant::now() + Duration::from_millis(1500);
        loop {
            if check() {
                return true;
            }
            if Instant::now() >= deadline {
                return false;
            }
            std::thread::sleep(Duration::from_millis(20));
        }
    }

    pub fn place(saved: SavedWindow, rect: Rect) -> Result<(), String> {
        if !matches(saved) {
            return Err("배치할 창이 닫혔거나 변경되었습니다.".into());
        }
        unsafe {
            if IsIconic(handle(saved.handle)) != 0 || IsZoomed(handle(saved.handle)) != 0 {
                // Restore size without taking keyboard focus or changing document selection.
                if ShowWindowAsync(handle(saved.handle), 4) == 0 {
                    return Err("창의 최대화 상태를 해제하지 못했습니다.".into());
                }
            }
        }
        if !wait_for(|| unsafe {
            IsIconic(handle(saved.handle)) == 0 && IsZoomed(handle(saved.handle)) == 0
        }) {
            return Err("창의 배치 준비가 완료되지 않았습니다.".into());
        }
        let flags = 0x0004 | 0x0010 | 0x4000; // NOZORDER | NOACTIVATE | ASYNCWINDOWPOS
        if unsafe {
            SetWindowPos(
                handle(saved.handle),
                std::ptr::null_mut(),
                rect.left,
                rect.top,
                rect.right - rect.left,
                rect.bottom - rect.top,
                flags,
            )
        } == 0
        {
            return Err("창 위치와 크기를 변경하지 못했습니다.".into());
        }
        if !wait_for(|| matches(saved) && rectangle(saved.handle).ok() == Some(rect)) {
            return Err("창 위치나 크기가 요청한 배치와 일치하지 않습니다.".into());
        }
        Ok(())
    }

    pub fn restore(saved: SavedWindow) -> Result<(), String> {
        if !matches(saved) {
            return Err("복원할 창이 닫혔거나 변경되었습니다.".into());
        }
        // WINDOWPLACEMENT uses workspace coordinates; never pass them to SetWindowPos.
        let placement = Placement {
            flags: saved.placement.flags | 4,
            ..saved.placement
        };
        if unsafe { SetWindowPlacement(handle(saved.handle), &placement) } == 0 {
            return Err("원래 창 배치를 복원하지 못했습니다.".into());
        }
        if !wait_for(|| {
            save(saved.handle).is_ok_and(|current| {
                current.pid == saved.pid
                    && current.placement.show == saved.placement.show
                    && current.placement.normal == saved.placement.normal
            })
        }) {
            return Err("원래 창 배치가 복원되었는지 확인하지 못했습니다.".into());
        }
        Ok(())
    }
}

#[cfg(target_os = "windows")]
fn restore_pair(saved: &SavedLayout) -> Result<bool, String> {
    let hwp_alive = native::matches(saved.hwp);
    let hwp_result = if hwp_alive {
        native::restore(saved.hwp)
    } else {
        Ok(())
    };
    let helper_result = native::restore(saved.helper);
    hwp_result.and(helper_result)?;
    Ok(hwp_alive)
}

#[tauri::command]
pub fn window_layout_state(state: State<'_, LayoutState>) -> Result<Value, String> {
    let arranged = state
        .0
        .lock()
        .map_err(|_| "창 배치 상태를 읽지 못했습니다.")?;
    Ok(json!({"active": *arranged}))
}

#[cfg(target_os = "windows")]
fn place_pair(pair: &SavedLayout, hwp_rect: Rect, helper_rect: Rect) -> Result<(), String> {
    let result = native::place(pair.hwp, hwp_rect)
        .and_then(|_| native::place(pair.helper, helper_rect))
        .and_then(|_| {
            if native::rectangle(pair.hwp.handle)? == hwp_rect
                && native::rectangle(pair.helper.handle)? == helper_rect
            {
                Ok(())
            } else {
                Err("두 창의 최종 배치가 일치하지 않습니다.".into())
            }
        });
    if let Err(error) = result {
        return Err(if restore_pair(pair).is_ok() {
            format!("{error} 직전 배치로 되돌렸습니다.")
        } else {
            format!("{error} 직전 배치로 되돌리지 못했습니다. 두 창을 확인한 뒤 다시 배치하세요.")
        });
    }
    Ok(())
}

#[tauri::command]
#[cfg(target_os = "windows")]
pub fn arrange_hwp_windows(
    window: tauri::WebviewWindow,
    state: State<'_, LayoutState>,
    hwp_hwnd: u64,
    hwp_pid: u32,
) -> Result<Value, String> {
    let mut arranged = state
        .0
        .lock()
        .map_err(|_| "창 배치 상태를 읽지 못했습니다.")?;
    let helper = window
        .hwnd()
        .map_err(|_| "JB에듀 폼 창을 찾지 못했습니다.")?
        .0 as usize;
    let hwp = usize::try_from(hwp_hwnd).map_err(|_| "한글 창 정보가 올바르지 않습니다.")?;
    if helper == hwp
        || hwp_pid == 0
        || native::identity(hwp)? != hwp_pid
        || !native::visible(hwp)
        || !native::is_hwp_process(hwp_pid)
    {
        return Err("배치할 한글 창이 닫혔거나 변경되었습니다. 다시 연결하세요.".into());
    }
    if !native::enabled(hwp) {
        return Err("한글의 대화상자를 닫은 뒤 다시 시도하세요.".into());
    }
    let work = native::work_area(hwp)?;
    let target_scale = window
        .available_monitors()
        .map_err(|_| "화면 배율을 읽지 못했습니다.")?
        .iter()
        .find(|monitor| {
            let position = monitor.position();
            let size = monitor.size();
            work.left >= position.x
                && work.top >= position.y
                && work.right <= position.x + size.width as i32
                && work.bottom <= position.y + size.height as i32
        })
        .map(|monitor| monitor.scale_factor())
        .ok_or("한글 창이 있는 화면의 배율을 읽지 못했습니다.")?;
    let source_scale = window
        .scale_factor()
        .map_err(|_| "JB에듀 폼 배율을 읽지 못했습니다.")?;
    let outer = window
        .outer_size()
        .map_err(|_| "JB에듀 폼 크기를 읽지 못했습니다.")?;
    let inner = window
        .inner_size()
        .map_err(|_| "JB에듀 폼 크기를 읽지 못했습니다.")?;
    let frame_height = outer.height.saturating_sub(inner.height) as f64 / source_scale;
    let minimum_height = window
        .app_handle()
        .config()
        .app
        .windows
        .iter()
        .find(|config| config.label == window.label())
        .and_then(|config| config.min_height)
        .unwrap_or(560.0);
    let helper_width = (outer.width as f64 / source_scale * target_scale).round() as i32;
    let (hwp_rect, helper_rect) = split_rectangles(
        work,
        helper_width,
        (600.0 * target_scale).ceil() as i32,
        ((minimum_height + frame_height) * target_scale).ceil() as i32,
    )?;
    let pair = SavedLayout {
        helper: native::save(helper)?,
        hwp: native::save(hwp)?,
    };
    if pair.hwp.pid != hwp_pid {
        return Err("배치할 한글 창이 변경되었습니다. 다시 연결하세요.".into());
    }
    place_pair(&pair, hwp_rect, helper_rect)?;
    *arranged = true;
    Ok(json!({"active": true, "message": "한글과 JB에듀 폼을 나란히 배치했습니다."}))
}

#[tauri::command]
#[cfg(not(target_os = "windows"))]
pub fn arrange_hwp_windows(
    _window: tauri::WebviewWindow,
    _state: State<'_, LayoutState>,
    _hwp_hwnd: u64,
    _hwp_pid: u32,
) -> Result<Value, String> {
    Err("창 분할 배치는 Windows에서만 사용할 수 있습니다.".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn splits_work_area_without_covering_taskbar() {
        let work = Rect {
            left: 0,
            top: 0,
            right: 1920,
            bottom: 1040,
        };
        let (hwp, helper) = split_rectangles(work, 516, 600, 598).unwrap();
        assert_eq!(
            hwp,
            Rect {
                left: 0,
                top: 0,
                right: 1404,
                bottom: 1040
            }
        );
        assert_eq!(
            helper,
            Rect {
                left: 1404,
                top: 0,
                right: 1920,
                bottom: 1040
            }
        );
    }

    #[test]
    fn supports_negative_monitor_coordinates_and_top_or_left_taskbars() {
        let work = Rect {
            left: -1840,
            top: 45,
            right: 0,
            bottom: 1080,
        };
        let (hwp, helper) = split_rectangles(work, 645, 750, 748).unwrap();
        assert_eq!(hwp.left, -1840);
        assert_eq!(helper.left, -645);
        assert_eq!(helper.top, 45);
        assert_eq!(hwp.bottom, 1080);
    }

    #[test]
    fn rejects_narrow_or_short_screens_before_moving_any_window() {
        assert!(split_rectangles(
            Rect {
                right: 1024,
                bottom: 768,
                ..Rect::default()
            },
            516,
            600,
            598
        )
        .is_err());
        assert!(split_rectangles(
            Rect {
                right: 1920,
                bottom: 700,
                ..Rect::default()
            },
            774,
            900,
            897
        )
        .is_err());
    }

    #[test]
    #[ignore = "Requires an isolated HWP instance supplied by verify-window-layout.py"]
    #[cfg(target_os = "windows")]
    fn live_private_hwp_layout_and_restore() {
        use std::ffi::c_void;
        #[link(name = "user32")]
        unsafe extern "system" {
            fn CreateWindowExW(
                ex: u32,
                class: *const u16,
                title: *const u16,
                style: u32,
                x: i32,
                y: i32,
                width: i32,
                height: i32,
                parent: *mut c_void,
                menu: *mut c_void,
                instance: *mut c_void,
                param: *mut c_void,
            ) -> *mut c_void;
            fn DestroyWindow(window: *mut c_void) -> i32;
            fn GetForegroundWindow() -> *mut c_void;
            fn SetWindowPlacement(window: *mut c_void, placement: *const Placement) -> i32;
        }
        struct OwnedWindow(*mut c_void);
        impl Drop for OwnedWindow {
            fn drop(&mut self) {
                unsafe {
                    DestroyWindow(self.0);
                }
            }
        }
        let target: usize = std::env::var("JB_LAYOUT_TEST_HWP_HWND")
            .expect("Private HWND required")
            .parse()
            .unwrap();
        let pid: u32 = std::env::var("JB_LAYOUT_TEST_HWP_PID")
            .expect("Private PID required")
            .parse()
            .unwrap();
        assert_eq!(native::identity(target).unwrap(), pid);
        assert!(native::is_hwp_process(pid));
        let class: Vec<u16> = "STATIC\0".encode_utf16().collect();
        let window = unsafe {
            CreateWindowExW(
                0x08000000,
                class.as_ptr(),
                class.as_ptr(),
                0x00CF0000,
                50,
                70,
                516,
                780,
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
            )
        };
        assert!(!window.is_null());
        let helper = OwnedWindow(window);
        let work = native::work_area(target).unwrap();
        let pair = SavedLayout {
            helper: native::save(helper.0 as usize).unwrap(),
            hwp: native::save(target).unwrap(),
        };
        let (hwp_rect, helper_rect) = split_rectangles(work, 516, 600, 598).unwrap();
        let foreground = unsafe { GetForegroundWindow() };
        place_pair(&pair, hwp_rect, helper_rect).unwrap();
        assert_eq!(native::rectangle(target).unwrap(), hwp_rect);
        assert_eq!(native::rectangle(helper.0 as usize).unwrap(), helper_rect);
        assert_eq!(
            unsafe { GetForegroundWindow() },
            foreground,
            "Layout must not steal focus"
        );
        let shifted = Rect {
            left: helper_rect.left - 40,
            right: helper_rect.right - 40,
            top: helper_rect.top + 20,
            bottom: helper_rect.bottom + 20,
        };
        native::place(pair.helper, shifted).unwrap();
        let repeat = SavedLayout {
            helper: native::save(helper.0 as usize).unwrap(),
            hwp: native::save(target).unwrap(),
        };
        place_pair(&repeat, hwp_rect, helper_rect).unwrap();
        assert_eq!(native::rectangle(helper.0 as usize).unwrap(), helper_rect);
        assert_eq!(native::rectangle(target).unwrap(), hwp_rect);
        // Error rollback uses this click's placement, not the first click's placement.
        assert!(restore_pair(&repeat).unwrap());
        assert_eq!(native::rectangle(helper.0 as usize).unwrap(), shifted);
        place_pair(&repeat, hwp_rect, helper_rect).unwrap();
        assert!(restore_pair(&pair).unwrap());
        assert_eq!(
            native::save(target).unwrap().placement.normal,
            pair.hwp.placement.normal
        );
        assert_eq!(
            native::save(helper.0 as usize).unwrap().placement.normal,
            pair.helper.placement.normal
        );
        let normal = native::save(target).unwrap();
        let maximized = Placement {
            show: 3,
            flags: 4,
            ..normal.placement
        };
        assert_ne!(
            unsafe { SetWindowPlacement(target as *mut c_void, &maximized) },
            0
        );
        std::thread::sleep(std::time::Duration::from_millis(200));
        let maximized = native::save(target).unwrap();
        assert_eq!(maximized.placement.show, 3);
        native::place(maximized, hwp_rect).unwrap();
        native::restore(maximized).unwrap();
        assert_eq!(native::save(target).unwrap().placement.show, 3);
        native::restore(normal).unwrap();
        println!("Private HWP: repeated alignment and per-click rollback verified, normal/maximized placement preserved; no document edit commands");
    }
}
