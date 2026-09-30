# Video Editor

A GUI video editor built on top of FFmpeg (Python + Tkinter). Only
`ffmpeg`/`ffprobe` must be installed; `tkinterdnd2` is optional (drag & drop).

## Run

```bash
python3 video_editor.py
```

Optional drag & drop support:

```bash
pip install tkinterdnd2
```

## Features

### 1. Concatenate
- Add multiple videos at once — **Ctrl/Shift+click** in the file dialog,
  or **drag & drop** files straight into the window
- Reorder with **Move Up / Move Down** (multi-select moves the whole block;
  list order = final order)
- Two modes:
  - **Re-encode (safe)** — normalizes all clips to the first video's
    resolution/fps and audio format, then joins (works with any input)
  - **Stream copy (fast)** — instant, but inputs must share codec parameters
- Trim every list item independently: select one clip, set its start and end
  times in seconds, then join only the kept ranges. Safe mode trims accurately;
  stream-copy cuts may align to nearby keyframes.
- Output format: mp4 / mkv / mov / webm

### 2. Quality Upgrade
- Scale: keep, 2x upscale, fit 1080p/720p, or custom WxH (lanczos resampling)
- Enhancement filters: denoise (hqdn3d), sharpen (unsharp), deband
- Encoder choice (x264 / x265 / VP9), CRF quality, preset
- Live preview of the generated FFmpeg filter chain

### 3. Labels / Text
- Multiple timed labels (start/end in seconds) burned into the video
- Positions: 9 presets (top/center/bottom × left/center/right) or custom X%/Y%
- Font family, size, color picker, outline, optional semi-transparent box
- Live preview of text color; labels render in list order

### 4. Basic Tools
- Trim / cut by start-end time
- Extract audio (mp3, aac, wav, flac, opus)
- Remove audio track
- Change speed (audio pitch corrected via atempo)
- Capture a frame as PNG
- Rotate (90° CW/CCW, 180°) and flip
- Adjust volume

### 5. Status / Log console
- Shows the exact CLI command being executed (`$ ffmpeg ...`)
- Live FFmpeg progress (frame/fps/time/speed) plus the progress bar
- Timestamped log of every operation (adds, drops, label edits, completion
  times, cancellations, failures) — errors in red, warnings in yellow
- Successful operations are shown in the console only; **failures and errors
  are also saved** to `video_editor.log` next to the script

All operations run in background threads with a progress bar and a Cancel
button, so the UI never freezes.

## Windows / macOS

Works on Linux, macOS, and Windows (pure Python stdlib + Tkinter). Install
FFmpeg and add it to `PATH`. Label fonts are resolved from the system font
directories of each platform.
