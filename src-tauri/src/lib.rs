use std::{
    net::{IpAddr, Ipv4Addr, SocketAddr, TcpListener, TcpStream},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};

use tauri::{Manager, Runtime};

struct ServerProcess(Mutex<Option<Child>>);

fn available_port() -> std::io::Result<u16> {
    let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0))?;
    Ok(listener.local_addr()?.port())
}

fn wait_for_server(port: u16) -> bool {
    let address = SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), port);
    let deadline = Instant::now() + Duration::from_secs(30);
    while Instant::now() < deadline {
        if TcpStream::connect_timeout(&address, Duration::from_millis(250)).is_ok() {
            return true;
        }
        thread::sleep(Duration::from_millis(150));
    }
    false
}

fn navigate_when_ready<R: Runtime>(handle: tauri::AppHandle<R>, port: u16) {
    thread::spawn(move || {
        if !wait_for_server(port) {
            eprintln!("General Rag local server did not start within 30 seconds.");
            return;
        }
        let navigation_handle = handle.clone();
        let _ = handle.run_on_main_thread(move || {
            let Some(window) = navigation_handle.get_webview_window("main") else {
                return;
            };
            let target = format!("http://127.0.0.1:{port}");
            match target.parse() {
                Ok(url) => {
                    if let Err(error) = window.navigate(url) {
                        eprintln!("Could not open General Rag: {error}");
                    }
                }
                Err(error) => eprintln!("Invalid local server URL: {error}"),
            }
        });
    });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            #[cfg(debug_assertions)]
            {
                let _ = app;
            }

            #[cfg(not(debug_assertions))]
            {
                let resources = app.path().resource_dir()?;
                let server_dir = resources.join("server");
                let node = resources.join("bin").join("node");
                let renderer = resources.join("bin").join("general-rag-renderer");
                let port = available_port()?;

                let child = Command::new(node)
                    .arg("server.js")
                    .current_dir(&server_dir)
                    .env("HOSTNAME", "127.0.0.1")
                    .env("PORT", port.to_string())
                    .env("JOURNAL_RENDERER", renderer)
                    .env("GENERAL_RAG_DESKTOP", "1")
                    .stdin(Stdio::null())
                    .stdout(Stdio::null())
                    .stderr(Stdio::null())
                    .spawn()?;

                app.manage(ServerProcess(Mutex::new(Some(child))));
                navigate_when_ready(app.handle().clone(), port);
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::Destroyed) {
                if let Some(state) = window.try_state::<ServerProcess>() {
                    if let Ok(mut process) = state.0.lock() {
                        if let Some(mut child) = process.take() {
                            let _ = child.kill();
                            let _ = child.wait();
                        }
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running General Rag");
}
