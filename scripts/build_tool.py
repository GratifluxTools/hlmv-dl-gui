"""hlmv-dl を単体の exe にビルドする（CI で実行）。

tool-venv の Python で実行する:
    tool-venv\\Scripts\\python scripts\\build_tool.py [--previous 前回の hlmv-dl.json]
出力: tools_out/hlmv-dl.exe と tools_out/hlmv-dl.json
--previous を渡し、前回と同じ commit なら何もせず終了する（tools_out が作られない）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import distribution
from pathlib import Path

OUT = Path("tools_out")
WORK = Path("build_tool")


def main() -> int:
    # Windows の CI では標準出力が cp1252 になり日本語で落ちるため UTF-8 に固定する
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--previous", type=Path, help="前回公開された hlmv-dl.json")
    args = ap.parse_args()

    dist = distribution("hlmv-dl")
    raw = dist.read_text("direct_url.json")  # pip が git の commit を記録している
    commit = json.loads(raw)["vcs_info"]["commit_id"] if raw else "unknown"

    if args.previous and args.previous.exists():
        old = json.loads(args.previous.read_text(encoding="utf-8"))
        if old.get("commit") == commit:
            print(f"hlmv-dl は更新されていません（{commit[:7]}）。ビルドをスキップします。")
            return 0

    # console_scripts の hlmv-dl がどの関数を呼ぶかを取得して、ラッパーを作る
    ep = next(e for e in dist.entry_points
              if e.group == "console_scripts" and e.name == "hlmv-dl")
    module, _, func = ep.value.partition(":")
    top = module.split(".")[0]

    WORK.mkdir(exist_ok=True)
    entry = WORK / "hlmv_entry.py"
    entry.write_text(
        "import sys\n"
        "# パイプ出力で日本語が cp1252 に落ちないよう UTF-8 に固定する\n"
        "for _s in (sys.stdout, sys.stderr):\n"
        "    if hasattr(_s, 'reconfigure'):\n"
        "        _s.reconfigure(encoding='utf-8', errors='replace')\n"
        "try:\n"
        "    import rich.console as _rc\n"
        "    if hasattr(_rc, 'detect_legacy_windows'):\n"
        "        _rc.detect_legacy_windows = lambda: False  # 旧コンソール描画を使わせない\n"
        "except ImportError:\n"
        "    pass\n"
        f"from {module} import {func.strip()} as _main\n"
        "sys.exit(_main())\n",
        encoding="utf-8",
    )

    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile",
        "--name", "hlmv-dl", "--collect-submodules", top,
        "--distpath", str(WORK / "dist"),
        "--workpath", str(WORK / "build"),
        "--specpath", str(WORK),
        str(entry),
    ], check=True)

    OUT.mkdir(exist_ok=True)
    exe = OUT / "hlmv-dl.exe"
    shutil.copy2(WORK / "dist" / "hlmv-dl.exe", exe)
    subprocess.run([str(exe), "--help"], check=True, capture_output=True)  # 起動確認

    meta = {
        "commit": commit,
        "sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (OUT / "hlmv-dl.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"ビルド完了: hlmv-dl {commit[:7]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
