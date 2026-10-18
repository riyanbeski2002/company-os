// Read-only inventory of the open AE project. Run: bash ae.sh probe.jsx out.txt
(function(){
var f = new File("__OUT__"); f.encoding = "UTF-8"; f.open("w");
try {
  var P = app.project;
  f.writeln("AE: " + app.version + "  project: " + (P.file ? P.file.fsName : "(unsaved)") + "  items=" + P.numItems + "  dirty=" + P.dirty);
  f.writeln("expressionEngine: " + P.expressionEngine);
  var ac = P.activeItem; f.writeln("active: " + (ac ? ac.name : "none"));
  for (var i = 1; i <= P.numItems; i++) {
    var it = P.item(i), k = (it instanceof CompItem) ? "COMP" : ((it instanceof FolderItem) ? "FLDR" : "FOOT");
    var ex = "";
    if (k == "COMP") ex = " " + it.width + "x" + it.height + " " + it.frameRate + "fps dur=" + it.duration + " layers=" + it.numLayers;
    f.writeln(k + " " + it.name + ex);
  }
} catch (e) { f.writeln("ERR " + e.toString() + " line " + e.line); }
f.close();
})();
