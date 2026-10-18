// saas_motion.jsx — SaaS-style motion techniques for After Effects, code-first.
// ExtendScript (ES3): no let/const/arrow functions/Array.map. Load from a build script with
//   $.evalFile(new File("__LIB__"));        // ae.sh replaces __LIB__ with this file's path
// then do all work inside SM.run("__OUT__", function (log) { ... }).
//
// Conventions (see references/ease-math.md):
//  * all times are seconds and are snapped to the comp's frame grid with SM.fr();
//  * ease is given as [r, influence] where r = speed as a MULTIPLE OF THE SEGMENT'S AVERAGE SPEED
//    (0 = stop, 9 = nine times the average); SM.seg() converts r to AE units/second per dimension;
//  * every key is switched to BEZIER before its ease is set (script keys start LINEAR);
//  * a null that receives children gets Anchor Point == Position == pivot, Scale 100, Rotation 0
//    before parenting, so parent compensation is a no-op and child values stay in comp space.

var SM = (typeof SM !== "undefined" && SM) ? SM : {};

(function (SM) {
  SM.VERSION = "1.0.0";
  SM.EASY = [0, 33.333];               // AE Easy Ease (speed 0, influence 33.33%)

  // ---------------------------------------------------------------- run / log
  SM.run = function (outPath, body) {
    var f = new File(outPath); f.encoding = "UTF-8"; f.open("w");
    var log = function (s) { f.writeln(String(s)); };
    app.beginSuppressDialogs();
    app.beginUndoGroup("SM build");
    try { body(log); log("OK"); }
    catch (e) { log("ERR " + e.toString() + " line " + e.line); }
    app.endUndoGroup();
    try { app.endSuppressDialogs(false); } catch (e2) {}
    f.close();
  };

  // ---------------------------------------------------------------- basics
  SM.isArr = function (v) { return v !== null && typeof v === "object" && typeof v.length === "number"; };
  SM.fr = function (comp, s) { var fd = comp.frameDuration; return Math.round(s / fd) * fd; };
  SM.nf = function (comp, s) { return Math.round(s / comp.frameDuration); };
  SM.tr = function (layer, mn) { return layer.property("ADBE Transform Group").property(mn); };
  SM.hex = function (h) {
    h = h.replace("#", "");
    return [parseInt(h.substr(0, 2), 16) / 255, parseInt(h.substr(2, 2), 16) / 255, parseInt(h.substr(4, 2), 16) / 255];
  };
  SM.r3 = function (v) {                                   // stringify numbers / arrays for logs
    if (SM.isArr(v)) { var a = []; for (var i = 0; i < v.length; i++) a.push(SM.r3(v[i])); return "[" + a.join(",") + "]"; }
    return String(Math.round(v * 1000) / 1000);
  };
  SM.dims = function (prop) {
    var v = prop.value; return SM.isArr(v) ? v.length : 1;
  };
  SM.isSpatial = function (prop) {
    var t = prop.propertyValueType;
    return (t === PropertyValueType.TwoD_SPATIAL || t === PropertyValueType.ThreeD_SPATIAL) && !prop.dimensionsSeparated;
  };
  SM.fit = function (prop, v) {                            // pad / trim a value to the property's dimensions
    var n = SM.dims(prop);
    if (n === 1) return SM.isArr(v) ? v[0] : v;
    var out = [], src = SM.isArr(v) ? v : [v];
    for (var i = 0; i < n; i++) out.push(i < src.length ? src[i] : (i === 2 ? (prop.matchName === "ADBE Scale" ? src[0] : 0) : src[src.length - 1]));
    return out;
  };

  SM.newComp = function (name, o) {
    o = o || {};
    var c = app.project.items.addComp(name, o.w || 1920, o.h || 1080, 1, o.dur || 6, o.fps || 60);
    if (o.bg) c.bgColor = SM.isArr(o.bg) ? o.bg : SM.hex(o.bg);
    return c;
  };

  // ---------------------------------------------------------------- keys and ease
  SM.key = function (prop, t, v) { prop.setValueAtTime(t, SM.fit(prop, v)); return prop.nearestKeyIndex(t); };

  SM._ke = function (spec, i, cur) {
    if (spec === null || spec === undefined) return new KeyframeEase(cur.speed, Math.max(0.1, Math.min(100, cur.influence)));
    var s = SM.isArr(spec[0]) ? spec[Math.min(i, spec.length - 1)] : spec;
    return new KeyframeEase(s[0], Math.max(0.1, Math.min(100, s[1])));
  };

  // Raw ease: spec = [speedUnitsPerSec, influence] for every dimension, or [[s,i],[s,i],...] per dimension,
  // or null to keep the current side. The array length comes from AE (Scale may want 3 on a 2D layer).
  SM.ease = function (prop, k, inSpec, outSpec) {
    prop.setInterpolationTypeAtKey(k, KeyframeInterpolationType.BEZIER, KeyframeInterpolationType.BEZIER);
    var ci = prop.keyInTemporalEase(k), co = prop.keyOutTemporalEase(k), a = [], b = [];
    for (var i = 0; i < ci.length; i++) { a.push(SM._ke(inSpec, i, ci[i])); b.push(SM._ke(outSpec, i, co[i])); }
    prop.setTemporalEaseAtKey(k, a, b);
  };

  // One animated segment v1@t1 -> v2@t2 with relative ease:
  //   e1 = [r, influence] on the outgoing side of the first key, e2 on the incoming side of the second key.
  // r is a multiple of the segment's average speed; converted per dimension (signed) for non-spatial
  // properties and as path speed for spatial ones. Returns {k1, k2, vbar}.
  SM.seg = function (prop, t1, v1, t2, v2, e1, e2) {
    SM.key(prop, t1, v1); SM.key(prop, t2, v2);
    var k1 = prop.nearestKeyIndex(t1), k2 = prop.nearestKeyIndex(t2);
    var a = SM.fit(prop, v1), b = SM.fit(prop, v2), D = t2 - t1, spec;
    var conv = function (e) {
      if (!e) return null;
      if (SM.isSpatial(prop)) {
        var d2 = 0; for (var i = 0; i < a.length; i++) d2 += (b[i] - a[i]) * (b[i] - a[i]);
        return [e[0] * Math.sqrt(d2) / D, e[1]];
      }
      if (!SM.isArr(a)) return [e[0] * (b - a) / D, e[1]];
      var per = []; for (var j = 0; j < a.length; j++) per.push([e[0] * (b[j] - a[j]) / D, e[1]]);
      return per;
    };
    SM.ease(prop, k1, null, conv(e1));
    k2 = prop.nearestKeyIndex(t2);
    SM.ease(prop, k2, conv(e2), null);
    return { k1: k1, k2: k2 };
  };

  // Straight lines between position keys (the "amateur" L-path needs this; AE defaults to auto-bezier).
  SM.linearPath = function (prop) {
    if (!SM.isSpatial(prop)) return;
    var z = SM.dims(prop) === 3 ? [0, 0, 0] : [0, 0];
    for (var k = 1; k <= prop.numKeys; k++) {
      prop.setSpatialAutoBezierAtKey(k, false); prop.setSpatialContinuousAtKey(k, false);
      prop.setSpatialTangentsAtKey(k, z, z);
    }
  };

  // ---------------------------------------------------------------- layers
  // Null whose local space equals comp space (2D) or whose pivot sits at its Position (3D).
  SM.addNull = function (comp, name, pivot, is3D) {
    var n = comp.layers.addNull(comp.duration);
    n.name = name; n.label = 9;
    if (is3D) {
      n.threeDLayer = true;
      SM.tr(n, "ADBE Anchor Point").setValue([0, 0, 0]);
      SM.tr(n, "ADBE Position").setValue(pivot ? SM.fit(SM.tr(n, "ADBE Position"), pivot) : [comp.width / 2, comp.height / 2, 0]);
    } else {
      var p = pivot || [comp.width / 2, comp.height / 2];
      SM.tr(n, "ADBE Anchor Point").setValue([p[0], p[1]]);
      SM.tr(n, "ADBE Position").setValue([p[0], p[1]]);
    }
    return n;
  };

  // Parent with compensation evaluated at time t (AE compensates using the parent's transform at comp.time).
  SM.parentAt = function (comp, child, parent, t) {
    var keep = comp.time; comp.time = (t === undefined) ? 0 : t;
    child.parent = parent;
    comp.time = keep;
  };

  // Rounded-rect card on its own shape layer, centred on the layer's Position. o: {name,size,radius,color,pos,opacity,stroke}
  SM.card = function (comp, o) {
    o = o || {};
    var L = comp.layers.addShape(); L.name = o.name || "Card";
    var root = L.property("ADBE Root Vectors Group");
    var g = root.addProperty("ADBE Vector Group"); g.name = "Card";
    var r = g.property("ADBE Vectors Group").addProperty("ADBE Vector Shape - Rect");
    r.property("ADBE Vector Rect Size").setValue(o.size || [400, 120]);
    r.property("ADBE Vector Rect Roundness").setValue(o.radius === undefined ? 24 : o.radius);
    var fill = L.property("ADBE Root Vectors Group").property(1).property("ADBE Vectors Group").addProperty("ADBE Vector Graphic - Fill");
    fill.property("ADBE Vector Fill Color").setValue(SM.isArr(o.color) ? o.color : SM.hex(o.color || "#FFFFFF"));
    if (o.opacity !== undefined) fill.property("ADBE Vector Fill Opacity").setValue(o.opacity);
    if (o.stroke) {
      var st = L.property("ADBE Root Vectors Group").property(1).property("ADBE Vectors Group").addProperty("ADBE Vector Graphic - Stroke");
      st.property("ADBE Vector Stroke Color").setValue(SM.isArr(o.stroke.color) ? o.stroke.color : SM.hex(o.stroke.color || "#FFFFFF"));
      st.property("ADBE Vector Stroke Width").setValue(o.stroke.width || 2);
    }
    SM.tr(L, "ADBE Position").setValue(o.pos || [comp.width / 2, comp.height / 2]);
    return L;
  };

  SM._findRect = function (group) {
    for (var i = 1; i <= group.numProperties; i++) {
      var p = group.property(i);
      if (p.matchName === "ADBE Vector Shape - Rect") return p;
      if (p.matchName === "ADBE Vector Group") { var r = SM._findRect(p.property("ADBE Vectors Group")); if (r) return r; }
    }
    return null;
  };
  // Contents > ... > Rectangle Path > Size of the first rectangle in a shape layer.
  SM.rectSize = function (layer) {
    var r = SM._findRect(layer.property("ADBE Root Vectors Group"));
    if (!r) throw new Error("SM.rectSize: no rectangle in " + layer.name);
    return r.property("ADBE Vector Rect Size");
  };

  SM.q = function (name) { return '"' + String(name).replace(/\\/g, "\\\\").replace(/"/g, '\\"') + '"'; };

  // Keep a layer glued to the left/right inner edge of a host whose size animates (e.g. a widening bar):
  // text inside a bar, a send button at its right end. o: {side:"left"|"right", pad:58, dy:0}
  SM.pinInside = function (layer, host, o) {
    o = o || {};
    var pad = (o.pad === undefined) ? 58 : o.pad;
    var x = (o.side === "right") ? "r.left+r.width-" + pad : "r.left+" + pad;
    SM.tr(layer, "ADBE Position").expression = "var H=thisComp.layer(" + SM.q(host.name) + ");var r=H.sourceRectAtTime(time,false);" +
      "var p=H.toComp([" + x + ",r.top+r.height/2]);[p[0],p[1]+" + (o.dy || 0) + "];";
  };

  // Hard cuts: layers[i] is visible on [times[i], times[i+1]).
  SM.cuts = function (layers, times) {
    for (var i = 0; i < layers.length; i++) {
      layers[i].inPoint = times[i];
      if (i + 1 < times.length) layers[i].outPoint = times[i + 1];
    }
  };

  // ================================================================= techniques
  // 1) Zoom at the cut — a needle-shaped speed peak exactly on the cut frame.
  // o: {target: layer|[layers], cut, from:100, to:115, half:0.2, influence:95, pivot:[x,y], name,
  //     back: {cut, half:0.24}  -> pulse: from->to at cut, to->from at back.cut (next cut, >= 0.6 s later)}
  // Backgrounds are never parented: only the persistent object scales.
  SM.zoomAtCut = function (comp, o) {
    var fd = comp.frameDuration, T = SM.fr(comp, o.cut), n = Math.max(1, SM.nf(comp, o.half || 0.2));
    var targets = SM.isArr(o.target) ? o.target : [o.target];
    var pivot = o.pivot || SM.tr(targets[0], "ADBE Position").valueAtTime(T, false);
    var nul = SM.addNull(comp, o.name || "ZOOM_NULL", [pivot[0], pivot[1]]);
    for (var i = 0; i < targets.length; i++) SM.parentAt(comp, targets[i], nul, 0);   // parent BEFORE keys
    var sc = SM.tr(nul, "ADBE Scale"), from = o.from || 100, to = o.to || 115, inf = o.influence || 95;
    var t1 = T - n * fd, t2 = T + (n - 1) * fd;       // midpoint T - half a frame -> largest step on (T-1, T)
    SM.seg(sc, t1, [from, from, 100], t2, [to, to, 100], [0, inf], [0, inf]);
    var res = { nul: nul, t1: t1, t2: t2, cut: T };
    if (o.back) {
      var T2 = SM.fr(comp, o.back.cut), n2 = Math.max(1, SM.nf(comp, o.back.half || 0.24));
      SM.seg(sc, T2 - n2 * fd, [to, to, 100], T2 + (n2 - 1) * fd, [from, from, 100], [0, inf], [0, inf]);
      res.back = T2;
    }
    return res;
  };

  // 2) UI morph — two shape layers cut at T; Rectangle Size (not Scale) on one axis; speed cusp at the cut,
  // matched by RELATIVE speed rho = (dH/dt)/H on both sides.
  // o: {sl1, sl2, cut, axis:"y"|"x", grow:0.18, shrink:0.18, dur:0.37, sl1Out:66, r1:9, inf1:10, inf2Out:7}
  SM.uiMorph = function (comp, o) {
    var fd = comp.frameDuration, T = SM.fr(comp, o.cut), N = Math.max(2, SM.nf(comp, o.dur || 0.37));
    var ax = (o.axis === "x") ? 0 : 1, p = (o.grow === undefined) ? 0.18 : o.grow, q = (o.shrink === undefined) ? 0.18 : o.shrink;
    var r1 = o.r1 || 9, sl1Out = o.sl1Out || 66, inf1 = o.inf1 || 10, inf2Out = o.inf2Out || 7;
    var s1 = SM.rectSize(o.sl1), s2 = SM.rectSize(o.sl2);
    var A1 = s1.valueAtTime(T - fd, false), H2v = s2.valueAtTime(T, false);
    var B1 = [A1[0], A1[1]]; B1[ax] = A1[ax] * (1 + p);
    var A2 = [H2v[0], H2v[1]]; A2[ax] = H2v[ax] * (1 - q);
    var D1 = N * fd, D2 = N * fd;
    var tA = T - (N + 1) * fd, tB = T - fd, tC = T, tD = T + N * fd;
    SM.seg(s1, tA, A1, tB, B1, [0, sl1Out], [r1, inf1]);
    // relative-speed match: rho1 = r1 * vbar1 / H1end ; s2 = rho1 * H2start ; r2 = s2 / vbar2
    var vbar1 = (B1[ax] - A1[ax]) / D1, rho1 = r1 * vbar1 / B1[ax];
    var vbar2 = (H2v[ax] - A2[ax]) / D2, r2 = rho1 * A2[ax] / vbar2;
    var inf2In = Math.min(86, 100 * (1 - 1 / r2));
    SM.seg(s2, tC, A2, tD, [H2v[0], H2v[1]], [r2, inf2Out], [0, inf2In]);
    o.sl1.outPoint = T; o.sl2.inPoint = T;
    return { cut: T, r2: r2, rho1: rho1, inf2In: inf2In, frames: N };
  };

  // 3) Mockup hand-off — flat UI accelerates into the cut, the device shot takes the energy on ANOTHER property.
  // scrollInto o: {prop, from, to, cut, ta:3.0, r:2.5}  (ends exactly on the cut frame)
  SM.scrollInto = function (comp, o) {
    var T = SM.fr(comp, o.cut), ta = o.ta || 3.0;
    return SM.seg(o.prop, SM.fr(comp, T - ta), o.from, T, o.to, [0, 50], [o.r || 2.5, 15]);
  };
  // settleAfterCut o: {prop, from, to, cut, dur:1.2, r:3.5, inf1:20, inf2:95}  (exponential-looking settle, tau ~0.2 s)
  SM.settleAfterCut = function (comp, o) {
    var T = SM.fr(comp, o.cut);
    return SM.seg(o.prop, T, o.from, SM.fr(comp, T + (o.dur || 1.2)), o.to, [o.r || 3.5, o.inf1 || 20], [0, o.inf2 || 95]);
  };

  // 4) Overlapping keyframes 2D — A->B on the object, B->C on a parent null that starts mid-way through A->B.
  // o: {layer, A, B, C, t0, mode:"render"|"taught", D, name}
  //   render (default): object 0->D out74/in56; null 0.42D->1.342D out67/in69; D = 1.39 s   (matches the author's render)
  //   taught:           Easy Ease everywhere; null 0.5D->1.62D; D = 0.95 s                 (as drawn on the timeline)
  SM.OVERLAP2D = {
    render: { D: 1.39, ns: 0.42, ne: 1.342, oOut: 74, oIn: 56, nOut: 67, nIn: 69 },
    taught: { D: 0.95, ns: 0.5, ne: 1.62, oOut: 33.333, oIn: 33.333, nOut: 33.333, nIn: 33.333 }
  };
  SM.overlap2D = function (comp, o) {
    var R = SM.OVERLAP2D[o.mode || "render"], D = o.D || R.D, t0 = SM.fr(comp, o.t0 || 0);
    var L = o.layer, pos = SM.tr(L, "ADBE Position");
    var tA = t0, tB = SM.fr(comp, t0 + D);
    SM.seg(pos, tA, o.A, tB, o.B, [0, R.oOut], [0, R.oIn]);
    var nul = SM.addNull(comp, o.name || "MOVE_2", o.B);          // pivot at B, identity transform
    SM.parentAt(comp, L, nul, tA);                                  // parent BEFORE the null's keys
    var np = SM.tr(nul, "ADBE Position"), tS = SM.fr(comp, t0 + R.ns * D), tE = SM.fr(comp, t0 + R.ne * D);
    SM.seg(np, tS, o.B, tE, o.C, [0, R.nOut], [0, R.nIn]);         // null moves by (C - B)
    return { nul: nul, tA: tA, tB: tB, tS: tS, tE: tE };
  };

  // The "amateur" reference: three keys on one layer, Easy Ease, straight path -> full stop at B.
  // o: {layer, A, B, C, t0, D1:0.95, D2:0.917}
  SM.sequential2D = function (comp, o) {
    var pos = SM.tr(o.layer, "ADBE Position"), t0 = SM.fr(comp, o.t0 || 0);
    var tB = SM.fr(comp, t0 + (o.D1 || 0.95)), tC = SM.fr(comp, tB + (o.D2 || 0.917));
    SM.seg(pos, t0, o.A, tB, o.B, SM.EASY, SM.EASY);
    SM.seg(pos, tB, o.B, tC, o.C, SM.EASY, SM.EASY);
    SM.linearPath(pos);
    return { tA: t0, tB: tB, tC: tC };
  };

  // 5) Null chain — N overlapping moves through points P0..Pn. Move 1 on the object, every next move on a NEW
  // null that becomes the new root (object -> MOVE_2 -> MOVE_3 -> ...). o: {layer, points, t0, D, step:0.5, inf:33.333}
  SM.overlapChain = function (comp, o) {
    var P = o.points, D = o.D || 0.95, step = o.step || 0.5, inf = o.inf || 33.333, t = SM.fr(comp, o.t0 || 0);
    var pos = SM.tr(o.layer, "ADBE Position");
    SM.seg(pos, t, P[0], SM.fr(comp, t + D), P[1], [0, inf], [0, inf]);
    var child = o.layer, nulls = [];
    for (var k = 1; k < P.length - 1; k++) {
      t = SM.fr(comp, t + step * D);
      var nul = SM.addNull(comp, "MOVE_" + (k + 1), P[k]);
      SM.parentAt(comp, child, nul, 0);
      SM.seg(SM.tr(nul, "ADBE Position"), t, P[k], SM.fr(comp, t + D), P[k + 1], [0, inf], [0, inf]);
      child = nul; nulls.push(nul);
    }
    return { nulls: nulls };
  };

  // 6) Overlapping keyframes 3D — object keys A->B (Position + X/Y/Z Rotation); a 3D null receives the object's
  // B pose at the mid-point of the first move, THEN the object is parented, then the null gets the C pose.
  // Pasting the B pose puts the null's pivot and axes on the object, so the null's rotation spins the object in
  // place instead of swinging it around a distant point.
  // o: {layer, A:{pos,rot}, B:{pos,rot}, C:{pos,rot}, t0, D1:2.1, mode:"taught"|"render", name}
  //   taught (default): Easy Ease, null starts 0.513*D1, lasts 1.08*D1
  //   render:           influence 64 everywhere, null starts 0.47*D1, lasts 1.25*D1 (only with poses fitted to it)
  SM.OVERLAP3D = { taught: { ns: 0.513, d2: 1.08, inf: 33.333 }, render: { ns: 0.47, d2: 1.25, inf: 64 } };
  SM._pose3 = function (layer) {
    return [SM.tr(layer, "ADBE Position"), SM.tr(layer, "ADBE Rotate X"), SM.tr(layer, "ADBE Rotate Y"), SM.tr(layer, "ADBE Rotate Z")];
  };
  SM._poseSeg = function (props, t1, P1, t2, P2, inf) {
    SM.seg(props[0], t1, P1.pos, t2, P2.pos, [0, inf], [0, inf]);
    for (var i = 0; i < 3; i++) {
      if (P1.rot[i] !== P2.rot[i]) SM.seg(props[i + 1], t1, P1.rot[i], t2, P2.rot[i], [0, inf], [0, inf]);
      else if (props[i + 1].numKeys === 0) props[i + 1].setValue(P1.rot[i]);
    }
  };
  SM.overlap3D = function (comp, o) {
    var R = SM.OVERLAP3D[o.mode || "taught"], D1 = o.D1 || 2.1, L = o.layer;
    L.threeDLayer = true;
    var tA = SM.fr(comp, o.t0 || 0), tB = SM.fr(comp, tA + D1);
    SM._poseSeg(SM._pose3(L), tA, o.A, tB, o.B, R.inf);
    var nul = comp.layers.addNull(comp.duration); nul.name = o.name || "MOVE_2"; nul.label = 9;
    nul.threeDLayer = true;                                        // 1) make the null 3D
    SM.tr(nul, "ADBE Anchor Point").setValue([0, 0, 0]);
    var tS = SM.fr(comp, tA + R.ns * D1), tE = SM.fr(comp, tS + R.d2 * D1);
    var np = SM._pose3(nul);
    // 2) "paste" the object's B pose onto the null at the mid-point (its first keys)
    SM.key(np[0], tS, o.B.pos);
    for (var i = 0; i < 3; i++) SM.key(np[i + 1], tS, o.B.rot[i]);
    // 3) only now parent (compensation at a time the null still holds the B pose)
    SM.parentAt(comp, L, nul, tA);
    // 4) C pose on the NULL (never on the object: a third object key brings the pause back)
    SM._poseSeg(np, tS, o.B, tE, o.C, R.inf);
    return { nul: nul, tA: tA, tB: tB, tS: tS, tE: tE };
  };

  // 7) Object entrance (match-cut "object swap"): linear drop-in + inertial bounce, Size X widens from a
  // square, an optional button (NOT parented) rides the right inner edge and spins one full turn.
  // o: {layer, t, drop:217, dropDur:0.117, width, widen:0.98, button, buttonPad:65}
  SM.BOUNCE = "var amp=.0375,freq=1.8,decay=3.2,n=0;if(numKeys>0){n=nearestKey(time).index;if(key(n).time>time)n--;}" +
    "if(n>0&&n==numKeys&&time>key(n).time){var t=time-key(n).time;var v=velocityAtTime(key(n).time-thisComp.frameDuration/10);" +
    "value+v*amp*Math.sin(freq*t*2*Math.PI)/Math.exp(decay*t);}else{value;}";
  SM.entrance = function (comp, o) {
    var L = o.layer, t = SM.fr(comp, o.t), pos = SM.tr(L, "ADBE Position"), rest = pos.valueAtTime(t, false);
    var t2 = SM.fr(comp, t + (o.dropDur || 0.117));
    SM.key(pos, t, [rest[0], rest[1] + (o.drop === undefined ? 217 : o.drop)]);
    SM.key(pos, t2, [rest[0], rest[1]]);                            // stays LINEAR on purpose
    pos.expression = SM.BOUNCE;
    var sz = SM.rectSize(L), s0 = sz.valueAtTime(t, false), tW = SM.fr(comp, t + (o.widen || 0.98));
    if (o.width) SM.seg(sz, t, [s0[1], s0[1]], tW, [o.width, s0[1]], [0, 75], [0, 75]);
    if (o.button) {
      SM.pinInside(o.button, L, { side: "right", pad: o.buttonPad || 65 });
      var rot = SM.tr(o.button, "ADBE Rotate Z");
      SM.seg(rot, t, 0, tW, 360, [0, 75], [0, 75]);
    }
    return { t: t, settled: SM.fr(comp, t + 1.2) };
  };

  // 8) Typing text + caret. o: {t0, cps:30, text}; caret o: {width:3, height:40, gap:6, color}
  SM.typeOn = function (textLayer, o) {
    var s = String(o.text).replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, "\\r");
    textLayer.property("ADBE Text Properties").property("ADBE Text Document").expression =
      'var s="' + s + '",t0=' + o.t0 + ',cps=' + (o.cps || 30) + ';s.substr(0,Math.max(0,Math.floor((time-t0)*cps)));';
    return { tEnd: o.t0 + o.text.length / (o.cps || 30) };
  };
  SM.caret = function (comp, textLayer, o) {
    o = o || {};
    var c = SM.card(comp, { name: textLayer.name + " caret", size: [o.width || 3, o.height || 40], radius: 1, color: o.color || "#FFFFFF" });
    SM.tr(c, "ADBE Position").expression = 'var T=thisComp.layer(' + SM.q(textLayer.name) + ');var r=T.sourceRectAtTime(time,false);' +
      'var p=T.toComp([r.left+r.width,r.top+r.height/2]);[p[0]+' + (o.gap || 6) + ',p[1]];';
    SM.tr(c, "ADBE Opacity").expression = 'var t0=' + o.t0 + ',tEnd=' + o.tEnd + ';' +
      'if(time<t0-2*thisComp.frameDuration){0}else if(time<tEnd){100}else{(Math.floor((time-tEnd)*4)%2)?0:100}';
    c.moveBefore(textLayer);
    return c;
  };

  // ================================================================= QA (sampling, no rendering)
  SM.qa = {};
  // world (screen) position of a layer's anchor at time t, through an expression sampler
  SM.qa.sampler = function (comp, layer) {
    var s = comp.layers.addNull(comp.duration); s.name = "__SM_SAMPLER"; s.enabled = false;
    var p = SM.tr(s, "ADBE Position");
    p.expression = 'var L=thisComp.layer(' + layer.index + ');var q=L.toComp(L.anchorPoint);[q[0],q[1]];';
    return { at: function (t) { return p.valueAtTime(t, false); }, remove: function () { s.remove(); } };
  };
  SM.qa._dist = function (a, b) { return Math.sqrt((a[0] - b[0]) * (a[0] - b[0]) + (a[1] - b[1]) * (a[1] - b[1])); };

  // Zoom: where does the largest per-frame scale step fall, and how big is it vs the amplitude?
  SM.qa.zoom = function (comp, z) {
    var fd = comp.frameDuration, sc = SM.tr(z.nul, "ADBE Scale"), best = -1, at = 0;
    var a = sc.valueAtTime(z.t1, false)[0], b = sc.valueAtTime(z.t2, false)[0];
    for (var t = z.t1; t < z.t2 - fd / 2; t += fd) {
      var d = Math.abs(sc.valueAtTime(t + fd, false)[0] - sc.valueAtTime(t, false)[0]);
      if (d > best) { best = d; at = t; }
    }
    var frac = best / Math.abs(b - a), onCut = Math.abs(at + fd - z.cut) < fd / 2;
    return { largestStepEndsOnCut: onCut, stepFrac: frac, pass: onCut && frac >= 0.33 };
  };

  // UI morph: relative speed rho on both sides of the cut must match (0.97-1.03).
  SM.qa.uiMorph = function (comp, o, m) {
    var fd = comp.frameDuration, ax = (o.axis === "x") ? 0 : 1, dt = fd / 20;
    var s1 = SM.rectSize(o.sl1), s2 = SM.rectSize(o.sl2), T = m.cut;
    var h1 = s1.valueAtTime(T - fd, false)[ax], v1 = (h1 - s1.valueAtTime(T - fd - dt, false)[ax]) / dt;
    var h2 = s2.valueAtTime(T, false)[ax], v2 = (s2.valueAtTime(T + dt, false)[ax] - h2) / dt;
    var ratio = (v2 / h2) / (v1 / h1);
    return { rho1: v1 / h1, rho2: v2 / h2, ratio: ratio, pass: ratio >= 0.97 && ratio <= 1.03 };
  };

  // Path metrics for overlap (2D or projected 3D): peak speed, minimum speed inside the turn window,
  // closest approach to point B. win = [t0, t1] of the turn (default: whole range).
  SM.qa.path = function (comp, layer, o) {
    var fd = comp.frameDuration, S = SM.qa.sampler(comp, layer), pts = [], t;
    for (t = o.t0; t <= o.t1 + 1e-6; t += fd / 2) pts.push({ t: t, p: S.at(t) });
    S.remove();
    var peak = 0, i, sp = [];
    for (i = 1; i < pts.length; i++) {
      var v = SM.qa._dist(pts[i].p, pts[i - 1].p) / (fd / 2); sp.push({ t: pts[i].t, v: v }); if (v > peak) peak = v;
    }
    var w0 = o.win ? o.win[0] : o.t0, w1 = o.win ? o.win[1] : o.t1, vmin = 1e9, tmin = 0;
    for (i = 0; i < sp.length; i++) if (sp[i].t >= w0 && sp[i].t <= w1 && sp[i].v < vmin) { vmin = sp[i].v; tmin = sp[i].t; }
    var closest = 1e9;
    if (o.B) for (i = 0; i < pts.length; i++) closest = Math.min(closest, SM.qa._dist(pts[i].p, o.B));
    var res = { peak: peak, minInTurn: vmin, minFrac: vmin / peak, tMin: tmin };
    if (o.B && o.A) { res.closestToB = closest; res.closestFrac = closest / SM.qa._dist(o.A, o.B); }
    return res;
  };

  // Speed of a property sampled per frame (|dv|/dt), for printing a speed graph as text.
  SM.qa.speedGraph = function (comp, prop, t0, t1, dim) {
    var fd = comp.frameDuration, out = [];
    for (var t = t0; t < t1 - fd / 2; t += fd) {
      var a = prop.valueAtTime(t, false), b = prop.valueAtTime(t + fd, false);
      var d = SM.isArr(a) ? (dim === undefined ? SM.qa._dist(a, b) : Math.abs(b[dim] - a[dim])) : Math.abs(b - a);
      out.push(Math.round(d / fd));
    }
    return out;
  };

  // ================================================================= stills for review
  // Writes 16-bit PNGs asynchronously; scripts/stills.py waits for them and builds a contact sheet.
  SM.shoot = function (comp, times, folder, prefix) {
    var dir = new Folder(folder); if (!dir.exists) dir.create();
    var out = [];
    for (var i = 0; i < times.length; i++) {
      var fnum = Math.round(times[i] / comp.frameDuration), s = "00000" + fnum;
      var f = new File(folder + "/" + (prefix || comp.name) + "_" + s.substr(s.length - 5) + ".png");
      comp.saveFrameToPng(fnum * comp.frameDuration, f); out.push(f.fsName);
    }
    return out;
  };
})(SM);
