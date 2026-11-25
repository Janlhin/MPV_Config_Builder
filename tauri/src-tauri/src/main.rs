//! MPV Config Builder · Tauri 预览外壳（2026-11-16）
//!
//! 职责与 `electron/main.js` 对齐的那几条：
//!   1. spawn Python 后端，**走 stdio，不开任何端口**；
//!   2. 把页面的 invoke 请求按 `id` 配对转发给后端；
//!   3. 退出时先关 stdin 让后端自然收尾，1.5s 不退才 kill（否则会打断正在写的 mpv.conf）；
//!   4. 窗口加载的是**同一份** `webui/static`（由 tauri.conf.json 的 frontendDist 指过去），
//!      前端只有一份，不存在第二份会漂移的副本。
//!
//! 预览版**没有**做的（见 `DECISIONS.md` 2026-11-16）：安装包、自绘标题栏、原生菜单、单实例锁。
//!
//! ⚠ 别把窗口改成加载 `http://127.0.0.1:<port>` —— 那样就开了端口，而且 CSP 同源兜底全没。

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::collections::HashMap;
use std::fs::{File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc::{channel, Sender};
use std::sync::{Mutex, OnceLock};
use std::thread;
use std::time::{Duration, Instant};

use serde_json::{json, Value};
use tauri::menu::MenuBuilder;
use tauri::Manager;

/// 单条请求的上限。与 `main.js` 的 `call(req, timeoutMs = 120000)` 一致。
const REQUEST_TIMEOUT: Duration = Duration::from_secs(120);
/// 退出时留给后端收尾的时间（`main.js` 的 `shutdown(1500)`）。
const SHUTDOWN_GRACE: Duration = Duration::from_millis(1500);

struct Backend {
    stdin: Mutex<Option<ChildStdin>>,
    child: Mutex<Option<Child>>,
    pending: Mutex<HashMap<u64, Sender<Value>>>,
    dead: Mutex<Option<String>>,
    seq: AtomicU64,
}

static BACKEND: OnceLock<Backend> = OnceLock::new();
/// 单实例锁：进程活多久就占多久，退出自动释放（Windows 文件句柄）。
static INSTANCE_LOCK: OnceLock<File> = OnceLock::new();

fn backend() -> &'static Backend {
    BACKEND.get_or_init(|| Backend {
        stdin: Mutex::new(None),
        child: Mutex::new(None),
        pending: Mutex::new(HashMap::new()),
        dead: Mutex::new(None),
        seq: AtomicU64::new(0),
    })
}

/* ---------------------------------------------------------------- 路径
 *
 * 预览版有两种跑法：
 *   `cargo run`（源码）      exe 在 tauri/src-tauri/target/debug/ —— 往上找到含
 *                            webui/server.py 的那一层就是仓库根；
 *   打好的 exe 被搬走         用 MPVCB_ROOT 显式指定。
 * Python 解释器用 MPVCB_PYTHON 覆盖（默认 "python"）。
 * ⚠ 这里**不写死盘符**（verify.py 有一条检查会拦机器专用绝对路径）。
 */

fn repo_root() -> PathBuf {
    if let Ok(p) = std::env::var("MPVCB_ROOT") {
        let p = PathBuf::from(p);
        if p.is_dir() {
            return p;
        }
    }
    let mut dir = std::env::current_exe()
        .ok()
        .and_then(|e| e.parent().map(|p| p.to_path_buf()))
        .unwrap_or_else(|| PathBuf::from("."));
    for _ in 0..6 {
        if dir.join("webui").join("server.py").is_file() {
            return dir;
        }
        if !dir.pop() {
            break;
        }
    }
    std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
}

/* ------------------------------------------------------- 后端进程管理 */

/// 拿单实例锁。拿不到 = 已经有一个窗口在跑，第二个直接退出。
fn acquire_instance_lock() -> bool {
    let base = std::env::var("LOCALAPPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(|_| std::env::temp_dir());
    let dir = base.join("MPVConfigBuilder");
    let _ = std::fs::create_dir_all(&dir);
    let path = dir.join("instance.lock");
    let file = match OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(&path)
    {
        Ok(f) => f,
        Err(_) => return true, // 锁文件都建不了就别拦用户
    };
    match file.try_lock() {
        Ok(()) => {
            let _ = INSTANCE_LOCK.set(file);
            true
        }
        Err(_) => false,
    }
}

fn spawn_backend(app: &tauri::AppHandle) -> Result<(), String> {
    let root = repo_root();
    // 打包后：后端是和安装包一起装进来的 exe，优先用它；源码运行才回落到 python。
    let bundled = std::env::var("MPVCB_BACKEND")
        .ok()
        .map(PathBuf::from)
        .filter(|p| p.is_file())
        .or_else(|| {
            app.path()
                .resource_dir()
                .ok()
                .map(|d| d.join("backend").join("MPVConfigBuilderBackend.exe"))
                .filter(|p| p.is_file())
        })
        // 源码运行（cargo run / dev）：资源目录里没有，就去仓库的 dist 找
        .or_else(|| {
            let p = root
                .join("dist")
                .join("MPVConfigBuilderBackend")
                .join("MPVConfigBuilderBackend.exe");
            if p.is_file() {
                Some(p)
            } else {
                None
            }
        });

    let mut cmd = if let Some(exe) = bundled {
        let mut c = Command::new(exe);
        c.arg("--stdio");
        c
    } else {
        let server = root.join("webui").join("server.py");
        if !server.is_file() {
            return Err(format!(
                "找不到后端脚本：{}（可用 MPVCB_ROOT 指定仓库根）",
                server.display()
            ));
        }
        let python = std::env::var("MPVCB_PYTHON").unwrap_or_else(|_| "python".to_string());
        let mut c = Command::new(&python);
        c.arg(&server).arg("--stdio");
        c
    };

    cmd.current_dir(&root)
        .env("PYTHONIOENCODING", "utf-8")
        .env("PYTHONUTF8", "1")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    let program = cmd.get_program().to_string_lossy().to_string();
    let mut child = cmd
        .spawn()
        .map_err(|e| format!("启动后端失败（{program}）：{e}"))?;
    let stdin = child.stdin.take();
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "拿不到后端 stdout".to_string())?;
    let stderr = child.stderr.take();

    let be = backend();
    *be.stdin.lock().unwrap() = stdin;
    *be.child.lock().unwrap() = Some(child);
    *be.dead.lock().unwrap() = None;

    // stdout = 协议流，一行一条 JSON。非 JSON 行是 bug，打日志但别装作没看见。
    thread::spawn(move || {
        let reader = BufReader::new(stdout);
        for line in reader.lines() {
            let Ok(line) = line else { break };
            let s = line.trim();
            if s.is_empty() {
                continue;
            }
            match serde_json::from_str::<Value>(s) {
                Ok(v) => {
                    if let Some(id) = v.get("id").and_then(|x| x.as_u64()) {
                        if let Some(tx) = backend().pending.lock().unwrap().remove(&id) {
                            let _ = tx.send(v);
                        }
                    }
                }
                Err(_) => {
                    let cut: String = s.chars().take(200).collect();
                    eprintln!("[backend] stdout 出现非 JSON 行（协议被污染）：{cut}");
                }
            }
        }
        *backend().dead.lock().unwrap() = Some("后端已退出".to_string());
    });

    // stderr = 日志，原样转出来（**绝不解析**）
    if let Some(err) = stderr {
        thread::spawn(move || {
            for line in BufReader::new(err).lines().map_while(Result::ok) {
                eprintln!("[backend] {line}");
            }
        });
    }

    Ok(())
}

fn call_backend(req: Value) -> Value {
    let be = backend();
    if let Some(err) = be.dead.lock().unwrap().clone() {
        return json!({ "ok": false, "error": err });
    }

    let mut msg = match req {
        Value::Object(o) => Value::Object(o),
        _ => return json!({ "ok": false, "error": "请求必须是 JSON 对象" }),
    };
    if msg
        .get("path")
        .and_then(|p| p.as_str())
        .unwrap_or("")
        .is_empty()
    {
        return json!({ "ok": false, "error": "请求缺少 path" });
    }

    let id = be.seq.fetch_add(1, Ordering::SeqCst) + 1;
    let (tx, rx) = channel::<Value>();
    be.pending.lock().unwrap().insert(id, tx);
    msg["id"] = json!(id);

    let write_err = {
        let mut guard = be.stdin.lock().unwrap();
        match guard.as_mut() {
            Some(stdin) => {
                let line = format!("{msg}\n");
                stdin
                    .write_all(line.as_bytes())
                    .and_then(|_| stdin.flush())
                    .err()
                    .map(|e| e.to_string())
            }
            None => Some("后端 stdin 已关闭".to_string()),
        }
    };
    if let Some(err) = write_err {
        be.pending.lock().unwrap().remove(&id);
        return json!({ "ok": false, "error": format!("写入后端失败：{err}") });
    }

    match rx.recv_timeout(REQUEST_TIMEOUT) {
        Ok(mut v) => {
            if let Some(o) = v.as_object_mut() {
                o.remove("id");
            }
            v
        }
        Err(_) => {
            be.pending.lock().unwrap().remove(&id);
            json!({ "ok": false, "error": "后端超时（120000 ms）" })
        }
    }
}

/// 先礼后兵：关 stdin 让后端读到 EOF 自己退，等 1.5s，不退才 kill。
fn shutdown_backend() {
    let be = backend();
    drop(be.stdin.lock().unwrap().take()); // 关管道 = 后端 for-line 读到 EOF

    let deadline = Instant::now() + SHUTDOWN_GRACE;
    loop {
        let exited = {
            let mut guard = be.child.lock().unwrap();
            match guard.as_mut() {
                Some(child) => matches!(child.try_wait(), Ok(Some(_))),
                None => true,
            }
        };
        if exited {
            return;
        }
        if Instant::now() >= deadline {
            break;
        }
        thread::sleep(Duration::from_millis(50));
    }
    if let Some(mut child) = be.child.lock().unwrap().take() {
        let _ = child.kill();
    }
}

/* ------------------------------------------------------------- 窗口 */

/// 页面从 Tauri 的资源协议加载，`api.js` 只看 `__MPVCB_INVOKE__` 在不在——
/// 在就走这条桥（stdio），不在才 fetch。所以这里注入一个同名函数即可，
/// 9 个页面一行都不用改。
const INIT_SCRIPT: &str = r#"
(function () {
  window.__MPVCB_INVOKE__ = function (req) {
    return window.__TAURI_INTERNALS__.invoke('mpvcb_invoke', { req: req });
  };
})();
"#;

#[tauri::command]
async fn mpvcb_invoke(req: Value) -> Value {
    match tauri::async_runtime::spawn_blocking(move || call_backend(req)).await {
        Ok(v) => v,
        Err(e) => json!({ "ok": false, "error": format!("内部错误：{e}") }),
    }
}

#[tauri::command]
fn mpvcb_window(window: tauri::WebviewWindow, action: String) -> Result<(), String> {
    match action.as_str() {
        "min" => window.minimize().map_err(|e| e.to_string()),
        "max" => {
            if window.is_maximized().unwrap_or(false) {
                window.unmaximize().map_err(|e| e.to_string())
            } else {
                window.maximize().map_err(|e| e.to_string())
            }
        }
        "close" => window.close().map_err(|e| e.to_string()),
        _ => Ok(()),
    }
}

/// 标题栏 ☰ 打开原生菜单（自绘标题栏 + 原生菜单并存的办法：
/// Windows 的无边框窗口没有菜单栏位置，改成弹出原生菜单）。
#[tauri::command]
fn mpvcb_menu(window: tauri::WebviewWindow) -> Result<(), String> {
    let menu = MenuBuilder::new(&window)
        .text("reload", "刷新")
        .text("help", "快捷键帮助")
        .separator()
        .text("quit", "退出")
        .build()
        .map_err(|e| e.to_string())?;
    window.popup_menu(&menu).map_err(|e| e.to_string())
}

#[tauri::command]
fn mpvcb_info() -> Value {
    let be = backend();
    let dead = be.dead.lock().unwrap().clone();
    json!({
        "tauri": true,
        "version": env!("CARGO_PKG_VERSION"),
        "backendAlive": dead.is_none(),
        "backendError": dead,
    })
}

fn main() {
    if !acquire_instance_lock() {
        eprintln!("[instance] 已经有一个 MPV Config Builder 在运行，本次启动退出");
        return;
    }
    let ctx = tauri::generate_context!();
    tauri::Builder::default()
        // v3 的运行时是显式选的（拆包成 tauri-runtime-wry）。不写这一行，
        // build 直接 RuntimeNotConfigured —— 不会走到 setup。
        .runtime(tauri_runtime_wry::Wry::default())
        .invoke_handler(tauri::generate_handler![
            mpvcb_invoke,
            mpvcb_info,
            mpvcb_window,
            mpvcb_menu
        ])
        .setup(|app| {
            if let Err(err) = spawn_backend(app.handle()) {
                eprintln!("[backend] 启动失败：{err}");
            }
            // 原生菜单：无边框窗口没有菜单栏位置，由标题栏 ☰ 弹出；
            // 事件统一在这里接，菜单项 ID 与 mpvcb_menu 里保持一致。
            app.on_menu_event(|app, event| {
                let id = event.id().0.as_str();
                match id {
                    "reload" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.eval("location.reload()");
                        }
                    }
                    "help" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.eval(
                                "document.dispatchEvent(new KeyboardEvent('keydown',{key:'?'}))",
                            );
                        }
                    }
                    "quit" => app.exit(0),
                    _ => {}
                }
            });
            tauri::WebviewWindowBuilder::new(
                app,
                "main",
                tauri::WebviewUrl::App(PathBuf::from("index.html")),
            )
            .title("MPV Config Builder")
            .inner_size(1280.0, 860.0)
            .min_inner_size(900.0, 600.0)
            .decorations(false)
            .center()
            .initialization_script(INIT_SCRIPT)
            .build()?;
            Ok(())
        })
        .build(ctx)
        .expect("Tauri 应用初始化失败")
        .run(|_handle, event| {
            if let tauri::RunEvent::Exit = event {
                shutdown_backend();
            }
        });
}
