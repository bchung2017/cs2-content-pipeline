"""fetch.py: download a demo, retrying until it is published.

Where pro demos are reliably hosted is still an open unknown (HLTV, organizer, FACEIT).
This handles a plain HTTPS URL to a .dem or a .zip containing one. HLTV serves .rar
archives behind Cloudflare; that path is not supported.
"""
from __future__ import annotations

import shutil
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


def download(url: str, dest: Path, attempts: int = 5, backoff_s: float = 60.0) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f)
            break
        except (urllib.error.URLError, TimeoutError):
            if attempt == attempts - 1:
                raise
            time.sleep(backoff_s * 2 ** attempt)
    if zipfile.is_zipfile(tmp):
        with zipfile.ZipFile(tmp) as z:
            dem = next(n for n in z.namelist() if n.endswith(".dem"))
            with z.open(dem) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
        tmp.unlink()
    else:
        tmp.replace(dest)
    return dest
