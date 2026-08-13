"""Thin ffmpeg helpers. ffmpeg comes from the imageio-ffmpeg wheel (static build),
since this VM has no system ffmpeg and no root to install one.
"""
import os
import subprocess

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def run(args, timeout=180):
    return subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-nostdin", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def probe_assets(src_path, start, dur, frame_dir, wav_path, fps=0.6, width=480):
    """Pull a handful of small frames plus a mono 16k wav for one candidate window.

    Uses input-side -ss so ffmpeg seeks instead of decoding from the top of the file.
    """
    os.makedirs(frame_dir, exist_ok=True)
    return run([
        "-ss", str(start), "-t", str(dur), "-i", src_path,
        "-map", "0:v:0", "-vf", f"fps={fps},scale={width}:-2", "-q:v", "4",
        os.path.join(frame_dir, "f_%02d.jpg"),
        "-map", "0:a:0?", "-ac", "1", "-ar", "16000", "-y", wav_path,
    ])


def cut_clip(src_path, start, dur, out_path, width=640, crf=26):
    """Cut a web-playable clip. Re-encoded (not stream-copied) so the cut is
    frame-accurate rather than snapping to the nearest keyframe, and so the result
    is small enough to stay well under the API's 32 MB upload cap.
    """
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    r = run([
        "-ss", str(start), "-t", str(dur), "-i", src_path,
        "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", f"scale={width}:-2,fps=24",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
        "-pix_fmt", "yuv420p", "-profile:v", "main",
        "-c:a", "aac", "-b:a", "96k", "-ac", "2",
        "-movflags", "+faststart", "-y", out_path,
    ])
    return r


def poster(src_path, out_path, at=1.0, width=640):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    return run([
        "-ss", str(at), "-i", src_path, "-frames:v", "1",
        "-vf", f"scale={width}:-2", "-q:v", "3", "-y", out_path,
    ])
