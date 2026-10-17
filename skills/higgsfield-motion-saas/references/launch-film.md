# The launch-film job, end to end (code path)

How the six October 2026 launch films were actually made, condensed into phases with gates. Paths are relative to the skill (`S=<skill dir>`).

## Contents
1. Phase map and time budget
2. Setup
3. Reading references
4. Concept
5. Look: palette, type, details, lens
6. Storyboard gate
7. Build: files, contracts, scenes
8. QA before rendering
9. Render, patch, sound
10. Delivery
11. Revisions
12. Working with agents
13. Disk and process hygiene

## 1. Phase map
| Phase | Output | Typical time |
|---|---|---|
| Setup + ref study | env ok, ref contact sheets | 5–10 min |
| Concept + look | beats on a BPM grid, palette, fonts from a specimen | 5–10 min |
| **Storyboard gate** | sheet of real frames + passport + estimate → wait for "гоу" | 15–25 min total |
| Build | engine + 4–7 scene files, per-cut contracts | 20–40 min |
| QA + draft | `--qa`, cut stills, 2-frame sheets, SUB=1 draft | 5–10 min |
| Final + sound | blurred render (2–5 min), lens, sound, mux, verify | 10 min |
| Revision round | targeted edits + patch render | 15–40 min |
Reroll took 39 min end to end (estimate was 1.5–2 h); BLIP. 63 min; LO. 1 h 53 min with two rounds; Strata 4 h 50 min with four versions and agent workflows. Quote the realistic numbers.

## 2. Setup
```bash
source $S/scripts/code/env.sh          # NODE (≥21), HFT_BROWSER (Chrome/Brave/Edge/Chromium/Yandex), numpy+PIL
$S/scripts/code/build_tools.sh         # bin/encode, bin/mux, bin/extract (swiftc; no ffmpeg needed)
df -h .                                 # a 12-sub-frame render writes ~2 GB; set WORK= on a big volume
```
Copy `assets/film-template/` to `<project>/film/` and smoke-test: `$S/scripts/code/stills.sh film/index.html stills/smoke 0.5,1.6,2.9`.

## 3. Reading references
- `bin/extract ref.mp4 refs/r1 0.5` then `python3 sheet.py refs/r1 refs/r1.jpg` — one sheet per ref, a frame every 0.5 s. For each transition you will borrow: `bin/extract ref.mp4 refs/r1_t3 0.0667 12.4 13.6 960` (1/15 s).
- YouTube tutorial refs: open in the browser pane, make the `<video>` fixed full-screen, seek, wait for `seeked` + 0.7 s, screenshot. Transcripts usually need a login; don't spend time searching old sessions.
- For each ref write one line: what to take (grammar, rhythm, a transition) and what to transform (palette, shapes, type, story). Multiple refs → a beat → source table.

## 4. Concept
- 15 s at 120 BPM: cuts on 0.5 s multiples; 6–9 beats; hook ≤1.5 s; payoff/CTA ≥1.5 s; clean end card ≥1 s.
- **One persistent hero object** carries the story through cuts: BLIP.'s LED face (hook → period of the wordmark → each pet → hub → device), Reroll's vinyl (the 0 in "2016" → the hero of the red frame → the o of "reroll"), LO.'s letter O (typed → zoomed into → becomes the planet), Strata's layer diamond (drawn by the pen → logo → exploded stack).
- A trend hook helps an invented product (Reroll: "2026 is the new 2016" nostalgia, researched by web search).
- Invent the brand: name, mark (one geometric idea tied to the product), palette. Never a real company's name, logo or signature colour.
- Typical arc: hook (a problem or a tease) → title/lockup → 3–4 feature beats (each one idea, ≤16 must-read words in the whole film) → payoff → CTA → end card.

## 5. Look
- **Palette:** 2 worlds (light/dark) + one accent that means one thing (AI, error, CTA). The accent and the frame centre belong to the story's key event. Derive tints from a seed; check must-read contrast ≥4.5:1, including over moving backgrounds.
- **Type:** render `assets/specimen/specimen.html` with 6–12 candidates in the film's real copy (+ a Cyrillic line if any caption is Russian), pick display / motif / UI. Display tracking −3.5…−4.5 %. List every face/weight in `FILM.fonts`.
- **Details:** 6–12 small true details near the hero (selection boxes, dimension pills, redlines that span real distances, guides, rulers iterated over *values*, swatches, comments, frame labels); never overlapping, ≥24 px from edges; the hero still reads at a 25 % thumbnail.
- **Lens:** plan it from the start (`lens.py` schedule per scene, or an in-page WebGL/Canvas lens for canvas films). Dark scenes: bloom .4–.6, ca 2–3, vig .4–.5. Paper scenes: k .03–.05, ca .8–1, vig .2–.3, no bloom. CRT/era scenes: k .2, rounded corners, scanlines .3.
- **Characters:** motion signatures (see `code-engine.md` §6), personality over decoration.

## 6. Storyboard gate
1. Build each beat's **hold pose** in the film engine (static `build()` + the pose at its key time) — not a separate mockup — so the approved look is what ships.
2. `stills.sh film/index.html stills/sb t1,t2,…` (one time per beat).
3. Copy `assets/storyboard/board.example.js` → `film/board.js`, fill: title "NAME — launch 15s · 16:9 · сториборд vN", subline (how it's made), per frame `NN · t0–t1 с · Name` + one Russian line on motion/transition, passport (5–8 swatches, fonts set in themselves, tech line: fps · BPM · blur · lens · sound), **"Отличия от рефов"**, **estimate**.
4. `node $S/scripts/code/capture.mjs "$S/assets/storyboard/storyboard.html?board=$PWD/film/board.js" stills/board --stills 0` → `still_0.00.png`. Look at it yourself first (critique each frame), then send with the estimate and wait.
A "go fast" user may skip re-approval of later boards, but the first board always goes out.

## 7. Build
- Files: `film/index.html` (fonts, `FILM.BG`, `FILM.CAM`, `FILM.start`), `film/scenes/sN_name.js` (one `<script>` each: a syntax error in one must not kill the others), `film/cues.json`, `film/lens.json`.
- **Write the contracts before the scenes** (a SPEC table): for each cut — time, outgoing move (curve, amplitude, pivot), incoming move, what carries over (object + its screen rect, or colour, or direction), and the check command (`stills.sh "film/index.html?only=s3,s4" … t−1f,t,t+1f`). For a carried object: exact screen rect at hand-off time.
- Scenes: `build(root)` creates DOM once (root visible → measurable); `update(lt)` only sets transforms/opacity/clip/text — never rebuilds DOM. Handle `lt<0` / `lt>dur` when using `pre`/`post`.
- Put zoom/position "camera" moves on a wrapper div (the null), not on the objects; expose `zoom(lt)` for `--qa`.
- Pre-roll the animation clock (start letters at lt −0.12 so the first frames after a cut already move), not the visibility.
- Register picture sounds with `FILM.cue(name, t, kind)` where they happen (click, pop, landing at spring start + ~0.13 s, typing).

## 8. QA before rendering
- `node capture.mjs film/index.html /tmp --qa` → zoom direction across every cut (✗ = flip).
- Stills at t−1f, t, t+1f for every cut; at every transition's midpoint; background-only (`?only=none`) at every flood midpoint.
- A sheet of 2-frame steps (0.067 s) through each character/idle motion and each transition — motion amplitude can't be judged on single stills.
- Whole-film sheet every 0.1–0.2 s after the draft: look for pops at frame 0, empty frames after cuts, objects parked at the edge before entering, text cut by the frame, dark-on-dark text during floods, held must-read lines <0.8 s.
- Grep capture logs for `SCENE ERRORS`.

## 9. Render, patch, sound
```bash
R=$S/scripts/code
$R/render_film.sh film/index.html film/draft.mp4 1 8                                     # ~30–60 s, no blur
LENS=1 LENS_ARGS="--sched film/lens.json" WORK=/big/disk/work \
  $R/render_film.sh film/index.html film/NAME_launch_15s_16x9_nosound.mp4 4 8 12 "1.9-2.6,7.0-7.6,12.1-12.6"
KEEP=1 FROM=9.6 TO=10.2 $R/render_film.sh …                                              # patch a range, then re-encode
node $R/capture.mjs film/index.html /tmp --cues film/cues.json
python3 $R/sound_template.py film/cues.json film/sound.wav                               # → sound.wav + sound.m4a, onset report
$R/bin/mux film/NAME_launch_15s_16x9_nosound.mp4 film/sound.m4a film/NAME_launch_15s_16x9.mp4
```
- Run finals with `run_in_background` and a log; a foreground render dies with the session. Kill a stuck render: `pkill -f capture.mjs` and the browser's `remote-debugging` processes.
- Patch renders: keep the frames (`KEEP=1`), re-capture only the changed range into the same `frames/`, re-encode — under a minute.
- Sound is a placeholder for the client's human mix; generate it while the picture renders; re-export cues and re-run (≈1 s) after any retime.

## 10. Delivery
- Pull frames back out of the final MP4 (`bin/extract final.mp4 chk 0.5`), check duration = 15.000 s, frame count 450, audio length (`afinfo`).
- Deliver `NAME_launch_15s_16x9.mp4` + `_nosound.mp4` (+ storyboard PNG). Message: one line per beat with timecodes, how it was made, what was verified (which sheets), remaining flaws stated honestly, how to re-render.

## 11. Revisions
- Back up the approved state (`film/_approved_v1/`), then change only the named things (see `client-taste.md` §5).
- "vN was better": extract vN's frames, copy vN's code/numbers verbatim, compare cut sheets side by side.
- A new ref mid-project: merge its beats into the approved cut; show the beat → ref table; sample the borrowed range densely and copy its motion grammar beat by beat in your own look.

## 12. Working with agents (only when the user opted into workflows)
- One agent per scene module, sharing one SPEC with numeric cut contracts; agents never edit the engine — they report requests (measured rects, background origins) and the orchestrator applies them.
- Build → adversarial critic (renders the module with its neighbours, returns `{verdict, issues:[{severity,time,what,fix}]}`) → fix only med/high.
- Unique `CAP_PORT` range per agent (20 ports; critics use the upper half). Create every file a prompt references *before* launching.
- Never SendMessage to a workflow-spawned agent — it resumes a duplicate that races the original on the same files. Coordinate through a file named in every prompt, or the next phase's prompts.
- Agents' check renders fill disks: give them `CAP_TMP`/`WORK` on the big volume and clean up after each round.
- Without workflows, building modules yourself is often faster (Reroll, BLIP., LO. were single-agent).

## 13. Hygiene
- Keep ≥5 GB free; the shell dies on ENOSPC (clean up via a terminal tab if Bash stops working). `render_film.sh` deletes sub-frames and browser profiles; delete check renders yourself.
- `sleep` is blocked in the tool runner: use `run_in_background` + completion notifications, or `until …; do sleep 5; done` inside a background job.
- In zsh, unquoted `$var` does not word-split (`set -- $r` breaks); `while read` drops a last line without a newline.
- Batch code edits with a Python replace that asserts each pattern matches exactly once; re-Read a file after editing it in place before using Write on it.
