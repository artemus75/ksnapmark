"""Upload targets for sharing a screenshot as a link (all via curl, nothing else needed)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from .i18n import tr
from .system import which

USER_AGENT = "KSnapMark/0.9"


@dataclass(frozen=True)
class Target:
    key: str
    label: str       # shown in menus
    host: str        # shown in the confirmation
    note: str        # retention / limits, shown in the confirmation


def targets(custom_url: str = "https://0x0.st") -> list[Target]:
    return [
        Target("0x0", "0x0.st", custom_url,
               tr("Link expires after the configured time (if the service supports it).")),
        Target("catbox", "catbox.moe", "https://catbox.moe",
               tr("Files are kept permanently, no account needed.")),
        Target("uguu", "uguu.se", "https://uguu.se",
               tr("Temporary hosting, files are deleted after a few hours.")),
    ]


def target(key: str, custom_url: str = "https://0x0.st") -> Target:
    for t in targets(custom_url):
        if t.key == key:
            return t
    return targets(custom_url)[0]


def command(curl: str, path: str, key: str, url: str, expires_hours: int) -> list[str]:
    """curl command line for the given target."""
    base = [curl, "-sS", "--fail", "-A", USER_AGENT]
    if key == "catbox":
        return base + ["-F", "reqtype=fileupload", "-F", f"fileToUpload=@{path}",
                       "https://catbox.moe/user/api.php"]
    if key == "uguu":
        return base + ["-F", f"files[]=@{path}", "https://uguu.se/upload?output=text"]
    cmd = base + ["-F", f"file=@{path}"]          # 0x0.st and compatible servers
    if expires_hours > 0:
        cmd += ["-F", f"expires={expires_hours}"]
    return cmd + [url]


def upload(path: str, key: str = "0x0", url: str = "https://0x0.st", expires_hours: int = 24) -> str:
    """Upload ``path`` and return the public link."""
    curl = which("curl")
    if not curl:
        raise RuntimeError(tr("curl is not installed (sudo pacman -S curl)."))
    res = subprocess.run(command(curl, path, key, url, expires_hours),
                         capture_output=True, text=True, timeout=120, check=False)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or tr("Upload failed."))
    out = res.stdout.strip().splitlines()[0].strip() if res.stdout.strip() else ""
    if not out.startswith("http"):
        raise RuntimeError(tr("Unexpected response from the server: {out}").format(out=res.stdout.strip()[:200]))
    return out
