//! 교육청 게시글에서 새 버전을 확인하고 서명된 NSIS 설치본을 적용한다.

use base64::{engine::general_purpose::STANDARD, Engine as _};
use minisign_verify::{PublicKey, Signature};
use semver::Version;
use serde::{Deserialize, Serialize};
use std::{
    collections::HashMap,
    fs,
    io::{Cursor, Read},
    path::{Path, PathBuf},
    process::Command,
    time::Duration,
};
use tauri::{AppHandle, Manager};
use zip::ZipArchive;

const MARKER: &str = "[업데이트정보]";
const MAX_ARCHIVE_BYTES: u64 = 350 * 1024 * 1024;
const MAX_INSTALLER_BYTES: u64 = 300 * 1024 * 1024;

#[derive(Clone, Debug, Deserialize)]
struct UpdateConfigFile {
    app: UpdateConfig,
}

#[derive(Clone, Debug, Deserialize)]
struct UpdateConfig {
    #[serde(default)]
    enabled: bool,
    #[serde(default)]
    app_id: String,
    #[serde(default)]
    post_url: String,
    #[serde(default)]
    public_key: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct BoardUpdate {
    version: String,
    download: String,
    signature: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct BoardUpdateCheck {
    configured: bool,
    current: String,
    update: Option<BoardUpdate>,
    message: String,
}

fn config_path(app: &AppHandle) -> Result<PathBuf, String> {
    #[cfg(debug_assertions)]
    {
        let dev_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap_or_else(|| Path::new("."))
            .join("update-config.json");
        if dev_path.is_file() {
            return Ok(dev_path);
        }
    }

    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|error| format!("리소스 폴더를 찾지 못했습니다: {error}"))?;
    for candidate in [
        resource_dir.join("update-config.json"),
        resource_dir.join("_up_").join("update-config.json"),
    ] {
        if candidate.is_file() {
            return Ok(candidate);
        }
    }
    Err("업데이트 설정 파일을 찾지 못했습니다.".to_string())
}

fn read_config(app: &AppHandle) -> Result<UpdateConfig, String> {
    let raw = fs::read_to_string(config_path(app)?)
        .map_err(|error| format!("업데이트 설정을 읽지 못했습니다: {error}"))?;
    let parsed: UpdateConfigFile =
        serde_json::from_str(&raw).map_err(|error| format!("업데이트 설정 형식 오류: {error}"))?;
    Ok(parsed.app)
}

fn unescape(text: &str) -> String {
    text.replace("&amp;", "&")
        .replace("&quot;", "\"")
        .replace("&#39;", "'")
        .replace("&apos;", "'")
        .replace("&nbsp;", " ")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
}

fn marker_segments(html: &str) -> Vec<String> {
    fn ends_line(tag: &str) -> bool {
        let name: String = tag
            .trim_start_matches('<')
            .trim_start_matches('/')
            .chars()
            .take_while(|character| character.is_ascii_alphanumeric())
            .collect();
        matches!(
            name.as_str(),
            "br" | "p" | "div" | "td" | "tr" | "li" | "table" | "body" | "h1" | "h2" | "h3"
        )
    }

    let mut found = Vec::new();
    let mut rest = html;
    while let Some(at) = rest.find(MARKER) {
        let mut cursor = &rest[at + MARKER.len()..];
        let mut text = String::new();
        loop {
            let Some(stop) = cursor
                .find(|character: char| character == '<' || character == '\r' || character == '\n')
            else {
                text.push_str(cursor);
                cursor = "";
                break;
            };
            text.push_str(&cursor[..stop]);
            let tail = &cursor[stop..];
            if !tail.starts_with('<') {
                cursor = tail;
                break;
            }
            let Some(close) = tail.find('>') else {
                cursor = "";
                break;
            };
            let is_end = ends_line(&tail[..close].to_ascii_lowercase());
            cursor = &tail[close + 1..];
            if is_end {
                break;
            }
        }
        found.push(text);
        rest = cursor;
    }
    found
}

fn parse_fields(segment: &str) -> HashMap<String, String> {
    let mut fields = HashMap::new();
    for part in unescape(segment).split('|') {
        if let Some((key, value)) = part.split_once('=') {
            fields.insert(key.trim().to_string(), value.trim().to_string());
        }
    }
    fields
}

fn attachment_links(html: &str) -> Vec<(String, String)> {
    let mut links = Vec::new();
    let mut rest = html;
    while let Some(at) = rest.find("href=\"") {
        let after = &rest[at + 6..];
        let Some(quote) = after.find('"') else {
            break;
        };
        let href = &after[..quote];
        let tail = &after[quote..];
        if href.contains("download.jbe") {
            let tag = &tail[..tail.find('>').unwrap_or(0)];
            let name = tag
                .find("title=\"")
                .and_then(|title_at| {
                    let value = &tag[title_at + 7..];
                    value.find('"').map(|end| value[..end].to_string())
                })
                .unwrap_or_default();
            links.push((unescape(href), unescape(&name)));
        }
        rest = tail;
    }
    links
}

fn absolute(href: &str, post_url: &str) -> String {
    if href.starts_with("http://") || href.starts_with("https://") {
        return href.to_string();
    }
    let origin = post_url
        .split_once("://")
        .map(|(scheme, rest)| {
            let host = rest.split('/').next().unwrap_or(rest);
            format!("{scheme}://{host}")
        })
        .unwrap_or_default();
    if href.starts_with('/') {
        format!("{origin}{href}")
    } else {
        format!("{origin}/{href}")
    }
}

fn pick_attachment(html: &str, post_url: &str, hint: &str) -> Result<String, String> {
    let zips: Vec<(String, String)> = attachment_links(html)
        .into_iter()
        .filter(|(_, name)| name.to_lowercase().ends_with(".zip"))
        .filter(|(_, name)| hint.is_empty() || name.contains(hint))
        .collect();
    match zips.len() {
        0 if hint.is_empty() => Err("게시글에 첨부된 ZIP 파일이 없습니다.".to_string()),
        0 => Err(format!("이름에 '{hint}'이(가) 든 첨부를 찾지 못했습니다.")),
        1 => Ok(absolute(&zips[0].0, post_url)),
        _ => {
            let names: Vec<&str> = zips.iter().map(|(_, name)| name.as_str()).collect();
            Err(format!(
                "첨부된 ZIP이 여러 개입니다. 표식에 파일=<이름 일부>를 넣어 하나를 고르세요: {}",
                names.join(", ")
            ))
        }
    }
}

fn parsed_version(value: &str) -> Option<Version> {
    let normalized = value
        .trim()
        .trim_start_matches(|character| character == 'v' || character == 'V')
        .trim_start_matches('.');
    Version::parse(normalized).ok()
}

fn http_client(timeout: Duration) -> Result<reqwest::blocking::Client, String> {
    reqwest::blocking::Client::builder()
        .timeout(timeout)
        .user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) JbHwpHelper")
        .build()
        .map_err(|error| format!("연결을 준비하지 못했습니다: {error}"))
}

fn fetch_post(url: &str) -> Result<String, String> {
    let response = http_client(Duration::from_secs(15))?
        .get(url)
        .send()
        .map_err(|error| format!("게시글을 열지 못했습니다: {error}"))?;
    if !response.status().is_success() {
        return Err(format!("게시글을 열지 못했습니다: {}", response.status()));
    }
    response
        .text()
        .map_err(|error| format!("게시글을 읽지 못했습니다: {error}"))
}

#[tauri::command]
pub fn check_board_update(app: AppHandle) -> Result<BoardUpdateCheck, String> {
    let current = app.package_info().version.to_string();
    let config = read_config(&app)?;
    if !config.enabled
        || config.post_url.trim().is_empty()
        || config.app_id.trim().is_empty()
        || config.public_key.trim().is_empty()
    {
        return Ok(BoardUpdateCheck {
            configured: false,
            current,
            update: None,
            message: "자동 업데이트 정보가 아직 설정되지 않았습니다.".to_string(),
        });
    }

    let post_url = config.post_url.trim();
    let html = fetch_post(post_url)?;
    let target = config.app_id.trim();
    let mine: Vec<HashMap<String, String>> = marker_segments(&html)
        .iter()
        .map(|segment| parse_fields(segment))
        .filter(|fields| fields.get("id").map(String::as_str) == Some(target))
        .collect();
    let chosen = mine
        .iter()
        .find(|fields| {
            (fields.contains_key("버전") || fields.contains_key("version"))
                && (fields.contains_key("서명") || fields.contains_key("signature"))
        })
        .or_else(|| mine.first());
    let Some(fields) = chosen else {
        return Ok(BoardUpdateCheck {
            configured: true,
            current,
            update: None,
            message: format!("게시글에서 {target} 업데이트 정보를 찾지 못했습니다."),
        });
    };
    let (Some(version), Some(signature)) = (
        fields.get("버전").or_else(|| fields.get("version")),
        fields.get("서명").or_else(|| fields.get("signature")),
    ) else {
        return Ok(BoardUpdateCheck {
            configured: true,
            current,
            update: None,
            message: "업데이트 정보에 버전 또는 서명이 아직 없습니다.".to_string(),
        });
    };

    let (Some(latest), Some(installed)) = (parsed_version(version), parsed_version(&current))
    else {
        return Ok(BoardUpdateCheck {
            configured: true,
            current,
            update: None,
            message: format!("게시글의 버전 형식을 읽지 못했습니다: {version}"),
        });
    };
    if latest <= installed {
        return Ok(BoardUpdateCheck {
            configured: true,
            current,
            update: None,
            message: "최신 버전을 사용 중입니다.".to_string(),
        });
    }

    let hint = fields.get("파일").map(String::as_str).unwrap_or("").trim();
    let listed = fields
        .get("게시글")
        .or_else(|| fields.get("주소"))
        .or_else(|| fields.get("다운로드"))
        .or_else(|| fields.get("post"))
        .or_else(|| fields.get("download"))
        .map(|value| value.trim())
        .filter(|value| !value.is_empty());
    let download = match listed {
        Some(url) if url.contains("download.jbe") => absolute(url, post_url),
        Some(url) => {
            let page_url = absolute(url, post_url);
            let page = fetch_post(&page_url)?;
            pick_attachment(&page, &page_url, hint)?
        }
        None => pick_attachment(&html, post_url, hint)?,
    };
    if !download.starts_with("https://") {
        return Err("업데이트 설치본은 HTTPS 주소에서만 받을 수 있습니다.".to_string());
    }

    let version = latest.to_string();
    Ok(BoardUpdateCheck {
        configured: true,
        current,
        update: Some(BoardUpdate {
            version: version.clone(),
            download,
            signature: signature.trim().to_string(),
        }),
        message: format!("새 버전 v.{version}이 있습니다."),
    })
}

fn decode_wrapped(value: &str, what: &str) -> Result<String, String> {
    let bytes = STANDARD
        .decode(value.trim())
        .map_err(|_| format!("{what} 형식이 올바르지 않습니다."))?;
    String::from_utf8(bytes).map_err(|_| format!("{what} 형식이 올바르지 않습니다."))
}

fn verify_installer(bytes: &[u8], signature: &str, public_key: &str) -> Result<(), String> {
    let key_text = decode_wrapped(public_key, "공개키")?;
    let key_line = key_text
        .lines()
        .rev()
        .find(|line| !line.trim().is_empty())
        .ok_or_else(|| "공개키가 비어 있습니다.".to_string())?;
    let key = PublicKey::from_base64(key_line.trim())
        .map_err(|error| format!("공개키를 읽지 못했습니다: {error}"))?;
    let signature_text = decode_wrapped(signature, "서명")?;
    let signature = Signature::decode(&signature_text)
        .map_err(|error| format!("서명을 읽지 못했습니다: {error}"))?;
    if key.verify(bytes, &signature, false).is_ok() || key.verify(bytes, &signature, true).is_ok() {
        Ok(())
    } else {
        Err("서명이 맞지 않습니다. 받은 파일을 설치하지 않습니다.".to_string())
    }
}

fn take_installer(bytes: &[u8]) -> Result<Vec<u8>, String> {
    let mut archive = ZipArchive::new(Cursor::new(bytes))
        .map_err(|error| format!("압축을 열지 못했습니다: {error}"))?;
    let mut found = None;
    for index in 0..archive.len() {
        let file = archive
            .by_index(index)
            .map_err(|error| format!("압축 항목을 읽지 못했습니다: {error}"))?;
        if file.is_dir() {
            continue;
        }
        let is_exe = file
            .enclosed_name()
            .and_then(|path| {
                path.extension()
                    .map(|extension| extension.eq_ignore_ascii_case("exe"))
            })
            .unwrap_or(false);
        if !is_exe {
            continue;
        }
        if found.is_some() {
            return Err("압축 안에 실행 파일이 여러 개입니다.".to_string());
        }
        if file.size() > MAX_INSTALLER_BYTES {
            return Err("설치본이 너무 큽니다.".to_string());
        }
        found = Some(index);
    }

    let index = found.ok_or_else(|| "압축 안에 설치본(.exe)이 없습니다.".to_string())?;
    let mut file = archive
        .by_index(index)
        .map_err(|error| format!("압축 항목을 읽지 못했습니다: {error}"))?;
    let mut installer = Vec::with_capacity(file.size() as usize);
    file.read_to_end(&mut installer)
        .map_err(|error| format!("설치본을 꺼내지 못했습니다: {error}"))?;
    Ok(installer)
}

fn download_dir(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app
        .path()
        .app_cache_dir()
        .map_err(|error| format!("임시 폴더를 찾지 못했습니다: {error}"))?
        .join("updates");
    fs::create_dir_all(&dir).map_err(|error| format!("임시 폴더를 만들지 못했습니다: {error}"))?;
    Ok(dir)
}

fn signature_path(installer: &Path) -> PathBuf {
    installer.with_extension("exe.signature")
}

#[tauri::command]
pub fn download_board_update(app: AppHandle, update: BoardUpdate) -> Result<String, String> {
    let config = read_config(&app)?;
    if !config.enabled || config.public_key.trim().is_empty() {
        return Err("업데이트 공개키가 설정되어 있지 않습니다.".to_string());
    }
    let response = http_client(Duration::from_secs(600))?
        .get(update.download.trim())
        .send()
        .map_err(|error| format!("설치본을 받지 못했습니다: {error}"))?;
    if !response.status().is_success() {
        return Err(format!("설치본을 받지 못했습니다: {}", response.status()));
    }
    if response.content_length().unwrap_or(0) > MAX_ARCHIVE_BYTES {
        return Err("업데이트 압축파일이 너무 큽니다.".to_string());
    }
    let mut archive = Vec::new();
    response
        .take(MAX_ARCHIVE_BYTES + 1)
        .read_to_end(&mut archive)
        .map_err(|error| format!("설치본을 읽지 못했습니다: {error}"))?;
    if archive.len() as u64 > MAX_ARCHIVE_BYTES {
        return Err("업데이트 압축파일이 너무 큽니다.".to_string());
    }

    let installer = take_installer(&archive)?;
    verify_installer(&installer, &update.signature, &config.public_key)?;
    let dir = download_dir(&app)?;
    for entry in
        fs::read_dir(&dir).map_err(|error| format!("임시 폴더를 읽지 못했습니다: {error}"))?
    {
        let path = entry
            .map_err(|error| format!("임시 파일을 읽지 못했습니다: {error}"))?
            .path();
        if path.is_file() {
            let _ = fs::remove_file(path);
        }
    }
    let target = dir.join(format!("JbHwpHelper-{}-setup.exe", update.version));
    fs::write(&target, &installer)
        .map_err(|error| format!("설치본을 저장하지 못했습니다: {error}"))?;
    fs::write(signature_path(&target), update.signature.trim())
        .map_err(|error| format!("설치본 서명을 저장하지 못했습니다: {error}"))?;
    Ok(target.to_string_lossy().to_string())
}

#[tauri::command]
pub fn apply_board_update(app: AppHandle, path: String) -> Result<(), String> {
    let config = read_config(&app)?;
    let installer = fs::canonicalize(PathBuf::from(path.trim()))
        .map_err(|_| "받아 둔 설치본을 찾지 못했습니다.".to_string())?;
    let dir = fs::canonicalize(download_dir(&app)?)
        .map_err(|error| format!("임시 폴더를 확인하지 못했습니다: {error}"))?;
    if installer.parent() != Some(dir.as_path()) {
        return Err("설치본 위치가 올바르지 않습니다.".to_string());
    }
    let installer_bytes = fs::read(&installer)
        .map_err(|error| format!("설치본을 다시 확인하지 못했습니다: {error}"))?;
    let signature = fs::read_to_string(signature_path(&installer))
        .map_err(|error| format!("설치본 서명을 다시 확인하지 못했습니다: {error}"))?;
    verify_installer(&installer_bytes, &signature, &config.public_key)?;

    Command::new(&installer)
        .args(["/UPDATE", "/P", "/R"])
        .spawn()
        .map_err(|error| format!("업데이트 설치를 시작하지 못했습니다: {error}"))?;
    app.exit(0);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{absolute, marker_segments, parse_fields, parsed_version};
    use semver::Version;

    #[test]
    fn parses_marker_split_by_inline_tags() {
        let html = "<p>[업데이트정보]id=JBHWP|<span>버전=v.4.0.2</span>|서명=abc</p>";
        let segments = marker_segments(html);
        assert_eq!(segments.len(), 1);
        let fields = parse_fields(&segments[0]);
        assert_eq!(fields.get("id").map(String::as_str), Some("JBHWP"));
        assert_eq!(fields.get("버전").map(String::as_str), Some("v.4.0.2"));
        assert_eq!(fields.get("서명").map(String::as_str), Some("abc"));
    }

    #[test]
    fn accepts_display_and_semver_versions() {
        assert_eq!(parsed_version("v.4.0.1"), Some(Version::new(4, 0, 1)));
        assert_eq!(parsed_version("4.0.2"), Some(Version::new(4, 0, 2)));
    }

    #[test]
    fn resolves_board_relative_download_url() {
        assert_eq!(
            absolute(
                "/board/download.jbe?id=1",
                "https://www.jbe.go.kr/board/view.jbe?id=2"
            ),
            "https://www.jbe.go.kr/board/download.jbe?id=1"
        );
    }
}
