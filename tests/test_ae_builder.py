"""skills/ae-builder: Riyan's claude.ai skill, adapted to run as video-editor's
lead skill for After Effects deliverables (headless worker, macOS). Pins the
adaptations: no claude.ai sandbox paths or mid-task questions, the frame rate
is a parameter rather than a hard-coded 25, the Fontsource fallback names
multi-word families correctly, and video-editor routes to it."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / "skills" / "ae-builder"

try:
    import numpy  # noqa: F401
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


def load(name):
    spec = importlib.util.spec_from_file_location(name, SKILL / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SKILL / "scripts"))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(SKILL / "scripts"))
    return mod


class TestAdaptedForVideoEditor(unittest.TestCase):
    def test_no_claude_ai_sandbox_paths_or_mid_task_questions(self):
        for f in SKILL.rglob("*"):
            if f.suffix in (".md", ".py", ".js", ".jsx"):
                text = f.read_text(encoding="utf-8")
                for bad in ("/home/claude", "/mnt/user-data", "AskUserQuestion"):
                    self.assertNotIn(bad, text, f)

    def test_video_editor_routes_ae_projects_to_it(self):
        text = (REPO / "agents" / "video-editor.md").read_text(encoding="utf-8")
        self.assertIn("An editable After Effects project rebuilding an existing animation:\n"
                      "  `ae-builder`.", text)
        entries = yaml.safe_load((REPO / "config" / "capability-registry.yaml").read_text())
        entry = next(e for e in entries["entries"] if e["id"] == "ae-builder")
        self.assertEqual((entry["trust_tier"], entry["approved_by"]), ("T0", "riyan"))

    def test_fontsource_fallback_slug_keeps_word_breaks(self):
        fetch_fonts = load("fetch_fonts")
        urls = []
        fetch_fonts.get = lambda url: urls.append(url)  # offline: every download misses
        with tempfile.TemporaryDirectory() as d:
            got, _ = fetch_fonts.fetch("Space Grotesk", ["Regular"], d)
        self.assertEqual(got, [])
        fontsource = [u for u in urls if "fontsource" in u]
        self.assertEqual(len(fontsource), 1)
        self.assertIn("/fonts/space-grotesk@latest/", fontsource[0])


@unittest.skipUnless(HAS_NUMPY, "ae-builder's fitter needs numpy")
class TestFrameRateIsAParameter(unittest.TestCase):
    def test_fit_samples_never_puts_two_keys_inside_one_frame(self):
        import numpy as np
        ease_fit = load("ease_fit")
        t = np.linspace(0, 0.6, 400)
        v = np.sin(t * 40) * np.exp(-t * 3) * 100   # wiggly: wants many keys
        gaps = {}
        for fps in (5, 25, 100):
            keys, _ = ease_fit.fit_samples(t, v, tol=0.001, fps=fps)
            ts = [k["t"] for k in keys]
            gaps[fps] = min(b - a for a, b in zip(ts, ts[1:]))
            self.assertGreaterEqual(gaps[fps], 1 / fps - 1e-9, fps)
        # ...and the frame rate really is what limits it (25 was hard-coded)
        self.assertLess(gaps[100], 1 / 25)

    def test_verify_curves_takes_fps_and_runs_from_any_cwd(self):
        with tempfile.TemporaryDirectory() as d:
            dump, checks = Path(d) / "keys.json", Path(d) / "checks.json"
            dump.write_text("{}")
            checks.write_text(json.dumps([{"key": "C > L > ADBE Scale", "curve": "outCubic",
                                           "t0": 0, "dur": 1, "from": 0, "to": 100}]))
            r = subprocess.run([sys.executable, "-I", str(SKILL / "scripts" / "verify_curves.py"),
                                str(dump), str(checks), "--fps", "30"],
                               cwd=d, capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stderr)   # a missing key fails the gate
        self.assertIn("MISSING C > L > ADBE Scale", r.stdout)


if __name__ == "__main__":
    unittest.main()
