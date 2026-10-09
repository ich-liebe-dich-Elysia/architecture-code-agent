"""Chinese desktop interface for the DeepSeek architecture coding Agent."""

from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from agent.game_launcher import GameLauncher, project_root


class AgentDesktop:
    """Run generation on a worker thread while Tk owns all screen updates."""

    def __init__(self, window: tk.Tk) -> None:
        self.window = window
        self.root = project_root()
        self.events: queue.Queue[dict] = queue.Queue(maxsize=400)
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.launcher = GameLauncher()
        self.closed = False
        self.busy = False
        self.game_busy = False
        self.game_project: Path | None = self._find_existing_game()
        self.documentation = tk.StringVar(value=str(self.root / "input" / "Architecture_Documentation.md"))
        self.views = tk.StringVar(value=str(self.root / "input" / "Architecture_View.md"))
        default_key = self.root.parent / "key.txt"
        self.key_file = tk.StringVar(value=str(default_key) if default_key.is_file() else "")
        self.api_key = tk.StringVar()
        self.model = tk.StringVar(value="deepseek-flash")
        self.base_url = tk.StringVar(value="https://api.deepseek.com")
        self.status = tk.StringVar(value="就绪 · 选择架构文档，连接 DeepSeek 并生成可运行项目")
        self.output_text = tk.StringVar(value=str(self.game_project or self.root / "output"))
        self._build_window()
        self._append_log("欢迎使用 Architecture Code Agent。生成时会调用 DeepSeek API，并安装、测试生成项目。")
        self._append_log("生成结果保存在 output 下的新目录中。已有游戏可直接点击“打开游戏”体验。")
        self.window.protocol("WM_DELETE_WINDOW", self._close)
        self.window.after(120, self._poll_events)

    def _find_existing_game(self) -> Path | None:
        output = self.root / "output"
        if not output.is_dir():
            return None
        marker = output / "latest-project.json"
        if marker.is_file():
            try:
                data = json.loads(marker.read_text(encoding="utf-8"))
                value = data.get("path")
                if isinstance(value, str) and value:
                    project = (output / value).resolve()
                    if project.is_relative_to(output.resolve()) and (project / "src" / "app.js").is_file() and (project / "public" / "index.html").is_file():
                        return project
            except (OSError, ValueError, TypeError, AttributeError):
                pass
        latest = self.root / ".agent" / "latest.json"
        if latest.is_file():
            try:
                data = json.loads(latest.read_text(encoding="utf-8"))
                value = data.get("project") or data.get("project_dir")
                if value:
                    project = Path(value)
                    if not project.is_absolute():
                        project = self.root / project
                    if (project / "src" / "app.js").is_file() and (project / "public" / "index.html").is_file():
                        return project
            except (OSError, ValueError, TypeError, AttributeError):
                pass
        candidates = [p for p in output.glob("space-fractions-llm*") if (p / "src" / "app.js").is_file() and (p / "public" / "index.html").is_file()]
        return max(candidates, key=lambda p: p.stat().st_mtime, default=None)

    def _build_window(self) -> None:
        window = self.window
        window.title("Architecture Code Agent · DeepSeek")
        window.geometry("1040x800")
        window.minsize(850, 690)
        window.configure(bg="#eef3f9")
        style = ttk.Style(window)
        style.theme_use("clam")
        style.configure("TFrame", background="#eef3f9")
        style.configure("Card.TFrame", background="white")
        style.configure("TLabel", background="#eef3f9", foreground="#172b4d", font=("Microsoft YaHei UI", 10))
        style.configure("Card.TLabel", background="white")
        style.configure("Muted.TLabel", background="#eef3f9", foreground="#5b6b84", font=("Microsoft YaHei UI", 9))
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 23, "bold"), foreground="#123768")
        style.configure("Section.TLabel", background="white", font=("Microsoft YaHei UI", 12, "bold"))
        style.configure("TButton", padding=(14, 8), font=("Microsoft YaHei UI", 10))
        style.configure("Primary.TButton", background="#245bc2", foreground="white", borderwidth=0)
        style.map("Primary.TButton", background=[("active", "#174baa"), ("disabled", "#9db5da")], foreground=[("disabled", "white")])
        style.configure("TEntry", padding=7, fieldbackground="#f7f9fd")
        style.configure("Horizontal.TProgressbar", background="#3476e4", troughcolor="#dde7f4")

        shell = ttk.Frame(window, padding=(26, 20))
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(3, weight=1)
        ttk.Label(shell, text="Architecture Code Agent", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(shell, text="架构文档 → DeepSeek 生成代码 → 自动测试与修复 → 交互式分数游戏", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(5, 17))

        form = ttk.Frame(shell, style="Card.TFrame", padding=18)
        form.grid(row=2, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="项目输入与模型连接", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        self._file_row(form, 1, "架构说明", self.documentation, [("Markdown 文档", "*.md"), ("所有文件", "*.*")])
        self._file_row(form, 2, "UML 视图", self.views, [("Markdown 文档", "*.md"), ("所有文件", "*.*")])
        self._file_row(form, 3, "密钥文件", self.key_file, [("文本文件", "*.txt"), ("所有文件", "*.*")])
        ttk.Label(form, text="或输入 API Key", style="Card.TLabel").grid(row=4, column=0, sticky="w", padx=(0, 14), pady=5)
        ttk.Entry(form, textvariable=self.api_key, show="●").grid(row=4, column=1, columnspan=2, sticky="ew", pady=5)
        ttk.Label(form, text="模型", style="Card.TLabel").grid(row=5, column=0, sticky="w", pady=5)
        model_row = ttk.Frame(form, style="Card.TFrame")
        model_row.grid(row=5, column=1, columnspan=2, sticky="ew", pady=5)
        model_row.columnconfigure(2, weight=1)
        ttk.Combobox(model_row, textvariable=self.model, values=("deepseek-flash", "deepseek-v4-pro"), width=22).grid(row=0, column=0, sticky="w")
        ttk.Label(model_row, text="API 地址", style="Card.TLabel").grid(row=0, column=1, padx=(18, 10))
        ttk.Entry(model_row, textvariable=self.base_url).grid(row=0, column=2, sticky="ew")
        ttk.Label(form, text="直接输入的密钥仅用于本次运行；留空时使用密钥文件或 DEEPSEEK_API_KEY 环境变量。", style="Card.TLabel", font=("Microsoft YaHei UI", 9)).grid(row=6, column=0, columnspan=3, sticky="w", pady=(7, 2))

        activity = ttk.Frame(shell, padding=(0, 17, 0, 0))
        activity.grid(row=3, column=0, sticky="nsew")
        activity.columnconfigure(0, weight=1)
        activity.rowconfigure(2, weight=1)
        toolbar = ttk.Frame(activity)
        toolbar.grid(row=0, column=0, sticky="ew")
        self.generate_button = ttk.Button(toolbar, text="开始生成项目", style="Primary.TButton", command=self._generate)
        self.generate_button.pack(side="left")
        self.cancel_button = ttk.Button(toolbar, text="取消生成", command=self._cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=(10, 0))
        self.open_button = ttk.Button(toolbar, text="打开游戏", command=self._open_game)
        self.open_button.pack(side="right")
        self.stop_button = ttk.Button(toolbar, text="停止游戏", command=self._stop_game, state="disabled")
        self.stop_button.pack(side="right", padx=(0, 10))
        self.progress = ttk.Progressbar(activity, mode="indeterminate")
        self.progress.grid(row=1, column=0, sticky="ew", pady=(14, 10))
        log_frame = ttk.Frame(activity)
        log_frame.grid(row=2, column=0, sticky="nsew")
        self.log = tk.Text(log_frame, wrap="word", height=10, background="#10233e", foreground="#deebff", insertbackground="white", relief="flat", borderwidth=0, padx=13, pady=10, font=("Microsoft YaHei UI", 9), state="disabled")
        self.log.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(log_frame, command=self.log.yview)
        scrollbar.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scrollbar.set)

        footer = ttk.Frame(shell, padding=(0, 10, 0, 0))
        footer.grid(row=4, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status, wraplength=850).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(footer, textvariable=self.output_text, style="Muted.TLabel", wraplength=750).grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Button(footer, text="打开结果目录", command=self._open_folder).grid(row=1, column=1, sticky="e", padx=(10, 0))

    def _file_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, filetypes: list[tuple[str, str]]) -> None:
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 14), pady=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=5)
        def pick() -> None:
            filename = filedialog.askopenfilename(parent=self.window, title=f"选择{label}", initialdir=str(self.root), filetypes=filetypes)
            if filename:
                variable.set(filename)
        ttk.Button(parent, text="浏览…", command=pick).grid(row=row, column=2, padx=(10, 0), pady=5)

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message[:5000] + "\n")
        lines = int(self.log.index("end-1c").split(".")[0])
        if lines > 500:
            self.log.delete("1.0", f"{lines - 500}.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _emit(self, event: dict) -> None:
        if self.closed:
            return
        try:
            self.events.put_nowait(event)
        except queue.Full:
            try:
                self.events.get_nowait()
            except queue.Empty:
                pass
            try:
                self.events.put_nowait(event)
            except queue.Full:
                pass

    def _generate(self) -> None:
        if self.busy:
            return
        documentation = Path(self.documentation.get().strip())
        views = Path(self.views.get().strip())
        for label, path in (("架构说明", documentation), ("UML 视图", views)):
            if not path.is_file():
                messagebox.showerror("无法生成", f"{label}文件不存在：\n{path}", parent=self.window)
                return
        key_path_text = self.key_file.get().strip()
        api_key = self.api_key.get().strip() or None
        key_path = Path(key_path_text) if key_path_text else None
        if not api_key and key_path is not None and not key_path.is_file():
            messagebox.showerror("无法生成", "密钥文件不存在，请重新选择或直接输入 API Key。", parent=self.window)
            return
        if not api_key and key_path is None and not os.environ.get("DEEPSEEK_API_KEY"):
            messagebox.showerror("缺少 API Key", "请选择 DeepSeek 密钥文件，或在界面中输入 API Key。", parent=self.window)
            return
        model = self.model.get().strip()
        base_url = self.base_url.get().strip()
        if not model or not base_url:
            messagebox.showerror("无法生成", "模型名称和 API 地址不能为空。", parent=self.window)
            return
        self.stop_event = threading.Event()
        self.busy = True
        self.generate_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.progress.start(12)
        self.status.set("正在生成 · 模型生成代码可能需要几分钟")
        self._append_log(f"\n开始生成：模型 {model}；输入 {documentation.name} / {views.name}")
        self.api_key.set("")

        def work() -> None:
            try:
                from agent.llm_workflow import run_generation

                result = run_generation(
                    documentation=documentation,
                    views=views,
                    output_root=self.root / "output",
                    api_key=api_key,
                    key_file=key_path,
                    base_url=base_url,
                    model=model,
                    max_repairs=2,
                    on_event=self._emit,
                    stop_event=self.stop_event,
                )
                self._emit({"_kind": "finished", "path": str(result)})
            except Exception as error:
                message = str(error)
                if api_key:
                    message = message.replace(api_key, "[API Key 已隐藏]")
                self._emit({"_kind": "generation_error", "message": message})
        self.worker = threading.Thread(target=work, name="agent-generation", daemon=True)
        self.worker.start()

    def _cancel(self) -> None:
        self.stop_event.set()
        self.cancel_button.configure(state="disabled")
        self.status.set("已请求取消 · 将在当前 API 请求或校验结束后停止")
        self._append_log("已请求取消。正在进行的网络请求可能需要等待超时或返回。")

    def _open_game(self) -> None:
        if self.game_busy:
            return
        project = self.game_project or self._find_existing_game()
        if project is None:
            directory = filedialog.askdirectory(parent=self.window, title="选择已生成的游戏项目目录", initialdir=str(self.root / "output"))
            if not directory:
                return
            project = Path(directory)
        self.game_project = project
        self.output_text.set(str(project))
        self.game_busy = True
        self.open_button.configure(state="disabled")
        self._append_log(f"正在启动游戏：{project.name}")
        def start() -> None:
            try:
                url = self.launcher.start(project)
                self._emit({"_kind": "game_started", "url": url})
            except Exception as error:
                self._emit({"_kind": "game_error", "message": str(error)})
        threading.Thread(target=start, name="game-launcher", daemon=True).start()

    def _stop_game(self) -> None:
        self.stop_button.configure(state="disabled")
        self.open_button.configure(state="disabled")
        self.game_busy = True
        def stop() -> None:
            self.launcher.stop()
            self._emit({"_kind": "game_stopped"})
        threading.Thread(target=stop, daemon=True).start()

    def _open_folder(self) -> None:
        path = self.game_project or self.root / "output"
        if not path.is_dir():
            path = self.root
        if os.name == "nt":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _poll_events(self) -> None:
        if self.closed:
            return
        for _ in range(50):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind = event.get("_kind")
            if kind in ("finished", "generation_error"):
                self.busy = False
                self.progress.stop()
                self.generate_button.configure(state="normal")
                self.cancel_button.configure(state="disabled")
                if kind == "finished":
                    self.game_project = Path(event["path"])
                    self.output_text.set(str(self.game_project))
                    self.status.set("生成完成 · 点击“打开游戏”体验生成结果")
                    self._append_log(f"生成完成：{self.game_project}")
                else:
                    cancelled = self.stop_event.is_set()
                    self.status.set("已取消生成" if cancelled else "生成失败 · 请查看下方原因后重试")
                    self._append_log(event["message"])
                    if not cancelled:
                        messagebox.showerror("生成失败", event["message"][:2000], parent=self.window)
            elif kind in ("game_started", "game_stopped", "game_error"):
                self.game_busy = False
                self.open_button.configure(state="normal")
                self.stop_button.configure(state="normal" if self.launcher.running else "disabled")
                if kind == "game_started":
                    self._append_log(f"游戏已在浏览器打开：{event['url']}")
                    if not self.busy:
                        self.status.set(f"游戏运行中 · {event['url']} · 关闭 Agent 会停止游戏服务")
                elif kind == "game_stopped":
                    self._append_log("游戏服务已停止。")
                    if not self.busy:
                        self.status.set("游戏已停止 · 可随时重新打开")
                else:
                    self._append_log(event["message"])
                    messagebox.showerror("无法打开游戏", event["message"][:2000], parent=self.window)
            else:
                message = str(event.get("message", ""))
                if message:
                    self._append_log(message)
                    if not self.stop_event.is_set():
                        self.status.set(message[:150])
        self.window.after(120, self._poll_events)

    def _close(self) -> None:
        if self.busy and not messagebox.askyesno("关闭 Agent", "当前生成尚未结束。关闭会请求取消，未完成的项目将保留。确定关闭？", parent=self.window):
            return
        self.closed = True
        self.stop_event.set()
        self.launcher.stop()
        self.window.destroy()


def main() -> None:
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    window = tk.Tk()
    AgentDesktop(window)
    window.mainloop()


if __name__ == "__main__":
    main()
