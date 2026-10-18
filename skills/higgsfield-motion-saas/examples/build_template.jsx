// Build-script template. Copy next to your project, edit the body, run:
//   bash <skill>/scripts/ae.sh build.jsx out.txt '{"save":"/abs/project.aep","stills":"/abs/stills"}'
// ae.sh replaces __OUT__, __LIB__ and __CONFIG__ before AE runs the file.
(function () {
  var OUT = "__OUT__", CFG = __CONFIG__ || {};
  try { $.evalFile(new File("__LIB__")); }
  catch (e) { var f = new File(OUT); f.open("w"); f.writeln("ERR loading lib: " + e.toString() + " line " + e.line); f.close(); return; }

  SM.run(OUT, function (log) {
    // Rebuild idempotently: remove a previous version of this comp first.
    var NAME = "Main";
    for (var i = app.project.numItems; i >= 1; i--) {
      var it = app.project.item(i);
      if (it instanceof CompItem && it.name === NAME) it.remove();
    }
    var comp = SM.newComp(NAME, { w: 1920, h: 1080, fps: 60, dur: 8, bg: "#0B0B12" });

    // --- layers (bottom -> top) and techniques, all times in seconds -------------------
    // var bar = SM.card(comp, { name: "Prompt bar", size: [938, 126], radius: 63, color: "#BE96FF", opacity: 25 });
    // var z = SM.zoomAtCut(comp, { target: bar, cut: 2.8, to: 135, back: { cut: 3.4 } });
    // log("zoom " + SM.qa.zoom(comp, z).pass);

    // --- review + save --------------------------------------------------------------
    if (CFG.stills) SM.shoot(comp, [0.5, 1.0, 2.0], CFG.stills, NAME);
    if (CFG.save) { app.project.save(new File(CFG.save)); log("saved " + CFG.save); }
  });
})();
