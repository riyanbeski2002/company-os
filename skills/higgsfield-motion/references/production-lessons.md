# Production lessons: process, pipeline and QA for films

How to run a film job with this user, build it, render it, check it and deliver it. These lessons come from every film session so far. **What the user likes on screen** lives in `client-taste.md`, and the frame laws live in the handbook (`parts/*.md`). This file covers the *how*.

- Every rule ends with its ledger ID in brackets, e.g. [P-01]. IDs starting with K- are resolved conflicts.
- The user's words are quoted verbatim, typos included.
- Read §0 on every job. Open the other sections when their stage comes up.

| Project | Session | What it was |
|---|---|---|
| Audio MCP | 2746ff-A | Higgsfield key frames, styleboard, token system |
| ZEVRA | 2746ff-B | 15–30 s SaaS launch for a fictional brand, in a real company's board style |
| onbeat | b9e6af | 15 s fictional techno-sync product film |
| SHIFT / SHIFT30 | 257453 | 30 s restaurant-SaaS ad: generated footage + animated product UI |
| PLAY | 5f377a | 30 s launch ad with animated game screens |
| PHYLLA | f18bfc | 30 s abstract LLM launch: generated montage + code-synth score |
| Ad Multiplier | fe5d90 (+ helper c75026) | remake of a team reel with a live generated hero |
| POST | 769e6b | 30 s LLM post-writer ad (parallax, push-in, defocus, match cut, flash) |

---

## 0. If you read nothing else

1. Show something visible within 10–15 min of any request. After that, send each deliverable the moment it exists. Never let 15–20 min pass without a visible change. [P-01]
2. Answer every «что там?» with: clock time, what changed, current stage, an image or video, a clock-time ETA, and an offer to stop now. [CM-01]
3. For a film, write and send the scenario first (shot table on the beat grid + trigger map + ≤2 questions) before building anything. [S-01]
4. Calibrate before fan-out: ~5 key frames, or 2–3 stills for a look change, and get a yes before building every frame. [P-03]
5. Make a rough cut with music early. Number every version and never overwrite a file the user has seen. [P-02]
6. Every film ships with sound: a music bed plus SFX. Never send a silent cut. [SN-01]
7. Never send a version without frame-level QA: a frame-diff scan of the encoded MP4, plus stills every 2 frames ±0.5 s around every cut. [Q-01]
8. One review round between client rounds at most. Ship the interim and let the user be the reviewer. Offer a second round instead of running it silently. [Q-05]
9. In a "make it better" pass, fix the defects you have already diagnosed and send them first. Delegate only the unknowns. [P-07]
10. On «стоп» / «пока стоп» / «все не надо», halt every workflow, generation and render at once, confirm nothing is still spending credits, and say what is done. [P-05]

---

## 1. Process and cadence

### First result and send cadence

- **First visible thing in ~10–15 min,** before any infrastructure, art contracts or agent workflows: script or storyboard on grey stubs → contact sheet → send. [P-01]
- **Then send each deliverable as it lands:** music choice, scenario, key-frame sheets per batch, clip sheets, footage reel, rough cut. [P-01]
- **Evidence:** «что нибудь есть» ×13+ and «какое состояние сейчас» ×6 (Audio MCP); «что там?» ~25× (ZEVRA), ×18 (Ad Multiplier); «давай быстрее, кидай кадры как будут» (PHYLLA); «пока стоп, покажи что есть» (POST, after 26 min of critics with nothing visible). PLAY showed its first frames only 34 min in. [P-01]
- **Rough cut early.** Once a script and some assets exist, assemble a rough cut. Use stills or ✦ GENERATION plates for missing shots. Send it with music before any multi-agent verification. The PHYLLA v1 rough cut took ~9 min. [P-02]
- **Keep a fast preview path:** no motion blur, no post, music muxed. It should take minutes, not hours, so you can answer «покажи что есть сейчас». [P-02]
- **Number versions** (v1, v2…, `_INTERIM`, `_DRAFT`) and never overwrite a file the user has seen. [P-02]
- **With every send, list what you still see wrong, with timecodes.** The user often picks fixes from that list. [P-02]

### Calibrate before fan-out

- **New direction:** render ~5 one-idea key frames and get a yes before building every frame. After the density rejection, 5 hand-built calibration frames were approved within a minute («да, собирай весь ролик»). [P-03]
- **Sweeping palette or font change:** show 2–3 key stills first. ZEVRA rebuilt all 18 shots (~30 min) for "dark + acid + tech font", and the user then rejected both: «шрифт не очень… добавь синего яркого цвета, а не зеленый… по визуалу прошлый нравится». [P-03]
- **Formats:** get the 16:9 master approved before building 9:16. Ask about the vertical before generating for it, because it adds ~half the build and doubles the generations. [P-13]
- **When the user drops something** («забудь про 9:16»), stop rendering, reviewing and fixing it the same day, freeze its code paths, and record the drop with the date and the user's words. In SHIFT round 1, the 9:16 cuts carried most of the bugs; dropping them freed two iterations for camera and pacing. [P-13]

### Directions and choices

- **Options:** present them as labelled directions on one sheet (A/B/C, frame number, short name) and ask which is closer. Expect two-word answers by frame number («a inputs / c pipeline» in 3 min). Keep numbering stable across rounds; don't renumber after deletions. [P-04]
- **After a rejection:** [P-04]
  1. Build 3–4 directions in parallel from one shared CONTEXT file, each a different bet on the axis the feedback named.
  2. Judge them with lenses that include a client proxy.
  3. Show key frames side by side as soon as they render.
  4. Propose a hybrid with a default action: "if you don't answer, I'll build the hybrid".
- **Judging directions:** grafts proposed by ≥2 judges are almost always right. Pick the base by what is hardest to retrofit (the product architecture). People decide on pictures, not scores. Don't run directions for polish passes. [P-04]
- **«С нуля, но с той же айдентикой»** means: [P-12]
  - keep the wordmark, fonts, colours, ornaments and approved footage;
  - throw away all layouts, card designs and pacing;
  - deeper or more saturated steps of the same hues are allowed, new hues are not;
  - any direction that recreated the v001 compositions was judged a fail.
- **Alternatives as a side track:** run a requested alternative (a recast, a new look) in the background next to the main build. When it lands, send a contact sheet with an honest list of what missed the brief, and offer to regenerate only those. [P-10]
- **Variants:** recommend one, but let the user pick. Don't announce your pick as decided: the assistant wrote «Беру S_prof2», and the user chose S_prof1, the more styled editorial variant. [P-10]

### Handling feedback

- **Terse negative feedback** («пусто», «коротко», «не то»): don't ask clarifying questions. Make one bold, complete revision quickly, keeping the agreed length, format and the previous version on disk. Send the new strip and invite the user to name any frame that still fails: «Если какой-то кадр всё ещё пустой — назови номер». onbeat v2 took ~7 min and got «собери mp4». [P-08]
- **Turn every feedback round into a file before any agent works on it:** [P-15]
  - the user's words, verbatim;
  - a translation;
  - WHAT STAYS (name the loved parts);
  - numbered, measurable changes.
- **Version the scenario as delta documents** («v3 replaces v2 and v1», «where they conflict, v4 wins») and send each version to the user. Snapshot the source before each new version. This kept 4 parallel builders aligned through 5 direction changes in ZEVRA. [P-15]
- **Passport exceptions.** Record every rule broken on purpose, at the user's request, in the film passport, with the user's words and what stays binding. [P-14]
  - Never relax: legibility floors, reading minimums, verbatim copy, honesty, flash safety.
  - Reviewers check the passport before "fixing" a documented exception.
  - SHIFT exceptions: camera verb/whip limits lifted («камера двигалась туда сюда»); measured reads instead of the formula («быстрее … не задерживалось»); card entries 0.25–0.35 s; saturated chapter plates; 9:16 dropped («забудь про 9:16»). PLAY kept an `exceptions[]` list in its style layer.

### Stops, urgency and polish

- **On a stop or redirect** («стоп…», «пока только…», «пока стоп», «пока не надо», «думаю стоп», «все не надо»): [P-05]
  - halt at once every background workflow, generation and render building the old direction;
  - confirm nothing keeps spending credits, helper sessions included;
  - say in one message what is done and what is resumable;
  - stop re-rendering and showing until asked;
  - back up the current version;
  - relaunch with the approved draft as the binding base, so agents don't reinvent the film;
  - recover already-submitted generation jobs with `jobs_wait` instead of resubmitting (a stopped batch had already created 3 jobs server-side).
- **Under urgency** («как ускорить?», «в течении часа», «мне срочно нужно»): [P-06]
  - re-plan for parallelism: independent stages in parallel, inputs sliced by script (8 parallel writers produced the handbook in 15 min);
  - set a hard deadline; at the deadline, ship the last state that passes tests and list exactly what was skipped;
  - give ETA ranges and don't let them slip repeatedly (15:00 → 15:10 → 15:20 happened);
  - multiply multi-agent estimates by 1.5–2: a 15 s film promised in 60–80 min took ~2 h, and a fix promised for 22:30 shipped at 23:48.
- **"Make it better" pass:** first fix inline the defects you have already diagnosed and send the improved version, then delegate only the unknowns. [P-07]
  - Apply findings as they arrive and re-render per segment. Never let all edits wait for every critic and verifier.
  - POST listed 6 visible bugs, handed them to critics, and none were fixed after 26 min.
  - If a workflow is stopped, harvest partial implementations from agent scratch copies and offer them, labelled unverified. POST's CONTROL critic had a working patched copy that was never delivered.
- **Keep polish passes short:** timebox look-dev; give the densest act more agents; make small content swaps in the main thread (edit → 10-still check strip in ~2 min); keep rendering the current state with music while critics run. A kit agent polished the ZEVRA ray shader through 3 iterations while the user wrote «я жду»; the 15 s workflow cost ~2 h and 2.1 M tokens. [P-09]
- **Review depth follows the user's patience:** [Q-05]
  - at most one review round between client rounds;
  - ship the interim with sound and let the client be the reviewer;
  - offer a second round instead of running it silently;
  - on «долго» / «гоу быстро» / «срочно», render from the last state that passed the key check and list what was skipped;
  - after a usable deliverable, report 2–3 known limitations and ask before launching long fix/verify workflows.
  - Every planned 2-round, 6-reviewer loop (~2 h) was overtaken by new feedback or cancelled. The only actionable notes came from the user watching rough cuts.
- **Interim sends, not silence.** «покажи когда будет готово» still means proactive interim sends: right after saying it, the user kept asking «что нибудь есть» every few minutes. [K-18]

### Higgsfield product films

- If the film is for a Higgsfield product with a launch family in the team library (handbook project code + Figma node ids), open those frames through Figma MCP **before designing**. Pull exact specs and assets (wordmark, cursor, stickers, glows, grid) into a `LIBRARY_SPEC` and build in that language. [P-11]
- Example: Ad Multiplier = project AS, file `RoQtfXjz3SR5bipwDLoE5I`, nodes `24515:17222`, `24516:5267`, `24545:19864`, `24454:8589`. The v3 notes never touched the design language, and the user said «давай по дизайну лучше сделаем / чекай library у скила который есть». [P-11]

---

## 2. Communication

- **Status answers** have this shape, in 3 short lines: [CM-01]
  1. delivered, with links (an image or video when one exists);
  2. running, with a clock-time ETA (never «не скажу»);
  3. anything the user must do.
- **Also include** the clock time, what changed since the last ping, the current stage, and an offer to stop now and ship known fixes. Own the delays you caused. [CM-01]
- **Why:** answers that came with a WIP sheet or draft MP4 ended the pinging; «показывать пока нечего» did not. In POST, «По оставшемуся времени точно не скажу» was followed by «ну что там, готово?», «есть результаты», then a stop. [CM-01]
- **Fast typing:** the user types fast and corrects in the next message (23:48:37 «мне нравится дизайн, он примитивен слишком…» → 23:48:45 «не нравится»). Read consecutive short messages, and messages queued mid-turn, together, and act on the latest meaning. Never ask about obvious typos. [CM-02]
- **Digests miss queued messages** stored as attachments (`origin.kind=human`); grep the raw JSONL for them when mining a session. [CM-02]
- **Quick questions get quick answers.** On «быстро»: one pick with a one-line reason, ≤4 short alternatives, no preamble. [CM-03]
- **Style names:** when asked what a style is called, give the established name plus its component techniques as usable prompt terms. Example: "bio-digital / techno-organic: bento grid, grainy aura gradients, halftone dot-matrix, technical annotations". Preset names: 'Living Lab' + Specimen / Phyllo / Grown Not Built / Seed → World. [CM-03]

---

## 3. Orchestration (agents, workflows, helpers)

- **Never SendMessage a subagent running inside a Workflow.** It forks a parallel copy that edits the same files, and TaskStop on that id also kills the workflow's own agent. Instead, pass notes to the next stage, or stop the workflow, edit the saved script prompt and relaunch with `resumeFromRunId` (finished agents come back from cache). This cost a restart and ~5 min in Ad Multiplier. [O-01]
- **Parallel builders own disjoint files:** [O-02]
  - split by segment group from the start; a launched workflow can't be re-split;
  - freeze the shared kit and cross-boundary function signatures before launch, owned by one integrator;
  - builders write change requests instead of editing others' files;
  - each builder renders into its own folder;
  - every agent gets the same CONTEXT file and the newest feedback file;
  - after every merge, re-render and check that every brief beat still renders;
  - give agents unique lowercase scratch names;
  - merge failures seen: a route-draw ended up inside a `//` comment; `B16` and `b16` merged on the case-insensitive disk.
- **Focused inputs:** give agents part files and JSON digests, not whole documents, and require an early written artifact. `build:system` spent 8 min and 354.8k tokens reading ~1 MB before writing anything. [O-03]
- **When the user screenshots an agent row** and asks «это что сейчас делаешь?», explain plainly and give an ETA to the first visible output. [O-03]
- **Never let workflow agents read raw `.jsonl` transcripts** (it tripped the safety classifier). Pre-extract job ids and choices into a small `state.json`. [O-03]
- **Carry over the idea of liked frames, never their devices.** Brief agents: "take the structural idea; density follows the genre rule". The Audio MCP 'system designer' made HUD frames, N° numbering, satellites, ring text, cables and glow shared across all frames, which produced the dashboard rejected 25 min later («слишком много фрагментов и лишнего мусора»). [O-04]
- **Helper and parallel hygiene:** [O-05]
  - QA finished segments read-only in parallel; snapshot only after the writer agent has returned;
  - route findings to the fixer or the next stage, not to an implementer about to finish (only 1 of 5 landed);
  - serialize heavy local jobs (`lockf`), render from frozen snapshot copies, and kill only your own browser processes: «Тяжёлые рендеры не запускай больше чем по одному одновременно»;
  - a second helper session gets read-only checks and asset/tool prep with separate file ownership, never a second editor on the same file.
- **Pre-produce during waits.** While an agent builds the next segments, prepare what the next stage needs, writing only new files in a helper folder: [P-17]
  - missing assets (e.g. grid clips);
  - SFX cue drafts from the code's timing constants;
  - an acceptance spec for the segments being built: per-time must-be-on-screen tables, cut contracts, a risk list with still times;
  - result in Ad Multiplier: 12 → 22 distinct grid clips were plugged in via an extra manifest, with no edits needed.

---

## 4. Scenario

### The scenario document (send it before building)

Write and send it before any film build. When asked for "scenario first", deliver only the scenario and stop. If concept agents are still running, draft the scenario yourself from the leading concept, send it, and merge the agent version later. [S-01]

- ZEVRA: the scenario arrived 3 min after the request, and the user said «гоу» within a minute.
- onbeat: concept + shot table + 2 questions got a one-line answer.
- PHYLLA: the user interrupted a download to ask «давай черновик сценария сразу как будет» while a synthesis agent had been running for 18+ min.

**Contents:** [S-01]
1. A one-line idea.
2. The acts.
3. A shot table on the beat grid (template below).
4. A trigger map (template below).
5. A passport line: format, fps / BPM, fonts, accents.
6. Closing rules.
7. ≤2 decision questions.

**Shot table.** Tag every shot sparse or dense, and alternate every 1–2 cuts. A film that is sparse in all but one shot reads as empty: onbeat v1 ran sparse, sparse, medium, sparse, sparse, dense, sparse → «очень коротко и пусто». [C-02]

| # | Time (beats) | Picture | Camera | On-screen text | Sound | Sparse / dense |
|---|---|---|---|---|---|---|
| 01 | 0.0–1.0 s (2 b) | … | push-in following … | … | kick + riser | dense |

**Trigger map.** Every transition needs a visible cause inside shot A that carries the eye into shot B. «The timeline says so» is not a trigger. Write the map before animating. [S-02]

| Time | Trigger (in shot A) | Effect (shot B) | How the camera follows |
|---|---|---|---|
| 6.5 s | toast arrives top-right | its module opens | camera follows the toast into the module |

- **Triggers that worked:** a toast arrives and the camera follows it into its module; a click spawns a state and the camera flies there; exit and entry share a direction; a lock-on ring carries a real object onto its UI twin; a slot fold; an avatar zoom-through; a touch becomes a number (finger on the 4th bun → «In stock: 4»); the product folds into a device on the drop. [S-02]
- **Doesn't count:** a toast that arrives 2 frames before the whip. [S-02]
- **Evidence:** «плюс чтобы тригеры были (логика переходв от чего к другому)» → SHIFT v003 «гуууд». [S-02]

### Shot count and structure

- **The 7-beat 15 s template is a minimum skeleton, not a shot list.** Plan ~10 shots for 15 s: [S-04]
  - a 1-beat burst series up front, and short punches before hits;
  - varied shot lengths (e.g. 2-1-1-4-6 beats);
  - long holds only where text must be read;
  - onbeat v1 copied the template (7 shots of 1.8–3.2 s) → «очень коротко и пусто». v2 kept 14.67 s with 10 shots: surprise by 1.4 s, name by 2.1 s, a 0.5-beat snap-zoom before the drop → «собери mp4».
- **One big moment.** Find ONE moment where the product physically transforms on the music drop (SHIFT: the whole app folds into the manager's tablet, «конец бомба когда экран в планшент ушел»). [S-03]
  - Compress the story so it ends at ~70–78% of the runtime.
  - Build into the moment over ~2 bars with an update on every beat, then hold a still end lockup.
  - Use the 'suck' ease (0.62, 0, 0.92, 0.42) with the boom on the landing frame.
  - Once the user loves the moment, make it bigger in every later version.
  - Test a candidate: does it involve the whole product, is it a physical transformation, does it land on one beat, does it hand the film back to a person? It often hides in the last paragraph of the brief.
- **Launch structures the user approved:** [S-05]

| Structure | Beats | Result |
|---|---|---|
| (a) Launch skeleton | macro hook 0–2 s → title on a downbeat (name by ~3 s) → prompt typing with highlighted words → Generate on the drop (words fly into the result) → proof → twist → slow-mo hero moment → one→many → end card | PLAY: 9 versions, iterations only on look and details, never on structure |
| (b) One continuous camera flight | 30 s in 4 acts, with bookend match cuts on the mark | ZEVRA: «задумка топ» |
| (c) Live-action story | story hook → title on a hit → the product mechanic as numbered beats → payoff → callback of the hook line → end card | Ad Multiplier remake v1: «офигенно» |

- **Brand timing.** Performance and product ads show the product or offer ≤3 s and the brand mark ≤5 s. An inspirational brand film for a new product may delay the name to the music lift (PHYLLA: name at 20 s, «вау») when every beat is still readable imagery and the hook surprises within 2 s. Record it as a passport exception. [K-16]

### Remakes and ideation

- **Remaking a reference reel or improving a team film:** [S-06]
  1. Download it and make a contact sheet every 0.5 s.
  2. Transcribe the VO.
  3. Write a table: what the original does wrong → what the remake fixes.
  4. Keep its strengths: the through-object, its worlds, and the team's own Figma as the benchmark («в фигме нашем это что надо»).
  5. Show the missing mechanism as ONE object per beat.
  6. Cut repetition and snap cuts to the beat grid.
- **Remake results:** Ad Multiplier went 63 s → 46.5 s: six Ref→Result pairs in a row were cut, the caption's mechanic was shown, and three sub-identities merged into one passport. In Audio MCP, a single `generate_audio()` pill was added, and the user liked it as frame 07. [S-06]
- **Ideation patterns that worked:** [S-08]
  - Offer 3 ideas that differ in spine (not in colour) and recommend one. Spines: service run, one object's journey, problem → switch, race against time, hero POV, "the line", scale zoom.
  - For a category-only brief, invent a fictional product whose story is the genre's own mechanic, with one hero glyph that reads 2–3 ways. onbeat: an outage is a missed beat, and the fix lands on the drop.
  - For "abstract but inspiring", build a visual rhyme between nature, body and product (seed / cell / word). Keep every beat instantly readable and avoid AI-launch clichés. Rhyme devices: a triad on consecutive beats, flash triplets, a callback line, a type morph (word → world).

### Product chapters with live footage

- **Chapter shape:** world cause (filmable) → one product gesture on a beat → a state readable in ≤1 s → world effect. [S-07]
- **Energy comes from footage ⇄ UI hand-offs:** [S-07]
  - footage folds into a UI slot;
  - a lock-on ring carries a real object onto its UI twin;
  - avatars and thumbnails are crops of your own takes, so a zoom-through reads as "this is that person".
- **Never draw labels or CV tags on real footage;** they imply features the product lacks. [S-07]
- **Load:** a 15 s film carries 1–2 jobs, 30 s carries 3. Put the strongest gesture in the middle chapter. Show a one-place reveal before any feature. [S-07]

### Readable without sound, and honest

- **Context text** («добавим текста контекста»): [S-09]
  - numbered step badges (01 Describe → 02 Build → …), in the safe zone, gone before the climax;
  - the VO as short centred captions: ≤32 chars per line, laid out in full before word reveals so they stay centred, each held ≥20 frames. A reviewer found a caption centred at x 599 under a badge at x 960.
- **Keep on-screen logic honest:** [S-10]
  - the prompt shown matches the generations it produces: use a rolling prompt that types short prompts matching each real clip, and label cards with the real clip («поправим промпт получается под любую рандомную»);
  - the winner carries the top metric (a winner card at 6.8x ROAS while a back card read 7.7x was a bug);
  - counters run monotonically from a plausible start;
  - labels match counts («Generate 12» followed by 20+ ads was flagged);
  - UI state matches what is visible (no "64 characters" footer over a blank card);
  - copy is verbatim from the brief, punctuation included (removing the brief's colons was judged a blocker);
  - one data bible feeds every on-screen number, and illustrative data is marked as such.
- **Named effects must read.** When the brief names effects (parallax, push-in, defocus, match cut, flash), each one must read unmistakably on screen. Keep a checklist row per effect with its timecode and a 1080p still that proves it. [S-11]
  - POST v1 had them in code, but on screen: focus stayed at 0 for 24 s; bokeh at alpha 0.02–0.09 was invisible; with no foreground layer, parallax read flat; the flash bloomed from the frame centre instead of the action point.

---

## 5. Motion recipes

### Core rules (full text in SKILL.md / client-taste.md)

- **Nothing pops.** Entries combine move + scale (0.96→1) + opacity + blur (8→0 px) on an expo-out; exits mirror on a cubic-in. Captions and CTAs take ~10 frames to enter, not 2–3. ZEVRA v3 «топорно» → v4 «хорошо, очень». [M-01]
- **No dead air:** something new every 0.5–0.6 s. A still frame is allowed only as a listed read: status 1.0 s; name + ✓ 0.6–0.7 s; three numbers 1.2 s; a list item 0.8 s; end lockup 2 s. Measure it on a render with `scripts/activity.mjs` instead of guessing. [M-05]
  - During every hold, the next trigger is already arriving. Strong music hits get a reaction on the hero: camera kick, light breath, highlight wipe, counter roll.
  - The readTime formula alone gave a cut that lingered; keep it for lines read while the camera moves.
  - SHIFT v003 → v004: dead air 4.87 → 1.53 s, longest stretch 1.20 → 0.37 s, approved («ок, жду финал»).
- **Montage of generated footage cuts fast:** ~40–50 cuts per 30 s, no single image held longer than ~1 s. Split long beats into 2–3 angles of 0.5–0.75 s. Keep must-read lines readable by holding one line over 2–4 sub-cuts, not by slowing the cuts. [M-06]
  - The PHYLLA v2 kit that won «вау» (v1 had ~22 cuts, v2 ~45): a 1.06→1.00 zoom punch on every bar downbeat; 6–10-frame flash words; an accelerating build (each cut ×0.8, down to 2 frames); a 0.5 s vacuum before the lift; 3-frame glitch slices on score stutters; white flashes only on drop, lift and final hit.
- **Pace vs speed.** Event density is high, but each move is smooth and unhurried. «чуть помедленнне» (PLAY) was about frantic motion, not about holding longer. [K-03]
- **Energy from camera and staging, not frantic speed.** Once a film is "powerful", default to the house/productive personality (`hf.enter/exit/move/camera`; headline 0.6 s, hero 0.9 s, camera 1.5 s): halve beat kicks, soften shake, lengthen zooms. Overshoot only on chips (≤6%) and props (≤10%). PLAY v2–v6 on `derive(energetic + playful)` hopped the cat on every beat; the house-easing version was approved. [M-07]
- **Active, motivated camera.** It follows what moves (card, toast, cursor, courier, route dot) or reveals the next piece of information. It stands still only on listed reads, and holds keep a gentle drift. In a generated montage, every clip carries one clear, purposeful move, varied across the set (macro push, crane, orbit, FPV, rack focus). Record the lifted handbook limits (one verb, moves ≥1 s, whip ≤1) as a passport exception. [CA-01]
- **Logical moves, eased at both ends.** No crash zoom on every shot, whip for its own sake, micro-shake, roll or jerky ramp. Fast moves are fine when they follow an object or land on a hit, always with motion blur and a soft landing. Shake ≤6 px, only on impacts. ZEVRA v2: easeInOutCubic/Quint with zero end slopes, at most one fast travel per act, direction carried across cuts. [CA-02]

### Overlap and cuts

- **Overlap motions:** [M-02]
  - the next move starts 4–8 frames before the previous one ends;
  - group members stagger by 2–3 frames;
  - details and shadows trail the hero by 2–4 frames;
  - holds keep an idle micro-drift (1.2–2.4% scale, ≤5 px) that eases to a stop over the last 6 frames;
  - helpers used: `Trans.seq(t0, durs, 6)`, `Trans.at(t0, i, 2.5)`, `Trans.lag(t, 3)`. This mirrors the teammate standard (higgsfield-motion-saas) the user shared.
- **Speed never drops to zero at a cut.** Accelerate into the cut, peak (with motion blur) on the cut frame, then decelerate. Give match cuts a short pulse-zoom (+3–5%, fastest on the cut frame). Use eases with a non-zero end slope for hand-offs, and check camera velocity at every act boundary. The ZEVRA defect scan found a zoom reversing across a cut and near-stops at 14.0, 16.3 and 27.4 s. [M-03]
  - The handbook's «Фокус через склейку» (cut on the start of a move) and this are both cut-on-action. For this user's smoothness standard, keep velocity non-zero through the cut, with the peak on the cut frame. [K-13]
- **Every cut needs a connecting device:** a shared element, a shape match, a continuous camera, or a fill growing from an object. [M-04]
  - **Morph shared elements in two layers:** the outer box morphs size, radius and position, while the inner content crossfades through a ~6 px blur.
  - **Size neighbours to morph:** equal heights or radii turn the cut into a clean stretch. The 'Sound on' pill was sized to 184 px to stretch into the prompt bar. Morph chain example: icon → plate → capsule → card → post → icon → wordmark.
  - **Background changes** only with a soft fill that grows from a button, card or line, never with a plain fade.
  - Mark such shots «не резать» in AE notes («Не резать, иначе матч-кат развалится»).

### Design for motion blur

- Cap peak speed at seams: ≤60–70 px/frame, ease-in-out over ~0.5 s. The DECODE seam went 0 → 85 → 147 px/frame in two frames, an unreadable smear. [M-08]
- Peel fanned or stacked semi-transparent cards farthest-first, in depth tiers, so they don't smear into one band (a fan of 15 cards merged across the heroine's chest). [M-08]
- An element entering mid-shutter is half-transparent for one frame. That is correct. [M-08]
- Check stills from the blurred render, not only from drafts. [M-08]

### Micro-choreography

Recipes for the moves that kept failing [M-09]:

| Move | Recipe | Failure seen |
|---|---|---|
| Main hit | anticipation (0.4 s light dip + accelerating push + rack focus) → snap on the hit frame; shake high-frequency (~11/17 Hz, tau ~0.13 s); the flash blooms from the action point (hot white core → accent), ≤1 big flash per second | shake at 2 Hz read as sway; the flash origin was computed but never written to CSS |
| Character jump | crouch → arc with stretch → squash, facing the direction of travel | the cat hopped in a frozen side pose |
| Text edit | mark the words to remove on the tap; remove them on the next hit in 0.2–0.3 s, without clipping masks; relay the surviving words with a 2-frame stagger in a non-crossing order | 'coffee' passed through 'Good' for ~10 frames |
| Mask transition | finish fading text inside a masked layer before the iris or mask starts | 'Winn / To' showed half-clipped during an iris |

### The cursor is a protagonist

- One sprite sized to read: ≈128–176 px at 1920 (the 117 px grab hand looked small). [M-10]
- It clicks with the arrow tip, never with the centre of the sprite. [M-10]
- It never covers the label it clicks (aim at the button edge; the hand covered the "2" in «Generate 12»), is never defocused, never rests on the result, and never crosses numbers being read. [M-10]
- Timing: hover 150–250 ms, press 1 → 0.96 → 1, state change 2 frames after the click. The ripple contrasts with the target (ink on lime). [M-10]
- On drags, the card lifts and follows on an arc, the target highlights, and the card shrinks into the slot. On touch devices, use a 56–72 px touch indicator. [M-10]
- It stays fully in frame on every press. [C-04]

### Named eases

Keep a small set of eases named by intent. `HF.E` gains `follow`, `snap`, `suck` and `whip`. [M-11]

| Intent | cubic-bezier |
|---|---|
| camera push / pull | (0.76, 0, 0.24, 1) |
| follow a moving object | (0.55, 0, 0.25, 1) |
| soft drift | (0.37, 0, 0.63, 1) |
| snap pull-back on a drop | (0.25, 0.1, 0, 1) |
| whip | (0.83, 0, 0.17, 1) |
| suck into a landing | (0.62, 0, 0.92, 0.42) |

- **Never tween a fill between distant hues through RGB:** magenta → lime passes through salmon and mustard (the Ad Multiplier winner bar). Crossfade two solid fills, or snap under a pop. [M-11]

### Camera in a single-camera brand film

- One dominant verb; every push ≥1.14× (smaller reads as static); moves start and land on hits; no peak camera velocity during text animation. [CA-04]
- End on a slow push toward the brand, never retreating from it. POST v1 reversed the camera's z-direction 5 times and ended pulling away from the logo. [CA-04]
- **Depth:** focus follows the action (rack to the acting element; the cursor is exempt from depth of field). "Real depth / parallax" needs a near layer made of story objects (e.g. typed notes in the foreground), not decorative fragments. POST had focus at 0 for 24 s, so the payoff "−38%" was a smear. [CA-04]
- **One→many:** fly the camera past every item. Example: a carousel of 13 window cards ~28° apart turns ~200° with ease-in/out while the camera pulls back from the hero item. Never a static ring or a plain pull-back. Keep a slow rotation (~1°/s) under the end card. The hero card sits +220 Z, scaled ~0.9, so ring cards never slice through it. [CA-03]

---

## 6. Product films (SaaS / app ads)

- **One persistent, believable app that the camera travels through.** It has: [T-03]
  - a sidebar with live counters;
  - a top bar with breadcrumb / Search ⌘K / clock / avatars;
  - real lists and states drawn from one fictional dataset.
- **Never one floating card under a centred headline per scene:** «не вгылядит как saas продукт» → the hybrid with full app chrome got «гуууд». [T-03]
- **Fidelity tiers:** draw the 1–3 controls of the beat at full fidelity. Everything else is quieter texture (≥28 px), cropped, or softened by depth. [T-03]
- **Window:** a frameless OS window, never a device mockup, with one family of radius, shadow and hairline. [T-03]
- **Screen time:** the product surface appears in ≥2 shots, and the UI demo takes 20–40% of the runtime. Genre decides density: brand/launch key frames stay restrained; productDemo shows the whole app. [T-03]
- **Framing architecture:** [C-06]
  - Author the UI at real units and make UI text big through camera scale. WIDE (×1.0–1.5, ≤1 s) is texture only; READ (×2.3–4.5) frames the 1–3 controls of the beat. SHIFT30 used ×1.85 for the overview, ×2.5 for chapter openers and ×3.3 for push-ins.
  - Fixed layer stack: static plate → world/app under one camera → lifted popovers → footage → screen-space overlays computed from world points → never-transformed chrome/lockup → grain.
  - Lay multi-surface products out in one world plane, with one shared object passing from surface to surface.
  - Crops: never cut the window chrome mid-header; keep the window edge and a strip of plate in macro shots.
- **Live footage chapters:** see §4 «Product chapters with live footage». [S-07]
- **Type system:** [TY-05]
  - one display face with a true italic, one UI grotesque with tabular figures, and mono only for clocks and IDs;
  - ≤1 italic accent word per line, and one accent device per frame;
  - levels in one frame differ ≥×2; ≤5 narrative styles; size up low-x-height serifs;
  - pairs that worked: Instrument Serif + Plus Jakarta Sans + DM Mono; Fraunces + Inter; Newsreader + Geist.
- **The wordmark is ONE imported function.** It masks up and stops, with no overshoot or blur-in. It is read 2–4 times for ≥0.5 s each, plus a held end lockup. [TY-05]
- **Glyph test frame first:** render `Aa Gg Qq 0–9 € ✓ ⌘`, italic and Cyrillic before building. [TY-05]
- **Colour and grain:** [TY-04]
  - Count the accent budget including decorative uses (bokeh, avatar letters, glow). One colour carries one meaning per film.
  - Grainy mesh gradients: 2–4 large, blurred radial blobs drifting slowly under a static, fine monochrome grain (3–7% luminance, soft-light). The grain kills banding. Keep it subtle on white (ZEVRA's was lowered 0.55 → 0.3) and never animate it.
  - Pinterest SaaS glow recipes (stacked blurred copies, light-beam trapezoids, a same-colour glow under a pill) are fine as light, never as glass objects. Reeded/fluted glass is legacy.

---

## 7. Generations / Higgsfield MCP

### Two modes

Every job runs in one of two modes [G-01]:

| Mode | When | What to do |
|---|---|---|
| **Design trial** | the user says «просто дизайн» / «пока нет, просто дизайн» | no generations; designed ✦ GENERATION placeholders |
| **Production** | the user names models or a resolution, authorises Higgsfield, or asks for assets for a film | generations are expected (steps below) |

- **Production steps:** [G-01]
  1. Check the balance.
  2. Preflight the cost: `get_cost` on one call. Seedance 2.5 at 1080p is ≈12 credits per second.
  3. Present the plan, including variants and a ~30% reshoot reserve.
  4. Generate in parallel with the motion work.
  5. QC every clip (below) and report the spend.
- **If unclear, ask once at the start.** If a brief has a photographic hero, ask whether generations are allowed instead of hand-drawing a code stand-in. Every film session after the trial used real generations, often volunteered by the user («используй seedance 2.5 1080p для изображения nano banano pro»; «подключи для генераций higgsfield mcp ты можешь»). Once the user authorised them mid-task while the assistant was redrawing an SVG sneaker by hand. [G-01]

### Anti-slop and casting

- **Never animate glossy Nano Banana Pro start frames for live action** («давай генерашки изменим, они сильно слопные»). Slop signs: golden-hour light, catalogue rooms, symmetric hero framing, smooth skin, posed grins, stock UGC grids, perfectly stacked props. [G-02]
- **Write phone-real footage instead:** real optics and imperfect framing; mixed colour temperature, clutter and noise; natural, slightly awkward acting via ACTING TASK; zero legible text. [G-02]
- **Stills are identity references, not first frames:** pass them in `image_references` with "take only appearance, never background or light". [G-02]
- **Where start frames are fine:** art-directed macro, nature or 3D shots; shots needing exact counts or hand-over compositions; and any time the user explicitly asks for a model (PHYLLA, NB Pro → Seedance i2v, was approved). [K-07]
- **Casting:** attractive, young (≈22–34), fit and well-groomed people, in fashion-editorial styling or fashionable plain athleisure (for this user, East Asian and white). This applies to every role, side characters included. [T-16]
  - Realism comes from camera, light and skin texture, never from unglamorous or older casting.
  - Where age was the joke, adapt the role (dad → boyfriend).
  - Use documentary realism only when the user asks for it.
  - Evidence: «давай бабушек заменим на красивыз девушкек, фэшн стилЬ, азиатки, милые и красотки, через soul 2 сначала» (PHYLLA); «да, перегенерь их моложе и красивее некоторых» (Ad Multiplier).
- **Casting procedure:** generate each identity in Soul 2 first, then animate in Seedance. Show 2 variants per hero. Prompt "no text, logos or prints on garments", then QC the cast sheet: text slipped onto 2–3 shirts. [T-16]

### Seedance prompt format

Write every Seedance prompt in the user's seedance-scene-director v2 format. The user attached `~/Downloads/seedance-scene-director-test-run-v2_1.md` in three sessions («вот скил для генерации норм видосов»). Use the installed scene skills (`seedance-scene-director`, `scene-card`). [G-03]

```
REFERENCE DEFINITIONS
SCENE
CHARACTERS
WORLD
ACTING TASK (MOTIVE – GOAL – OBSTACLE – TACTIC)
SHOTS (timecoded)
CAMERA AND LOOK
AUDIO
CONSTRAINTS
```

- Each take is one continuous shot with one motivated camera move: start → path → arrival → purpose. [G-03]
- Exception: a multi-shot story generated in one call, to keep cast and world consistent. [G-03]
- Open mid-motion, with the money moment 1–3 s into the take. [G-03]
- The camera direction continues the neighbouring UI transition. Static generated clips look like stock footage. [G-03]

### Model parameters that worked

Verified on the live MCP in ZEVRA, SHIFT, PHYLLA and Ad Multiplier [G-04]:

| Model | Parameters |
|---|---|
| Soul 2 | `soul_2`, quality `2k`, 16:9 / 3:4 / 9:16. Generate people's identity here first. |
| Nano Banana | `nano_banana_pro` or `nano_banana_2_1`, resolution `4k` (default 1k); `thinking_level` high for complex stills |
| Seedance | `seedance_2_5`, mode `omni_reference`; `start_image` = a finished image job_id, passed directly; cast in `image_references`; resolution `1080p` (default 720p); `bitrate_mode` high; `generate_audio` false (default true); integer duration 4–30 s; count 2 for variants. Output is 24 fps HEVC. |
| Batching | ≤12 per batch; poll `jobs_wait` (≤12 ids, ≤15 s long-poll); `generate_image_batch` count is fixed at 1 |
| Timing | images 30–60 s; a 5 s Seedance clip at 1080p ≈3–6 min |

- Re-check schemas with `models_explore` once per project. [G-04]
- In SHIFT, identity stayed consistent when the key frame was generated with the cast stills as references and the same stills were passed again to Seedance. [G-04]

### MCP gotchas

- **Preset interception.** `generate_video` may return a preset recommendation instead of a job ('IN THE DARK', '3D RENDER', 'EXIT THE DREAM'). It costs nothing. Hit rate: 3 of 6 requests in ZEVRA, 6 of 7 in SHIFT. [G-05]
  1. Show the user the preset preview if it might be relevant.
  2. Resubmit only the failed indices with `declined_preset_id`.
  3. Keep passing `declined_preset_id` on later requests.
- **Presets are not consent.** Never execute a preset just because it was browsed. Check every item's status in a batch result. [G-05]
- **Other gotchas:** [G-06]

| Problem | Fix |
|---|---|
| `remove_background` fails on 4K sources | downscale to ≤2048–2752 px first: `sips -Z 2048` → `media_upload` → PUT with both signed headers → `media_confirm` type image |
| video background removal eats dark hair | use a green-screen plate instead (live hero cut-out below) |
| false NSFW (a pink round "cell" was flagged twice) | change its colour or shape |
| visible studio lamps | prompt "seamless void, light source off-frame" |
| `nano_banana_pro` jobs are reported as `nano_banana_2` | a label quirk, not a wrong model |
| `nano_banana_2_1` and `seedance_2_5` ignore reference-element placeholders | pass identity stills as `image_references`. Models that honour reference elements: nano_banana_pro, nano_banana_2, gpt_image_2, seedream, cinematic_studio, seedance_2_0, kling3_0 |
| `video_analysis` jobs can stay queued for 40+ min | plan around the wait |
| the tools can't read chat attachments | call `media_upload_widget` as the only tool in that turn |
| a media id is not what you think (a "clean product still" id was a man's portrait) | view an id before using it as a reference |
| slow CDN | retry downloads in the background, and keep a job-id ledger on disk |

- **Higgsfield-only mode** (sandbox / Higgsedit, no local machine): [G-17]
  - foreground `sandbox_exec` runs ≤120 s; use background jobs (15-min lease) and poll;
  - the sandbox is discarded ~10 s after a call, so re-download inputs and upload outputs on every call;
  - `image_paths` (≤4 images, ≤512 KiB) is the only way to see frames;
  - `media_confirm` needs a type;
  - Higgsedit camera keys are in absolute seconds, and every top-level node needs z;
  - motion blur is capped at 16 samples; audio is spine-only (mix elsewhere); `p.cut` has no rate option.

### Prompting for accuracy

- **Product accuracy:** pass a clean product still as a second reference next to the identity portrait: `@Image2` "the product only: shape and colours; ignore its background". With text alone, the model swaps in a generic variant: a walking pad kept coming out as a treadmill with handrails and a console. A crop from a good clip frame with stickers painted out fixed it, and GRID_07–09 passed on the first take. [G-07]
- **No legible text, UI or logos from the model:** [G-08]
  - end every prompt with "No text, no letters, no logos";
  - give props "no printing";
  - ban logo-prone items, or drop them after repeated failures (shoes → white socks, no laptop);
  - turn device screens away, or make them a uniform blank emissive surface with all corners visible, then composite the designed UI in post;
  - state the cut count: "Count of cuts: zero";
  - the client's own logo never goes into footage;
  - blanked-out logos read as AI patches: paint them out or reroll;
  - seen: Nike swooshes on 3 takes, an Apple logo on a laptop lid, hidden jump cuts, two white rectangles on the heroine's chest found in final QA.
- **Counts:** video models "complete" whatever a moving camera newly reveals, and copy everything visible in a reference. When a count matters: [G-09]
  - make the geometry unable to hold more (a narrow single-row container);
  - show the count in a reference;
  - state it in CONSTRAINTS ("exactly four… never a second row");
  - generate 2 variants and count the objects on every take's contact sheet;
  - pass only the references a shot needs, and crop unwanted props out of them;
  - seen: a wide container with 4 buns gained a second row as the camera rose («камера «досочиняла» второй ряд булочек»); a "seated guests" still with a podium planted an extra lectern.
- **Cast and world bible:** [G-11]
  - one verbatim wording per person, prop and place, pasted into every prompt (near-synonyms read as redesigns: "mint-green" vs "sage-green" tiles);
  - generate in order: empty world plate → hero product → cast in the world;
  - reuse people across roles.
- **Start frames composed for the edit:** [G-11]
  - frame at the camera move's start position, with the action already under way;
  - reserve a calm type zone sized for the largest type (≥40% of frame height for a display word), with faces kept out of it for the whole move;
  - place hand-over objects at the coordinates the trigger map needs;
  - 9:16 gets its own prompt.

### QC every take before it enters the edit

- Decode at native 24 fps (`scripts/extract.swift`). Make a 0.5 s contact sheet, plus fine sheets ±0.5 s around key moments. [G-10]
- Judge at the size the take will be seen (e.g. 360×640 for a grid tile), with an independent, skeptical agent. [G-10]

| Verdict | When |
|---|---|
| **Fail** | wrong or missing product; recognisable logo or text; gross physics or anatomy errors; identity drift; hidden cuts (consecutive-frame diff spikes, e.g. 8.85 vs a ~3 baseline); too dark; a duplicate |
| **Pass, log it** | soft defects visible only at 1080p zoom |
| **Keep, use a window** | the defect falls outside the window you need |
| **Reshoot** (≤1–2 tries, one fix at a time) | the take contradicts a UI fact, breaks identity at a hero moment, fails the camera move, or shows text |

- Check small accent colours for drift: Soul 2 turned acid lime yellow and mint. [G-10]
- Record usable windows and key moments in a clip manifest. In the Ad Multiplier grid round, 10 of 12 tiles were accepted; hard props took up to 11 takes. [G-10]
- **One→many beats need distinct items.** Every visible item is a different variant: different genre, technique and palette, never tinted into the brand colour. A grid needs ~20+ distinct clips with no repeats among neighbours, diagonals included. In a montage, every full-screen beat gets its own shot. A photo ↔ dot-matrix twin of the same shot also reads as a repeat. Check clip ids per cut yourself before sending («там есть повторябщийся элементы их тоже гоу заменим, прооверь сам»). [T-19]

### Using footage in the edit

- **Frame rates:** [G-12]
  - Never retime a clip to a fractional speed like 0.75×: every 4th frame duplicates and judders. Keep 1× and choose the window instead.
  - In a 30 fps film with 24 fps Seedance clips, play at exactly 1.25× (one source frame per film frame), but only where speed reads as energy: camera-led moves, objects, hands under 1 s. Plan in-points knowing the action plays 25% faster: `in = s_key − (t_event − t0) × 1.25`.
  - Faces and walks over 1 s play at 1.0 with a neighbour-frame crossfade.
  - Default to 24 fps (it matches Seedance). A mostly-footage film is delivered at 24 fps @ 120 BPM, and a supplied track's tempo replaces the 120 BPM grid. Ask whether a brief's 30 fps is firm. [K-14]
- **In-points by what is seen and heard at the key beat:** [G-15]
  - the face is toward camera when the headline lands (a heroine glanced aside exactly on «Scale what wins»);
  - audio starts in a pause, not mid-word;
  - the clip is long enough never to loop or wrap on screen; hold the last frame (a winner clip wrapped mid-scene and its progress bar snapped from 100 to 0);
  - skip black openings and avoid grimaces;
  - the clip's micro-story matches the beats.
- **The user's own generations:** use all of them, and put theirs at the hero moments: the full-bleed reveal after Generate, and the post/CTA. A mix of diverse genres sells "any idea". In ZEVRA, the user's SUV clip replaced Claude's at the 12 s reveal («заменим на другую генерацию которую я скидывал»). [G-13]
- **Seedance editing tricks:** [G-16]
  - treat a 5 s clip as raw material: 0.5–1.2 s per cut at 1.5–3× speed, feeding 2–3 cuts from different seconds;
  - play clips reversed for wraps and pull-backs (generate the uncoil from a frame that already shows the wrap);
  - pushes into a pupil or tunnel that end on black make free cuts;
  - keep happy accidents (in PHYLLA, a breath plume grew into a glowing tree and became a hero shot);
  - design one take to serve ≥2 edit windows, to cut cost.

### Live hero cut-out

When a person is the hero of a code-rendered piece (title, cover, orbit), they must be a live generated video cut-out, not a static photo cut-out: «и где девушка я думал будет живая генерация ее типа». [T-17]

Technique [G-14]:

1. Make an identity still (NB Pro or Soul 2).
2. Generate a Seedance 2.5 `omni_reference` plate: 9:16, 1080p, 6 s, `generate_audio` false. Flat, evenly lit `#00B140` seamless green; rim light; locked tripod; full body with margin; no props or text; "no green spill".
3. Chroma-key it yourself into an RGBA PNG sequence, with a manifest (union bbox, loopIn / loopOut).
4. Fit it to the still's subject box and play it as `<img>` frames, with different in-points per segment.

- Don't script glances into a plate meant for graphics: a scripted "glance to the side" landed exactly on the «Scale what wins» headline. [G-14]

---

## 8. Sound

- **Every film ships with sound:** a music bed plus designed SFX, plus in-card dialogue where it carries the story. Review MP4s go out with music. onbeat, a techno sync film, was delivered silent because the skill had no audio step. Evidence: «гибрид, собирай и звук с звуковыми эффектами нужен»; «покажи mp4 с музыкой». [SN-01]

### A supplied track

1. **Analyse it:** `afconvert -f WAVE -d LEI16 -c 1 track.mp3 mono.wav` → RMS / flux onsets, BPM, drops, breaks, best windows (`scripts/music_window.py`). [SN-02]
2. **Read «лучший момент 30 сек с 01:00»** as: search windows that start after 60 s. [SN-02]
3. **Propose the fragment as a table,** with one alternative. The user answered «ок, оставь первый, гоу дальше». [SN-02]

| Track time | What the music does | What happens in the film |
|---|---|---|
| e.g. 1:04.2 | drop | Generate; words fly into the result |

4. **Snap scenario times to the real hits,** with the main action on the drop. The track's tempo replaces the 120 BPM house grid. POST snapped its 4/9/17/24 s marks to 4.28/8.99/17.5/24.24. [SN-02]
5. **Cut it** to the film's exact length with a 0.25–1 s fade at a hard out: `python3 scripts/cut_audio.py track.mp3 1:06.4 30 audio/score.wav --fade 0.5`. [SN-02]
6. **Verify on the final muxed audio at every picture hit** (RMS in 12.5 ms windows). Energy-based detection can be beats off: the analyser put the PLAY drop 2 beats late. Fix by shifting the music start, not the picture. [SN-02]

### No track: synthesise one

- **Higgsfield has no general music or SFX generator:** `sonilo_music` and `mirelo_text_to_audio` are "Game pipeline only", and the rest are speech models. [SN-03]
- **Default:** synthesise an original score and SFX in code, locked to the film's events and BPM: `scripts/render_audio.mjs` renders `assets/templates/audio/score.html` (WebAudio OfflineAudioContext in the headless browser); pure Node WAV also works. [SN-03]
- **«В стиле <film/artist>»:** describe only the sound vocabulary, never the title. Approved code scores: an Arrival-style score («может музыку сделаем non ip в стиле the arrival…» → v2 «отлично», v3 «вау») and a French-house bed with Rhodes keys («клавиши по типу daft punk звук»). [SN-03]
- **Alternative bed:** a Seedance t2v clip with a SOUNDTRACK prompt, audio only, lengthened with `video_extension`. Keep it phase-locked to the beat grid, and land its final hit on the end wordmark. One extension slipped by an eighth note, and the TITLE hit fell in a gap. [SN-03]
- **Fallback:** offer a licensed track. [SN-03]

### «Музыка подинамичнее» = contrast and drive, not loudness

- Climax-level energy (choir, percussion, sound design on every transition) from the first drop, with only a short planned vacuum before the lift. [SN-04]
- Atmospheric texture locked to tempo: calls every bar, 16th-note ostinati, tape-stops at phrase ends, shimmers on downbeats. [SN-04]
- Pickup fills and risers into transitions, and a groove change per chapter. [SN-04]
- A recurring 4–6-note motif, sidechain pump, and a build that climbs into the drop. [SN-04]
- Stutters in the score are mirrored by glitch slices in the picture. [SN-04]
- A thinning breakdown made the first build the quietest part of the film. Turning things up was never the fix. Evidence: «давай как с 20 секунды везде добавим мощную динамику и хора и всяких звуков чтобы не скучно было слушать»; «давай еще к музыке добавим типа звуков какиех как arrival но к темпу». [SN-04]

### One events file, SFX design, mix

- **Drive picture and sound from ONE events file** (times as frame numbers, kind, weight, note). Picture times derive from it, and the score and SFX render from it, so a retime stays in sync. [SN-05]
  - Felt hits sit on beat frames; whips land on the beat; a status lands 2 frames after its click.
  - Schedule SFX with lookahead and lead visual landings by ~0.08 s.
  - Take clip-audio start times from the scene code, never from a hand-kept default (a 0.25 s desync, MAYA_START 0.75 vs DEFAULT 1.0, was caught before render).
  - At 30 fps / 120 BPM, one beat = 15 frames.
- **SFX design:** [SN-06]
  - one tuned sound family, in the key of the bed;
  - placed after the voices (UI one-shots go in speech gaps);
  - colour maps to timbre (accent = bright glass pops, secondary = soft ticks);
  - peaks land on the fastest moment of the motion curve;
  - repeated actions reuse the same sound;
  - the segment's main visual hit is its loudest moment;
  - Ad Multiplier used 109 procedural cues (click, pop, whoosh, riser, impact, ding, slap, tick).
- **Whooshes follow the camera.** With an active camera, whooshes on camera throws are welcome (SHIFT v003: whooshes on every throw, impacts on triggers → «гуууд»). They follow the picture's direction and don't stack. "Whoosh ≤1 per film" is for calm, single-camera brand films. [SN-06] [K-12]
- **Mix dialogue first, and measure:** [SN-07]
  - master −14 LUFS integrated, true peak ≤−1 dBTP (ship at −1.2 / −1.3 for AAC), 0 clipped samples (`scripts/master.swift`);
  - the story voice is the loudest voice; in-card UGC audio sits below it;
  - music ducks ~10 dB under payoff lines;
  - key accents stand out by carving and multiband ducking: ≥+8 dB only in their principal band (+23 dB broadband was too loud);
  - loudness rises through the build; stems sum to the mix;
  - the Ad Multiplier v3.1 master sat at −21 LUFS with the payoff line only +2.7 dB over the music; the QA lens called it "not client-ready".
- **You cannot hear audio. Say so plainly:** [SN-08]
  - verify by numbers: per-section loudness, envelope, sync;
  - send each new score version on its own right away («и мне скинешь трек сразу для чека»), with a one-line structure caption: «вдох 0–2 → удар 0:02 → … → финальный удар 0:28»;
  - name the timestamps to listen to and the known risks;
  - offer a library or licensed track as a fallback.

---

## 9. Rendering

### Tools

Run `bash scripts/setup.sh` once per machine. It checks Node ≥22, the browser, `swiftc` and `afconvert`, and compiles the Swift tools into `${HFT_BIN:-~/.cache/higgsfield-motion/bin}` when they are missing, stale or the wrong arch, clearing quarantine (`xattr -dr com.apple.quarantine`). Each script's usage is in its header comment. [R-13]

| Job | Tool | Notes |
|---|---|---|
| Browser launch | `scripts/cdp.mjs` | shared by capture / render / strip; collision-free, cleans up [R-05] |
| Stills | `node scripts/render.mjs <out_dir> a.html b.html …` | HTML → PNG, same browser flags as capture (WebGL, file access); `--size`, `--serve`, `--strict`. A page that is only correct at a time t (exposes `__seek`) goes through `capture.mjs --stills t` |
| Frames | `node scripts/capture.mjs <page> <out_dir>` | `--workers N`, `--mb N --shutter 0.5`, `--draft`, `--size WxH`, `--serve`, `--clean`, `--lenient`, `--check-determinism`, `--stills t1,t2,…`. Exit 3 = page errors, 4 = frames still missing, 5 = seek-order test failed [R-07] |
| Contact strip | `node scripts/strip.mjs <stills_dir> <out.png> [title] [cols] [--fps N] [--step N]` | reads `still_*` and `f_<n>` names; `--fps` defaults to `_comp.json` |
| Encode (silent) | `encode <frames_dir> <fps> <out.mp4> [mbps=24]` | fails on bad frames, gaps and a count mismatch with `_comp.json` [R-07] |
| Encode frames + audio | `encode_av <frames_dir> <fps> <audio\|-> <out.mp4> [mbps=24]` | one pass, H.264 High BT.709 + AAC-LC 256 kbps, audio trimmed to the picture [R-02] |
| Mux | `mux <video.mp4> <audio> <out.mp4> [--offset s]` | passthrough video; non-AAC audio converted with afconvert; fix a late beat with `--offset`, never the picture [R-02] [SN-02] |
| Footage → frames | `extract <clip.mp4> <out_dir> [fps=native] [maxW=1920]` | `f_0000.jpg …` at native fps + `_clip.json` with the real frame count [R-09] |
| Check the deliverable | `probe <video.mp4> [out_dir [t… \| auto]] [--fps N] [--dur S] [--audio]` | duration, fps, CFR check, codec, colour tags, audio, check frames from the MP4 [R-10] |
| Master the mix | `master <in> [out.wav\|out.m4a] [--lufs -14] [--tp -1.2] [--sections a-b,…]` | BS.1770-4; no `out` = measure only [SN-07] |
| Cut a track | `python3 scripts/cut_audio.py <track> <start> <length> <out.m4a\|out.wav> [--fade 0.25]` | start in s or m:ss; length = frames / fps [SN-02] |
| Music | `music_window.py`, `render_audio.mjs` + `assets/templates/audio/score.html` | see §8 |
| QA | `fdiff.swift`, `activity.mjs`, `textcheck.mjs` | see §10 |
| Footage in a page | `assets/templates/shared/clips.js` | clamps, holds, LRU [R-09] |

### The two render paths

Drafts stay fast; only masters pay for motion blur [R-01] [D-01]:

| | Draft / interim | Master |
|---|---|---|
| Capture | `capture.mjs --draft` (JPEG q95, 4 workers, never blur) | `capture.mjs --mb 8 --shutter 0.5 --workers N --clean` |
| Motion blur | none | 180° shutter, adaptive sub-frames |
| Encode | `encode_av` at 20 Mbps, or `encode` + `mux` | `encode_av` at 20–30 Mbps (default 24) |
| Time | a 720-frame render ≈1–5 min | ≈20 s per second of film at N=8; 25–30 min for a 47 s film at 48 on fast scenes |
| Before sending | frame count, `fdiff`, stills around cuts | the same + `probe` on the encoded file + `avconvert` share copy |

```sh
BIN="${HFT_BIN:-$HOME/.cache/higgsfield-motion/bin}"     # after: bash scripts/setup.sh
# interim: fast, no blur, music muxed
node scripts/capture.mjs film/index.html out/draft --draft --clean
"$BIN/encode_av" out/draft 24 audio/score.wav out/film_v003_DRAFT.mp4 20
# master: 180° motion blur, mastered mix, probed
node scripts/capture.mjs film/index.html out/master --mb 8 --shutter 0.5 --workers 4 --clean
"$BIN/master" audio/mix.wav audio/mix_master.wav --lufs -14 --tp -1.2
"$BIN/encode_av" out/master 24 audio/mix_master.wav out/film_v003.mp4 24
"$BIN/probe" out/film_v003.mp4 out/check_v003 auto --fps 24 --dur 30 --audio
avconvert --preset Preset1920x1080 --source out/film_v003.mp4 --output out/film_v003_share.mp4
```

### Motion blur (masters only)

- Render masters with real motion blur by default: a 180° shutter by sub-frame accumulation (`--mb N --shutter 0.5`). [R-01]
  - Sample at `ts_k = n/fps + (k/N)·0.5/fps` and average in linear light.
  - N is adaptive: start at 8 and refine while neighbouring sub-frames differ (`--mb-max 32` and `--mb-diff 2.0` by default; raise `--mb-max` to 48 for very fast moves). Static frames render once.
  - Footage and live plates hold one source frame across all sub-frames (`window.__mbBase` / `__mbDT`, frame-aligned in-points).
  - Never fake blur with CSS on moving items. Drafts and interims render without blur.
- **Why adaptive:** 8 sub-frames left ladders on chips moving 170 px/frame («PRCCPDDSSOOF»), and 24 still combed at ~600 px/frame. The handbook marks 180° blur [обязательно]; three sessions rebuilt it because capture.mjs couldn't do it. [R-01]

### Page contract (`__seek`) beyond "no clocks"

- `__seek` is continuous in fractional t: valid at sub-frame offsets, clamped to `duration − 1e-4`. [R-08]
- No NaN, undefined or Infinity in styles (a missing `T.key` gave `opacity:NaN`). [R-08]
- Dependencies are computed in order within the frame: never read another object's pose from the previous frame (the card match-move read `phone.p` before `setP`). [R-08]
- Eased states instead of `t >= x` switches. [R-08]
- Footage and live plates are drawn as `<img>`, not canvas. [R-08]
- **Checks:** [R-08]
  - a Node-side evaluator over every frame and sub-frame;
  - `capture.mjs --check-determinism`: forward, reverse and shuffled stills compared by pixel diff with a visibility threshold (hashes always differ because of raster noise). A 1-px title column depended on seek order (`overflow:hidden` + `translateY`);
  - probe that every computed effect parameter reaches the DOM (a flash origin was computed but never written).

### Fonts, images, file access

- **Page code that measures text** (getBBox, measureText, width-based layout): wait for window `load`, then `document.fonts.load(face, sampleText)` for every face, then `fonts.ready`, and only then build. Fallback-font metrics put the onbeat cursor on the "t". [R-03]
- **Capture:** preload every FontFace at start. After each `__seek`, await `fonts.ready` and `decode()` of pending `<img>`, then two rAFs. Pages may expose `window.__ready`; capture and render wait for it. [R-03]
- **file:// taints canvases** and blocks WebGL textures made from local images or frame sequences (getImageData SecurityError in ZEVRA, SHIFT and PHYLLA). Capture/render launch with `--allow-file-access-from-files`; for ES modules, masks and pixel readback, serve the folder over 127.0.0.1 with a zero-dependency server. [R-04]
- **Playable HTML players with music:** python `http.server` ignores Range, so seeks snap to 0. Load the audio via fetch → Blob URL, make the wall clock the master and drift-correct the audio, ignore AbortError from `play()`, and handle NotAllowedError with a click gate. [R-04]

### Browser, parallelism, failure

- **Collision-free launch** (`cdp.mjs`): `--remote-debugging-port=0`, parse "DevTools listening on" from stderr, an `mkdtemp` profile, and kill the browser + remove the profile on exit, SIGINT, SIGTERM or a throw. The old random port + `/tmp/brave-cap-PORT` never deleted profiles: 898 dirs (7.7 GB) were left on this Mac; `rm -rf /tmp/brave-cap-* /tmp/brave-render-*` frees them. [R-05]
- **Capture in parallel and verify completeness:** [R-06]
  - `--workers N` (tabs over frame slices). A 30 s film takes 40–405 s in one tab and ~32 s with 4 workers.
  - Afterwards, list missing indices, re-capture the missing runs (≤3 passes), and fail if any remain. `_comp.json` is written for the encoder.
  - Render finals into your own freshly cleaned folder. Never encode from a folder another agent may be writing: one interim was encoded from 483 of 900 frames.
  - Before encoding, check frame count = duration × fps.
- **Fail loudly:** [R-07]
  - capture collects page exceptions, console errors, failed requests and HTTP ≥400, reports which t threw, and exits non-zero (`--lenient` overrides);
  - `hf-motion.js` throws when an explicitly requested style does not resolve, instead of falling back to 'higgsfield' (a zsh word-splitting bug passed three styles as one; 96 frames rendered in the wrong style and the run exited 0);
  - `encode.swift` fails on unreadable frames, append failures and index gaps instead of silently holding frames.

### Footage in a `__seek` page

- Generated footage enters as image sequences extracted at native fps (`extract.swift`). Headless Chromium has no H.264, and `<video>` seeking is not frame-deterministic. [R-09]
- `clips.js`: clamp the frame index to [0, n−1] and hold the last frame, never loop; read the real frame count from extract's `_clip.json` (a 5 s clip had 120 frames, and requesting `f_0120` threw in `__seek` and killed the worker); cover-crop around the subject; fallback chain clip → still → ✦ GENERATION plate; keep an LRU of decoded images. [R-09]
- Headless decoding is not fully deterministic either (frames 285/286 sometimes rendered paler): re-check frames around reveals after every render. [R-09]

### Constant-frame-rate masters

- Frame-align every clip's in/out point to 1/fps before composing. Unaligned AVMutableComposition points produced 24.023 fps, 1125 frames and one 8 ms frame at a seam. [R-10]
- Probe the ENCODED file (duration, fps, codec, audio track) and pull check frames from it before sending (`probe.swift`). [R-10]
- Set BT.709 colour tags. [R-10]
- `encode_av.swift` feeds each AVAssetWriterInput from its own `requestMediaDataWhenReady` queue, joined by a DispatchGroup; manual interleaving deadlocked («Энкодер завис (2 с CPU, 33 КБ на выходе)»). An MP4 passthrough cannot carry PCM, so `mux` converts non-AAC audio first (`afconvert -f m4af -d aac -b 256000 in.wav out.m4a`). Verify channel count and duration with `probe --audio` or `mdls`. [R-02]

### Chromium / CSS / WebGL pitfalls

- Never put opacity <1, filter, mask, clip-path or blend on an ancestor of a `backdrop-filter` element. [R-11]
- Hide with `display:none`. `visibility:hidden` with an SVG filter still punched a rectangle, and a child with `visibility:visible` overrides a hidden parent. [R-11]
- Build glows from layered gradients and box-shadows; `mix-blend-mode` leaves unpainted tiles. [R-11]
- No `will-change: transform` on camera-scaled layers: it rasterises at the initial scale, so push-ins go blurry. [R-11]
- Never override a layered border-box gradient ring with a `background` shorthand. [R-11]
- Uniquify ids of SVGs inlined several times. ImageBitmap uploads ignore `UNPACK_FLIP_Y_WEBGL`. [R-11]
- **Performance:** bake static oklab mesh plates (300 → 30 ms per frame); no CSS blur on already-soft discs; no `backdrop-filter` over moving 3D; animate transforms, not height or left; cache DOM writes. [R-11]

### Code-camera math

- Interpolate a big zoom in log space, and derive the camera position from the anchor's screen offset. A linear world lerp whipped the match-cut anchor ~500 px in 2 frames. [R-12]
- CSS-3D roll or shake needs a rotation-aware minimum scale and clamp: `sMin = max((960·cos r + 540·sin r + m)/halfW, (960·sin r + 540·cos r + m)/halfH)`. A 3° dutch roll leaked the ground colour 809 px along the top edge. [R-12]
- Push hero cards forward in Z so ring cards never intersect them. [R-12]
- Add velocity-proportional directional blur only during whips. Give combined camera + object moves one ease. [R-12]

### Film code architecture

- One events/timeline file drives both picture and sound. [R-14]
- One copy file holds every on-screen string (the editable-text deliverable). [R-14]
- One module per scene (`scene(t, fmt)`), or segment pages via `?seg=` rendered separately. [R-14]
- A shared read-only kit (runtime, camera, palette, eases); builders edit only their own act files. [R-14]
- Snapshot the source before each pass (`film_snapshots/vNNN`). [R-14]
- A playable HTML player still exposes `window.__comp` / `__seek` and keeps `?clean=1` and `?t=`. [R-14]
- Code-drawn art follows a contract: factory `createX()` → `{el, set(state)}`, anchors, no `<text>`, seeded PRNG, prefixed ids, a size budget. The renderer runs on stubs with the same API, so the art never blocks frames. [R-14]

### Environment (the user's Mac)

- No ffmpeg; Playwright's ffmpeg is VP8-only. Brave is the only Chromium browser. Node v22: the scripts need Node 22+ for global WebSocket. Python 3.14 without numpy, scipy or PIL. `swiftc`, `afconvert` and `avconvert` are available; there is no `timeout` command. [R-13]
- Stay on Swift/AVFoundation, stdlib Python and zero-dependency Node. [R-13]
- **zsh traps:** an unquoted `$var` does not word-split; `echo ====` fails; an unmatched glob aborts. Quote workspace paths: they contain spaces. [R-13]
- Prebuilt arm64 unsigned binaries can be quarantined on colleagues' Macs, so compile from source on first use (`setup.sh` does it). [R-13]

---

## 10. Review and QA checklist

### Before every send (fast, always)

- [ ] Frame count = duration × fps; the folder was not being written by another agent. [R-06]
- [ ] `fdiff.swift` on the encoded MP4: spikes vs the local median, freezes ≥6 frames. [Q-01]
- [ ] Stills every 2 frames, ±0.5 s around every cut, plus event sheets around triggers. Read them. [Q-01]
- [ ] `activity.mjs`: no dead air over 0.5–0.6 s outside listed reads (largest 12×12-block mean |Δluma| < 8/255 for ≥0.2 s on a 384 px grey downsample; a global mean misses a small cursor moving over a still UI). [M-05]
- [ ] `textcheck.mjs`: effective text size and worst-pixel contrast (below). [TY-01]
- [ ] Music muxed and checked at the picture hits. [SN-01] [SN-02]
- [ ] `probe.swift` on the encoded file. [R-10]
- [ ] Your own list of what is still wrong, with timecodes. [P-02]

A motion critic must measure per-frame geometry: whole-frame luma said "clean" while 18 local defects existed. ZEVRA v4.2 went out before the critics finished, and the user found the defects. [Q-01]

### When the user says «там есть пару дефектов»

Scan at once and send a ranked list (serious / medium / minor, with timecodes), then ask which seconds they saw. User screenshots often show the player timecode (0:12 / 0:30): map it to the frame. «там есть пару дефектов, нужно чекнуть» → 18 defects → «гоу, правь всё и скинь с музыкой». [Q-01]

### Motion defects (every cut and morph)

- [ ] one-frame swaps; objects slamming into frame edges and stopping dead [Q-02]
- [ ] frames or shadows vanishing mid-morph; flashes of the wrong clip [Q-02]
- [ ] zoom direction reversing across a cut; near-zero velocity at cuts [Q-02]
- [ ] captions entering in 2–3 frames [Q-02]
- [ ] lingering exit fragments: giant blurred glyphs, stray pills, doubled or broken lines [Q-02]
- [ ] double text during hand-offs; murky crossfades and grey "dirty" frames [Q-02]
- [ ] empty capsule or card frames; taglines fully visible for <1.0 s; two prompt lines at once [Q-02]
- [ ] code after `//` so an animation never draws; cards crossing paths [Q-02]
- [ ] double exposures under motion blur from discontinuous terms: a camera-follow jump, a caret box average, re-centring captions, two counter digits at once [Q-02]

### Type and free zones

- [ ] **Every text block owns a free zone for its whole lifetime** (title, caption, chapter badge, end-card line, held line). Check moving trajectories against text boxes, not only rest frames. [C-03]
  - hero objects, tiles, cards and video never pass under or over type;
  - a headline reaches opacity 0 before busy footage arrives under it;
  - a line held across sub-cuts clears eyes, faces, hands and the hero in EVERY shot beneath it («поправь you на глазе»);
  - the caption band (~y 840–1000 in 16:9) stays reserved while a caption shows.
- [ ] Over light surfaces, use a solid caption pill: a translucent backdrop pill dropped words to ~1.6:1. [C-03]
- [ ] In generated clips, sample frames to measure the subject's drift before placing overlays (head x ≈ 1380 → 1610). [C-03]
- [ ] **Legibility for a 16:9 film watched in a phone feed (×~0.2):** meaningful text ≥64 px mixed case or ≥48 px caps; labels ≥28 px; nothing <20 px; chips that carry the beat 36–40 px+. Effective size = CSS size × every ancestor and camera scale (a pull-back shrank in-app text below 20 px). HOOK / PROOF / STORY chips at 26 px were ~5 px on a phone. [TY-01]
- [ ] **Contrast at the worst pixel under the glyphs,** WCAG and APCA: <4.5:1 or Lc <60 is flagged. Hook words measured 2.75:1 over footage. [TY-01]
- [ ] **Pixel-check title lockups:** word-reveal masks don't clip descenders (pad the masks; PLAY's p/y/g were clipped by `overflow:hidden`); the logo tile aligns to the cap-height centre with a real gap (~40 px; it sat 39 px low with a 0 px gap); inputs and prompt bars are opaque. [TY-02]
- [ ] **Zoom-check sticker and pill glyphs at 1:1.** Cap-trimmed, tight Space Grotesk caps rendered «AĐ» and «YOUR A D»; the fix was the kern before D, 0.06 → 0.015 em, in the shared builder. [TY-02]
- [ ] Never break an offer or number–unit pair across lines ("20%" / "off"); no one-word widows; one sentence per line in big text posts. [TY-03]
- [ ] Motif bars under ~24 px wide use a solid accent fill (gradients turn to mush: «на таком размере градиент превращается в грязь»), with glow ~6 px at 35%. [TY-03]
- [ ] A logo mark built from bars is heavier and taller than the wordmark's stems, or it reads as letters («IIII»). [TY-03]
- [ ] Loosen display tracking (~−3.5%) when glyphs fuse; outline text ~−1%. [TY-03]

### Faces, crops, planes

- [ ] No flying element, cursor, orbit card or tile crosses a subject's face (an orbit card flew across the heroine's face at 0.5 s). Back-ring cards draw behind the subject. [C-04]
- [ ] A hero cut-out over the title crosses only with the hair crown, never over letters needed to read the word (the title read «Ads S udio»). [C-04]
- [ ] The cursor stays fully in frame on every press. [C-04]
- [ ] Every crop is deliberate: an object sits fully inside title-safe or is decisively cut (e.g. phone bottom ≤870 or ≥1150, never 900–1000; one was cut at 930–945). Never slice a word mid-glyph. [C-05]
- [ ] Overlays never cover the brand mark (a toast covered the in-phone logo). [C-05]
- [ ] Plan z so flying elements never pass through another plane (a wordmark flew through the phone plane). [C-05]
- [ ] Fill or shrink UI mocks so no large void or blank skeleton box remains (a mini card was 45% empty white). [C-05]
- [ ] Each effect named in the brief reads on screen, with a timecoded proof still (§4). [S-11]

### Content hygiene

- [ ] Strip content carried over from reference files: real employee photos and names (an employee's real photo sat next to AI portraits, and the name 'Adlet' carried into the voice-clone card), leftover placeholder text («Имя»), competitor brand names inside your product's UI («ElevenLabs»), duplicate IDs. [Q-07]
- [ ] Kill ideas a viewer would not instantly understand. After a rejection, grep the templates and kits for the motif so it never comes back: the rejected empty glass capsule returned as the hero of the neutral styleboard and motion-demo templates, and for ~4 frames in ZEVRA. [T-07]
- [ ] One→many items are all distinct; clip ids checked per cut. [T-19]

### Final pixel-polish pass (before calling it final)

«нужно дополишить по дизайну очень очень хорошо и аккуратно»: [Q-06]
- [ ] captions centred on the axis; equal edge insets for HUD; badges and captions in safe zones;
- [ ] no clipped glyphs or overlaps;
- [ ] consistent light/dark surfaces within a frame;
- [ ] clean gradients, no muddy browns («Play it.» was cleaned to orange → pink → violet).

### Review method (final candidate only, time-boxed)

- **Depth:** see §1, Q-05. One fast self-check on every send; deep review only on the final candidate. [Q-05]
- **Brief critics with `client-taste.md` and a client-proxy lens** that re-reads the verbatim feedback history and asks: would the client reject this again? Not generic "top studio / creative director" personas. A generic critique called >60% empty canvas a flaw and prescribed HUD, N° numbering and corner marks, the opposite of the client. [Q-03]
  - Pair a minimalism critic with a judge who looks "through the client's eyes".
  - Judges never override a prior client approval.
  - The user's own notes go before reviewer findings.
  - Reject fixes that break beat sync or remove the strongest moment.
- **The method that converged:** [Q-04]
  - single-lens reviewers (client proxy, triggers & camera, UI craft & measured legibility, brief & copy, sound & sync, footage) who render the current source themselves;
  - segment critics plus one global lens (tokens / transport / audio), returning timecoded, severity-ranked findings with numeric fixes;
  - skeptical verifiers per scene, defaulting to refute;
  - ONE fixer;
  - QA on a frozen snapshot, with "an empty list is fine" in every prompt;
  - time-box each critic (~8–10 min, ≤5 findings), and apply fixes per segment as findings arrive.
  - Typical false positives: a claim read from code, missing motion blur in preview frames, a stale interim, timing judged at the wrong fps.
- **Never rebuild the rejected composition with new polish.** Put each new direction's key frames side by side with the rejected draft. SHIFT direction D (3D UI planes) recreated v001's layouts and scored 3.5/10 as "v001 re-polished". [Q-09]
- **Approval labels:** write «утверждено / approved» only when the user explicitly approved it. The handbook called film15 and three3d «утверждённый вид», but the user never reviewed them and stopped the work («стоп разбор и создание Audio MCP»): they are "draft, no client feedback". What was approved: the Audio MCP stills 01 and 03–14 after round 5 (07 and 08 explicitly; S1 and L1 by silent acceptance). [Q-08] [K-19]

---

## 11. Delivery and packaging

### Default film deliverable

- 16:9, 1920×1080, 24 fps, exact duration. [D-01]
- H.264 High BT.709 master rendered from PNG frames at 20–30 Mbps, with AAC 256 kbps music + SFX. [D-01]
- A share copy for chat: `avconvert --preset Preset1920x1080 --source master.mp4 --output share.mp4` (~35 MB per 30 s; raw 30 s renders at 20–24 Mbps run 75–108 MB). [D-01]
- A contact strip every 0.5–1 s, and a transitions sheet (each cut, every 2 frames ±5). [D-01]
- The score as a separate file. [D-01]
- Russian `NOTES.md`: scene/timing table, how to change texts and colours, how to re-render, fix log. [D-01]
- Editable source with all strings in one copy file; the generations folder and the clip manifest. [D-01]
- Drafts: JPEG frames at 20 Mbps. [D-01]
- With approved stills for After Effects, use the Russian per-shot AE notes template in `13_part1d` «Передача в After Effects». [D-02]

### Persist before the workspace disappears

- At the end of a film job, copy the project to a named folder in `~/Downloads` (final MP4, score and strip at the top level), verify the copy, and offer one zip of chat + assets, saying what was excluded («перенеси всё в ~/Downloads/PHYLLA», «дай мне чат zip», «и давай assets вместе»). The PHYLLA assets zip came to 885 MB; regenerable frame JPEGs were left out. [P-16]
- Don't depend on another session's scratch folder for the skill or the tokens: unzip the `.skill` into the project and copy the scripts into `lib/`. The skill and the user's tokens.json once existed only in an old scratch folder. [P-16]

### Packaging a skill or process for colleagues

«Дай мне рабочий skill нашего этого процесса чтобы я мог передать другим»:
- **The package:** a compact `.skill` with no example MP4/PNG and no duplicates; exports generated on demand (12.7 MB → 719 KB). The SKILL description stays ≤1024 chars (launch-film's 1115 chars was rejected; higgsfield-motion's is 808). [D-03]
- **Description:** Russian, in the team template (name — what it does / Откуда / Главная идея / Что умеет / Как работает / Когда срабатывает) or the Telegram "brag" post style. [D-03]
- **README (Russian):** «чем поможет и как поможет сделать», install, how to start, what you get at each stage, time and credits. List the real requirements (Node 22+). [D-03]
- **On request, an English one-prompt master preset** for bare Opus that names the Higgsfield libraries: models and params, Soul ID, reference elements, media library, presets as ideas only, cost estimate, batches ≤12, `declined_preset_id`. Note that it is untested on bare Opus. [D-03]

---

## 12. Tokens

- **«Мой tokens.json»** is the user's "Higgsfield Motion Frames — design tokens" v2.0.0 file, already embedded verbatim as `HFT.brands.higgsfield.legacy`. Use it as the base (refs on `color.brand.*` need `.hex`), export it with `JSON.stringify(…, null, 2)` when asked, and respect its ranges. Only if a physical copy is needed, search case-insensitively for `*token*.json` (scratch-workspaces included) and offer a persistent copy. A doc block using `"$ref"` as a key name once crashed the resolver. [TK-01]
- **In Node nothing is global:** `const HFT = require('./scripts/hf-tokens.js'); const HF = require('./scripts/hf-motion.js')`. `HFT.timeline()` returns an object with `.beats`. Add brands via `HFT.defineBrand(config)`, never by mutating `HFT.brands`; brand fonts must exist in `HFT.fonts`. [TK-04]
- **Register reference-driven identities in HFT** (`HFT.defineBrand`, `derive()` from the reference seeds, or a fitting preset) instead of hand-rolled palettes, so `validate()` still checks contrast and type. ZEVRA, SHIFT, FLOW and PLAY all bypassed the HFT runtime; the ZEVRA look is almost exactly `soft-pastel-ui` with a blue accent. [TK-02]
  - Use `HFT.color` (wcag, apca, over, OKLCH) instead of rewriting colour maths.
  - Keep each project look as a thin style layer over the base tokens (`$ref` / `$within` / `$override` with notes), with an explicit exceptions list.
  - Archive every previous look and scene version, so pivots cost minutes and reverts are trivial. PLAY pivoted look 3 times in one afternoon, 12–30 min each.
- **Token fidelity:** [TK-03]
  - Before drawing a component, look up its `components.*` / `motion.*` spec and build it literally. Then lint the hand-built geometry: `validate()` checks the theme, not your DOM. POST drifted on the phone, delta pill, shock rings, ripple colour, cursor dwell and caption size.
  - Pull type sizes, fonts and colours from `HFT.theme()` before writing the scenario. In onbeat, every frame had to be resized («Шрифты крупнее, чем в сценарии. Размеры взяты из движка токенов»).
  - Known drift: the tech-terminal handbook card (display 150 / headline 96 / label 26, "no accent font") disagrees with the engine (192 / 136 / 50, accent Doto). SKILL's old "Inter + Space Grotesk only" disagrees with the engine's Inter Tight + JetBrains Mono. Trust `hf-tokens.js`.

---

## 13. Research

- **Figma MCP study:** read-only `use_figma`; one `setCurrentPageAsync` per call; return ≤20 KB; ≤~5 `node.screenshot` calls per call; ~12 project agents concurrent. The errors were oversized responses, not rate limits. A full 84-project archive study took ~3 h 15 min. [O-06]
- **Without login:** Pinterest pin/topic pages and search are open (9–20 pins per query), but "more like this" is closed. Instagram shows only the last ~32 reel covers. X shows almost nothing. [O-06]
- Open a separate browser tab if an agent is using the shared browser. [O-06]

---

## 14. Sister skills

Two genre-specific skills were packaged from this user's sessions. higgsfield-motion stays the token and handbook base, and its cross-cutting lessons and script fixes are folded in here. Use a sister skill for its full genre pipeline instead of rebuilding it; the user decides whether to merge or keep them separate. [K-24]

| Skill | Built from | Use it for | What it adds |
|---|---|---|---|
| `product-motion-ad` | SHIFT (257453) | product / SaaS / app ads with footage ⇄ UI hand-offs | 8-stage pipeline (scenario → directions + judge panel → generations → `scene(t)` build → sound → review → master); tools `activity.mjs`, `textcheck.mjs`, `evalscene.mjs`, `film2.mjs` (motion-blur master), `montage.mjs`, `grid.mjs`, `color.mjs`, `synth/` (events-driven score + `audiocheck2.mjs`), `final.sh`; workflow scripts `directions_and_judges.js`, `parallel_build.js`, `review_loop.js`; BRIEF / CONTEXT / FEEDBACK / MANIFEST / PASSPORT templates; `references/lessons.md` (the SHIFT decision log) |
| `launch-film` | PHYLLA (f18bfc) | launch / promo / brand films built from generated montage | `/launch-film` command (`--mode` full / stills / code, `--music`, `--score`, `--cast`); `render_film.sh` (draft / final), `music_window.py`, `cut_audio.py`, `render_audio.mjs` + `assets/template/audio/score.html` (score presets), `mix_vo.py`; references `music.md`, `edit_engine.md`, `generation.md`, `qa_and_lessons.md`, `example_phylla.md` |

- Their source folders were session scratch copies (`scratch-2026-10-08-257453/skills/product-motion-ad`, `scratch-2026-10-08-f18bfc/skill/launch-film`) and may be gone; prefer the installed skills. [K-24] [P-16]
- product-motion-ad renders through Playwright and a `scene(t)` module contract. higgsfield-motion keeps raw CDP and `__seek`, and ports only the features. [K-24]
