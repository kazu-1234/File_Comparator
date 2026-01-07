# -*- coding: utf-8 -*-
# バージョン: v1.5.2
# 作成日: 2026-01-08
"""
File Comparison Tool (GUI Version) v1.5.2

指定された「元フォルダ」と「比較先フォルダ」を比較します。
Windows版Google Drive（ファイルストリーム）での使用を想定し、
ファイルをダウンロードせずにメタデータのみで高速に判定する機能を備えています。

【機能追加 v1.5.2】
- 設定画面の「閉じる」ボタンを削除。

【機能追加 v1.5.1】
- 設定画面のレイアウト調整（免責事項が見切れる問題を修正）。

【機能追加 v1.5.0】
- 設定メニューを追加（バージョン情報、アップデート確認、免責事項）。
- GitHub経由でのアップデート確認機能を追加。

【機能追加 v1.4.0】
- 「不足分をコピー」機能を追加。
- 比較終了後、不足ファイルがある場合にボタンが有効化される。
- 実行ファイル(.pyw)と同じ場所に「Extracted_Missing_Files_...」フォルダを作成し、
  階層構造を維持したまま不足ファイルをコピーする。
"""

# --- ライブラリのインポート ---
import os
import sys
import threading
import traceback
import time
import shutil  # ファイルコピー用
import json
import urllib.request
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox

# Windowsのレジストリ操作用（テーマ検知）
try:
    import winreg
except ImportError:
    winreg = None

# 高DPI対応（Windows用）
try:
    import ctypes
    if sys.platform == 'win32':
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
except (ImportError, AttributeError):
    pass

# --- グローバル定数 ---
LOG_FILENAME = "comparison_result_log.txt"
GITHUB_REPO = "kazu-1234/file_comparator" # GitHubリポジトリ名 (ユーザー名/リポジトリ名)
CURRENT_VERSION = "v1.5.2" # 現在のバージョン

# --- ツールチップクラス ---
class ToolTip:
    """
    ウィジェットにカーソルを合わせたときに説明を表示するクラス。
    """
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.id = None
        # add="+" でイベントを共存させる
        self.widget.bind("<Enter>", self.schedule_show, add="+")
        self.widget.bind("<Leave>", self.hide_tip, add="+")
        self.widget.bind("<ButtonPress>", self.hide_tip, add="+")

    def schedule_show(self, event=None):
        self.unschedule()
        self.id = self.widget.after(500, self.show_tip) # 0.5秒後に表示

    def unschedule(self):
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None

    def show_tip(self, event=None):
        if self.tip_window or not self.text:
            return
        
        try:
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        except Exception:
            return
        
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True) # タイトルバーを消す
        tw.wm_geometry(f"+{x}+{y}")
        
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         background="#ffffe0", foreground="#000000",
                         relief=tk.SOLID, borderwidth=1,
                         font=("Yu Gothic UI", 10, "normal"))
        label.pack(ipadx=8, ipady=5)

    def hide_tip(self, event=None):
        self.unschedule()
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None

# --- カスタムラジオボタンクラス (Canvas描画 / 幅自動調整版) ---
class CustomRadioButton(tk.Canvas):
    """
    Canvasを使って描画するカスタムラジオボタン。
    テキストの長さに応じて幅を自動調整する。
    """
    def __init__(self, master, text, variable, value, height=40):
        super().__init__(master, height=height, highlightthickness=0, bd=0)
        self.text = text
        self.variable = variable
        self.value = value
        self.colors = {}
        
        # 描画サイズの設定
        self.radius = 10 # 半径
        self.center_y = height // 2
        self.center_x = 20
        self.line_width = 3 # 枠線の太さ

        # テキスト幅の計算とキャンバス幅の設定
        self._adjust_width()

        # イベントバインド
        self.bind("<Button-1>", self.on_click)
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        
        # 変数の変更を監視
        self.variable.trace_add("write", self.update_display)
        
        self.is_hover = False

    def _adjust_width(self):
        """テキストの長さを測定してCanvasの幅を設定する"""
        font = ("Yu Gothic UI", 10, "normal")
        text_id = self.create_text(0, 0, text=self.text, font=font, anchor="nw")
        bbox = self.bbox(text_id)
        self.delete(text_id)
        
        if bbox:
            text_width = bbox[2] - bbox[0]
            total_width = (self.center_x + self.radius + 15) + text_width + 10
            self.configure(width=total_width)
        else:
            self.configure(width=200)

    def set_colors(self, colors):
        """テーマカラーを受け取って更新"""
        self.colors = colors
        self.configure(bg=colors["bg"])
        self.update_display()

    def on_click(self, event):
        self.variable.set(self.value)

    def on_enter(self, event):
        self.is_hover = True
        self.update_display()

    def on_leave(self, event):
        self.is_hover = False
        self.update_display()

    def update_display(self, *args):
        if not self.colors: return
        self.delete("all")

        is_selected = (self.variable.get() == self.value)
        
        fg_color = self.colors["radio_text"]
        accent_color = self.colors["btn"]
        bg_color = self.colors["bg"]

        outline_color = accent_color if (is_selected or self.is_hover) else fg_color
        
        self.create_oval(
            self.center_x - self.radius, self.center_y - self.radius,
            self.center_x + self.radius, self.center_y + self.radius,
            outline=outline_color, width=self.line_width
        )

        if is_selected:
            inner_radius = self.radius - 5
            self.create_oval(
                self.center_x - inner_radius, self.center_y - inner_radius,
                self.center_x + inner_radius, self.center_y + inner_radius,
                fill=accent_color, outline=accent_color
            )

        self.create_text(
            self.center_x + self.radius + 15, self.center_y,
            text=self.text, anchor="w", fill=fg_color,
            font=("Yu Gothic UI", 10, "bold" if is_selected else "normal")
        )

# --- メインアプリクラス ---
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"File Comparator {CURRENT_VERSION}")
        self.geometry("850x700")

        # システムのテーマ設定を検出
        self.is_dark_mode = self._detect_system_theme()
        
        # カラーパレット定義
        self.colors = {
            "dark": {
                "bg": "#2e2e2e", "frame": "#3c3c3c", "text": "#ffffff",
                "btn": "#007aff", "btn_hover": "#005ecb", "btn_text": "#ffffff",
                "log_bg": "#1e1e1e", "log_fg": "#d4d4d4", "entry_bg": "#505050", "entry_fg": "#ffffff",
                "stop_btn": "#c0392b", "stop_btn_active": "#e74c3c",
                "radio_text": "#ffffff"
            },
            "light": {
                "bg": "#f0f0f0", "frame": "#ffffff", "text": "#333333",
                "btn": "#007aff", "btn_hover": "#005ecb", "btn_text": "#ffffff",
                "log_bg": "#ffffff", "log_fg": "#333333", "entry_bg": "#ffffff", "entry_fg": "#333333",
                "stop_btn": "#e74c3c", "stop_btn_active": "#ff6b6b",
                "radio_text": "#333333"
            }
        }

        self._setup_variables()
        self._setup_styles()
        self._create_widgets()
        self._apply_theme_colors()

        self.log(f"ようこそ！ {CURRENT_VERSION}")
        self.log(f"現在のシステムテーマ({'ダーク' if self.is_dark_mode else 'ライト'})を適用しました。")
        self.log("Google Drive対応：ファイルをダウンロードせずにメタデータのみで比較します。")

    def _detect_system_theme(self):
        """Windowsのシステムテーマ設定（アプリモード）を検出する"""
        if sys.platform == 'win32' and winreg:
            try:
                key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                    value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                    return value == 0 # 0ならダークモード
            except OSError:
                pass
        return True # デフォルト

    def _setup_variables(self):
        self.stop_event = threading.Event()
        self.source_dir_var = tk.StringVar()
        self.target_dir_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="simple")
        
        # 結果保持用
        self.last_missing_items = []
        self.last_source_dir = ""

    def _get_current_colors(self):
        return self.colors["dark"] if self.is_dark_mode else self.colors["light"]

    def _setup_styles(self):
        self.style = ttk.Style(self)
        self.style.theme_use('clam')

    def _apply_theme_colors(self):
        c = self._get_current_colors()
        self.configure(bg=c["bg"])

        self.style.configure("TButton", font=("Yu Gothic UI", 10, "bold"), padding=10, relief="flat", background=c["btn"], foreground=c["btn_text"], borderwidth=0)
        self.style.map("TButton", background=[('active', c["btn_hover"]), ('disabled', c["frame"])])
        
        self.style.configure("Stop.TButton", background=c["stop_btn"], foreground=c["btn_text"])
        self.style.map("Stop.TButton", background=[('active', c["stop_btn_active"]), ('disabled', c["frame"])])

        self.style.configure("Main.TFrame", background=c["bg"])
        self.style.configure("Control.TFrame", background=c["frame"])
        self.style.configure("Header.TLabel", background=c["bg"], foreground=c["text"], font=("Yu Gothic UI", 16, "bold"))
        self.style.configure("Normal.TLabel", background=c["bg"], foreground=c["text"], font=("Yu Gothic UI", 10))
        
        if hasattr(self, 'entry_source'):
            self.entry_source.config(bg=c["entry_bg"], fg=c["entry_fg"], insertbackground=c["text"])
            self.entry_target.config(bg=c["entry_bg"], fg=c["entry_fg"], insertbackground=c["text"])
        if hasattr(self, 'log_area'):
            self.log_area.config(bg=c["log_bg"], fg=c["log_fg"], insertbackground=c["text"])
        
        if hasattr(self, 'rb_simple'):
            self.rb_simple.set_colors(c)
            self.rb_detailed.set_colors(c)

    def _create_widgets(self):
        main_frame = ttk.Frame(self, padding="15", style="Main.TFrame")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        header_frame = ttk.Frame(main_frame, style="Main.TFrame")
        header_frame.pack(fill=tk.X, pady=(0, 20))
        ttk.Label(header_frame, text="File Comparator", style="Header.TLabel").pack(side=tk.LEFT)
        
        # 設定ボタン (右上に配置)
        self.btn_settings = ttk.Button(header_frame, text="⚙ 設定", width=8, command=self.open_settings)
        self.btn_settings.pack(side=tk.RIGHT)

        # Folder Input
        input_frame = ttk.Frame(main_frame, style="Main.TFrame")
        input_frame.pack(fill=tk.X, pady=5)
        input_frame.columnconfigure(1, weight=1)

        ttk.Label(input_frame, text="元フォルダ (基準):", style="Normal.TLabel").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.entry_source = tk.Entry(input_frame, textvariable=self.source_dir_var, relief=tk.FLAT)
        self.entry_source.grid(row=0, column=1, sticky="ew", padx=5, pady=5, ipady=4)
        ttk.Button(input_frame, text="参照...", width=8, command=lambda: self._select_dir(self.source_dir_var)).grid(row=0, column=2, padx=5, pady=5)

        ttk.Label(input_frame, text="比較先フォルダ:", style="Normal.TLabel").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.entry_target = tk.Entry(input_frame, textvariable=self.target_dir_var, relief=tk.FLAT)
        self.entry_target.grid(row=1, column=1, sticky="ew", padx=5, pady=5, ipady=4)
        ttk.Button(input_frame, text="参照...", width=8, command=lambda: self._select_dir(self.target_dir_var)).grid(row=1, column=2, padx=5, pady=5)

        # Mode Selection
        mode_frame = ttk.Frame(main_frame, style="Main.TFrame")
        mode_frame.pack(fill=tk.X, pady=(20, 10))
        ttk.Label(mode_frame, text="比較モード:", style="Normal.TLabel").pack(side=tk.LEFT, padx=(5, 15))
        
        self.rb_simple = CustomRadioButton(mode_frame, text="簡易モード (ファイル名のみ)", variable=self.mode_var, value="simple")
        self.rb_simple.pack(side=tk.LEFT, padx=10)
        
        self.rb_detailed = CustomRadioButton(mode_frame, text="詳細モード", variable=self.mode_var, value="detailed")
        self.rb_detailed.pack(side=tk.LEFT, padx=10)

        # Tooltips
        ToolTip(self.rb_simple, "【簡易モード】\nファイル名（パス）だけで比較します。\nクラウド上のファイルをダウンロードせずに\n最も高速にチェックできます。")
        ToolTip(self.rb_detailed, "【詳細モード】\nファイル名に加え、ファイルサイズと作成日時も比較します。\n中身（ハッシュ）は読み込みませんが、メタデータを取得するため\n簡易モードよりわずかに時間がかかります。\n同名でも更新されていないファイル等を検出したい場合に有効です。")

        # Action Buttons
        action_frame = ttk.Frame(main_frame, style="Main.TFrame")
        action_frame.pack(fill=tk.X, pady=20)
        action_frame.columnconfigure((0, 1, 2), weight=1)

        self.btn_run = ttk.Button(action_frame, text="比較を実行", command=self.start_comparison_thread)
        self.btn_run.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        self.btn_copy = ttk.Button(action_frame, text="不足分をコピー", command=self.start_copy_thread)
        self.btn_copy.grid(row=0, column=1, sticky="ew", padx=(5, 5))
        self.btn_copy.config(state=tk.DISABLED) # 初期は無効

        self.btn_stop = ttk.Button(action_frame, text="中断", command=self.stop_current_task, style="Stop.TButton")
        self.btn_stop.grid(row=0, column=2, sticky="ew", padx=(5, 0))
        self.btn_stop.config(state=tk.DISABLED)

        # Log Area
        ttk.Label(main_frame, text="実行ログ:", style="Normal.TLabel").pack(anchor="w", pady=(10, 0))
        self.log_area = scrolledtext.ScrolledText(main_frame, wrap=tk.NONE, height=15, font=("Consolas", 10), relief=tk.FLAT, borderwidth=0)
        self.log_area.pack(fill=tk.BOTH, expand=True, pady=5)
        self.log_area.configure(state='disabled')

    def log(self, message):
        if self.log_area:
            timestamp = time.strftime("[%H:%M:%S] ")
            self.log_area.configure(state='normal')
            self.log_area.insert(tk.END, timestamp + message + "\n")
            self.log_area.configure(state='disabled')
            self.log_area.see(tk.END)
            self.update_idletasks()

    def _select_dir(self, string_var):
        path = filedialog.askdirectory(parent=self)
        if path: string_var.set(path.replace('/', os.sep))

    def set_buttons_state(self, is_running):
        self.btn_run.config(state=tk.DISABLED if is_running else tk.NORMAL)
        self.btn_stop.config(state=tk.NORMAL if is_running else tk.DISABLED)
        # コピーボタンは実行中は無効、実行していないときは「不足ファイルがあれば有効」
        if is_running:
            self.btn_copy.config(state=tk.DISABLED)
        else:
            self.btn_copy.config(state=tk.NORMAL if self.last_missing_items else tk.DISABLED)

    # --- 比較処理 ---
    def start_comparison_thread(self):
        source = self.source_dir_var.get().strip()
        target = self.target_dir_var.get().strip()

        if not source or not os.path.exists(source):
            messagebox.showwarning("警告", "有効な「元フォルダ」を選択してください。")
            return
        if not target or not os.path.exists(target):
            messagebox.showwarning("警告", "有効な「比較先フォルダ」を選択してください。")
            return
        if os.path.abspath(source) == os.path.abspath(target):
            messagebox.showwarning("警告", "元フォルダと比較先フォルダが同じです。")
            return

        self.last_missing_items = [] # リセット
        self.last_source_dir = ""
        self.set_buttons_state(is_running=True)
        self.stop_event.clear()
        
        self.log_area.configure(state='normal')
        self.log_area.delete('1.0', tk.END)
        self.log_area.configure(state='disabled')

        mode = self.mode_var.get()
        thread = threading.Thread(target=self._process_comparison, args=(source, target, mode), daemon=True)
        thread.start()
        self.monitor_thread(thread)

    def _process_comparison(self, source_dir, target_dir, mode):
        try:
            mode_label = "詳細モード" if mode == "detailed" else "簡易モード"
            self.log(f"■ {mode_label}で処理を開始します")
            self.log(f"元フォルダ: {source_dir}")
            self.log(f"比較先フォルダ: {target_dir}")
            self.log("-" * 40)

            self.log("元フォルダをスキャン中...")
            source_files = self._get_files_info(source_dir, mode)
            if self.stop_event.is_set(): return
            self.log(f"-> {len(source_files)} 個のファイル")

            self.log("比較先フォルダをスキャン中...")
            target_files = self._get_files_info(target_dir, mode)
            if self.stop_event.is_set(): return
            self.log(f"-> {len(target_files)} 個のファイル")

            self.log("差分を計算中...")
            source_keys = set(source_files.keys())
            target_keys = set(target_files.keys())

            missing_items = sorted(list(source_keys - target_keys))
            mismatch_items = []
            if mode == "detailed":
                common_items = source_keys & target_keys
                for rel_path in common_items:
                    s_info = source_files[rel_path]
                    t_info = target_files[rel_path]
                    if 'error' in s_info or 'error' in t_info: continue
                    size_diff = s_info['size'] != t_info['size']
                    time_diff = abs(s_info['ctime'] - t_info['ctime']) > 2.0
                    if size_diff or time_diff:
                        reason = []
                        if size_diff: reason.append(f"サイズ不一致(元:{s_info['size']:,} B, 先:{t_info['size']:,} B)")
                        if time_diff: reason.append("作成日時不一致")
                        mismatch_items.append((rel_path, ", ".join(reason)))

            # 結果保持（コピー機能用）
            self.last_missing_items = missing_items
            self.last_source_dir = source_dir

            self.log("-" * 40)
            total_issues = len(missing_items) + len(mismatch_items)
            self.log(f"結果: 合計 {total_issues} 件の問題が見つかりました。")
            if len(missing_items) > 0: self.log(f"  - 不足: {len(missing_items)} 件")
            if len(mismatch_items) > 0: self.log(f"  - 不一致: {len(mismatch_items)} 件")
            self.log("-" * 40)

            if total_issues == 0:
                self.log("おめでとうございます！差異はありません。")
                return

            if missing_items:
                self.log("【不足しているファイル】")
                for item in missing_items:
                    if self.stop_event.is_set(): return
                    self.log(f"[不足] {item}")
                
                # 不足がある場合のみ案内
                self.log("\n※「不足分をコピー」ボタンで抽出可能です。")

            if mismatch_items:
                self.log("\n【不一致のファイル】")
                for item, reason in sorted(mismatch_items, key=lambda x: x[0]):
                    if self.stop_event.is_set(): return
                    self.log(f"[不一致] {item} ({reason})")

        except Exception:
            self.log("予期せぬエラーが発生しました。")
            self.log(traceback.format_exc())

    # --- コピー処理 ---
    def start_copy_thread(self):
        if not self.last_missing_items or not self.last_source_dir:
            return
        
        # 実行ファイルの場所を取得
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            
        timestamp = time.strftime('%Y-%m-%d_%H-%M-%S')
        dest_root = os.path.join(base_dir, f"Extracted_Missing_Files_{timestamp}")

        if not messagebox.askyesno("確認", f"不足ファイルを以下のフォルダにコピーしますか？\n\n{dest_root}"):
            return

        self.set_buttons_state(is_running=True)
        self.stop_event.clear()
        
        thread = threading.Thread(target=self._process_copy, args=(dest_root,), daemon=True)
        thread.start()
        self.monitor_thread(thread)

    def _process_copy(self, dest_root):
        try:
            self.log(f"\n■ コピー処理を開始します...")
            self.log(f"出力先: {dest_root}")
            
            os.makedirs(dest_root, exist_ok=True)
            
            count = 0
            total = len(self.last_missing_items)
            
            for rel_path in self.last_missing_items:
                if self.stop_event.is_set():
                    self.log("コピーを中断しました。")
                    return
                
                src_path = os.path.join(self.last_source_dir, rel_path)
                dst_path = os.path.join(dest_root, rel_path)
                
                try:
                    # フォルダ階層作成
                    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                    # コピー (メタデータも保持)
                    shutil.copy2(src_path, dst_path)
                    count += 1
                    if count % 10 == 0: # ログが多すぎないように間引く
                        self.log(f"コピー中 ({count}/{total}): {rel_path}")
                except Exception as e:
                    self.log(f"エラー: コピー失敗 {rel_path}: {e}")

            self.log("-" * 40)
            self.log(f"コピー完了: {count}/{total} ファイル")
            self.log(f"保存先: {dest_root}")
            
            # 完了後フォルダを開く
            try:
                os.startfile(dest_root)
            except:
                pass

        except Exception:
            self.log("コピー中にエラーが発生しました。")
            self.log(traceback.format_exc())

    # --- 共通スレッド制御 ---
    def stop_current_task(self):
        self.log("停止信号を送信しました...")
        self.stop_event.set()
        self.btn_stop.config(state=tk.DISABLED)

    def monitor_thread(self, thread):
        if thread.is_alive():
            self.after(100, lambda: self.monitor_thread(thread))
        else:
            self.set_buttons_state(is_running=False)
            if self.stop_event.is_set(): pass # ログは各処理内で出す
            else: self.log("\n処理が完了しました。")

    def _get_files_info(self, root_dir, mode):
        file_map = {}
        root_dir_len = len(root_dir)
        try:
            for root, dirs, files in os.walk(root_dir):
                if self.stop_event.is_set(): break
                for filename in files:
                    full_path = os.path.join(root, filename)
                    rel_path = full_path[root_dir_len:].lstrip(os.sep)
                    info = {'path': full_path}
                    if mode == "detailed":
                        try:
                            stat = os.stat(full_path)
                            info['size'] = stat.st_size
                            info['ctime'] = stat.st_ctime
                        except OSError as e:
                            info['error'] = str(e)
                    file_map[rel_path] = info
        except Exception as e:
            self.log(f"エラー: フォルダスキャン失敗: {e}")
            return {}
        return file_map

    # --- 設定画面・アップデートなど ---
    def open_settings(self):
        """設定画面を開く"""
        settings_win = tk.Toplevel(self)
        settings_win.title("設定")
        settings_win.geometry("450x400") # サイズ拡張
        settings_win.grab_set() # モーダルにする
        
        # テーマ適用 (簡易的)
        bg_color = self.colors["dark"]["bg"] if self.is_dark_mode else self.colors["light"]["bg"]
        fg_color = self.colors["dark"]["text"] if self.is_dark_mode else self.colors["light"]["text"]
        settings_win.configure(bg=bg_color)

        frame = tk.Frame(settings_win, bg=bg_color, padx=20, pady=20)
        frame.pack(fill=tk.BOTH, expand=True)

        # バージョン表示
        tk.Label(frame, text="File Comparator", font=("Yu Gothic UI", 14, "bold"), bg=bg_color, fg=fg_color).pack(pady=(0, 5))
        tk.Label(frame, text=f"Version: {CURRENT_VERSION}", font=("Yu Gothic UI", 10), bg=bg_color, fg=fg_color).pack(pady=(0, 20))

        # アップデートボタン
        btn_update = ttk.Button(frame, text="アップデートを確認", command=lambda: self.check_update(settings_win), width=20)
        btn_update.pack(pady=10)

        # 免責事項
        disclaimer_frame = tk.LabelFrame(frame, text="免責事項", bg=bg_color, fg=fg_color, padx=10, pady=10)
        disclaimer_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        disclaimer_text = (
            "本ソフトウェアの使用により生じたいかなる損害\n"
            "（データ損失、システム不具合など）についても、\n"
            "開発者は一切の責任を負いません。\n"
            "必ずバックアップを取った上で、\n"
            "ユーザー自身の責任において使用してください。"
        )
        tk.Label(disclaimer_frame, text=disclaimer_text, justify=tk.LEFT, bg=bg_color, fg=fg_color, font=("Yu Gothic UI", 9)).pack(anchor="w")

        # 閉じるボタン削除 (設定画面は右上の×で閉じる)
        # ttk.Button(frame, text="閉じる", command=settings_win.destroy).pack(pady=(10, 0))

    def check_update(self, parent_win):
        """GitHubから最新リリースを確認する"""
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(url)
            # GitHub APIはUser-Agentが必要な場合がある
            req.add_header('User-Agent', 'Python/FileComparator')
            
            with urllib.request.urlopen(req) as res:
                data = json.loads(res.read().decode('utf-8'))
                latest_tag = data.get('tag_name', '')
                html_url = data.get('html_url', '')

            if not latest_tag:
                messagebox.showinfo("確認", "最新バージョンの取得に失敗しました。", parent=parent_win)
                return

            # バージョン比較 (簡易的に文字列比較)
            # v1.5.0 と v1.5.1 などを比較。数字部分をパースするのが厳密だが、
            # ここでは単純にタグが現在のバージョンと異なるかどうかで判定する。
            if latest_tag != CURRENT_VERSION:
                # バージョンが違う（新しいと仮定）
                msg = f"新しいバージョンが見つかりました: {latest_tag}\n\nダウンロードページを開きますか？"
                if messagebox.askyesno("アップデート", msg, parent=parent_win):
                    webbrowser.open(html_url)
            else:
                messagebox.showinfo("確認", "お使いのバージョンは最新です。", parent=parent_win)

        except urllib.error.HTTPError as e:
            if e.code == 404:
                messagebox.showwarning("エラー", "リポジトリまたはリリースが見つかりません。", parent=parent_win)
            else:
                messagebox.showerror("エラー", f"通信エラーが発生しました: {e.code}", parent=parent_win)
        except Exception as e:
            messagebox.showerror("エラー", f"アップデート確認中にエラーが発生しました。\n{e}", parent=parent_win)

if __name__ == "__main__":
    try:
        app = App()
        app.mainloop()
    except Exception as e:
        error_msg = traceback.format_exc()
        try:
            with open("launch_error.log", "w", encoding="utf-8") as f:
                f.write(error_msg)
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("起動エラー", f"エラーが発生しました。\n\n{e}\n\n詳細は launch_error.log を確認してください。")
        except: pass