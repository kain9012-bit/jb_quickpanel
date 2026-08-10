use serde_json::{json, Value};
use std::ffi::c_void;
use std::io::{BufRead, BufReader, Write};
#[cfg(debug_assertions)]
use std::path::Path;
use std::path::PathBuf;
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex,
};
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager, PhysicalPosition, State, WindowEvent,
};

struct BackendProcess {
    child: Child,
    input: ChildStdin,
    output: BufReader<ChildStdout>,
    next_id: u64,
}

impl BackendProcess {
    fn request(&mut self, command: &str, args: Value) -> Result<Value, String> {
        self.next_id += 1;
        let request_id = self.next_id;
        let payload = json!({ "id": request_id, "command": command, "args": args });
        writeln!(self.input, "{payload}")
            .map_err(|error| format!("Python 서버에 요청을 보내지 못했습니다: {error}"))?;
        self.input
            .flush()
            .map_err(|error| format!("Python 서버 요청을 전송하지 못했습니다: {error}"))?;

        let mut line = String::new();
        let read = self
            .output
            .read_line(&mut line)
            .map_err(|error| format!("Python 서버 응답을 읽지 못했습니다: {error}"))?;
        if read == 0 {
            return Err(
                "Python COM 서버가 예기치 않게 종료되었습니다. 다시 실행해 주세요.".to_string(),
            );
        }
        let response: Value = serde_json::from_str(line.trim())
            .map_err(|error| format!("Python 서버 응답 형식이 올바르지 않습니다: {error}"))?;
        if response.get("id").and_then(Value::as_u64) != Some(request_id) {
            return Err("Python 서버 응답 순서가 맞지 않습니다.".to_string());
        }
        Ok(response)
    }
}

impl Drop for BackendProcess {
    fn drop(&mut self) {
        let request_id = self.next_id + 1;
        let payload = json!({
            "id": request_id,
            "command": "shutdown",
            "args": { "silent": true }
        });
        let _ = writeln!(self.input, "{payload}");
        let _ = self.input.flush();

        for _ in 0..40 {
            match self.child.try_wait() {
                Ok(Some(_)) => return,
                Ok(None) => std::thread::sleep(std::time::Duration::from_millis(50)),
                Err(_) => break,
            }
        }
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

#[derive(Default)]
struct BackendState {
    process: Arc<Mutex<Option<BackendProcess>>>,
}

struct RuntimeState {
    quitting: AtomicBool,
    close_to_tray: AtomicBool,
    always_on_top: AtomicBool,
}

#[cfg(debug_assertions)]
fn python_candidate(repository_root: &Path) -> PathBuf {
    let venv = repository_root
        .join(".venv")
        .join("Scripts")
        .join("python.exe");
    if venv.is_file() {
        venv
    } else {
        PathBuf::from("python")
    }
}

fn spawn_backend(app: &AppHandle) -> Result<BackendProcess, String> {
    #[cfg(debug_assertions)]
    let mut command = {
        let prototype_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .ok_or_else(|| "Tauri 앱 루트 경로를 확인하지 못했습니다.".to_string())?
            .to_path_buf();
        let repository_root = prototype_root
            .parent()
            .ok_or_else(|| "저장소 루트 경로를 확인하지 못했습니다.".to_string())?
            .to_path_buf();
        let server = prototype_root.join("backend").join("server.py");
        if !server.is_file() {
            return Err(format!(
                "Python COM 서버 파일이 없습니다: {}",
                server.display()
            ));
        }

        let mut command = Command::new(python_candidate(&repository_root));
        command.arg("-u").arg(&server).current_dir(&repository_root);
        command
    };

    #[cfg(not(debug_assertions))]
    let mut command = {
        let resource_dir = app
            .path()
            .resource_dir()
            .map_err(|error| format!("배포 리소스 경로를 확인하지 못했습니다: {error}"))?;
        let backend = resource_dir.join("binaries").join("jb_hwp_backend.exe");
        if !backend.is_file() {
            return Err(format!(
                "Python COM 백엔드 파일이 없습니다: {}",
                backend.display()
            ));
        }
        let mut command = Command::new(&backend);
        command.current_dir(resource_dir);
        command
    };

    #[cfg(debug_assertions)]
    let _ = app;

    command
        .env("PYTHONUTF8", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .env(
            "JB_TAURI_EXE",
            std::env::current_exe()
                .map(|path| path.to_string_lossy().into_owned())
                .unwrap_or_default(),
        )
        .env(
            "JB_TAURI_DEV",
            if cfg!(debug_assertions) { "1" } else { "0" },
        )
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }

    let mut child = command
        .spawn()
        .map_err(|error| format!("Python COM 서버를 시작하지 못했습니다: {error}"))?;
    let input = child
        .stdin
        .take()
        .ok_or_else(|| "Python 서버 입력 채널을 열지 못했습니다.".to_string())?;
    let output = child
        .stdout
        .take()
        .ok_or_else(|| "Python 서버 출력 채널을 열지 못했습니다.".to_string())?;
    Ok(BackendProcess {
        child,
        input,
        output: BufReader::new(output),
        next_id: 0,
    })
}

#[tauri::command]
async fn hwp_request(
    app: AppHandle,
    state: State<'_, BackendState>,
    command: String,
    args: Value,
) -> Result<Value, String> {
    if command.len() > 80
        || !command
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
    {
        return Err("올바르지 않은 명령 이름입니다.".to_string());
    }

    let process = Arc::clone(&state.process);
    tauri::async_runtime::spawn_blocking(move || {
        let mut guard = process
            .lock()
            .map_err(|_| "Python 서버 잠금을 열지 못했습니다.".to_string())?;
        if guard.is_none() {
            *guard = Some(spawn_backend(&app)?);
        }
        let result = guard
            .as_mut()
            .expect("backend initialized")
            .request(&command, args);
        if result.is_err() {
            *guard = None;
        }
        result
    })
    .await
    .map_err(|error| format!("Python 서버 작업 스레드가 중단되었습니다: {error}"))?
}

fn auto_format_cancel_path() -> PathBuf {
    std::env::temp_dir().join("jb_hwp_helper_tauri_auto_format.cancel")
}

#[tauri::command]
fn cancel_auto_format() -> Result<Value, String> {
    std::fs::write(auto_format_cancel_path(), b"cancel")
        .map_err(|error| format!("서식 자동 지정 중지 신호를 보내지 못했습니다: {error}"))?;
    Ok(json!({
        "ok": true,
        "message": "서식 자동 지정 중지를 요청했습니다."
    }))
}

fn show_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
    }
}

#[tauri::command]
fn set_window_preferences(
    app: AppHandle,
    state: State<'_, RuntimeState>,
    always_on_top: bool,
    close_to_tray: bool,
) -> Result<Value, String> {
    if let Some(window) = app.get_webview_window("main") {
        window
            .set_always_on_top(always_on_top)
            .map_err(|error| format!("항상 위 설정을 적용하지 못했습니다: {error}"))?;
        set_no_activate(&window, always_on_top);
    }
    state.close_to_tray.store(close_to_tray, Ordering::SeqCst);
    state.always_on_top.store(always_on_top, Ordering::SeqCst);
    Ok(json!({
        "ok": true,
        "always_on_top": always_on_top,
        "close_to_tray": close_to_tray
    }))
}

#[tauri::command]
fn set_window_input_mode(
    window: tauri::WebviewWindow,
    state: State<'_, RuntimeState>,
    enabled: bool,
) -> Result<Value, String> {
    let no_activate = !enabled && state.always_on_top.load(Ordering::SeqCst);
    set_no_activate(&window, no_activate);
    if enabled {
        let _ = window.set_focus();
    }
    Ok(json!({"ok": true, "input_mode": enabled}))
}

#[cfg(target_os = "windows")]
fn set_no_activate(window: &tauri::WebviewWindow, enabled: bool) {
    const GWL_EXSTYLE: i32 = -20;
    const WS_EX_NOACTIVATE: i32 = 0x08000000;
    const SWP_NOSIZE: u32 = 0x0001;
    const SWP_NOMOVE: u32 = 0x0002;
    const SWP_NOZORDER: u32 = 0x0004;
    const SWP_NOACTIVATE: u32 = 0x0010;
    const SWP_FRAMECHANGED: u32 = 0x0020;

    #[link(name = "user32")]
    unsafe extern "system" {
        fn GetWindowLongW(hwnd: *mut c_void, index: i32) -> i32;
        fn SetWindowLongW(hwnd: *mut c_void, index: i32, value: i32) -> i32;
        fn SetWindowPos(
            hwnd: *mut c_void,
            after: *mut c_void,
            x: i32,
            y: i32,
            cx: i32,
            cy: i32,
            flags: u32,
        ) -> i32;
    }

    if let Ok(hwnd) = window.hwnd() {
        let raw = hwnd.0 as *mut c_void;
        unsafe {
            let style = GetWindowLongW(raw, GWL_EXSTYLE);
            let next_style = if enabled {
                style | WS_EX_NOACTIVATE
            } else {
                style & !WS_EX_NOACTIVATE
            };
            SetWindowLongW(raw, GWL_EXSTYLE, next_style);
            SetWindowPos(
                raw,
                std::ptr::null_mut(),
                0,
                0,
                0,
                0,
                SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
            );
        }
    }
}

#[cfg(not(target_os = "windows"))]
fn set_no_activate(_window: &tauri::WebviewWindow, _enabled: bool) {}

fn dock_window(window: &tauri::WebviewWindow) {
    let Ok(Some(monitor)) = window.primary_monitor() else {
        return;
    };
    let Ok(size) = window.outer_size() else {
        return;
    };
    let monitor_position = monitor.position();
    let monitor_size = monitor.size();
    let x = monitor_position.x + monitor_size.width as i32 - size.width as i32 - 12;
    let y = monitor_position.y + 42;
    let _ = window.set_position(PhysicalPosition::new(x, y));
}
fn center_window(window: &tauri::WebviewWindow) {
    let Ok(Some(monitor)) = window.primary_monitor() else {
        return;
    };
    let Ok(size) = window.outer_size() else {
        return;
    };
    let monitor_position = monitor.position();
    let monitor_size = monitor.size();
    let x = monitor_position.x + ((monitor_size.width as i32 - size.width as i32) / 2).max(0);
    let y = monitor_position.y + ((monitor_size.height as i32 - size.height as i32) / 2).max(0);
    let _ = window.set_position(PhysicalPosition::new(x, y));
}

fn parse_saved_position(value: &str) -> Option<(i32, i32)> {
    let position = if let Some((x, y)) = value.split_once(',') {
        (x.trim().parse().ok()?, y.trim().parse().ok()?)
    } else {
        let (_size, coordinates) = value.split_once('+')?;
        let (x, y) = coordinates.split_once('+')?;
        (x.trim().parse().ok()?, y.trim().parse().ok()?)
    };
    if position.0 <= -10000 || position.1 <= -10000 {
        None
    } else {
        Some(position)
    }
}

#[cfg(test)]
mod position_tests {
    use super::parse_saved_position;

    #[test]
    fn parses_current_and_legacy_positions() {
        assert_eq!(parse_saved_position("1392,42"), Some((1392, 42)));
        assert_eq!(parse_saved_position("500x820+1392+42"), Some((1392, 42)));
    }

    #[test]
    fn rejects_windows_minimized_sentinel() {
        assert_eq!(parse_saved_position("-32000,-32000"), None);
    }
}

#[tauri::command]
fn apply_window_position(
    window: tauri::WebviewWindow,
    mode: String,
    last_geometry: String,
) -> Result<Value, String> {
    match mode.as_str() {
        "center" => center_window(&window),
        "last" => {
            if let Some((x, y)) = parse_saved_position(&last_geometry) {
                window
                    .set_position(PhysicalPosition::new(x, y))
                    .map_err(|error| format!("마지막 창 위치를 적용하지 못했습니다: {error}"))?;
            } else {
                dock_window(&window);
            }
        }
        _ => dock_window(&window),
    }
    let position = window
        .outer_position()
        .map_err(|error| format!("창 위치를 읽지 못했습니다: {error}"))?;
    Ok(json!({
        "ok": true,
        "last_geometry": format!("{},{}", position.x, position.y)
    }))
}

fn setup_desktop(app: &mut tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let show_item = MenuItem::with_id(app, "show", "열기", true, None::<&str>)?;
    let quit_item = MenuItem::with_id(app, "quit", "완전히 종료", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show_item, &quit_item])?;
    let mut tray = TrayIconBuilder::with_id("prototype-tray")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "show" => show_main_window(app),
            "quit" => {
                app.state::<RuntimeState>()
                    .quitting
                    .store(true, Ordering::SeqCst);
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_main_window(tray.app_handle());
            }
        });
    if let Some(icon) = app.default_window_icon() {
        tray = tray.icon(icon.clone());
    }
    tray.build(app)?;

    if let Some(window) = app.get_webview_window("main") {
        dock_window(&window);
        set_no_activate(&window, true);
        if std::env::args().any(|argument| argument == "--tray") {
            let _ = window.hide();
        }
    }
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(BackendState::default())
        .manage(RuntimeState {
            quitting: AtomicBool::new(false),
            close_to_tray: AtomicBool::new(false),
            always_on_top: AtomicBool::new(true),
        })
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            show_main_window(app)
        }))
        .setup(setup_desktop)
        .on_window_event(|window, event| {
            if window.label() != "main" {
                return;
            }
            if let WindowEvent::CloseRequested { api, .. } = event {
                let state = window.state::<RuntimeState>();
                if state.quitting.load(Ordering::SeqCst) {
                    return;
                }
                if state.close_to_tray.load(Ordering::SeqCst) {
                    api.prevent_close();
                    let _ = window.hide();
                } else {
                    state.quitting.store(true, Ordering::SeqCst);
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            hwp_request,
            cancel_auto_format,
            set_window_preferences,
            set_window_input_mode,
            apply_window_position
        ])
        .run(tauri::generate_context!())
        .expect("Tauri 앱 실행 실패");
}
