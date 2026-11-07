"""hlmv-dl の Windows 向け GUI。"""
from __future__ import annotations

import csv
import shlex
import sys
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QSettings, QSize, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QFileDialog,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QSplitter, QTabWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

import core
from icons import icon, pixmap
from theme import PALETTE, qss

C = PALETTE
KIND_LABEL = {"Audio Guide": "音声ガイド", "Commentary": "コメンタリー"}
STATE_TEXT = {"cached": "取得済", "run": "DL中", "done": "完了",
              "skip": "スキップ", "fail": "失敗", "cancel": "中止"}
STATE_COLOR = {"done": C["ok"], "fail": C["err"], "run": C["accent"],
               "cancel": C["warn"], "cached": C["muted"], "skip": C["muted"]}
COL_CHK, COL_STATE, COL_ID, COL_KIND, COL_LANG, COL_NAME = range(6)


def make_button(text, icon_name=None, slot=None, object_name=None, icon_color=None):
    b = QPushButton(text)
    if icon_name:
        b.setIcon(icon(icon_name, icon_color or C["text"], 16))
        b.setIconSize(QSize(16, 16))
    if object_name:
        b.setObjectName(object_name)
    if slot:
        b.clicked.connect(slot)
    return b


class Worker(QThread):
    """fn(log) をバックグラウンドで実行する。"""
    log = Signal(str)
    ok = Signal(object)
    err = Signal(str)

    def __init__(self, fn: Callable, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            result = self.fn(self.log.emit)
        except Exception as e:  # noqa: BLE001
            self.err.emit(str(e))
        else:
            self.ok.emit(result)


class DownloadWorker(QThread):
    log = Signal(str)
    status = Signal(str, str)      # title_id, 状態キー
    progress = Signal(int, int)    # 処理済み, 合計
    done = Signal(int, int, bool)  # 成功, 失敗, 中止したか

    def __init__(self, items: list[tuple[str, str]], out_dir: str, keep: bool, parent=None):
        super().__init__(parent)
        self.items = items
        self.out_dir = Path(out_dir)
        self.keep = keep
        self._cancel = False
        self._proc = None

    def cancel(self):
        self._cancel = True
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    def _set_proc(self, proc):
        self._proc = proc

    def run(self):
        ok = fail = 0
        total = len(self.items)
        try:
            self.out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self.log.emit(f"出力先を作成できません: {e}")
            self.done.emit(0, total, False)
            return
        for i, (tid, name) in enumerate(self.items, 1):
            if self._cancel:
                break
            if tid in core.downloaded_ids(self.out_dir):
                self.status.emit(tid, "skip")
                self.log.emit(f"スキップ（既に存在）: {name}")
                self.progress.emit(i, total)
                continue
            self.status.emit(tid, "run")
            self.log.emit(f"\n=== [{i}/{total}] {name}（ID {tid}）===")
            try:
                code = core.download_one(tid, self.out_dir, self.keep, self.log.emit, self._set_proc)
            except Exception as e:  # noqa: BLE001
                code = -1
                self.log.emit(f"例外: {e}")
            if self._cancel:
                self.status.emit(tid, "cancel")
                self.log.emit("中止しました")
                break
            if code == 0:
                ok += 1
                self.status.emit(tid, "done")
            else:
                fail += 1
                self.status.emit(tid, "fail")
                self.log.emit(f"失敗（終了コード {code}）")
            self.progress.emit(i, total)
        self.done.emit(ok, fail, self._cancel)


class StatusLine(QWidget):
    """アイコン付きの 1 行表示。"""

    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        self.icon = QLabel()
        self.text = QLabel()
        self.text.setTextFormat(Qt.TextFormat.RichText)
        self.text.setWordWrap(True)
        lay.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self.text, 1)

    def set(self, icon_name: str, color: str, html: str):
        self.icon.setPixmap(pixmap(icon_name, color, 20))
        self.text.setText(html)


class ToolDialog(QDialog):
    """hlmv-dl の現在のバージョン確認と更新。"""
    changed = Signal()

    def __init__(self, parent: "MainWindow"):
        super().__init__(parent)
        self.win = parent
        self.setWindowTitle("ツールの更新")
        self.resize(660, 440)
        self._info: Optional[dict] = None
        self._checking = False
        self._w: Optional[Worker] = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(14)

        head = QLabel("hlmv-dl の管理")
        head.setObjectName("title")
        lay.addWidget(head)

        self.l_local = StatusLine()
        self.l_latest = StatusLine()
        self.l_error = StatusLine()
        for w in (self.l_local, self.l_latest, self.l_error):
            lay.addWidget(w)

        row = QHBoxLayout()
        self.b_check = make_button("再チェック", "refresh", self.check)
        self.b_apply = make_button("更新を適用", "download", self.apply,
                                   object_name="primary", icon_color=C["bg"])
        row.addWidget(self.b_check)
        row.addStretch(1)
        row.addWidget(self.b_apply)
        lay.addLayout(row)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        lay.addWidget(self.log, 1)

        lay.addWidget(make_button("閉じる", None, lambda: self.accept()), 0,
                      Qt.AlignmentFlag.AlignRight)

        self._render()
        self.check()

    def _busy(self, busy: bool):
        self.b_check.setEnabled(not busy)
        can_apply = self._info is not None and self._info["available"]
        self.b_apply.setEnabled(not busy and can_apply)

    def _task(self, fn, on_ok, on_err):
        self._busy(True)
        w = Worker(fn)
        w.log.connect(self.log.appendPlainText)
        w.ok.connect(lambda res: (self._busy(False), on_ok(res)))
        w.err.connect(lambda m: self._on_err(m, on_err))
        self._w = w
        w.start()

    def _on_err(self, msg: str, on_err):
        self._busy(False)
        self.log.appendPlainText(f"エラー: {msg}")
        on_err(msg)

    def _render(self, error: str = ""):
        muted = C["muted"]
        cur = core.current_info()
        if cur:
            commit = (cur.get("commit") or "不明")[:7]
            self.l_local.set("package", C["text"],
                             f"<b>現在のツール</b>　{cur.get('where', '')}　{commit}　"
                             f"<span style='color:{muted}'>{cur.get('built_at', '')}</span>")
        else:
            self.l_local.set("package", C["warn"],
                             "<b>現在のツール</b>　未取得（「ツールを取得」で入手できます）")

        if self._checking:
            self.l_latest.set("clock", muted, "最新版を確認しています…")
        elif self._info:
            i = self._info
            if i["available"]:
                self.l_latest.set("arrow-up-circle", C["accent"],
                                  f"<b>更新があります</b>　{i['latest'][:7]}　"
                                  f"<span style='color:{muted}'>{i['built_at']}</span>")
            else:
                self.l_latest.set("check-circle", C["ok"],
                                  f"<b>最新です</b>　{i['latest'][:7]}")
        self.l_latest.setVisible(self._checking or self._info is not None)

        self.l_error.setVisible(bool(error))
        if error:
            self.l_error.set("alert", C["warn"], error)
        self.b_apply.setText("ツールを取得" if not cur else "更新を適用")

    def check(self, *_):
        self._info = None
        self._checking = True
        self._render()
        self._task(core.check_update, on_ok=self._on_checked, on_err=self._on_check_err)

    def _on_checked(self, r: dict):
        self._checking = False
        self._info = r
        self._render()
        self._busy(False)

    def _on_check_err(self, msg: str):
        self._checking = False
        self._render(f"確認できませんでした: {msg}")

    def apply(self, *_):
        if not self._info:
            return
        if self.win.is_downloading():
            QMessageBox.information(self, "実行中", "ダウンロード中は更新できません。停止してから実行してください。")
            return
        info = self._info
        self._task(lambda log: core.apply_update(info, log),
                   on_ok=self._on_applied,
                   on_err=lambda m: self._render(f"更新に失敗しました: {m}"))

    def _on_applied(self, _commit):
        self.changed.emit()
        self.check()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("hlmv-dl")
        self.resize(1180, 780)
        self.settings = QSettings("hlmv-gui", "hlmv-gui")
        self.titles: dict[str, core.Title] = {}
        self.have: set[str] = set()
        self.state: dict[str, str] = {}
        self._workers: list[Worker] = []
        self.dl: Optional[DownloadWorker] = None

        self._build_menu()
        self._build_ui()
        self._load_settings()
        self.statusBar().showMessage("準備中…")
        self.reload_list()
        self.load_help()

    # ---------- UI 構築 ----------

    def _build_menu(self):
        tools = self.menuBar().addMenu("ツール")
        act = QAction(icon("package", C["text"], 16), "ツールの更新…", self)
        act.triggered.connect(self.open_tool_dialog)
        tools.addAction(act)
        act = QAction(icon("file", C["text"], 16), "一覧を CSV で保存…", self)
        act.triggered.connect(self.export_csv)
        tools.addAction(act)
        act = QAction(icon("refresh", C["text"], 16), "一覧を再読込", self)
        act.setShortcut("F5")
        act.triggered.connect(self.reload_list)
        tools.addAction(act)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 16, 18, 12)
        root.setSpacing(10)

        # ヘッダー
        header = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(pixmap("headphones", C["accent"], 34))
        titles = QVBoxLayout()
        titles.setSpacing(0)
        t = QLabel("hlmv-dl")
        t.setObjectName("title")
        sub = QLabel("音声ガイド・コメンタリーをまとめてダウンロード")
        sub.setObjectName("subtle")
        titles.addWidget(t)
        titles.addWidget(sub)
        header.addWidget(logo)
        header.addSpacing(6)
        header.addLayout(titles)
        header.addStretch(1)
        header.addWidget(make_button("ツールの更新", "package", self.open_tool_dialog))
        header.addWidget(make_button("CSV", "file", self.export_csv))
        root.addLayout(header)

        # 出力先
        row = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("出力先フォルダ")
        self.out_edit.editingFinished.connect(self._on_out_changed)
        row.addWidget(self.out_edit, 1)
        row.addWidget(make_button("参照", "folder", self.pick_dir))
        row.addWidget(make_button("開く", "external", self.open_dir))
        root.addLayout(row)

        # 検索・絞り込み
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("タイトル・ID で検索（スペース区切りで AND）")
        self.search.addAction(icon("search", C["muted"], 16), QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(self.apply_filter)
        self.kind = QComboBox()
        self.kind.addItem("すべての種類", None)
        self.kind.addItem("音声ガイド", "Audio Guide")
        self.kind.addItem("コメンタリー", "Commentary")
        self.kind.currentIndexChanged.connect(self.apply_filter)
        self.lang = QComboBox()
        self.lang.addItem("すべての言語", None)
        self.lang.currentIndexChanged.connect(self.apply_filter)
        self.only_new = QCheckBox("未取得のみ")
        self.only_new.toggled.connect(self.apply_filter)
        row.addWidget(self.search, 1)
        row.addWidget(self.kind)
        row.addWidget(self.lang)
        row.addWidget(self.only_new)
        root.addLayout(row)

        # 選択操作
        row = QHBoxLayout()
        row.addWidget(make_button("表示中を全選択", "check-square", lambda: self.set_visible_checked(True)))
        row.addWidget(make_button("表示中を全解除", "x", lambda: self.set_visible_checked(False)))
        row.addWidget(make_button("選択を反転", "list", self.invert_visible))
        row.addWidget(make_button("一覧を再読込", "refresh", self.reload_list))
        row.addStretch(1)
        self.count_label = QLabel()
        self.count_label.setObjectName("subtle")
        row.addWidget(self.count_label)
        root.addLayout(row)

        # 一覧
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["", "状態", "ID", "種類", "言語", "タイトル"])
        self.table.setHorizontalHeaderItem(COL_CHK, QTableWidgetItem(icon("check-square", C["muted"], 16), ""))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        self.table.itemClicked.connect(self._on_clicked)
        self.table.itemDoubleClicked.connect(self._on_double_clicked)

        # 下部タブ
        self.tabs = QTabWidget()
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(20000)
        self.tabs.addTab(self.log_view, icon("list", C["muted"], 16), "ログ")

        cmd = QWidget()
        cl = QVBoxLayout(cmd)
        crow = QHBoxLayout()
        prompt = QLabel("hlmv-dl")
        prompt.setObjectName("subtle")
        crow.addWidget(prompt)
        self.cmd_in = QLineEdit()
        self.cmd_in.setPlaceholderText("例:  --list   /   12345 -o D:\\audio --keep-package   （Enter で実行）")
        self.cmd_in.returnPressed.connect(self.run_custom)
        crow.addWidget(self.cmd_in, 1)
        crow.addWidget(make_button("実行", "play", self.run_custom))
        cl.addLayout(crow)
        self.cmd_out = QPlainTextEdit()
        self.cmd_out.setReadOnly(True)
        self.cmd_out.setMaximumBlockCount(20000)
        cl.addWidget(self.cmd_out, 1)
        self.tabs.addTab(cmd, icon("terminal", C["muted"], 16), "コマンドライン")

        helpw = QWidget()
        hl = QVBoxLayout(helpw)
        hrow = QHBoxLayout()
        hrow.addWidget(make_button("再読込", "refresh", self.load_help))
        hrow.addWidget(make_button("コピー", "copy",
                                   lambda: QApplication.clipboard().setText(self.help_view.toPlainText())))
        hrow.addStretch(1)
        hl.addLayout(hrow)
        self.help_view = QPlainTextEdit()
        self.help_view.setReadOnly(True)
        hl.addWidget(self.help_view, 1)
        self.tabs.addTab(helpw, icon("help", C["muted"], 16), "ヘルプ")

        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.table)
        split.addWidget(self.tabs)
        split.setSizes([430, 250])
        root.addWidget(split, 1)

        # ダウンロード操作
        row = QHBoxLayout()
        self.keep = QCheckBox("ZIP・情報 JSON も保存（--keep-package）")
        self.progress = QProgressBar()
        self.progress.setFormat("%v / %m")
        self.start_btn = make_button("ダウンロード開始", "download", self.start_download,
                                     object_name="primary", icon_color=C["bg"])
        self.start_btn.setMinimumWidth(200)
        self.stop_btn = make_button("停止", "stop", self.stop_download, object_name="danger")
        self.stop_btn.setEnabled(False)
        row.addWidget(self.keep)
        row.addWidget(self.progress, 1)
        row.addWidget(self.start_btn)
        row.addWidget(self.stop_btn)
        root.addLayout(row)

    # ---------- 設定・終了 ----------

    def _load_settings(self):
        default = str(Path.home() / "Music" / "hlmv-dl")
        self.out_edit.setText(self.settings.value("out_dir", default, type=str))
        self.keep.setChecked(self.settings.value("keep", False, type=bool))
        geo = self.settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)

    def _save_settings(self):
        self.settings.setValue("out_dir", self.out_edit.text().strip())
        self.settings.setValue("keep", self.keep.isChecked())
        self.settings.setValue("geometry", self.saveGeometry())

    def closeEvent(self, event):
        if self.is_downloading():
            r = QMessageBox.question(self, "終了確認", "ダウンロード中です。中止して終了しますか？")
            if r != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.dl.cancel()
            self.dl.wait(5000)
        self._save_settings()
        super().closeEvent(event)

    def is_downloading(self) -> bool:
        return bool(self.dl and self.dl.isRunning())

    # ---------- 出力先 ----------

    def _on_out_changed(self, *_):
        self.settings.setValue("out_dir", self.out_edit.text().strip())
        self.refresh_have()

    def pick_dir(self, *_):
        start = self.out_edit.text().strip() or str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "出力先フォルダを選択", start)
        if d:
            self.out_edit.setText(d)
            self._on_out_changed()

    def open_dir(self, *_):
        p = Path(self.out_edit.text().strip())
        if p.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
        else:
            QMessageBox.information(self, "開けません", "出力先フォルダが存在しません。")

    # ---------- 非同期実行 ----------

    def _run(self, fn, on_ok=None, on_err=None, log=None):
        w = Worker(fn)
        if log:
            w.log.connect(log)
        if on_ok:
            w.ok.connect(on_ok)
        w.err.connect(on_err or self._show_error)
        self._workers.append(w)
        w.finished.connect(lambda: self._workers.remove(w) if w in self._workers else None)
        w.start()

    def _show_error(self, msg: str):
        self.statusBar().showMessage("エラーが発生しました")
        QMessageBox.warning(self, "エラー", msg)

    # ---------- 一覧 ----------

    def reload_list(self, *_):
        if not core.hlmv_exe():
            self.populate([])
            self.statusBar().showMessage("ツールが見つかりません。「ツールの更新」から取得できます。")
            return
        self.statusBar().showMessage("一覧を取得中…")
        self._run(core.fetch_titles, on_ok=self._on_list,
                  on_err=lambda m: (self.statusBar().showMessage("一覧の取得に失敗しました"),
                                    QMessageBox.warning(self, "エラー", m)))

    def _on_list(self, titles):
        self.populate(titles)
        self.statusBar().showMessage(f"{len(titles)} 件を取得しました")
        self._run(core.check_update, on_ok=self._on_update_quiet, on_err=lambda m: None)

    def _on_update_quiet(self, r: dict):
        if r["installed"] and r["available"]:
            self.statusBar().showMessage("hlmv-dl に更新があります（ツール → ツールの更新）")

    def _chk_item(self, on: bool) -> QTableWidgetItem:
        it = QTableWidgetItem()
        it.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self._paint_chk(it, on)
        return it

    def _paint_chk(self, it: QTableWidgetItem, on: bool):
        it.setData(Qt.ItemDataRole.UserRole, on)
        it.setIcon(icon("check-square" if on else "square",
                        C["accent"] if on else C["muted"], 18))

    def _row_checked(self, r: int) -> bool:
        return bool(self.table.item(r, COL_CHK).data(Qt.ItemDataRole.UserRole))

    def _set_row_checked(self, r: int, on: bool):
        self._paint_chk(self.table.item(r, COL_CHK), on)

    def populate(self, titles):
        self.titles = {t.id: t for t in titles}
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(titles))
        for r, t in enumerate(titles):
            self.table.setItem(r, COL_CHK, self._chk_item(False))
            self.table.setItem(r, COL_STATE, QTableWidgetItem(""))
            self.table.setItem(r, COL_ID, QTableWidgetItem(t.id))
            self.table.setItem(r, COL_KIND, QTableWidgetItem(KIND_LABEL.get(t.kind, t.kind)))
            self.table.setItem(r, COL_LANG, QTableWidgetItem(t.language))
            self.table.setItem(r, COL_NAME, QTableWidgetItem(t.name))
        self.table.setSortingEnabled(True)

        cur = self.lang.currentData()
        self.lang.blockSignals(True)
        self.lang.clear()
        self.lang.addItem("すべての言語", None)
        for lg in sorted({t.language for t in titles}):
            self.lang.addItem(lg, lg)
        self.lang.setCurrentIndex(max(self.lang.findData(cur), 0))
        self.lang.blockSignals(False)
        self.refresh_have()

    def refresh_have(self, *_):
        out = Path(self.out_edit.text().strip() or ".")
        ids = core.downloaded_ids(out)
        self.have = {tid for tid in self.titles if tid in ids}
        for r in range(self.table.rowCount()):
            self._paint(r)
        self.apply_filter()

    def _paint(self, r: int):
        tid = self.table.item(r, COL_ID).text()
        key = self.state.get(tid) or ("cached" if tid in self.have else "")
        item = self.table.item(r, COL_STATE)
        item.setText(STATE_TEXT.get(key, ""))
        item.setForeground(QBrush(QColor(STATE_COLOR.get(key, C["text"]))))

    def _is_got(self, tid: str) -> bool:
        return tid in self.have or self.state.get(tid) == "done"

    def apply_filter(self, *_):
        words = self.search.text().lower().split()
        kind = self.kind.currentData()
        lang = self.lang.currentData()
        only_new = self.only_new.isChecked()
        for r in range(self.table.rowCount()):
            tid = self.table.item(r, COL_ID).text()
            t = self.titles.get(tid)
            if t is None:
                continue
            hay = f"{t.id} {KIND_LABEL.get(t.kind, t.kind)} {t.kind} {t.language} {t.name}".lower()
            hide = any(w not in hay for w in words)
            hide = hide or (kind is not None and t.kind != kind)
            hide = hide or (lang is not None and t.language != lang)
            hide = hide or (only_new and self._is_got(tid))
            self.table.setRowHidden(r, hide)
        self.update_count()

    def update_count(self, *_):
        total = self.table.rowCount()
        visible = sum(1 for r in range(total) if not self.table.isRowHidden(r))
        checked = len(self.checked_items())
        self.count_label.setText(f"表示 {visible} / 全 {total}　　選択 {checked} 件")
        self.start_btn.setText(f"ダウンロード開始（{checked} 件）")

    def checked_items(self) -> list[tuple[str, str]]:
        out = []
        for r in range(self.table.rowCount()):
            if self._row_checked(r):
                tid = self.table.item(r, COL_ID).text()
                out.append((tid, self.titles[tid].name))
        return out

    def _on_clicked(self, item: QTableWidgetItem):
        if item.column() == COL_CHK:
            r = item.row()
            self._set_row_checked(r, not self._row_checked(r))
            self.update_count()

    def _on_double_clicked(self, item: QTableWidgetItem):
        if item.column() != COL_CHK:
            r = item.row()
            self._set_row_checked(r, not self._row_checked(r))
            self.update_count()

    def set_visible_checked(self, on: bool):
        for r in range(self.table.rowCount()):
            if not self.table.isRowHidden(r):
                self._set_row_checked(r, on)
        self.update_count()

    def invert_visible(self, *_):
        for r in range(self.table.rowCount()):
            if not self.table.isRowHidden(r):
                self._set_row_checked(r, not self._row_checked(r))
        self.update_count()

    def export_csv(self, *_):
        if not self.titles:
            QMessageBox.information(self, "CSV", "保存する一覧がありません。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "CSV を保存", "hlmv-list.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["ID", "種類", "言語", "タイトル", "取得済"])
                for t in self.titles.values():
                    w.writerow([t.id, KIND_LABEL.get(t.kind, t.kind), t.language, t.name,
                                "はい" if self._is_got(t.id) else ""])
        except OSError as e:
            QMessageBox.warning(self, "エラー", f"保存できませんでした: {e}")
            return
        self.statusBar().showMessage(f"CSV を保存しました: {path}")

    # ---------- ダウンロード ----------

    def start_download(self, *_):
        if self.is_downloading():
            return
        out = self.out_edit.text().strip()
        if not out:
            QMessageBox.warning(self, "出力先", "出力先フォルダを指定してください。")
            return
        if not core.hlmv_exe():
            QMessageBox.warning(self, "ツールがありません",
                                "ツールが見つかりません。\n「ツールの更新」から取得してください。")
            return
        items = self.checked_items()
        if not items:
            QMessageBox.information(self, "未選択", "ダウンロードするタイトルにチェックを入れてください。")
            return

        self._on_out_changed()
        for tid, _ in items:
            self.state.pop(tid, None)
        self.refresh_have()

        self.dl = DownloadWorker(items, out, self.keep.isChecked(), self)
        self.dl.log.connect(self.log_view.appendPlainText)
        self.dl.status.connect(self.set_state)
        self.dl.progress.connect(self._on_progress)
        self.dl.done.connect(self._on_done)
        self.progress.setRange(0, len(items))
        self.progress.setValue(0)
        self._set_busy(True)
        self.tabs.setCurrentIndex(0)
        self.log_view.appendPlainText(f"開始: {len(items)} 件（出力先: {out}）")
        self.dl.start()

    def stop_download(self, *_):
        if self.is_downloading():
            self.dl.cancel()
            self.stop_btn.setEnabled(False)
            self.statusBar().showMessage("停止しています…")

    def set_state(self, tid: str, key: str):
        self.state[tid] = key
        if key == "done":
            self.have.add(tid)
        for r in range(self.table.rowCount()):
            if self.table.item(r, COL_ID).text() == tid:
                self._paint(r)
                break

    def _on_progress(self, i: int, total: int):
        self.progress.setValue(i)

    def _on_done(self, ok: int, fail: int, cancelled: bool):
        self._set_busy(False)
        msg = f"完了: 成功 {ok} 件 / 失敗 {fail} 件" + ("（中止）" if cancelled else "")
        self.log_view.appendPlainText(msg)
        self.statusBar().showMessage(msg)
        self.refresh_have()
        if not cancelled:
            QMessageBox.information(self, "ダウンロード完了", msg)

    def _set_busy(self, busy: bool):
        self.start_btn.setEnabled(not busy)
        self.stop_btn.setEnabled(busy)

    # ---------- コマンドライン・ヘルプ ----------

    def run_custom(self, *_):
        exe = core.hlmv_exe()
        if not exe:
            QMessageBox.warning(self, "ツールがありません", "ツールが見つかりません。「ツールの更新」から取得してください。")
            return
        text = self.cmd_in.text().strip()
        args = [a.strip('"') for a in shlex.split(text, posix=False)] if text else []
        self.tabs.setCurrentIndex(1)
        self._run(lambda log: core.run([exe, *args], log=log),
                  log=self.cmd_out.appendPlainText, on_ok=lambda res: None)

    def load_help(self, *_):
        exe = core.hlmv_exe()
        if not exe:
            self.help_view.setPlainText("ツールが見つかりません。")
            return
        self._run(lambda log: core.run([exe, "--help"], log=log, quiet=True),
                  on_ok=lambda res: self.help_view.setPlainText(res[1] or "(出力なし)"))

    # ---------- ツール ----------

    def open_tool_dialog(self, *_):
        dlg = ToolDialog(self)
        dlg.changed.connect(self.reload_list)
        dlg.exec()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("hlmv-dl")
    app.setStyleSheet(qss())
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
