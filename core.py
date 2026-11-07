"""hlmv-dl の操作。同梱版または GitHub Releases から更新した exe を呼び出す。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

try:
    from repo_config import UPDATE_REPO  # CI が github.repository を書き出す
except ImportError:
    UPDATE_REPO = "OWNER/hlmv-gui"  # 開発時は自分のリポジトリ名に変更

TOOL_TAG = "tool-latest"
EXE_NAME = "hlmv-dl.exe"
META_NAME = "hlmv-dl.json"
APP_TOOL_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "hlmv-gui" / "tools"

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
LIST_RE = re.compile(r"^\s*(\d+) / ([^/]+?) / ([^/]+?) / (.+?)\s*$")
ID_IN_NAME = re.compile(r" \[(\d+)\]\.opus$")

LogFn = Callable[[str], None]


@dataclass
class Title:
    id: str
    kind: str       # "Audio Guide" または "Commentary"
    language: str
    name: str


# ---------- ツールの場所・バージョン ----------

def bundled_dir() -> Path:
    """PyInstaller で同梱されたファイルの場所（開発時はこのファイルの隣）。"""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "tools"


def tool_path() -> Optional[Path]:
    """更新版を優先し、無ければ同梱版を使う。"""
    for p in (APP_TOOL_DIR / EXE_NAME, bundled_dir() / EXE_NAME):
        if p.is_file():
            return p
    return None


def hlmv_exe() -> Optional[str]:
    p = tool_path()
    return str(p) if p else None


def current_info() -> Optional[dict]:
    p = tool_path()
    if not p:
        return None
    try:
        meta = json.loads(p.with_name(META_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    meta["where"] = "更新版" if p.parent == APP_TOOL_DIR else "同梱版"
    return meta


# ---------- 更新 ----------

def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "hlmv-gui"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def check_update(log: Optional[LogFn] = None) -> dict:
    try:
        rel = _get_json(f"https://api.github.com/repos/{UPDATE_REPO}/releases/tags/{TOOL_TAG}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError("ツールの配布リリースがまだありません（tool-release ワークフローを実行してください）。")
        raise
    assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
    if EXE_NAME not in assets or META_NAME not in assets:
        raise RuntimeError("ツールの配布物が不足しています。")

    meta = _get_json(assets[META_NAME])
    cur = current_info() or {}
    installed = cur.get("commit")
    return {
        "installed": installed,
        "where": cur.get("where"),
        "latest": meta["commit"],
        "built_at": meta.get("built_at", ""),
        # 同じ commit でも exe を作り直していれば更新扱いにする
        "available": cur.get("sha256") != meta.get("sha256"),
        "meta": meta,
        "exe_url": assets[EXE_NAME],
    }


def apply_update(info: dict, log: LogFn) -> str:
    """配布物をダウンロードし、チェックサムと起動確認を通してから差し替える。"""
    APP_TOOL_DIR.mkdir(parents=True, exist_ok=True)
    tmp = APP_TOOL_DIR / "hlmv-dl.download"
    target = APP_TOOL_DIR / EXE_NAME
    meta = info["meta"]

    log(f"ダウンロード中: hlmv-dl {meta['commit'][:7]}")
    req = urllib.request.Request(info["exe_url"], headers={"User-Agent": "hlmv-gui"})
    with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)

    if hashlib.sha256(tmp.read_bytes()).hexdigest() != meta.get("sha256"):
        tmp.unlink(missing_ok=True)
        raise RuntimeError("チェックサムが一致しません。もう一度お試しください。")

    code, out = run([str(tmp), "--help"], quiet=True)
    if code != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"ダウンロードしたツールが起動しませんでした:\n{out}")

    try:
        os.replace(tmp, target)
    except PermissionError:
        raise RuntimeError("ツールが使用中のため更新できません。ダウンロードを止めてから再試行してください。")
    target.with_name(META_NAME).write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"更新しました: hlmv-dl {meta['commit'][:7]}")
    return meta["commit"]


# ---------- 実行 ----------

def child_env() -> dict:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["NO_COLOR"] = "1"    # 色や装飾の制御文字を出さない
    env["TERM"] = "dumb"     # 端末ではないことを明示する
    env["COLUMNS"] = "1000"  # 表の折り返し・省略で行が壊れないようにする
    return env


def run(args: list[str], log: Optional[LogFn] = None, quiet: bool = False) -> tuple[int, str]:
    if log and not quiet:
        log("$ " + " ".join(args))
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=child_env(), creationflags=NO_WINDOW)
    out = (proc.stdout + proc.stderr).strip()
    if log and not quiet and out:
        log(out)
    return proc.returncode, out


def parse_list(text: str) -> list[Title]:
    titles = []
    for line in text.splitlines():
        m = LIST_RE.match(line)
        if m:
            titles.append(Title(*m.groups()))
    return titles


def fetch_titles(log: Optional[LogFn] = None) -> list[Title]:
    exe = hlmv_exe()
    if not exe:
        raise RuntimeError("ツールが見つかりません。ツール → ツールの更新 から取得してください。")
    if log:
        log("$ hlmv-dl --list")
    code, out = run([exe, "--list"], quiet=True)
    if code != 0:
        raise RuntimeError(f"一覧の取得に失敗しました:\n{out}")
    return parse_list(out)


def downloaded_ids(out_dir: Path) -> set[str]:
    if not out_dir.is_dir():
        return set()
    return {m.group(1) for p in out_dir.iterdir() if (m := ID_IN_NAME.search(p.name))}


def download_one(title_id: str, out_dir: Path, keep: bool, log: LogFn, on_start: Callable) -> int:
    exe = hlmv_exe()
    if not exe:
        raise RuntimeError("ツールが見つかりません。")
    args = [exe, title_id, "-o", str(out_dir)]
    if keep:
        args.append("--keep-package")
    log("$ " + " ".join(args))
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace",
                            env=child_env(), creationflags=NO_WINDOW)
    on_start(proc)
    assert proc.stdout is not None
    for line in proc.stdout:
        log(line.rstrip("\r\n"))
    return proc.wait()
