// Example piece (7.5 s): prompt-bar entrance + typing -> match cuts with a zoom pulse -> UI morph into a
// dashboard card -> rows drop in with overlap. Shows how the techniques compose in one build script.
// Run: bash scripts/ae.sh examples/saas_teaser.jsx out.txt '{"save":"/abs/teaser.aep","stills":"/abs/stills"}'
(function () {
  var OUT = "__OUT__", CFG = __CONFIG__ || {};
  try { $.evalFile(new File("__LIB__")); }
  catch (e) { var f = new File(OUT); f.open("w"); f.writeln("ERR loading lib: " + e.toString() + " line " + e.line); f.close(); return; }

  SM.run(OUT, function (log) {
    for (var i = app.project.numItems; i >= 1; i--) {
      var it = app.project.item(i);
      if (it instanceof CompItem && (it.name === "Teaser" || it.name === "Teaser Hero")) it.remove();
    }
    var FPS = 60, DUR = 7.5, LAV = "#BE96FF";
    var main = SM.newComp("Teaser", { fps: FPS, dur: DUR, bg: "#0B0B12" });
    var hero = SM.newComp("Teaser Hero", { fps: FPS, dur: DUR });

    // ---------------- background plates in Main (hard cuts; never scaled)
    function plate(name, c1, c2) {
      var L = SM.card(main, { name: name, size: [1920, 1080], radius: 0, color: c1 });
      var fx = L.property("ADBE Effect Parade").addProperty("ADBE Ramp");
      fx.property("ADBE Ramp-0001").setValue([960, 300]); fx.property("ADBE Ramp-0002").setValue(SM.hex(c2));
      fx.property("ADBE Ramp-0003").setValue([960, 1400]); fx.property("ADBE Ramp-0004").setValue(SM.hex(c1));
      fx.property("ADBE Ramp-0005").setValue(2);      // radial
      return L;
    }
    var plates = [plate("plate dusk", "#1C1D49", "#5A3C8C"), plate("plate rose", "#3A0436", "#C2ABB5"),
                  plate("plate grass", "#14301F", "#6E9C55"), plate("plate olive", "#2A2108", "#B39A4A"),
                  plate("plate night", "#06060C", "#1C1D49")];
    SM.cuts(plates, [0, 2.2, 2.8, 3.4, 4.3]);

    // ---------------- hero precomp: bar + button + text + caret, then the dashboard card
    var bar = SM.card(hero, { name: "Prompt bar", size: [126, 126], radius: 63, color: LAV, opacity: 30, stroke: { color: "#FFFFFF", width: 2 } });
    var btn = SM.card(hero, { name: "Send", size: [96, 96], radius: 48, color: "#F4F1FF" });
    var en = SM.entrance(hero, { layer: bar, t: 0.3, width: 938, button: btn });

    var txt = hero.layers.addText("x"); txt.name = "Prompt text";
    var td = txt.property("ADBE Text Properties").property("ADBE Text Document"), tv = td.value;
    tv.font = "HelveticaNeue-Medium"; tv.fontSize = 38; tv.fillColor = [1, 1, 1];
    tv.justification = ParagraphJustification.LEFT_JUSTIFY; td.setValue(tv);
    SM.pinInside(txt, bar, { side: "left", pad: 58, dy: 13 });
    var ty = SM.typeOn(txt, { t0: 0.72, cps: 22, text: "Design a dashboard for my startup" });   // types through the first cut
    var caret = SM.caret(hero, txt, { t0: 0.72, tEnd: ty.tEnd, height: 40 });

    // dashboard card (SL2) + rows
    var card = SM.card(hero, { name: "Dashboard card", size: [760, 640], radius: 40, color: LAV, opacity: 30, stroke: { color: "#FFFFFF", width: 2 } });
    var mo = { sl1: bar, sl2: card, cut: 4.3, axis: "y" };
    var m = SM.uiMorph(hero, mo);
    var qm = SM.qa.uiMorph(hero, mo, m);
    log("morph: rho ratio " + SM.r3(qm.ratio) + " pass=" + qm.pass);
    btn.outPoint = 4.3; txt.outPoint = 4.3; caret.outPoint = 4.3;

    var labels = ["Revenue   $48.2k", "Active users   12,480", "Conversion   4.7%"];
    for (var r = 0; r < 3; r++) {
      var y = 540 - 170 + r * 170, t = SM.fr(hero, 4.55 + r * 0.45 * 0.4);   // next row starts at 0.45 of the previous drop
      var row = SM.card(hero, { name: "Row " + (r + 1), size: [660, 130], radius: 24, color: "#201A46", opacity: 80 });
      var lab = hero.layers.addText(labels[r]); lab.name = "Label " + (r + 1);
      var ld = lab.property("ADBE Text Properties").property("ADBE Text Document"), lv = ld.value;
      lv.font = "HelveticaNeue-Medium"; lv.fontSize = 34; lv.fillColor = SM.hex("#F4F1FF");
      lv.justification = ParagraphJustification.LEFT_JUSTIFY; ld.setValue(lv);
      SM.pinInside(lab, row, { side: "left", pad: 40, dy: 12 });
      // drop in from 70 px above with a fast start and a settle (no overshoot), plus a quick fade
      SM.seg(SM.tr(row, "ADBE Position"), t, [960, y - 70], SM.fr(hero, t + 0.45), [960, y], [3.5, 20], [0, 95]);
      SM.seg(SM.tr(row, "ADBE Opacity"), t, 0, SM.fr(hero, t + 0.15), 100, [0, 33.333], [0, 33.333]);
      SM.seg(SM.tr(lab, "ADBE Opacity"), t, 0, SM.fr(hero, t + 0.15), 100, [0, 33.333], [0, 33.333]);
      row.inPoint = t; lab.inPoint = t;
    }

    // ---------------- hero into Main + zoom pulse on the second/third cuts
    var heroL = main.layers.add(hero);
    var z = SM.zoomAtCut(main, { target: heroL, cut: 2.8, to: 135, back: { cut: 3.4 }, pivot: [960, 540] });
    var qz = SM.qa.zoom(main, z);
    log("zoom: step ends on cut=" + qz.largestStepEndsOnCut + " frac=" + SM.r3(qz.stepFrac));

    if (CFG.stills) {
      SM.shoot(main, [0.3, 0.5, 1.2, 2.18, 2.2, 2.75, 2.8, 3.1, 3.4, 4.25, 4.3, 4.6, 5.2, 7.0], CFG.stills, "teaser");
    }
    if (CFG.save) { app.project.save(new File(CFG.save)); log("saved " + CFG.save); }
  });
})();
