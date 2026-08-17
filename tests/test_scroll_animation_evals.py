"""Runs scroll-animation's evals.json for real, against a real ffmpeg call.

This is the difference between a Skill and a markdown file with the same
name: a skill can ship a script and prove it works, not just describe what
it should do. extract_frames.sh is deterministic and mechanical — there is
no excuse for "roughly 60 frames" when the input is a 2-second clip at
30fps; it is exactly 60 or the script is wrong.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "scroll-animation" / "scripts" / "extract_frames.sh"

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestExtractFramesEval1(unittest.TestCase):
    """evals.json eval 1: frame count must match duration * fps exactly."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.video = Path(self.tmp.name) / "test.mp4"
        self.outdir = Path(self.tmp.name) / "frames"
        # A synthetic 2-second test pattern — no external asset needed, fully
        # reproducible, exactly 2.0s so the frame-count assertion is exact.
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
             "-i", "testsrc=duration=2:size=64x64:rate=30",
             str(self.video)],
            check=True, capture_output=True)

    def test_frame_count_matches_duration_times_fps_exactly(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), str(self.video), str(self.outdir), "30"],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        frames = sorted(self.outdir.glob("frame-*.png"))
        self.assertEqual(len(frames), 60,
                         f"2s at 30fps must be exactly 60 frames, got {len(frames)}")

    def test_frames_are_sequentially_named_and_nonzero_size(self):
        subprocess.run(["bash", str(SCRIPT), str(self.video), str(self.outdir), "30"],
                       capture_output=True, text=True, check=True)
        frames = sorted(self.outdir.glob("frame-*.png"))
        self.assertEqual(frames[0].name, "frame-0001.png")
        self.assertEqual(frames[-1].name, "frame-0060.png")
        for f in frames:
            self.assertGreater(f.stat().st_size, 0, f)

    def test_a_different_fps_produces_a_different_exact_count(self):
        outdir10 = Path(self.tmp.name) / "frames10"
        subprocess.run(["bash", str(SCRIPT), str(self.video), str(outdir10), "10"],
                       capture_output=True, text=True, check=True)
        frames = list(outdir10.glob("frame-*.png"))
        self.assertEqual(len(frames), 20)  # 2s * 10fps


class TestExtractFramesEval2(unittest.TestCase):
    """evals.json eval 2: a missing input must fail loudly, never silently."""

    def test_missing_input_fails_with_nonzero_exit_and_stderr_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                ["bash", str(SCRIPT), f"{tmp}/does-not-exist.mp4", f"{tmp}/out"],
                capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not found", result.stderr)
            self.assertFalse(Path(f"{tmp}/out").exists())


if __name__ == "__main__":
    unittest.main()
