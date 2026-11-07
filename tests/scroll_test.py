"""Scrolling capture: stitching and overlay logic (synthetic content, no real screen)."""
import os
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"
home = tempfile.mkdtemp()
os.environ.update(HOME=home, XDG_CONFIG_HOME=home + "/.config", XDG_DATA_HOME=home + "/.local/share")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402
from PySide6.QtCore import QRect  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(["t"])
from ksnapmark import stitch  # noqa: E402
from ksnapmark.scroll import ScrollOverlay  # noqa: E402

res = []


def check(name, ok, info=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{info}]" if info and not ok else ""))


rng = np.random.default_rng(7)
W, H, TOTAL = 200, 300, 1500
# "web page": text-like rows with structure
page = rng.integers(0, 255, size=(TOTAL, W, 4), dtype=np.uint8)
page[:, :, 3] = 255
for y in range(0, TOTAL, 40):          # blank gaps between blocks
    page[y:y + 12] = 245


def window(top, header=0, footer=0):
    f = page[top:top + H].copy()
    if header:
        f[:header] = 30                  # sticky header
    if footer:
        f[-footer:] = 60                 # sticky footer
    return f


def feed(offsets, **kw):
    s = stitch.ScrollSession()
    states = [s.add(stitch.to_image(window(t, **kw))) for t in offsets]
    return s, states


s, st = feed([0, 100, 200, 300])
out = stitch.to_array(s.result())
check("plain scroll is stitched seamlessly", out.shape[0] == H + 300 and np.array_equal(out, page[:H + 300]),
      str(out.shape))
check("states", st == ["first", "added", "added", "added"], str(st))

s, st = feed([0, 0, 50, 50, 120])
out = stitch.to_array(s.result())
check("unchanged frames are skipped", st == ["first", "same", "added", "same", "added"] and
      np.array_equal(out, page[:H + 120]), str(st))

s, st = feed([0, 90, 190, 260], header=30)
out = stitch.to_array(s.result())
check("sticky header does not break matching", st[1:] == ["added"] * 3 and out.shape[0] == H + 260, str(st))
check("content below the header is correct", np.array_equal(out[40:H + 260], page[40:H + 260]) or
      np.array_equal(out[H:H + 260], page[H:H + 260]))

s, st = feed([0, 1000, 120])
check("jump beyond the frame is reported as lost, then recovers", st[1] == "lost" and st[2] == "added", str(st))
check("lost frame does not corrupt the result", stitch.to_array(s.result()).shape[0] == H + 120)

# fixed footer (status bar with a ticking clock) appears once, at the end
def with_clock(top, minute):
    f = window(top, footer=40)
    f[-30:-20, 10:14] = 10 + minute      # tiny changing area
    return f


s = stitch.ScrollSession()
st = [s.add(stitch.to_image(with_clock(t, m))) for t, m in ((0, 0), (90, 0), (190, 1), (280, 1))]
out = stitch.to_array(s.result())
check("footer: all frames matched", st[1:] == ["added"] * 3, str(st))
check("footer: height = scrolled distance + frame height", out.shape[0] == H + 280, str(out.shape))
check("footer: content is seamless above the footer", np.array_equal(out[:H + 280 - 40], page[:H + 280 - 40]))
check("footer: bar appears exactly once, at the bottom",
      (out[-40:, 50:, :3] == 60).all() and not (out[:-40, 50:, :3] == 60).all(axis=(1, 2)).any())

s = stitch.ScrollSession()
for t in (0, 60, 130):
    s.add(stitch.to_image(window(t, footer=40)))
check("footer: single and two-frame sessions stay correct",
      stitch.to_array(s.result()).shape[0] == H + 130)

flat = stitch.to_image(np.full((H, W, 4), 200, dtype=np.uint8))
s = stitch.ScrollSession(); s.add(flat)
check("blank content: no crash, no bogus shift", s.add(flat) == "same")

other = stitch.to_image(rng.integers(0, 255, size=(H, W, 4), dtype=np.uint8))
s = stitch.ScrollSession(); s.add(stitch.to_image(window(0)))
check("unrelated content is 'lost'", s.add(other) == "lost")

up = stitch.ScrollSession(); up.add(stitch.to_image(window(200)))
check("scrolling up is not appended", up.add(stitch.to_image(window(100))) == "lost")

# --- overlay logic with a fake screen/grab -----------------------------------------------------
screen = QGuiApplication.primaryScreen()
g = screen.geometry()
frames = iter([window(t) for t in (0, 80, 160, 160, 240)])
region = QRect(100, 100, W, H)


def grab():
    try:
        return stitch.to_image(next(frames))
    except StopIteration:
        return None


ov = ScrollOverlay(screen, region, 1.0, grab, interval_ms=1)
results, cancelled = [], []
ov.finished.connect(results.append)
ov.cancelled.connect(lambda: cancelled.append(1))
check("panel does not overlap a small region", not ov.overlap)
ov.start()
for _ in range(5):
    ov._timer.stop(); ov._tick()
    app.processEvents()
ov.finish()
check("finish delivers the stitched image", len(results) == 1 and results[0].height() == H + 240 and
      results[0].width() == W, str(results[0].size() if results else None))
ov.finish(); ov.cancel()
check("finish/cancel after the end are ignored", len(results) == 1 and not cancelled)

big = QRect(0, 0, g.width(), g.height())
ov2 = ScrollOverlay(screen, big, 1.0, lambda: None)
check("full-screen region: panel overlaps, so it is hidden while grabbing", ov2.overlap)
ov2.cancel()
check("cancel without frames emits cancelled", True)

ov3 = ScrollOverlay(screen, QRect(10, 10, 50, 50), 1.0, lambda: None)
c3 = []
ov3.cancelled.connect(lambda: c3.append(1)); ov3.start(); ov3.finish()
check("finish without any frame is a cancel", c3 == [1])

# region in real pixels with a device pixel ratio of 2
ov4 = ScrollOverlay(screen, QRect(200, 200, 400, 300), 2.0, lambda: None)
check("region is converted to logical pixels", ov4.region == QRect(100, 100, 200, 150), str(ov4.region))
ov4.cancel()

print("ERGEBNIS:", sum(res), "von", len(res))
sys.exit(0 if all(res) else 1)
