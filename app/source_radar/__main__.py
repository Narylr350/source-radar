import os
import subprocess
import sys

os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Suppress console windows from ALL subprocess calls (crawl4ai/Playwright etc.)
if sys.platform == "win32":
    _CREATE_NO_WINDOW = 0x08000000
    _orig_popen = subprocess.Popen.__init__

    def _no_window_init(self, *args, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | _CREATE_NO_WINDOW
        _orig_popen(self, *args, **kwargs)

    subprocess.Popen.__init__ = _no_window_init

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
