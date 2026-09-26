#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser, font as tkfont
import subprocess
import json
import os
import re
import shutil
import threading
import tempfile
import queue
import logging
import shlex
import time

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _Root = TkinterDnD.Tk
except ImportError:
    DND_FILES = None
    _Root = tk.Tk

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv",
              ".wmv", ".ts", ".m4v", ".mpg", ".mpeg"}


def probe(path):
    cmd = [FFPROBE, "-v", "error", "-show_entries",
           "format=duration,size:stream=codec_type,codec_name,width,height,avg_frame_rate,sample_rate,channels",
           "-of", "json", path]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    data = json.loads(out)
    info = {"duration": float(data.get("format", {}).get("duration", 0)),
            "size": int(data.get("format", {}).get("size", 0)),
            "v": None, "a": None}
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and not info["v"]:
            fr = s.get("avg_frame_rate", "0/1")
            try:
                n, d = fr.split("/")
                fps = float(n) / float(d) if float(d) else 0
            except Exception:
                fps = 0
            info["v"] = {"codec": s.get("codec_name"), "w": s.get("width"),
                         "h": s.get("height"), "fps": fps}
        elif s.get("codec_type") == "audio" and not info["a"]:
            info["a"] = {"codec": s.get("codec_name"),
                         "sr": s.get("sample_rate"), "ch": s.get("channels")}
    return info


def human_size(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


def human_dur(s):
    s = int(s)
    return f"{s // 60:02d}:{s % 60:02d}"


class VideoEditor(_Root):
    def __init__(self):
        super().__init__()
        self.title("Video Editor")
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = min(1280, max(960, int(sw * 0.92)))
        h = min(900, max(560, int(sh * 0.92)))
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(900, 520)
        self.configure(bg="#1e1e2e")
        self.videos = []
        self.labels = []
        self.progress_var = tk.DoubleVar(value=0)
        self.status_var = tk.StringVar(value="Ready")
        self.cmd_var = tk.StringVar(value="Ready")
        self.prog_var = tk.StringVar(value="")
        self._cancelled = False
        self._msgs = queue.Queue()
        self._init_logging()
        self._build_style()
        self._setup_dnd()
        self._build_ui()
        self.after(80, self._poll_msgs)
        self._log(f"Video Editor started (ffmpeg: {FFMPEG})")

    def _init_logging(self):
        self.logger = logging.getLogger("video_editor")
        self.logger.setLevel(logging.DEBUG)
        self.log_path = ""
        if not self.logger.handlers:
            fh = None
            for base in (os.path.dirname(os.path.abspath(__file__)),
                         tempfile.gettempdir()):
                path = os.path.join(base, "video_editor.log")
                try:
                    fh = logging.FileHandler(path, encoding="utf-8")
                    self.log_path = path
                    break
                except OSError:
                    continue
            if fh:
                fh.setFormatter(logging.Formatter(
                    "%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S"))
                fh.setLevel(logging.ERROR)
                self.logger.addHandler(fh)

    def _log(self, msg, level="info"):
        getattr(self.logger, level)(msg)
        self._post(self._append_log,
                   f"[{time.strftime('%H:%M:%S')}] {msg}", level)

    def _append_log(self, line, level="info"):
        if not hasattr(self, "log_text"):
            return
        tag = level if level in ("error", "warning") else None
        if tag:
            self.log_text.insert("end", line + "\n", tag)
        else:
            self.log_text.insert("end", line + "\n")
        if int(self.log_text.index("end-1c").split(".")[0]) > 2000:
            self.log_text.delete("1.0", "600.0")
        self.log_text.see("end")

    def _setup_dnd(self):
        self._dnd_ok = False
        if DND_FILES is None:
            return
        try:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
            self.dnd_bind("<<DropEnter>>", lambda e: "copy")
            self._dnd_ok = True
        except Exception:
            pass

    def _on_drop(self, event):
        try:
            paths = list(self.tk.splitlist(event.data))
        except Exception:
            paths = [event.data]
        added = 0
        for p in paths:
            p = p.strip()
            if not p:
                continue
            if (os.path.splitext(p)[1].lower() in VIDEO_EXTS
                    and os.path.isfile(p)
                    and p not in [v["path"] for v in self.videos]):
                try:
                    self.videos.append({"path": p, "info": probe(p)})
                    added += 1
                except Exception as e:
                    self._log(f"Cannot read file {p}: {e}", "error")
        if added:
            self._refresh_concat()
            self.nb.select(0)
            self.status_var.set(f"Added {added} video(s) via drag & drop")
            self._log(f"Drag & drop: added {added} video(s)")
        else:
            self.status_var.set("No new video files found in drop")
            self._log("Drag & drop: no new video files found", "warning")
        return "copy"

    def _post(self, fn, *args):
        self._msgs.put((fn, args))

    def _poll_msgs(self):
        try:
            while True:
                fn, args = self._msgs.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        self.after(80, self._poll_msgs)

    def _build_style(self):
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        bg = "#1e1e2e"
        fg = "#cdd6f4"
        accent = "#89b4fa"
        self.style.configure(".", background=bg, foreground=fg,
                             fieldbackground="#313244", borderwidth=0)
        self.style.configure("TFrame", background=bg)
        self.style.configure("TLabel", background=bg, foreground=fg)
        self.style.configure("TButton", background="#45475a", foreground=fg,
                             focuscolor="#45475a", padding=(10, 6))
        self.style.map("TButton", background=[("active", accent)],
                       foreground=[("active", "#1e1e2e")])
        self.style.configure("Accent.TButton", background=accent,
                             foreground="#1e1e2e", padding=(14, 8))
        self.style.map("Accent.TButton", background=[("active", "#b4d0fb")])
        self.style.configure("TNotebook", background=bg)
        self.style.configure("TNotebook.Tab", background="#313244",
                             foreground=fg, padding=(14, 6))
        self.style.map("TNotebook.Tab", background=[("selected", accent)],
                       foreground=[("selected", "#1e1e2e")])
        self.style.configure("TListbox", background="#313244", foreground=fg,
                             selectbackground=accent, selectforeground="#1e1e2e")
        self.style.configure("Treeview", background="#313244", foreground=fg,
                             fieldbackground="#313244", rowheight=26)
        self.style.map("Treeview", background=[("selected", accent)],
                       foreground=[("selected", "#1e1e2e")])
        self.style.configure("Horizontal.TProgressbar",
                             background=accent, troughcolor="#313244")
        self.style.configure("TScale", background=bg, troughcolor="#313244")
        self.style.configure("TCheckbutton", background=bg, foreground=fg)
        self.style.map("TCheckbutton", background=[("active", bg)])
        self.style.configure("TLabelframe", background=bg, foreground=accent)
        self.style.configure("TLabelframe.Label", background=bg, foreground=accent)
        self.style.configure("TEntry", fieldbackground="#313244", foreground=fg)
        self.style.configure("TCombobox", fieldbackground="#313244", foreground=fg,
                             background="#45475a", arrowcolor=fg)
        self.style.map("TCombobox",
                       fieldbackground=[("readonly", "#313244"), ("active", "#313244")],
                       foreground=[("readonly", fg)],
                       selectbackground=[("readonly", "#313244")],
                       selectforeground=[("readonly", fg)])

    def _build_ui(self):
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="🎬 Video Editor", font=("Helvetica", 18, "bold"),
                  foreground="#89b4fa").pack(side="left")
        ttk.Label(top, textvariable=self.status_var).pack(side="right")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=4)

        self._tab_concat()
        self._tab_quality()
        self._tab_labels()
        self._tab_basic()

        # ---------- status / log console ----------
        con = ttk.Frame(self, padding=(8, 0))
        con.pack(fill="x")

        hdr = ttk.Frame(con)
        hdr.pack(fill="x")
        ttk.Label(hdr, text="Status / Log", font=("Helvetica", 10, "bold"),
                  foreground="#89b4fa").pack(side="left")
        if self.log_path:
            ttk.Label(hdr, text=self.log_path, foreground="#6c7086",
                      font=("Courier", 8)).pack(side="right")
        ttk.Button(hdr, text="Clear log",
                   command=lambda: self.log_text.delete("1.0", "end")
                   ).pack(side="right", padx=8)

        ttk.Label(con, textvariable=self.cmd_var, foreground="#a6e3a1",
                  font=("Courier", 9), anchor="w").pack(fill="x", pady=(2, 0))
        ttk.Label(con, textvariable=self.prog_var, foreground="#f9e2af",
                  font=("Courier", 9), anchor="w").pack(fill="x")

        lf = ttk.Frame(con)
        lf.pack(fill="x", pady=(2, 4))
        self.log_text = tk.Text(lf, height=6, bg="#11111b", fg="#cdd6f4",
                                font=("Courier", 9), wrap="word",
                                state="normal", relief="flat",
                                highlightthickness=1,
                                highlightbackground="#313244")
        self.log_text.tag_configure("error", foreground="#f38ba8")
        self.log_text.tag_configure("warning", foreground="#f9e2af")
        lsb = ttk.Scrollbar(lf, orient="vertical",
                            command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=lsb.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        lsb.pack(side="right", fill="y")

        bar = ttk.Frame(self, padding=(8, 4))
        bar.pack(fill="x")
        self.pbar = ttk.Progressbar(bar, variable=self.progress_var,
                                    maximum=100, mode="determinate")
        self.pbar.pack(fill="x", side="left", expand=True, padx=(0, 8))
        ttk.Button(bar, text="Cancel", command=self._cancel).pack(side="right")

    # ---------- helpers ----------
    def _pick_videos(self):
        paths = filedialog.askopenfilenames(
            title="Select video files",
            filetypes=[("Video files", "*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv *.ts *.m4v"),
                       ("All files", "*.*")])
        return list(paths)

    def _run_ffmpeg(self, args, on_done=None):
        self._run_ffmpeg_duration(args, 0, on_done)

    def _run_ffmpeg_duration(self, args, duration, on_done=None):
        self._cancelled = False
        self.progress_var.set(0)
        self.status_var.set("Processing...")
        self.config(cursor="watch")
        cmd = " ".join(shlex.quote(a) for a in [FFMPEG, "-y", *args])
        self.cmd_var.set("$ " + cmd)
        self.prog_var.set("starting ffmpeg...")
        self._log("$ " + cmd)
        t0 = time.time()

        def worker():
            code = 1
            try:
                proc = subprocess.Popen([FFMPEG, "-y", *args],
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True)
                for raw in proc.stdout:
                    if self._cancelled:
                        proc.terminate()
                        break
                    raw = raw.rstrip("\n")
                    if not raw:
                        continue
                    self.logger.debug(raw)
                    if "time=" in raw:
                        tail = raw.split("\r")[-1].strip()
                        if tail:
                            self._post(self.prog_var.set, tail[:180])
                        if duration > 0:
                            m = re.search(r"time=(\d+):(\d+):(\d+)\.(\d+)", raw)
                            if m:
                                t = (int(m.group(1)) * 3600 + int(m.group(2)) * 60
                                     + int(m.group(3)) + int(m.group(4)) / 100)
                                pct = min(99, t / duration * 100)
                                self._post(self.progress_var.set, pct)
                    else:
                        for sub in raw.split("\r"):
                            sub = sub.strip()
                            if sub:
                                self._post(self._append_log, sub)
                code = proc.wait()
            except Exception as e:
                self._log(f"ffmpeg error: {e}", "error")
                code = 1
            ok = code == 0 and not self._cancelled
            self._post(self._done, ok, on_done, time.time() - t0, code)
        threading.Thread(target=worker, daemon=True).start()

    def _done(self, ok, on_done, elapsed=None, code=None):
        self.config(cursor="")
        dur = f" in {elapsed:.1f}s" if elapsed is not None else ""
        if ok:
            self.progress_var.set(100)
            self.status_var.set("Done")
            self.prog_var.set(f"completed{dur}")
            self._log(f"Completed{dur}")
        else:
            self.status_var.set("Cancelled / Failed")
            if self._cancelled:
                self.prog_var.set("cancelled by user")
                self._log("Operation cancelled by user", "warning")
            else:
                self.prog_var.set(f"ffmpeg failed (exit code {code})")
                self._log(f"ffmpeg failed (exit code {code})", "error")
            messagebox.showwarning("Video Editor", "Operation cancelled or failed.")
        if on_done:
            on_done(ok)

    def _saved(self, title, out):
        def cb(ok):
            if ok:
                messagebox.showinfo(title, f"Saved:\n{out}")
        return cb

    def _cancel(self):
        self._cancelled = True
        self.status_var.set("Cancelling...")
        self._log("Cancel requested by user", "warning")

    def _output_path(self, default="output.mp4"):
        return filedialog.asksaveasfilename(
            defaultextension=".mp4",
            initialfile=default,
            filetypes=[("MP4 video", "*.mp4"), ("MKV video", "*.mkv"),
                       ("All files", "*.*")])

    def _add_job(self, name, status="done"):
        pass

    # ---------- Tab 1: Concat ----------
    def _tab_concat(self):
        f = ttk.Frame(self.nb, padding=10)
        self.nb.add(f, text="  Concatenate  ")

        left = ttk.Frame(f)
        left.pack(side="left", fill="both", expand=True)

        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=(0, 6))
        ttk.Button(btns, text="+ Add Videos",
                   command=self._concat_add).pack(side="left", padx=(0, 4))
        ttk.Button(btns, text="Remove Selected",
                   command=self._concat_remove).pack(side="left", padx=4)
        ttk.Button(btns, text="Move Up",
                   command=lambda: self._concat_move(-1)).pack(side="left", padx=4)
        ttk.Button(btns, text="Move Down",
                   command=lambda: self._concat_move(1)).pack(side="left", padx=4)
        ttk.Button(btns, text="Clear",
                   command=self._concat_clear).pack(side="left", padx=4)

        cols = ("#", "File", "Duration", "Resolution", "Size")
        self.concat_tree = ttk.Treeview(left, columns=cols, show="headings",
                                        selectmode="extended", height=14)
        for c, w in zip(cols, (40, 340, 90, 110, 90)):
            self.concat_tree.heading(c, text=c)
            self.concat_tree.column(c, width=w, anchor="w")
        self.concat_tree.pack(fill="both", expand=True)

        sb = ttk.Scrollbar(left, orient="vertical", command=self.concat_tree.yview)
        self.concat_tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")

        right = ttk.Frame(f, padding=(14, 0))
        right.pack(side="right", fill="y")

        ttk.Label(right, text="Output format").pack(anchor="w")
        self.concat_fmt = ttk.Combobox(right, values=["mp4", "mkv", "mov", "webm"],
                                       state="readonly", width=12)
        self.concat_fmt.set("mp4")
        self.concat_fmt.pack(anchor="w", pady=(2, 10))

        ttk.Label(right, text="Concat mode").pack(anchor="w")
        self.concat_mode = ttk.Combobox(right, values=["Re-encode (safe)", "Stream copy (fast)"],
                                        state="readonly", width=22)
        self.concat_mode.set("Re-encode (safe)")
        self.concat_mode.pack(anchor="w", pady=(2, 10))

        ttk.Button(right, text="▶ Concatenate", style="Accent.TButton",
                   command=self._concat_go).pack(fill="x", pady=8)

        hint = "Order in the list = order\nin the final video.\n\nFiles dialog: Ctrl/Shift+click\nto select multiple videos."
        if self._dnd_ok:
            hint += "\n\nOr drag & drop video files\nstraight into this window."
        else:
            hint += "\n\nTip: pip install tkinterdnd2\nto enable drag & drop."
        ttk.Label(right, text=hint, foreground="#a6adc8",
                  justify="left").pack(anchor="w", pady=10)

    def _concat_add(self):
        added = 0
        for p in self._pick_videos():
            if p not in [v["path"] for v in self.videos]:
                self.videos.append({"path": p, "info": probe(p)})
                added += 1
        if added:
            self._log(f"Added {added} video(s) to concat list")
        self._refresh_concat()

    def _concat_remove(self):
        sel = self.concat_tree.selection()
        idxs = sorted([int(i) for i in sel], reverse=True)
        for i in idxs:
            self.videos.pop(i)
        if idxs:
            self._log(f"Removed {len(idxs)} video(s) from concat list")
        self._refresh_concat()

    def _concat_move(self, delta):
        sel = sorted(int(i) for i in self.concat_tree.selection())
        if not sel:
            return
        n = len(self.videos)
        if delta < 0 and sel[0] == 0:
            return
        if delta > 0 and sel[-1] == n - 1:
            return
        selset = set(sel)
        selected = [self.videos[i] for i in sel]
        rest = [self.videos[i] for i in range(n) if i not in selset]
        if delta < 0:
            ins = sel[0] - 1
        else:
            ins = (sel[-1] + 1) - len(sel) + 1
        self.videos = rest[:ins] + selected + rest[ins:]
        self._refresh_concat()
        moved = [str(i) for i in range(ins, ins + len(sel))]
        self.concat_tree.selection_set(*moved)

    def _concat_clear(self):
        if self.videos:
            self._log(f"Cleared concat list ({len(self.videos)} video(s))")
        self.videos.clear()
        self._refresh_concat()

    def _refresh_concat(self):
        self.concat_tree.delete(*self.concat_tree.get_children())
        for i, v in enumerate(self.videos):
            inf = v["info"]
            res = f"{inf['v']['w']}x{inf['v']['h']}" if inf["v"] else "audio"
            self.concat_tree.insert("", "end", iid=str(i), values=(
                i + 1, os.path.basename(v["path"]), human_dur(inf["duration"]),
                res, human_size(inf["size"])))

    def _concat_go(self):
        if len(self.videos) < 2:
            messagebox.showinfo("Concatenate", "Add at least 2 videos.")
            return
        out = self._output_path("concatenated.mp4")
        if not out:
            return
        fmt = self.concat_fmt.get()
        stream_copy = self.concat_mode.get().startswith("Stream")
        self._log(f"Concat start: {len(self.videos)} videos, "
                  f"mode={'stream-copy' if stream_copy else 're-encode'}, "
                  f"format={fmt} -> {out}")

        # normalize all to same resolution / fps using first video
        first = self.videos[0]["info"]
        w, h = (first["v"]["w"], first["v"]["h"]) if first["v"] else (1280, 720)
        fps = first["v"]["fps"] if first["v"] and first["v"]["fps"] > 0 else 30

        if stream_copy:
            self._concat_stream_copy(out, fmt)
        else:
            self._concat_reencode(out, fmt, w, h, fps)

    def _concat_reencode(self, out, fmt, w, h, fps):
        tmp = tempfile.mkdtemp(prefix="ved_concat_")
        total = sum(v["info"]["duration"] for v in self.videos)

        # Step 1: normalize each file
        def normalize_all(done_cb):
            results = [None] * len(self.videos)

            def step(i):
                if i >= len(self.videos):
                    done_cb(results)
                    return
                v = self.videos[i]
                dst = os.path.join(tmp, f"part{i:03d}.mp4")
                args = ["-i", v["path"],
                        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                               f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps={fps}",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                        "-c:a", "aac", "-ar", "44100", "-ac", "2",
                        "-pix_fmt", "yuv420p", dst]
                self.status_var.set(f"Normalizing {i+1}/{len(self.videos)}...")

                def after(ok, i=i, dst=dst):
                    if ok:
                        results[i] = dst
                        step(i + 1)
                    else:
                        shutil.rmtree(tmp, ignore_errors=True)

                self._run_ffmpeg_duration(args, v["info"]["duration"], after)

            step(0)

        def do_concat(results):
            listfile = os.path.join(tmp, "list.txt")
            with open(listfile, "w") as f:
                for r in results:
                    f.write(f"file '{r.replace(os.sep, '/')}'\n")
            args = ["-f", "concat", "-safe", "0", "-i", listfile, "-c", "copy", out]
            self.status_var.set("Merging...")
            self._run_ffmpeg_duration(args, total,
                                      lambda ok: self._cleanup(tmp, ok, out))

        normalize_all(do_concat)

    def _concat_stream_copy(self, out, fmt):
        tmp = tempfile.mkdtemp(prefix="ved_sc_")
        listfile = os.path.join(tmp, "list.txt")
        with open(listfile, "w") as f:
            for v in self.videos:
                f.write(f"file '{v['path'].replace(os.sep, '/')}'\n")
        args = ["-f", "concat", "-safe", "0", "-i", listfile, "-c", "copy", out]
        total = sum(v["info"]["duration"] for v in self.videos)
        self._run_ffmpeg_duration(args, total, lambda ok: self._cleanup(tmp, ok, out))

    def _cleanup(self, tmp, ok, out):
        shutil.rmtree(tmp, ignore_errors=True)
        if ok:
            messagebox.showinfo("Concatenate", f"Saved:\n{out}")

    # ---------- Tab 2: Quality ----------
    def _tab_quality(self):
        f = ttk.Frame(self.nb, padding=10)
        self.nb.add(f, text="  Quality Upgrade  ")

        left = ttk.Frame(f)
        left.pack(side="left", fill="both", expand=True)

        ttk.Label(left, text="Select input video", font=("Helvetica", 11, "bold")).pack(anchor="w")
        row = ttk.Frame(left)
        row.pack(fill="x", pady=6)
        self.q_path = tk.StringVar()
        ttk.Entry(row, textvariable=self.q_path).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(row, text="Browse...", command=self._q_browse).pack(side="left")

        self.q_info = tk.StringVar(value="No file selected")
        ttk.Label(left, textvariable=self.q_info, foreground="#a6adc8").pack(anchor="w", pady=(0, 8))

        gf = ttk.LabelFrame(left, text="Scale / Resolution", padding=8)
        gf.pack(fill="x", pady=6)
        self.q_scale_mode = tk.StringVar(value="keep")
        for val, txt in [("keep", "Keep original resolution"),
                         ("2x", "Upscale 2x"),
                         ("1080p", "Fit to 1080p"),
                         ("720p", "Fit to 720p"),
                         ("custom", "Custom size")]:
            ttk.Radiobutton(gf, text=txt, value=val, variable=self.q_scale_mode,
                            command=self._q_scale_changed).pack(anchor="w", pady=1)
        cr = ttk.Frame(gf)
        cr.pack(fill="x", pady=4)
        ttk.Label(cr, text="Width").pack(side="left")
        self.q_w = tk.StringVar(value="1920")
        ttk.Entry(cr, textvariable=self.q_w, width=7).pack(side="left", padx=(4, 12))
        ttk.Label(cr, text="Height").pack(side="left")
        self.q_h = tk.StringVar(value="1080")
        ttk.Entry(cr, textvariable=self.q_h, width=7).pack(side="left", padx=4)

        gf2 = ttk.LabelFrame(left, text="Enhancement", padding=8)
        gf2.pack(fill="x", pady=6)
        self.q_denoise = tk.BooleanVar(value=True)
        self.q_sharpen = tk.BooleanVar(value=True)
        self.q_unsharp = tk.BooleanVar(value=False)
        self.q_deband = tk.BooleanVar(value=False)
        ttk.Checkbutton(gf2, text="Denoise (hqdn3d)", variable=self.q_denoise).pack(anchor="w")
        ttk.Checkbutton(gf2, text="Sharpen (unsharp)", variable=self.q_sharpen).pack(anchor="w")
        ttk.Checkbutton(gf2, text="Extra unsharp pass", variable=self.q_unsharp).pack(anchor="w")
        ttk.Checkbutton(gf2, text="Deband", variable=self.q_deband).pack(anchor="w")

        gf3 = ttk.LabelFrame(left, text="Encoding", padding=8)
        gf3.pack(fill="x", pady=6)
        er = ttk.Frame(gf3)
        er.pack(fill="x")
        ttk.Label(er, text="Encoder").pack(side="left")
        self.q_enc = ttk.Combobox(er, values=["libx264", "libx265", "libvpx-vp9"],
                                  state="readonly", width=14)
        self.q_enc.set("libx264")
        self.q_enc.pack(side="left", padx=6)
        ttk.Label(er, text="CRF").pack(side="left", padx=(14, 0))
        self.q_crf = tk.StringVar(value="18")
        ttk.Entry(er, textvariable=self.q_crf, width=5).pack(side="left", padx=4)
        ttk.Label(er, text="Preset").pack(side="left", padx=(14, 0))
        self.q_preset = ttk.Combobox(
            er, values=["ultrafast", "superfast", "veryfast", "faster", "fast",
                        "medium", "slow", "slower", "veryslow"],
            state="readonly", width=12)
        self.q_preset.set("medium")
        self.q_preset.pack(side="left", padx=4)

        ttk.Button(left, text="▶ Upgrade Quality", style="Accent.TButton",
                   command=self._q_go).pack(fill="x", pady=12)

        right = ttk.LabelFrame(f, text="Live preview of filter chain", padding=10)
        right.pack(side="right", fill="both", expand=True, padx=(12, 0))
        self.q_preview = tk.Text(right, bg="#313244", fg="#a6e3a1",
                                 font=("Courier", 11), wrap="word", state="disabled")
        self.q_preview.pack(fill="both", expand=True)

    def _q_browse(self):
        p = filedialog.askopenfilename(
            filetypes=[("Video files", "*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv"), ("All files", "*.*")])
        if p:
            self.q_path.set(p)
            info = probe(p)
            v = info["v"]
            self.q_info.set(f"{os.path.basename(p)}  |  "
                            f"{v['w']}x{v['h']} @ {v['fps']:.0f}fps" if v else os.path.basename(p))
            self._q_scale_changed()

    def _q_scale_changed(self):
        mode = self.q_scale_mode.get()
        if mode == "custom":
            return
        p = self.q_path.get()
        if not p:
            return
        info = probe(p)
        v = info["v"]
        if not v:
            return
        w, h = v["w"], v["h"]
        if mode == "2x":
            w, h = w * 2, h * 2
        elif mode == "1080p":
            if h > 1080 or True:
                s = 1080 / h
                w, h = int(w * s) // 2 * 2, 1080
        elif mode == "720p":
            s = 720 / h
            w, h = int(w * s) // 2 * 2, 720
        self.q_w.set(str(w))
        self.q_h.set(str(h))
        self._q_update_preview()

    def _q_filter_chain(self):
        w = self.q_w.get() or "1920"
        h = self.q_h.get() or "1080"
        parts = []
        parts.append(f"scale={w}:{h}:flags=lanczos")
        if self.q_denoise.get():
            parts.append("hqdn3d=3:2:6:4")
        if self.q_deband.get():
            parts.append("deband=1thr=0.02:2thr=0.02:3thr=0.02:4thr=0.02")
        if self.q_sharpen.get():
            parts.append("unsharp=5:5:0.8:5:5:0.0")
        if self.q_unsharp.get():
            parts.append("unsharp=7:7:0.6:7:7:0.0")
        return ",".join(parts)

    def _q_update_preview(self):
        chain = self._q_filter_chain()
        enc = self.q_enc.get()
        crf = self.q_crf.get()
        preset = self.q_preset.get()
        txt = (f"-vf \"{chain}\"\n"
               f"-c:v {enc} -crf {crf} -preset {preset}\n"
               f"-pix_fmt yuv420p -c:a aac -b:a 192k\n")
        self.q_preview.configure(state="normal")
        self.q_preview.delete("1.0", "end")
        self.q_preview.insert("1.0", txt)
        self.q_preview.configure(state="disabled")

    def _q_go(self):
        p = self.q_path.get()
        if not p or not os.path.exists(p):
            messagebox.showinfo("Quality", "Select a valid input video first.")
            return
        out = self._output_path("enhanced_" + os.path.basename(p))
        if not out:
            return
        info = probe(p)
        chain = self._q_filter_chain()
        args = ["-i", p, "-vf", chain,
                "-c:v", self.q_enc.get(), "-crf", self.q_crf.get(),
                "-preset", self.q_preset.get(),
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", out]
        self._run_ffmpeg_duration(args, info["duration"],
                                  self._saved("Quality", out))

    # ---------- Tab 3: Labels ----------
    def _tab_labels(self):
        f = ttk.Frame(self.nb, padding=10)
        self.nb.add(f, text="  Labels / Text  ")

        left = ttk.Frame(f)
        left.pack(side="left", fill="both", expand=True)

        row = ttk.Frame(left)
        row.pack(fill="x", pady=(0, 6))
        ttk.Label(row, text="Input video").pack(side="left")
        self.lbl_path = tk.StringVar()
        ttk.Entry(row, textvariable=self.lbl_path).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row, text="Browse...", command=self._lbl_browse).pack(side="left")

        ttk.Label(left, text="Labels (top to bottom = draw order)",
                  font=("Helvetica", 11, "bold")).pack(anchor="w", pady=(6, 2))

        cols = ("Text", "Start", "End", "Position", "Size", "Color")
        self.lbl_tree = ttk.Treeview(left, columns=cols, show="headings",
                                     selectmode="browse", height=8)
        for c, w in zip(cols, (180, 70, 70, 90, 60, 90)):
            self.lbl_tree.heading(c, text=c)
            self.lbl_tree.column(c, width=w, anchor="w")
        self.lbl_tree.pack(fill="both", expand=True)
        self.lbl_tree.bind("<<TreeviewSelect>>", lambda e: self._lbl_load_sel())

        bf = ttk.Frame(left)
        bf.pack(fill="x", pady=6)
        ttk.Button(bf, text="+ Add", command=self._lbl_add).pack(side="left", padx=(0, 4))
        ttk.Button(bf, text="Update Selected", command=self._lbl_update).pack(side="left", padx=4)
        ttk.Button(bf, text="Remove Selected", command=self._lbl_remove).pack(side="left", padx=4)

        ttk.Button(left, text="▶ Burn Labels Into Video", style="Accent.TButton",
                   command=self._lbl_go).pack(fill="x", pady=8)

        # editor panel
        ed = ttk.LabelFrame(f, text="Label editor", padding=10)
        ed.pack(side="right", fill="y", padx=(12, 0))

        ttk.Label(ed, text="Text").pack(anchor="w")
        self.lbl_text = tk.StringVar(value="Your text here")
        ttk.Entry(ed, textvariable=self.lbl_text, width=30).pack(fill="x", pady=(2, 6))

        ttk.Label(ed, text="Start time (s)").pack(anchor="w")
        self.lbl_start = tk.StringVar(value="0")
        ttk.Entry(ed, textvariable=self.lbl_start, width=10).pack(fill="x", pady=(2, 6))

        ttk.Label(ed, text="End time (s)").pack(anchor="w")
        self.lbl_end = tk.StringVar(value="5")
        ttk.Entry(ed, textvariable=self.lbl_end, width=10).pack(fill="x", pady=(2, 6))

        ttk.Label(ed, text="Position").pack(anchor="w")
        self.lbl_pos = ttk.Combobox(
            ed, state="readonly", width=26,
            values=["Top-left", "Top-center", "Top-right",
                    "Middle-left", "Center", "Middle-right",
                    "Bottom-left", "Bottom-center", "Bottom-right",
                    "Custom (x%, y%)"])
        self.lbl_pos.set("Bottom-center")
        self.lbl_pos.pack(fill="x", pady=(2, 6))

        cr = ttk.Frame(ed)
        cr.pack(fill="x")
        ttk.Label(cr, text="X%").pack(side="left")
        self.lbl_x = tk.StringVar(value="50")
        ttk.Entry(cr, textvariable=self.lbl_x, width=6).pack(side="left", padx=(4, 10))
        ttk.Label(cr, text="Y%").pack(side="left")
        self.lbl_y = tk.StringVar(value="90")
        ttk.Entry(cr, textvariable=self.lbl_y, width=6).pack(side="left", padx=4)

        ttk.Label(ed, text="Font size").pack(anchor="w", pady=(6, 0))
        self.lbl_size = tk.StringVar(value="48")
        ttk.Entry(ed, textvariable=self.lbl_size, width=10).pack(fill="x", pady=(2, 6))

        ttk.Label(ed, text="Font").pack(anchor="w")
        fams = sorted({f for f in tkfont.families()})
        self.lbl_font = ttk.Combobox(ed, values=fams, width=26)
        default = "DejaVu Sans" if "DejaVu Sans" in fams else fams[0]
        self.lbl_font.set(default)
        self.lbl_font.pack(fill="x", pady=(2, 6))

        ttk.Label(ed, text="Color").pack(anchor="w")
        self.lbl_color = tk.StringVar(value="#FFFFFF")
        crow = ttk.Frame(ed)
        crow.pack(fill="x", pady=(2, 6))
        self.lbl_swatch = tk.Label(crow, text="  ", bg="#FFFFFF", width=4)
        self.lbl_swatch.pack(side="left", padx=(0, 6))
        ttk.Button(crow, text="Pick...", command=self._lbl_pick_color).pack(side="left")
        ttk.Entry(crow, textvariable=self.lbl_color, width=10).pack(side="left", padx=4)

        ttk.Label(ed, text="Outline (0-10)").pack(anchor="w")
        self.lbl_outline = tk.StringVar(value="2")
        ttk.Entry(ed, textvariable=self.lbl_outline, width=10).pack(fill="x", pady=(2, 6))

        self.lbl_bg = tk.BooleanVar(value=False)
        ttk.Checkbutton(ed, text="Semi-transparent background box",
                        variable=self.lbl_bg).pack(anchor="w", pady=4)

        ttk.Label(ed, text="Preview", foreground="#a6adc8").pack(anchor="w", pady=(8, 2))
        self.lbl_preview = tk.Label(ed, text="Your text here", bg="#313244",
                                    fg="#FFFFFF", width=26, height=3,
                                    font=("Helvetica", 14, "bold"), relief="groove")
        self.lbl_preview.pack(fill="x")
        self.lbl_text.trace_add("write", lambda *a: self._lbl_update_preview())
        self.lbl_color.trace_add("write", lambda *a: self._lbl_update_preview())
        self._lbl_update_preview()

    def _lbl_browse(self):
        p = filedialog.askopenfilename(
            filetypes=[("Video files", "*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv"), ("All files", "*.*")])
        if p:
            self.lbl_path.set(p)

    def _lbl_pick_color(self):
        c = colorchooser.askcolor(color=self.lbl_color.get(), title="Label color")
        if c and c[1]:
            self.lbl_color.set(c[1].upper())

    def _lbl_update_preview(self):
        self.lbl_preview.configure(fg=self.lbl_color.get())

    def _pos_xy(self):
        pos = self.lbl_pos.get()
        table = {
            "Top-left": (5, 8), "Top-center": (50, 8), "Top-right": (95, 8),
            "Middle-left": (5, 50), "Center": (50, 50), "Middle-right": (95, 50),
            "Bottom-left": (5, 92), "Bottom-center": (50, 92), "Bottom-right": (95, 92),
        }
        if pos in table:
            return table[pos]
        try:
            return float(self.lbl_x.get()), float(self.lbl_y.get())
        except ValueError:
            return 50.0, 90.0

    def _collect_label(self):
        text = self.lbl_text.get()
        if not text:
            return None
        try:
            start = max(0.0, float(self.lbl_start.get()))
            end = max(start + 0.1, float(self.lbl_end.get()))
        except ValueError:
            start, end = 0.0, 5.0
        x, y = self._pos_xy()
        color = self.lbl_color.get()
        if not re.match(r"^#[0-9a-fA-F]{6}$", color):
            color = "#FFFFFF"
        return {"text": text, "start": start, "end": end,
                "x": x, "y": y,
                "size": int(self.lbl_size.get() or 48),
                "font": self.lbl_font.get(),
                "color": color,
                "outline": int(self.lbl_outline.get() or 0),
                "bg": self.lbl_bg.get(),
                "pos": self.lbl_pos.get()}

    def _lbl_add(self):
        lab = self._collect_label()
        if not lab:
            return
        self.labels.append(lab)
        self._log(f"Label added: '{lab['text'][:30]}' "
                  f"({lab['start']}s-{lab['end']}s, {lab['pos']})")
        self._refresh_labels()

    def _lbl_update(self):
        sel = self.lbl_tree.selection()
        if not sel:
            return
        i = int(sel[0])
        lab = self._collect_label()
        if lab:
            self.labels[i] = lab
            self._log(f"Label #{i + 1} updated: '{lab['text'][:30]}'")
            self._refresh_labels()
            self.lbl_tree.selection_set(str(i))

    def _lbl_remove(self):
        sel = self.lbl_tree.selection()
        if not sel:
            return
        i = int(sel[0])
        self.labels.pop(i)
        self._log(f"Label #{i + 1} removed")
        self._refresh_labels()

    def _lbl_load_sel(self):
        sel = self.lbl_tree.selection()
        if not sel:
            return
        lab = self.labels[int(sel[0])]
        self.lbl_text.set(lab["text"])
        self.lbl_start.set(str(lab["start"]))
        self.lbl_end.set(str(lab["end"]))
        self.lbl_pos.set(lab.get("pos", "Custom (x%, y%)"))
        self.lbl_x.set(str(lab["x"]))
        self.lbl_y.set(str(lab["y"]))
        self.lbl_size.set(str(lab["size"]))
        self.lbl_font.set(lab["font"])
        self.lbl_color.set(lab["color"])
        self.lbl_outline.set(str(lab["outline"]))
        self.lbl_bg.set(lab["bg"])
        self._lbl_update_preview()

    def _refresh_labels(self):
        self.lbl_tree.delete(*self.lbl_tree.get_children())
        for i, lab in enumerate(self.labels):
            self.lbl_tree.insert("", "end", iid=str(i), values=(
                lab["text"][:28], f"{lab['start']}s", f"{lab['end']}s",
                lab["pos"].replace(" (x%, y%)", ""), lab["size"], lab["color"]))

    def _label_filter(self, w, h):
        """Build drawtext filter chain from self.labels."""
        chain = []
        for i, lab in enumerate(self.labels):
            x_pct, y_pct = lab["x"], lab["y"]
            # convert to pixel expression, centered
            x_expr = f"(w*{x_pct/100})-(text_w/2)"
            y_expr = f"(h*{y_pct/100})-(text_h/2)"
            color = lab["color"].replace("#", "0x")
            fontfile = self._resolve_font(lab["font"])
            text = lab["text"].replace("\\", "\\\\").replace("'", "\\'") \
                             .replace(":", "\\:").replace("%", "\\%")
            parts = [f"text='{text}'"]
            parts.append(f"fontfile='{fontfile}'" if fontfile else f"font='{lab['font']}'")
            parts.append(f"fontsize={lab['size']}")
            parts.append(f"fontcolor={color}")
            parts.append(f"x={x_expr}")
            parts.append(f"y={y_expr}")
            parts.append(f"enable='between(t,{lab['start']},{lab['end']})'")
            if lab["outline"] > 0:
                parts.append(f"borderw={lab['outline']}")
                parts.append("bordercolor=black")
            if lab["bg"]:
                parts.append("box=1")
                parts.append("boxcolor=black@0.45")
                parts.append("boxborderw=10")
            chain.append("drawtext=" + ":".join(parts))
        return chain

    def _resolve_font(self, family):
        # fontconfig lookup (Linux/macOS)
        try:
            out = subprocess.run(["fc-match", "-f", "%{file}", family],
                                 capture_output=True, text=True, timeout=5).stdout.strip()
            if out and os.path.exists(out):
                return out
        except Exception:
            pass
        # direct family match in system font dirs (esp. Windows)
        font_dirs = [
            os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
            "/System/Library/Fonts", "/Library/Fonts",
            os.path.expanduser("~/.fonts"),
        ]
        fam = (family or "").lower().replace(" ", "")
        for d in font_dirs:
            for ext in (".ttf", ".otf"):
                p = os.path.join(d, fam + ext)
                if os.path.exists(p):
                    return p
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arialbd.ttf"),
            os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segoeui.ttf"),
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return None

    def _lbl_go(self):
        p = self.lbl_path.get()
        if not p or not os.path.exists(p):
            messagebox.showinfo("Labels", "Select an input video first.")
            return
        if not self.labels:
            messagebox.showinfo("Labels", "Add at least one label.")
            return
        out = self._output_path("labeled_" + os.path.basename(p))
        if not out:
            return
        info = probe(p)
        v = info["v"] or {"w": 1280, "h": 720}
        chain = self._label_filter(v["w"], v["h"])
        vf = ",".join(chain)
        args = ["-i", p, "-vf", vf,
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-pix_fmt", "yuv420p", "-c:a", "copy", out]
        self._run_ffmpeg_duration(args, info["duration"],
                                  self._saved("Labels", out))

    # ---------- Tab 4: Basic tools ----------
    def _tab_basic(self):
        f = ttk.Frame(self.nb, padding=10)
        self.nb.add(f, text="  Basic Tools  ")

        row = ttk.Frame(f)
        row.pack(fill="x", pady=(0, 8))
        ttk.Label(row, text="Input video").pack(side="left")
        self.bt_path = tk.StringVar()
        ttk.Entry(row, textvariable=self.bt_path).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row, text="Browse...", command=self._bt_browse).pack(side="left")

        panes = ttk.Frame(f)
        panes.pack(fill="both", expand=True)

        # --- Trim ---
        t = ttk.LabelFrame(panes, text="Trim / Cut", padding=10)
        t.pack(fill="x", pady=(0, 8))
        r = ttk.Frame(t)
        r.pack(fill="x")
        ttk.Label(r, text="Start (s)").pack(side="left")
        self.bt_start = tk.StringVar(value="0")
        ttk.Entry(r, textvariable=self.bt_start, width=8).pack(side="left", padx=4)
        ttk.Label(r, text="End (s)").pack(side="left", padx=(10, 0))
        self.bt_end = tk.StringVar(value="10")
        ttk.Entry(r, textvariable=self.bt_end, width=8).pack(side="left", padx=4)
        ttk.Button(r, text="▶ Trim", style="Accent.TButton",
                   command=self._bt_trim).pack(side="right")

        # --- Extract audio ---
        a = ttk.LabelFrame(panes, text="Extract audio", padding=10)
        a.pack(fill="x", pady=(0, 8))
        r = ttk.Frame(a)
        r.pack(fill="x")
        self.bt_acodec = ttk.Combobox(r, values=["mp3", "aac", "wav", "flac", "opus"],
                                      state="readonly", width=8)
        self.bt_acodec.set("mp3")
        self.bt_acodec.pack(side="left", padx=(0, 8))
        ttk.Button(r, text="▶ Extract Audio", style="Accent.TButton",
                   command=self._bt_audio).pack(side="left")

        # --- Remove audio ---
        ra = ttk.LabelFrame(panes, text="Remove audio track", padding=10)
        ra.pack(fill="x", pady=(0, 8))
        ttk.Button(ra, text="▶ Remove Audio", style="Accent.TButton",
                   command=self._bt_noaudio).pack(side="left")

        # --- Speed ---
        s = ttk.LabelFrame(panes, text="Change speed", padding=10)
        s.pack(fill="x", pady=(0, 8))
        r = ttk.Frame(s)
        r.pack(fill="x")
        ttk.Label(r, text="Factor").pack(side="left")
        self.bt_speed = tk.StringVar(value="2.0")
        ttk.Entry(r, textvariable=self.bt_speed, width=7).pack(side="left", padx=4)
        ttk.Label(r, text="(0.5 = half speed, 2 = double)", foreground="#a6adc8").pack(side="left", padx=4)
        ttk.Button(r, text="▶ Apply Speed", style="Accent.TButton",
                   command=self._bt_speed_go).pack(side="right")

        # --- Screenshot ---
        sc = ttk.LabelFrame(panes, text="Capture frame (screenshot)", padding=10)
        sc.pack(fill="x", pady=(0, 8))
        r = ttk.Frame(sc)
        r.pack(fill="x")
        ttk.Label(r, text="At (s)").pack(side="left")
        self.bt_ss_t = tk.StringVar(value="1")
        ttk.Entry(r, textvariable=self.bt_ss_t, width=8).pack(side="left", padx=4)
        ttk.Button(r, text="▶ Capture PNG", style="Accent.TButton",
                   command=self._bt_ss).pack(side="left")

        # --- Rotate ---
        ro = ttk.LabelFrame(panes, text="Rotate", padding=10)
        ro.pack(fill="x", pady=(0, 8))
        r = ttk.Frame(ro)
        r.pack(fill="x")
        self.bt_rot = ttk.Combobox(r, values=["90° clockwise", "90° counter-clockwise",
                                              "180°", "Flip horizontal", "Flip vertical"],
                                   state="readonly", width=22)
        self.bt_rot.set("90° clockwise")
        self.bt_rot.pack(side="left", padx=(0, 8))
        ttk.Button(r, text="▶ Rotate", style="Accent.TButton",
                   command=self._bt_rotate).pack(side="left")

        # --- Mute volume / adjust volume ---
        v = ttk.LabelFrame(panes, text="Adjust volume", padding=10)
        v.pack(fill="x")
        r = ttk.Frame(v)
        r.pack(fill="x")
        ttk.Label(r, text="Volume %").pack(side="left")
        self.bt_vol = tk.StringVar(value="100")
        ttk.Entry(r, textvariable=self.bt_vol, width=7).pack(side="left", padx=4)
        ttk.Button(r, text="▶ Apply Volume", style="Accent.TButton",
                   command=self._bt_volume).pack(side="left")

    def _bt_browse(self):
        p = filedialog.askopenfilename(
            filetypes=[("Video files", "*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv"), ("All files", "*.*")])
        if p:
            self.bt_path.set(p)

    def _bt_need(self):
        p = self.bt_path.get()
        if not p or not os.path.exists(p):
            messagebox.showinfo("Basic Tools", "Select an input video first.")
            return None
        return p

    def _bt_trim(self):
        p = self._bt_need()
        if not p:
            return
        out = self._output_path("trimmed_" + os.path.basename(p))
        if not out:
            return
        info = probe(p)
        try:
            s, e = float(self.bt_start.get()), float(self.bt_end.get())
        except ValueError:
            messagebox.showinfo("Trim", "Invalid start/end.")
            return
        args = ["-i", p, "-ss", str(s), "-to", str(e),
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "aac", "-pix_fmt", "yuv420p", out]
        self._run_ffmpeg_duration(args, max(0, e - s),
                                  self._saved("Trim", out))

    def _bt_audio(self):
        p = self._bt_need()
        if not p:
            return
        fmt = self.bt_acodec.get()
        out = filedialog.asksaveasfilename(defaultextension=f".{fmt}",
                                           initialfile=os.path.splitext(os.path.basename(p))[0] + f".{fmt}",
                                           filetypes=[(f"{fmt.upper()} audio", f"*.{fmt}")])
        if not out:
            return
        info = probe(p)
        acodec = {"mp3": "libmp3lame", "aac": "aac", "wav": "pcm_s16le",
                  "flac": "flac", "opus": "libopus"}[fmt]
        args = ["-i", p, "-vn", "-c:a", acodec, out]
        self._run_ffmpeg_duration(args, info["duration"],
                                  self._saved("Audio", out))

    def _bt_noaudio(self):
        p = self._bt_need()
        if not p:
            return
        out = self._output_path("noaudio_" + os.path.basename(p))
        if not out:
            return
        info = probe(p)
        args = ["-i", p, "-an", "-c:v", "copy", out]
        self._run_ffmpeg_duration(args, info["duration"],
                                  self._saved("Remove Audio", out))

    def _bt_speed_go(self):
        p = self._bt_need()
        if not p:
            return
        try:
            sp = float(self.bt_speed.get())
            if sp <= 0:
                raise ValueError
        except ValueError:
            messagebox.showinfo("Speed", "Invalid speed factor.")
            return
        out = self._output_path(f"speed{sp}x_" + os.path.basename(p))
        if not out:
            return
        info = probe(p)
        args = ["-i", p,
                "-filter_complex", f"[0:v]setpts=PTS/{sp}[v];[0:a]atempo={min(max(sp, 0.5), 4)}[a]",
                "-map", "[v]", "-map", "[a]",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "aac", "-pix_fmt", "yuv420p", out]
        self._run_ffmpeg_duration(args, info["duration"] / sp if sp else 1,
                                  self._saved("Speed", out))

    def _bt_ss(self):
        p = self._bt_need()
        if not p:
            return
        out = filedialog.asksaveasfilename(defaultextension=".png",
                                           initialfile="frame.png",
                                           filetypes=[("PNG image", "*.png"), ("JPEG image", "*.jpg")])
        if not out:
            return
        try:
            t = float(self.bt_ss_t.get())
        except ValueError:
            t = 1.0
        args = ["-ss", str(t), "-i", p, "-frames:v", "1", out]
        self._run_ffmpeg(args, self._saved("Screenshot", out))

    def _bt_rotate(self):
        p = self._bt_need()
        if not p:
            return
        out = self._output_path("rotated_" + os.path.basename(p))
        if not out:
            return
        info = probe(p)
        choice = self.bt_rot.get()
        if choice == "90° clockwise":
            vf = "transpose=1"
        elif choice == "90° counter-clockwise":
            vf = "transpose=2"
        elif choice == "180°":
            vf = "transpose=1,transpose=1"
        elif choice == "Flip horizontal":
            vf = "hflip"
        else:
            vf = "vflip"
        args = ["-i", p, "-vf", vf,
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "copy", "-pix_fmt", "yuv420p", out]
        self._run_ffmpeg_duration(args, info["duration"],
                                  self._saved("Rotate", out))

    def _bt_volume(self):
        p = self._bt_need()
        if not p:
            return
        try:
            vol = float(self.bt_vol.get()) / 100.0
        except ValueError:
            messagebox.showinfo("Volume", "Invalid percentage.")
            return
        out = self._output_path("volume_" + os.path.basename(p))
        if not out:
            return
        info = probe(p)
        args = ["-i", p, "-filter:a", f"volume={vol}",
                "-c:v", "copy", "-c:a", "aac", out]
        self._run_ffmpeg_duration(args, info["duration"],
                                  self._saved("Volume", out))


if __name__ == "__main__":
    app = VideoEditor()
    app.mainloop()
