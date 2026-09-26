# Video Editor

A GUI video editor built on top of FFmpeg (Python + Tkinter). No extra Python
dependencies — only `ffmpeg`/`ffprobe` must be installed.

## Run

```bash
python3 video_editor.py
```

## Features

### 1. Concatenate
- Add multiple videos, reorder them with **Move Up / Move Down** (list order = final order)
- Two modes:
  - **Re-encode (safe)** — normalizes all clips to the first video's
    resolution/fps and audio format, then joins (works with any input)
  - **Stream copy (fast)** — instant, but inputs must share codec parameters
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

All operations run in background threads with a progress bar and a Cancel
button, so the UI never freezes.
