"""Read files out of a large remote .zip without downloading all of it (HTTP range requests).

    python ml/scripts/remote_zip.py list URL
    python ml/scripts/remote_zip.py get URL OUT_DIR PREFIX [PREFIX ...]

URL may redirect to a short-lived signed URL (e.g. Mendeley's S3 links); it is resolved again when it expires.
"""

from __future__ import annotations

import io
import sys
import time
import urllib.request
import zipfile
from pathlib import Path


UA = {"User-Agent": "curl/8.5.0"}  # some dataset hosts refuse Python's default client name


class HttpFile(io.RawIOBase):
    def __init__(self, url: str) -> None:
        self.url = url
        self.pos = 0
        self._resolve()

    def _resolve(self) -> None:
        req = urllib.request.Request(self.url, headers={**UA, "Range": "bytes=0-0"})
        with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 (fixed https dataset URLs)
            self.final = r.geturl()
            self.size = int(r.headers["Content-Range"].split("/")[-1])
        self.resolved_at = time.monotonic()

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = 0) -> int:
        self.pos = {0: offset, 1: self.pos + offset, 2: self.size + offset}[whence]
        return self.pos

    def read(self, n: int = -1) -> bytes:
        if n < 0:
            n = self.size - self.pos
        if n == 0 or self.pos >= self.size:
            return b""
        end = min(self.pos + n, self.size) - 1
        for attempt in range(5):
            if time.monotonic() - self.resolved_at > 200:  # signed URLs live 300 s
                self._resolve()
            req = urllib.request.Request(self.final, headers={**UA, "Range": f"bytes={self.pos}-{end}"})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310
                    data = r.read()
                break
            except Exception:  # expired link or a dropped connection: resolve again and retry
                if attempt == 4:
                    raise
                time.sleep(2)
                self._resolve()
        self.pos += len(data)
        return data

    def readinto(self, b) -> int:  # type: ignore[no-untyped-def]
        data = self.read(len(b))
        b[: len(data)] = data
        return len(data)


def main() -> None:
    cmd, url = sys.argv[1], sys.argv[2]
    zf = zipfile.ZipFile(io.BufferedReader(HttpFile(url), buffer_size=1 << 20))
    if cmd == "list":
        tops: dict[str, list[int]] = {}
        for i in zf.infolist():
            parts = i.filename.split("/")
            key = "/".join(parts[:3])
            t = tops.setdefault(key, [0, 0])
            t[0] += 1
            t[1] += i.file_size
        for k, (n, size) in sorted(tops.items()):
            print(f"{n:6d} files {size / 1e6:9.1f} MB  {k}")
    elif cmd == "get":
        out, prefixes = Path(sys.argv[3]), sys.argv[4:]
        members = [i for i in zf.infolist() if not i.is_dir() and i.filename.startswith(tuple(prefixes))]
        total = sum(i.file_size for i in members)
        print(f"extracting {len(members)} files, {total / 1e6:.1f} MB")
        for i in members:
            zf.extract(i, out)
        print("done")


if __name__ == "__main__":
    main()
