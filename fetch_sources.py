"""Download the public-domain source films from archive.org into raw/.

Resumable: skips anything already fully downloaded, and uses a .part file plus an
HTTP Range header so an interrupted run picks up where it left off rather than
starting the file over.
"""
import os
import sys

import requests

from sources import SOURCES, download_urls

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")


def raw_path(src):
    return os.path.join(RAW, f"{src['key']}.mp4")


def fetch(src, url=None):
    dest = raw_path(src)
    part = dest + ".part"
    url = url or download_urls(src)[0]

    if os.path.exists(dest):
        print(f"[{src['key']}] already have {os.path.getsize(dest)/1e6:.0f} MB, skipping", flush=True)
        return True

    have = os.path.getsize(part) if os.path.exists(part) else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    print(f"[{src['key']}] downloading from byte {have} ...", flush=True)

    try:
        with requests.get(url, headers=headers, stream=True, timeout=120) as r:
            if r.status_code not in (200, 206):
                print(f"[{src['key']}] HTTP {r.status_code}", flush=True)
                return False
            # A 200 to a Range request means the server ignored it: restart cleanly.
            mode = "ab" if (have and r.status_code == 206) else "wb"
            if mode == "wb":
                have = 0
            total = int(r.headers.get("Content-Length", 0)) + have
            done = have
            with open(part, mode) as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
                    done += len(chunk)
                    if total and done % (50 << 20) < (1 << 20):
                        print(f"[{src['key']}] {done/1e6:.0f}/{total/1e6:.0f} MB", flush=True)
    except requests.RequestException as e:
        print(f"[{src['key']}] failed: {e}", flush=True)
        return False

    os.replace(part, dest)
    print(f"[{src['key']}] done: {os.path.getsize(dest)/1e6:.0f} MB", flush=True)
    return True


def main():
    os.makedirs(RAW, exist_ok=True)
    wanted = sys.argv[1:] or [s["key"] for s in SOURCES]
    ok = 0
    for src in SOURCES:
        if src["key"] not in wanted:
            continue
        urls = download_urls(src)
        done = False
        for attempt in range(3):
            # Cycle through the mirrors so a URL that always 500s doesn't burn
            # every retry.
            if fetch(src, urls[attempt % len(urls)]):
                ok += 1
                done = True
                break
            print(f"[{src['key']}] retry {attempt + 1}/3", flush=True)
        if not done:
            print(f"[{src['key']}] GAVE UP", flush=True)
    print(f"fetched {ok}/{len(wanted)} sources", flush=True)


if __name__ == "__main__":
    main()
