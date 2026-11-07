"""Upload targets: curl command lines and response handling (fake curl, no network)."""
import os
import stat
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"
home = tempfile.mkdtemp()
os.environ.update(HOME=home, XDG_CONFIG_HOME=home + "/.config", XDG_DATA_HOME=home + "/.local/share")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ksnapmark import uploaders  # noqa: E402

res = []


def check(n, c, extra=""):
    res.append(bool(c)); print(("PASS " if c else "FAIL ") + n + (f"  [{extra}]" if extra and not c else ""))


C = "/usr/bin/curl"
c0 = uploaders.command(C, "/tmp/a.png", "0x0", "https://0x0.st", 24)
check("0x0: file + expires + url", "file=@/tmp/a.png" in c0 and "expires=24" in c0 and c0[-1] == "https://0x0.st", str(c0))
check("0x0: no expiry when 0", "expires=0" not in uploaders.command(C, "/tmp/a.png", "0x0", "https://x.example", 0))
check("0x0: own server address used", uploaders.command(C, "/tmp/a.png", "0x0", "https://x.example", 1)[-1] == "https://x.example")
c1 = uploaders.command(C, "/tmp/a.png", "catbox", "ignored", 24)
check("catbox: reqtype + fileToUpload + api url", "reqtype=fileupload" in c1 and "fileToUpload=@/tmp/a.png" in c1
      and c1[-1] == "https://catbox.moe/user/api.php" and not any("expires" in a for a in c1), str(c1))
c2 = uploaders.command(C, "/tmp/a.png", "uguu", "ignored", 24)
check("uguu: files[] + text output", "files[]=@/tmp/a.png" in c2 and c2[-1] == "https://uguu.se/upload?output=text", str(c2))
check("all https", all(c[-1].startswith("https://") for c in (c0, c1, c2)))
check("target list", [t.key for t in uploaders.targets()] == ["0x0", "catbox", "uguu"])
check("unknown target falls back to 0x0", uploaders.target("nope").key == "0x0")

d = tempfile.mkdtemp(); fake = os.path.join(d, "curl")
old = os.environ["PATH"]; os.environ["PATH"] = d + ":" + old


def fake_curl(body, code=0):
    open(fake, "w").write(f"#!/usr/bin/env bash\n{body}\nexit {code}\n"); os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)


fake_curl("echo https://files.example/abc.png")
check("link is returned", uploaders.upload("/tmp/a.png", "catbox") == "https://files.example/abc.png")
fake_curl("printf 'https://a.example/1.png\\nextra\\n'")
check("only the first line counts", uploaders.upload("/tmp/a.png", "uguu") == "https://a.example/1.png")
fake_curl("echo '<html>error</html>'")
try:
    uploaders.upload("/tmp/a.png"); check("non-link response is an error", False)
except RuntimeError as e:
    check("non-link response is an error", "error" in str(e))
fake_curl("echo boom >&2", 22)
try:
    uploaders.upload("/tmp/a.png"); check("curl failure is reported", False)
except RuntimeError as e:
    check("curl failure is reported", "boom" in str(e))
os.environ["PATH"] = tempfile.mkdtemp()
try:
    uploaders.upload("/tmp/a.png"); check("missing curl is reported", False)
except RuntimeError as e:
    check("missing curl is reported", "curl" in str(e))
os.environ["PATH"] = old
print("ERGEBNIS:", sum(res), "von", len(res)); sys.exit(0 if all(res) else 1)
