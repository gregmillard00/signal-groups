"""Score candidate 10s windows locally, before spending any inter1 API calls.

inter1 reads faces and voice. A window with no visible face, or with nobody
speaking, tells it nothing - and every upload costs money. So we sweep a lot of
candidate windows cheaply here (face detection + speech-activity estimate, both
running locally) and only send the best ones to the API.

Face detection is YuNet via OpenCV's DNN module; OpenCV 5 no longer ships the old
Haar cascade XMLs, and YuNet is more accurate on grainy 1940s-60s prints anyway.
"""
import glob
import json
import math
import os
import shutil
import tempfile
import wave

import cv2
import numpy as np

from media import probe_assets

HERE = os.path.dirname(os.path.abspath(__file__))
YUNET = os.path.join(HERE, "models", "face_detection_yunet_2023mar.onnx")

_detector = None


def detector(size):
    global _detector
    if _detector is None:
        _detector = cv2.FaceDetectorYN.create(YUNET, "", size, 0.7, 0.3, 5000)
    _detector.setInputSize(size)
    return _detector


def face_stats(frame_dir):
    """Returns (fraction of frames containing a face, median relative face height)."""
    paths = sorted(glob.glob(os.path.join(frame_dir, "*.jpg")))
    if not paths:
        return 0.0, 0.0
    hits, sizes = 0, []
    for p in paths:
        img = cv2.imread(p)
        if img is None:
            continue
        h, w = img.shape[:2]
        det = detector((w, h))
        _, faces = det.detect(img)
        if faces is None or len(faces) == 0:
            continue
        hits += 1
        # faces rows are [x, y, w, h, ...landmarks..., score]
        sizes.append(max(float(f[3]) for f in faces) / h)
    return hits / len(paths), float(np.median(sizes)) if sizes else 0.0


def speech_stats(wav_path):
    """Rough voice-activity estimate: fraction of 25 ms frames that are loud enough
    and low-ish in zero-crossing rate. Music and room tone score lower than speech,
    and silence scores ~0.
    """
    if not os.path.exists(wav_path):
        return 0.0, -90.0
    try:
        with wave.open(wav_path, "rb") as w:
            n = w.getnframes()
            if n == 0:
                return 0.0, -90.0
            raw = w.readframes(n)
            rate = w.getframerate()
    except (wave.Error, EOFError):
        return 0.0, -90.0

    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if x.size == 0:
        return 0.0, -90.0

    step = max(1, int(rate * 0.025))
    frames = x[: (x.size // step) * step].reshape(-1, step)
    if frames.shape[0] == 0:
        return 0.0, -90.0

    rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)
    overall_db = 20 * math.log10(float(np.sqrt((x ** 2).mean()) + 1e-12))

    # Adaptive floor: speech sits well above this clip's own quiet passages.
    floor = np.percentile(rms, 20) * 3.0
    loud = rms > max(floor, 0.006)

    zcr = (np.diff(np.signbit(frames), axis=1).sum(axis=1)) / step
    voiced = loud & (zcr < 0.28)
    return float(voiced.mean()), overall_db


def score_window(src_path, start, dur=10.0):
    tmp = tempfile.mkdtemp(prefix="ihprobe_")
    try:
        frame_dir = os.path.join(tmp, "frames")
        wav = os.path.join(tmp, "a.wav")
        r = probe_assets(src_path, start, dur, frame_dir, wav)
        face_frac, face_size = face_stats(frame_dir)
        voiced, db = speech_stats(wav)
    except Exception as e:
        return {"start": start, "error": str(e), "score": -1.0}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # Reward: a face present in most frames, a reasonably close framing, and
    # someone actually talking for a good chunk of the window.
    score = (
        2.2 * face_frac
        + 1.6 * min(face_size / 0.30, 1.0)
        + 2.4 * min(voiced / 0.45, 1.0)
    )
    if face_frac < 0.5 or voiced < 0.12:
        score *= 0.25  # hard-ish reject: nothing for inter1 to read

    return {
        "start": round(start, 2),
        "face_frac": round(face_frac, 3),
        "face_size": round(face_size, 3),
        "voiced": round(voiced, 3),
        "db": round(db, 1),
        "score": round(score, 3),
        "stderr": r.stderr[:200] if r.returncode else "",
    }
