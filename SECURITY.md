# Security and privacy notes

## Reporting a vulnerability

Please report security problems privately (GitHub "Report a vulnerability" in the Security tab, or by e-mail to the
maintainer) instead of opening a public issue.

## What KSnapMark stores and sends

| What | Where | Notes |
|---|---|---|
| Upload ("Share → Upload") | `upload_url` (default `https://0x0.st`) | Creates a **public** link that anyone with the URL can open. KSnapMark asks before every upload. Change `upload_url` or do not use the feature if this is a problem. |
| History | `~/.local/share/ksnapmark/history` | Last N captures as PNG files (directory mode 0700). Disable in Settings or clear with one button. |
| Ideas collection | `~/.local/share/ksnapmark/` | SQLite database and images, including OCR text of every saved image. Not encrypted. |
| Persistent redaction list (optional) | `~/.config/ksnapmark/redact_terms.txt` | Plain text, mode 0600. Off by default. |
| Local control socket | `$XDG_RUNTIME_DIR/ksnapmark.sock` | Used by the shortcut command to talk to the background process; accessible by your user only. |

Nothing is sent anywhere else. There is no telemetry.

## Limits of auto-redact

Auto-redact relies on OCR. It can miss text in logos, handwriting, very small, blurred or unusual fonts. Always check the
result before sharing. For secrets, prefer the *Redact* tool (solid fill) over blur or pixelate.

## Window titles

`--selftest` reports do not contain window titles. The window-snapping feature on KDE reads window geometry through a
short-lived KWin script; titles are not stored.
