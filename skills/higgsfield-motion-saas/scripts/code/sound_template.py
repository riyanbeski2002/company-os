"""Soundtrack for a code-built film, driven by the film's own cue list (no hand-copied times).
    node scripts/code/capture.mjs film/index.html /tmp --cues film/cues.json
    python3 scripts/code/sound_template.py film/cues.json film/sound.wav
    scripts/code/bin/mux film/film.mp4 film/sound.m4a film/final.mp4
The user's FINAL sound is usually made by a human in Premiere — this is a placeholder that sells the cut rhythm.
Always deliver *_nosound.mp4 too. Say plainly that the track was checked numerically, not listened to.
Edit the score below; the rules: every cut gets a hit, a riser ENDS on every speed-peak cut, every visible click / pop /
landing gets a sound at CONTACT time (spring start + ~0.13 s), music ducks under hits, mute the arpeggio in the
0.3 s before big cuts so the riser can land.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sound_kit as S

cues_path, out = sys.argv[1], sys.argv[2]
import json
comp = json.load(open(cues_path)).get('comp', {})
S.init(comp.get('duration', 15.0), seed=7)
cuts, cues = S.load_cues(cues_path)
BPM = 120; beat = 60 / BPM

# bed: one chord per section between cuts (Dm Bb F Gm …), pad + bass, ducked by hits
CHORDS = [[50, 57, 62, 65], [46, 53, 58, 62], [53, 57, 60, 65], [43, 50, 55, 58]]
edges = [0.0] + list(cuts) + [S.DUR]
for i in range(len(edges) - 1):
    a, b = edges[i], edges[i + 1]; ch = CHORDS[i % len(CHORDS)]
    S.add(S.pad(ch, b - a + .3, .9), a, .5, bus='mus', hall=.2)
    S.add(S.bass(ch[0] - 12, b - a, .8), a, .35, bus='mus')
# pulse: hats on 8ths, quiet; a kick per beat after the first cut
t = beat / 2
while t < S.DUR - .3:
    S.add(S.hat2(1.0, .03), t, .05, pan=.3 if int(t / beat * 2) % 2 else -.3, bus='drum')
    t += beat / 2
for c in cuts:                                   # the cuts ARE the rhythm
    S.add_end(S.riser2(.45), c, .45, hall=.12)
    S.hit(c, 1.0, .9, chord=[x + 12 for x in CHORDS[0]], clap_g=.2, cym=.06)
for q in cues:                                   # picture sounds from the film's FILM.cue(name, t, kind)
    k, t = q['kind'], q['t']
    if k == 'ui': S.add(S.mclick(), t, .35, pan=.15, room=.2)
    elif k == 'pop': S.add(S.wpop(900), t, .3, room=.15)
    elif k == 'type': S.add(S.keyclick(), t, .2, pan=.1, room=.1)
    elif k == 'whoosh': S.add_end(S.whip(.22), t, .35)
S.master(out, fade_from=S.DUR - .45)
S.verify([('cut', c, 'lf') for c in cuts] + [(q['name'][:12], q['t'], 'hf') for q in cues if q['kind'] == 'ui'])
