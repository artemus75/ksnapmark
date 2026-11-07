"""Mouse pointer option: the right flag reaches each capture backend (nothing by default)."""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
cfgdir = tempfile.mkdtemp()
os.environ["XDG_CONFIG_HOME"] = cfgdir

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
from ksnapmark import capture, config, dbus_capture  # noqa: E402

res = []


def check(name, ok, info=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{info}]" if info and not ok else ""))
    res.append(bool(ok))


seen = {}
capture._stdout_png = lambda cmd: seen.setdefault("stdout", cmd)
capture._file_png = lambda builders: seen.setdefault("file", [b("OUT") for b in builders])


def commands(cursor: bool):
    cfg = config.load()
    cfg.include_cursor = cursor
    config.save(cfg)
    seen.clear()
    out = {}
    capture._DESKTOP_BACKENDS["grim"]()
    out["grim"] = seen.pop("stdout")
    capture._DESKTOP_BACKENDS["gnome-screenshot"]()
    out["gnome"] = seen.pop("file")[0]
    capture._DESKTOP_BACKENDS["scrot"]()
    out["scrot"] = seen.pop("file")[0]
    capture._spectacle()
    out["spectacle"] = seen.pop("file")[0]
    return out


off = commands(False)
on = commands(True)
check("default: no pointer flag anywhere",
      "-c" not in off["grim"] and "-p" not in off["gnome"] and "-p" not in off["scrot"] and "-p" not in off["spectacle"])
check("grim -c", "-c" in on["grim"])
check("gnome-screenshot -p", "-p" in on["gnome"])
check("scrot -p", "-p" in on["scrot"])
check("spectacle -p", "-p" in on["spectacle"])
check("spectacle keeps -b -n and output file", on["spectacle"][:2] == ["spectacle", "-b"] and on["spectacle"][-1] == "OUT")

# KWin: the option is passed on
calls = []


def fake_kwin(name, timeout_ms=20000, include_cursor=False):
    calls.append(include_cursor)
    raise dbus_capture.CaptureError("stop")


dbus_capture.kwin_capture_screen = fake_kwin
screen = app.primaryScreen()
capture._kwin_screens([screen])
cfg = config.load()
cfg.include_cursor = False
config.save(cfg)
capture._kwin_screens([screen])
check("KWin gets include-cursor True/False from the setting", calls == [True, False], str(calls))

cfg = config.load()
check("setting survives save/load", cfg.include_cursor is False)
print("ERGEBNIS:", sum(res), "von", len(res))
sys.exit(0 if all(res) else 1)
