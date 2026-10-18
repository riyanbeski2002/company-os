// Demo + self-test: builds every technique in its own comp, prints QA metrics, shoots stills, saves the project.
// Run:  bash scripts/ae.sh examples/demo_all.jsx out.txt '{"stills":"/abs/dir","save":"/abs/demo.aep"}'
(function () {
  var OUT = "__OUT__", CFG = __CONFIG__;
  try { $.evalFile(new File("__LIB__")); }
  catch (e) { var f = new File(OUT); f.open("w"); f.writeln("ERR loading lib: " + e.toString() + " line " + e.line); f.close(); return; }

  // "fresh": start from a new empty project — only for a scratch session whose open project holds nothing of value.
  if (CFG.fresh) { app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES); app.newProject(); }

  SM.run(OUT, function (log) {
    var BG = "#0B0B12", INK = "#F4F1FF", LAV = "#BE96FF";
    var shots = [];

    // ---------------------------------------------------------- T1 match cut + zoom pulse
    var c1 = SM.newComp("T1 Match cut + zoom", { dur: 4, bg: BG });
    var plates = [
      SM.card(c1, { name: "plate 1", size: [1920, 1080], radius: 0, color: "#3B2A6B" }),
      SM.card(c1, { name: "plate 2", size: [1920, 1080], radius: 0, color: "#6B2A45" }),
      SM.card(c1, { name: "plate 3", size: [1920, 1080], radius: 0, color: "#1F5C4A" }),
      SM.card(c1, { name: "plate 4", size: [1920, 1080], radius: 0, color: "#5C4A1F" })
    ];
    SM.cuts(plates, [0, 1.0, 1.6, 2.43]);
    var bar = SM.card(c1, { name: "Prompt bar", size: [938, 126], radius: 63, color: LAV, opacity: 35, stroke: { color: "#FFFFFF", width: 2 } });
    var z = SM.zoomAtCut(c1, { target: bar, cut: 1.6, to: 135, back: { cut: 2.43 } });
    var qz = SM.qa.zoom(c1, z);
    log("T1 zoom: largestStepEndsOnCut=" + qz.largestStepEndsOnCut + " stepFrac=" + SM.r3(qz.stepFrac) + " pass=" + qz.pass);
    log("T1 zoom speed (scale %/frame*fps) around cut: " + SM.qa.speedGraph(c1, SM.tr(z.nul, "ADBE Scale"), z.t1, z.t2 + 1 / 60, 0).join(" "));
    shots.push([c1, [0.9, 1.4, 1.583, 1.6, 1.8, 2.43]]);

    // ---------------------------------------------------------- T2 UI morph
    var c2 = SM.newComp("T2 UI morph", { dur: 2.5, bg: BG });
    var sl1 = SM.card(c2, { name: "Shape Layer 1", size: [912, 312], radius: 40, color: INK });
    var sl2 = SM.card(c2, { name: "Shape Layer 2", size: [662, 900], radius: 40, color: INK });
    var mo = { sl1: sl1, sl2: sl2, cut: 1.0, axis: "y" };
    var m = SM.uiMorph(c2, mo);
    var qm = SM.qa.uiMorph(c2, mo, m);
    log("T2 morph: frames=" + m.frames + " r2=" + SM.r3(m.r2) + " inf2In=" + SM.r3(m.inf2In) + " rho1=" + SM.r3(qm.rho1) + " rho2=" + SM.r3(qm.rho2) + " ratio=" + SM.r3(qm.ratio) + " pass=" + qm.pass);
    log("T2 SL1 height speed px/s: " + SM.qa.speedGraph(c2, SM.rectSize(sl1), 1.0 - 23 / 60, 1.0 - 1 / 60, 1).join(" "));
    log("T2 SL2 height speed px/s: " + SM.qa.speedGraph(c2, SM.rectSize(sl2), 1.0, 1.0 + 22 / 60, 1).join(" "));
    shots.push([c2, [0.6, 0.9, 0.983, 1.0, 1.05, 1.4]]);

    // ---------------------------------------------------------- T3 overlap 2D: sequential vs overlap
    var A = [232, 546], B = [1669, 546], C = [1669, 261];   // the author's demo geometry (QA targets are geometry-specific)
    var c3a = SM.newComp("T3a Sequential (amateur)", { dur: 2.5, bg: BG });
    var dotA = SM.card(c3a, { name: "dot", size: [120, 120], radius: 60, color: INK });
    var s3a = SM.sequential2D(c3a, { layer: dotA, A: A, B: B, C: C, t0: 0.1 });
    var q3a = SM.qa.path(c3a, dotA, { t0: s3a.tA, t1: s3a.tC, win: [s3a.tB - 0.05, s3a.tB + 0.05], A: A, B: B });
    log("T3a sequential: minFrac=" + SM.r3(q3a.minFrac) + " closestFrac=" + SM.r3(q3a.closestFrac) + " (expect ~0 / ~0)");

    var c3b = SM.newComp("T3b Overlap 2D (render)", { dur: 2.5, bg: BG });
    var dotB = SM.card(c3b, { name: "dot", size: [120, 120], radius: 60, color: INK });
    var o3 = SM.overlap2D(c3b, { layer: dotB, A: A, B: B, C: C, t0: 0.1, mode: "render" });
    var q3b = SM.qa.path(c3b, dotB, { t0: o3.tA, t1: o3.tE, win: [o3.tS, o3.tB], A: A, B: B });
    log("T3b overlap render: minFrac=" + SM.r3(q3b.minFrac) + " closestFrac=" + SM.r3(q3b.closestFrac) + " (target 0.26 / 0.079, fail <0.05)");

    var c3c = SM.newComp("T3c Overlap 2D (taught)", { dur: 2.5, bg: BG });
    var dotC = SM.card(c3c, { name: "dot", size: [120, 120], radius: 60, color: INK });
    var o3c = SM.overlap2D(c3c, { layer: dotC, A: A, B: B, C: C, t0: 0.1, mode: "taught" });
    var q3c = SM.qa.path(c3c, dotC, { t0: o3c.tA, t1: o3c.tE, win: [o3c.tS, o3c.tB], A: A, B: B });
    log("T3c overlap taught: minFrac=" + SM.r3(q3c.minFrac) + " closestFrac=" + SM.r3(q3c.closestFrac) + " (target 0.175 / 0.062-0.066)");
    shots.push([c3a, [0.5, 1.05, 1.3]]); shots.push([c3b, [0.7, 1.1, 1.5]]);

    // ---------------------------------------------------------- T4 null chain
    var c4 = SM.newComp("T4 Null chain", { dur: 4, bg: BG });
    var dotD = SM.card(c4, { name: "dot", size: [100, 100], radius: 50, color: LAV });
    SM.overlapChain(c4, { layer: dotD, points: [[200, 800], [960, 800], [960, 300], [1700, 300], [1700, 800]], t0: 0.1, D: 0.9 });
    var q4 = SM.qa.path(c4, dotD, { t0: 0.1, t1: 2.5, win: [0.55, 1.9] });   // between the first and the last move's start
    log("T4 chain: minFrac over turns=" + SM.r3(q4.minFrac) + " (must be > 0.05)");
    shots.push([c4, [0.5, 1.0, 1.5, 2.0]]);

    // ---------------------------------------------------------- T5 overlap 3D (+ compensation check)
    var c5 = SM.newComp("T5 Overlap 3D", { dur: 6, bg: BG });
    var PA = { pos: [246, 463, 0], rot: [0, 0, 0] }, PB = { pos: [1669, 465, 0], rot: [0, 360, 0] }, PC = { pos: [472, 235, 0], rot: [0, 720, -16] };
    var ghost = SM.card(c5, { name: "ghost (no parent)", size: [180, 280], radius: 30, color: "#444466" });
    ghost.threeDLayer = true; ghost.enabled = false;
    SM._poseSeg(SM._pose3(ghost), SM.fr(c5, 0.2), PA, SM.fr(c5, 0.2 + 2.1), PB, 33.333);
    var can = SM.card(c5, { name: "can", size: [180, 280], radius: 30, color: LAV });
    var o5 = SM.overlap3D(c5, { layer: can, A: PA, B: PB, C: PC, t0: 0.2, D1: 2.1, mode: "taught" });
    var Sg = SM.qa.sampler(c5, ghost), Sc = SM.qa.sampler(c5, can), maxd = 0;
    for (var t = o5.tA; t <= o5.tS; t += 1 / 30) maxd = Math.max(maxd, SM.qa._dist(Sg.at(t), Sc.at(t)));
    Sg.remove(); Sc.remove();
    log("T5 3D compensation: max |object - unparented ghost| on [tA,tS] = " + SM.r3(maxd) + " px (must be < 1)");
    var q5 = SM.qa.path(c5, can, { t0: o5.tA, t1: o5.tE, win: [o5.tS, o5.tB] });
    log("T5 3D taught: minFrac=" + SM.r3(q5.minFrac) + " (target ~0.118, QA >= 0.05)");
    shots.push([c5, [0.2, 1.0, 1.6, 2.1, 2.6, 3.4, 4.6]]);

    // ---------------------------------------------------------- T6 mockup hand-off
    var c6 = SM.newComp("T6 Mockup hand-off", { dur: 4, bg: BG });
    var page = SM.card(c6, { name: "UI page", size: [1400, 3000], radius: 24, color: "#EDEAF7" });
    var pp = SM.tr(page, "ADBE Position");
    SM.scrollInto(c6, { prop: pp, from: [960, 1500], to: [960, -400], cut: 3.0, ta: 2.6 });
    page.outPoint = 3.0;
    var device = SM.card(c6, { name: "Device screen", size: [1100, 700], radius: 36, color: "#EDEAF7", stroke: { color: "#222230", width: 24 } });
    device.threeDLayer = true; device.inPoint = 3.0;
    SM.settleAfterCut(c6, { prop: SM.tr(device, "ADBE Rotate X"), from: -55, to: 0, cut: 3.0 });
    log("T6 scroll speed into cut px/s: " + SM.qa.speedGraph(c6, pp, 2.5, 3.0, 1).join(" "));
    log("T6 lid X-rotation speed after cut deg/s: " + SM.qa.speedGraph(c6, SM.tr(device, "ADBE Rotate X"), 3.0, 3.6).join(" "));
    var rx = SM.tr(device, "ADBE Rotate X"), prog = [];
    for (var k = 1; k <= 7; k++) prog.push(SM.r3((rx.valueAtTime(3.0 + k * 0.1, false) + 55) / 55));
    log("T6 settle progress at +0.1..0.7 s: " + prog.join(" ") + " (reference 0.35 0.67 0.78 0.88 0.92 0.94 0.96)");
    shots.push([c6, [2.5, 2.983, 3.0, 3.1, 3.4]]);

    // ---------------------------------------------------------- T7 object entrance + typing + caret
    var c7 = SM.newComp("T7 Entrance + typing", { dur: 3, bg: "#2A1F3D" });
    var gbar = SM.card(c7, { name: "Glass bar", size: [131, 131], radius: 65, color: LAV, opacity: 35, stroke: { color: "#FFFFFF", width: 2 } });
    var btn = SM.card(c7, { name: "Send", size: [100, 100], radius: 50, color: "#FFFFFF" });
    var en = SM.entrance(c7, { layer: gbar, t: 0.2, width: 933, button: btn });
    var txt = c7.layers.addText("x"); txt.name = "Prompt text";
    var td = txt.property("ADBE Text Properties").property("ADBE Text Document"), tv = td.value;
    tv.fontSize = 40; tv.fillColor = [1, 1, 1]; tv.justification = ParagraphJustification.LEFT_JUSTIFY; td.setValue(tv);
    SM.pinInside(txt, gbar, { side: "left", pad: 58, dy: 14 });     // text rides the bar's left inner edge
    var ty = SM.typeOn(txt, { t0: 0.62, cps: 30, text: "Build me a landing page" });
    SM.caret(c7, txt, { t0: 0.62, tEnd: ty.tEnd, height: 40 });
    var pq = SM.tr(gbar, "ADBE Position"), ys = [];
    for (var f = 0; f <= 72; f += 8) ys.push(SM.r3(pq.valueAtTime(0.2 + f / 60, false)[1] - 540));
    log("T7 entrance Y offset every 8 frames: " + ys.join(" ") + " (reference: +217 at 0, about -46 at +14f, +19 at +30f)");
    shots.push([c7, [0.2, 0.25, 0.43, 0.7, 1.0, 1.6, 2.6]]);

    // ---------------------------------------------------------- stills + save
    var n = 0;
    for (var s = 0; s < shots.length; s++) { var r = SM.shoot(shots[s][0], shots[s][1], CFG.stills, "S" + s); n += r.length; }
    log("stills requested: " + n);
    var rq = app.project.renderQueue.items.add(c5), oms = rq.outputModule(1).templates;
    log("output module templates: " + oms.join(" | ")); rq.remove();
    if (CFG.save) { app.project.save(new File(CFG.save)); log("saved " + CFG.save); }
  });
})();
