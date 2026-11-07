"""Translation checks: language detection, complete German catalog, matching placeholders."""
import ast
import glob
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
res = []


def check(name, ok, info=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{info}]" if info and not ok else ""))
    res.append(bool(ok))


def lang_for(**env):
    base = {k: v for k, v in os.environ.items() if k not in ("LANG", "LANGUAGE", "LC_ALL", "LC_MESSAGES", "KSNAPMARK_LANG")}
    base.update(PYTHONPATH=ROOT, XDG_CONFIG_HOME="/nonexistent", **env)
    out = subprocess.run([sys.executable, "-c", "from ksnapmark import i18n; print(i18n.LANG)"],
                         env=base, capture_output=True, text=True)
    return out.stdout.strip()


check("LANG=de_DE.UTF-8 -> de", lang_for(LANG="de_DE.UTF-8") == "de")
check("LANG=en_US.UTF-8 -> en", lang_for(LANG="en_US.UTF-8") == "en")
check("LANG=C -> en", lang_for(LANG="C") == "en")
check("unsupported language falls back to the next LANGUAGE entry", lang_for(LANGUAGE="fr:de", LANG="fr_FR.UTF-8") == "de")
check("unsupported language only -> en", lang_for(LANG="fr_FR.UTF-8") == "en")
check("KSNAPMARK_LANG overrides the system", lang_for(LANG="de_DE.UTF-8", KSNAPMARK_LANG="en") == "en")
check("nothing set -> en", lang_for() == "en")

from ksnapmark.translations.de import CATALOG  # noqa: E402

used = {}
for path in glob.glob(os.path.join(ROOT, "ksnapmark", "*.py")):
    for node in ast.walk(ast.parse(open(path).read())):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr":
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                used[node.args[0].value] = os.path.basename(path)

missing = [s for s in used if s not in CATALOG]
check("every tr() text has a German translation", not missing, str(missing[:3]))
stale = [s for s in CATALOG if s not in used]
check("no unused catalog entries", not stale, str(stale[:3]))


def fields(text):
    return sorted(re.findall(r"\{(\w+)", text))


bad = [s for s, de in CATALOG.items() if fields(s) != fields(de)]
check("placeholders match between English and German", not bad, str(bad[:3]))
check("German catalog has no identical (untranslated) entries",
      not [s for s, de in CATALOG.items() if s == de and len(s) > 12], "")

print("ERGEBNIS:", sum(res), "von", len(res))
sys.exit(0 if all(res) else 1)
