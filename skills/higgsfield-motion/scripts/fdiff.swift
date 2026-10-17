// fdiff — frame-difference scan of the ENCODED film (MP4 / MOV): one-frame glitches, jumps, freezes, dead air, timing.
// Run it on every version before it is sent: whole-frame luma once said "clean" while 18 local defects existed, and a
// version that went out before QA came back with «там есть пару дефектов».
//
// usage: fdiff <film.mp4> [--from s] [--to s] [--until s] [--at s] [--csv out.csv] [--out dir] [--fail]
//              [--spike 3] [--floor 3] [--ratio 2] [--freeze 6] [--still 0.15] [--moving 2] [--dead 8] [--dead-min 0.2]
//
// Every decoded frame (presentation order) is reduced to a 384-px-wide grey grid and compared with the previous one:
//   mad       mean |Δluma| over the whole frame (0–255)          → energy of the change
//   blockmax  the largest mean |Δluma| of any 12×12 block         → LOCAL change (a cursor or a chip on a still frame)
// Findings, each with frame number, seconds and the player timecode (m:ss + frame):
//   OUTLIER   a frame that differs from BOTH neighbours much more than they differ from each other
//             (min(dAB, dBC) > --floor and ≥ --ratio (2) × dAC): a one-frame swap, a stray layer, a flash. Fast
//             continuous motion keeps dAC ≈ dAB ≈ dBC and is not flagged. Designed
//             flashes (≤ 2 frames, drop / lift / final hit only) show here too — confirm each one is intended.
//   JUMP      mad ≥ --spike × the local median (±6 frames) and ≥ --floor: a cut, a pop, a slam. Cuts are expected;
//             pull stills every 2 frames ±0.5 s around each one and read them.
//   FREEZE    ≥ --freeze (6) consecutive frames with mad < --still (0.15) — "mid-motion" when the picture moves
//             (mean mad > --moving) both before and after: a stall, a dropped seek, a held render. A planned hold
//             (end lockup) has motion only on one side.
//   DEAD AIR  blockmax < --dead (8/255) for ≥ --dead-min (0.2 s) before --until: nothing new is happening. Allowed only
//             as a listed read (status 1.0 s, name + ✓ 0.6–0.7 s, three numbers 1.2 s, list item 0.8 s, end lockup 2 s).
//   TIMING    frame durations that differ from the nominal 1/fps by > 1 ms (an unaligned seam: one 8 ms frame and
//             24.023 fps once came out of an AVMutableComposition), the frame count and the real fps.
// --at s     the user's screenshot shows the player at 0:12 → `--at 12` prints every frame of that second with its numbers.
// --out dir  writes JPEGs (640 px) of each flagged frame with its neighbours: <dir>/f<frame>_<kind>.jpg — read them.
// --csv f    frame,t,mad,blockmax,ratio for a chart.
// Exit code: 0 · 1 usage / unreadable file · 2 with --fail when an OUTLIER, a mid-motion FREEZE or a TIMING error exists.
// Companion: scripts/activity.mjs (the same dead-air metric on a frames folder, with event gaps and a PNG chart).
// Build (macOS): swiftc -O fdiff.swift -o fdiff   (or scripts/setup.sh). Needs macOS 13+.
import AVFoundation
import CoreImage
import Foundation

func fail(_ msg: String, code: Int32 = 1) -> Never {
    FileHandle.standardError.write("fdiff: \(msg)\n".data(using: .utf8)!)
    exit(code)
}
final class Box<T>: @unchecked Sendable { var value: T?; init() {} }
func blocking<T>(_ body: @escaping @Sendable () async throws -> T) throws -> T {
    let box = Box<Result<T, Error>>(), sem = DispatchSemaphore(value: 0)
    Task.detached { do { box.value = .success(try await body()) } catch { box.value = .failure(error) }; sem.signal() }
    sem.wait()
    return try box.value!.get()
}

// ---------------------------------------------------------------- arguments
var args = Array(CommandLine.arguments.dropFirst())
let USAGE = "usage: fdiff <film.mp4> [--from s] [--to s] [--until s] [--at s] [--csv f] [--out dir] [--fail] [--spike 3] [--floor 3] [--ratio 2] [--freeze 6] [--still 0.15] [--moving 2] [--dead 8] [--dead-min 0.2]"
var opts: [String: String] = [:]
var flags = Set<String>()
var positional: [String] = []
let valueKeys: Set<String> = ["--from", "--to", "--until", "--at", "--csv", "--out", "--spike", "--floor", "--ratio", "--freeze", "--still", "--moving", "--dead", "--dead-min"]
var ai = 0
while ai < args.count {
    let a = args[ai]
    if valueKeys.contains(a) {
        guard ai + 1 < args.count else { fail("\(a) needs a value\n\(USAGE)", code: 1) }
        opts[a] = args[ai + 1]; ai += 2; continue
    }
    if a == "--fail" || a == "--help" || a == "-h" { flags.insert(a); ai += 1; continue }
    if a.hasPrefix("--") { fail("unknown option \(a)\n\(USAGE)") }
    positional.append(a); ai += 1
}
if flags.contains("--help") || flags.contains("-h") || positional.count != 1 { print(USAGE); exit(positional.count == 1 ? 0 : 1) }
func num(_ k: String, _ d: Double) -> Double {
    guard let s = opts[k] else { return d }
    guard let v = Double(s), v.isFinite else { fail("\(k) must be a number (got \(s))") }
    return v
}
let path = positional[0]
guard FileManager.default.fileExists(atPath: path) else { fail("no such file: \(path)") }
let SPIKE = num("--spike", 3), FLOOR = num("--floor", 3), RATIO = num("--ratio", 2), FREEZE = Int(num("--freeze", 6)), STILL = num("--still", 0.15)
let MOVING = num("--moving", 2), DEAD = num("--dead", 8), DEADMIN = num("--dead-min", 0.2)
let FROM = num("--from", 0), TO = num("--to", .infinity)
let AT: Double? = opts["--at"].map { _ in num("--at", 0) }

// ---------------------------------------------------------------- open
let url = URL(fileURLWithPath: path)
let asset = AVURLAsset(url: url)
let vtrack: AVAssetTrack
do {
    guard let t = try blocking({ try await asset.loadTracks(withMediaType: .video).first }) else { fail("\(url.lastPathComponent) has no video track") }
    vtrack = t
} catch { fail("cannot read \(path): \(error.localizedDescription)") }
let duration = CMTimeGetSeconds((try? blocking { try await asset.load(.duration) }) ?? .zero)
let nominal = Double((try? blocking { try await vtrack.load(.nominalFrameRate) }) ?? 0)
let natural = (try? blocking { try await vtrack.load(.naturalSize) }) ?? .zero
let audioTracks = (try? blocking { try await asset.loadTracks(withMediaType: .audio) }) ?? []
let UNTIL = num("--until", duration)

// ---------------------------------------------------------------- decode → grey grid
let GW = 384, BS = 12
var GH = 216
var gridReady = false
func makeReader(_ fmt: OSType) -> (AVAssetReader, AVAssetReaderTrackOutput) {
    let reader: AVAssetReader
    do { reader = try AVAssetReader(asset: asset) } catch { fail("cannot open a reader: \(error.localizedDescription)") }
    let out = AVAssetReaderTrackOutput(track: vtrack, outputSettings: [kCVPixelBufferPixelFormatTypeKey as String: fmt])
    out.alwaysCopiesSampleData = false
    guard reader.canAdd(out) else { fail("cannot decode the video track") }
    reader.add(out)
    if FROM > 0 || TO.isFinite {
        let start = CMTime(seconds: max(0, FROM - 0.5), preferredTimescale: 600)
        let end = TO.isFinite ? CMTime(seconds: TO + 0.5, preferredTimescale: 600) : .positiveInfinity
        reader.timeRange = CMTimeRange(start: start, end: end)
    }
    guard reader.startReading() else { fail("decode failed: \(reader.error?.localizedDescription ?? "unknown")") }
    return (reader, out)
}

/// box-averaged luma grid (GW × GH) from the Y plane of a full-range 4:2:0 buffer
func grid(_ pb: CVPixelBuffer) -> [Float] {
    CVPixelBufferLockBaseAddress(pb, .readOnly); defer { CVPixelBufferUnlockBaseAddress(pb, .readOnly) }
    let w = CVPixelBufferGetWidthOfPlane(pb, 0), h = CVPixelBufferGetHeightOfPlane(pb, 0)
    let rb = CVPixelBufferGetBytesPerRowOfPlane(pb, 0)
    guard let base = CVPixelBufferGetBaseAddressOfPlane(pb, 0)?.assumingMemoryBound(to: UInt8.self) else { fail("no luma plane") }
    if !gridReady { GH = max(BS, Int((Double(GW) * Double(h) / Double(w) / Double(BS)).rounded()) * BS); gridReady = true }
    var g = [Float](repeating: 0, count: GW * GH), n = [Float](repeating: 0, count: GW * GH)
    for y in 0..<h {
        let gy = min(GH - 1, y * GH / h), row = base + y * rb, o = gy * GW
        for x in 0..<w { let gx = min(GW - 1, x * GW / w); g[o + gx] += Float(row[x]); n[o + gx] += 1 }
    }
    for i in 0..<g.count { g[i] /= max(1, n[i]) }
    return g
}
func mad(_ a: [Float], _ b: [Float]) -> Double {
    var s: Float = 0; for i in 0..<a.count { s += abs(a[i] - b[i]) }; return Double(s) / Double(a.count)
}
func blockmax(_ a: [Float], _ b: [Float]) -> Double {
    let bw = GW / BS, bh = GH / BS
    var best: Float = 0
    for by in 0..<bh { for bx in 0..<bw {
        var s: Float = 0
        for y in (by * BS)..<(by * BS + BS) { let o = y * GW + bx * BS; for x in 0..<BS { s += abs(a[o + x] - b[o + x]) } }
        best = max(best, s)
    } }
    return Double(best) / Double(BS * BS)
}

struct Row { var i: Int; var t: Double; var mad: Double; var bmax: Double; var dAC: Double }
var rows: [Row] = []
var pts: [Double] = []
do {
    let (reader, out) = makeReader(kCVPixelFormatType_420YpCbCr8BiPlanarFullRange)
    var prev: [Float]? = nil, prev2: [Float]? = nil
    var idx = 0
    while let sb = out.copyNextSampleBuffer() {
        guard CMSampleBufferGetNumSamples(sb) > 0, let pb = CMSampleBufferGetImageBuffer(sb) else { continue }
        let t = CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(sb))
        if t < FROM - 0.5 - 1e-6 { continue }
        if TO.isFinite && t > TO + 0.5 { break }
        let g = grid(pb)
        pts.append(t)
        if let p = prev {
            rows.append(Row(i: idx, t: t, mad: mad(g, p), bmax: blockmax(g, p), dAC: prev2.map { mad(g, $0) } ?? .nan))
        } else {
            rows.append(Row(i: idx, t: t, mad: .nan, bmax: .nan, dAC: .nan))
        }
        prev2 = prev; prev = g; idx += 1
    }
    if reader.status == .failed { fail("decode failed at frame \(idx): \(reader.error?.localizedDescription ?? "unknown")") }
}
guard rows.count >= 3 else { fail("only \(rows.count) frame(s) decoded — nothing to compare") }

// frame numbers: from the presentation time on the real grid (a range read starts mid-film)
let fdur: Double = {
    let ds = zip(pts.dropFirst(), pts).map { $0 - $1 }.filter { $0 > 0 }.sorted()
    if nominal > 0 { return 1 / nominal }
    return ds.isEmpty ? 1 / 24 : ds[ds.count / 2]
}()
let fps = 1 / fdur
func fnum(_ t: Double) -> Int { Int((t / fdur).rounded()) }
func tc(_ t: Double) -> String {
    let n = fnum(t), fr = Int(fps.rounded()), s = n / max(1, fr), f = n % max(1, fr)
    return String(format: "%d:%02d+%02df", s / 60, s % 60, f)
}
func at(_ r: Row) -> String { String(format: "f%-5d %7.3f s  %@", fnum(r.t), r.t, tc(r.t)) }

// ---------------------------------------------------------------- findings (inside [FROM, TO])
let inRange = { (r: Row) -> Bool in r.t >= FROM - 1e-6 && r.t <= TO + 1e-6 }
struct Finding { var kind: String; var row: Row; var note: String }
var outliers: [Finding] = [], jumps: [Finding] = []
for k in 1..<(rows.count - 1) {
    let A = rows[k], B = rows[k + 1]           // A.mad = d(prev, A); B.mad = d(A, B); B.dAC = d(prev, B)
    guard inRange(A), A.mad.isFinite, B.mad.isFinite, B.dAC.isFinite else { continue }
    let lo = min(A.mad, B.mad), ratio = lo / max(B.dAC, 0.5)
    if lo > FLOOR && ratio >= RATIO {
        outliers.append(Finding(kind: "OUTLIER", row: A, note: String(format: "d(prev,f) %.1f · d(f,next) %.1f · d(prev,next) %.1f · ×%.1f", A.mad, B.mad, B.dAC, ratio)))
    }
}
for k in 1..<rows.count {
    let r = rows[k]
    guard inRange(r), r.mad.isFinite else { continue }
    var win: [Double] = []
    for j in max(1, k - 6)...min(rows.count - 1, k + 6) where j != k && rows[j].mad.isFinite { win.append(rows[j].mad) }
    win.sort()
    let med = win.isEmpty ? 0 : win[win.count / 2]
    if r.mad >= FLOOR && r.mad >= SPIKE * max(med, 0.3) && !outliers.contains(where: { $0.row.i == r.i || $0.row.i + 1 == r.i }) {
        let back = k + 1 < rows.count && rows[k + 1].dAC.isFinite && rows[k + 1].dAC < r.mad * 0.5
        jumps.append(Finding(kind: "JUMP", row: r, note: String(format: "mad %.1f vs local median %.2f (×%.1f)%@", r.mad, med, r.mad / max(med, 0.3), back ? " · returns next frame" : "")))
    }
}
var freezes: [(Row, Row, Int, Bool, Double, Double)] = []
do {
    var s: Int? = nil
    for k in 1...rows.count {
        let still = k < rows.count && rows[k].mad.isFinite && rows[k].mad < STILL && inRange(rows[k])
        if still && s == nil { s = k }
        if !still, let a = s {
            let n = k - a + 1                        // frames shown identically: the run's predecessor + the run
            if n >= FREEZE {
                let before = rows[max(1, a - 6)..<a].map { $0.mad }.filter { $0.isFinite }
                let after = rows[k..<min(rows.count, k + 6)].map { $0.mad }.filter { $0.isFinite }
                let mb = before.isEmpty ? 0 : before.reduce(0, +) / Double(before.count)
                let ma = after.isEmpty ? 0 : after.reduce(0, +) / Double(after.count)
                freezes.append((rows[a - 1], rows[k - 1], n, mb > MOVING && ma > MOVING, mb, ma))
            }
            s = nil
        }
    }
}
var dead: [(Double, Double)] = []
do {
    var s: Int? = nil
    for k in 1...rows.count {
        let d = k < rows.count && rows[k].bmax.isFinite && rows[k].bmax < DEAD && inRange(rows[k])
        if d && s == nil { s = k }
        if !d, let a = s {
            let t0 = rows[a].t, t1 = rows[k - 1].t + fdur   // unchanged frame steps × 1/fps (same metric as activity.mjs)
            if t1 - t0 >= DEADMIN - 1e-9 { dead.append((t0, t1)) }
            s = nil
        }
    }
}
let deadBefore = dead.filter { $0.0 < UNTIL - 1e-9 }.map { ($0.0, min($0.1, UNTIL)) }
let longest = deadBefore.map { $0.1 - $0.0 }.max() ?? 0, totalDead = deadBefore.map { $0.1 - $0.0 }.reduce(0, +)
var timing: [String] = []
for k in 1..<pts.count {
    let d = pts[k] - pts[k - 1]
    if abs(d - fdur) > 0.001 { timing.append(String(format: "f%d at %.4f s: %.2f ms (nominal %.2f ms)", k, pts[k], d * 1000, fdur * 1000)) }
}

// ---------------------------------------------------------------- report
let realFps = pts.count > 1 ? Double(pts.count - 1) / (pts.last! - pts.first!) : 0
print(String(format: "fdiff  %@  %dx%d  %d frames decoded  %.3f s  nominal %.3f fps  measured %.3f fps  audio %@",
             url.lastPathComponent, Int(natural.width), Int(natural.height), pts.count, duration, nominal, realFps, audioTracks.isEmpty ? "NONE" : "\(audioTracks.count) track(s)"))
if FROM > 0 || TO.isFinite { print(String(format: "range %.2f – %@ s", FROM, TO.isFinite ? String(format: "%.2f", TO) : "end")) }
print(String(format: "thresholds: outlier floor %.1f ×%.1f · jump ×%.1f · freeze ≥%d frames < %.2f · dead blockmax < %.0f for ≥ %.2f s", FLOOR, RATIO, SPIKE, FREEZE, STILL, DEAD, DEADMIN))
print("\nOUTLIERS (one-frame glitches; designed flashes show here too) — \(outliers.count)")
for f in outliers { print("  " + at(f.row) + "  " + f.note) }
print("\nJUMPS (cuts, pops, slams: read stills every 2 frames ±0.5 s around each) — \(jumps.count)")
for f in jumps { print("  " + at(f.row) + "  " + f.note) }
print("\nFREEZES (≥ \(FREEZE) identical frames) — \(freezes.count)")
for (a, b, n, mid, mb, ma) in freezes {
    print("  " + at(a) + String(format: "  → f%d  %d frames (%.2f s)  %@", fnum(b.t), n, Double(n) * fdur, mid ? String(format: "MID-MOTION (motion before %.1f, after %.1f): a stall?", mb, ma) : String(format: "hold (before %.1f, after %.1f)", mb, ma)))
}
print(String(format: "\nDEAD AIR (no local change ≥ %.2f s) before %.2f s — longest %.2f s · total %.2f s", DEADMIN, UNTIL, longest, totalDead))
for (a, b) in dead { print(String(format: "  %7.3f → %7.3f s  %.2f s  (%@ → %@)%@", a, b, b - a, tc(a), tc(b), a >= UNTIL - 1e-9 ? "  after --until" : "")) }
print("\nTIMING — \(timing.isEmpty ? "constant frame rate, every frame \(String(format: "%.2f", fdur * 1000)) ms" : "\(timing.count) irregular frame(s)")")
for s in timing.prefix(12) { print("  " + s) }
if abs(Double(pts.count) - duration * fps) > 1.5 && !(FROM > 0 || TO.isFinite) { print(String(format: "  frame count %d ≠ duration × fps = %.1f", pts.count, duration * fps)) }

if let s = AT {
    print(String(format: "\nFRAMES OF SECOND %.0f (player %d:%02d)", s.rounded(.down), Int(s) / 60, Int(s) % 60))
    print("  frame    t        timecode    mad    blockmax  d(prev,next)")
    for r in rows where r.t >= s.rounded(.down) - 1e-6 && r.t < s.rounded(.down) + 1 - 1e-6 {
        print(String(format: "  f%-5d %7.3f  %@  %6.2f  %7.2f  %@", fnum(r.t), r.t, tc(r.t), r.mad.isFinite ? r.mad : 0, r.bmax.isFinite ? r.bmax : 0, r.dAC.isFinite ? String(format: "%.2f", r.dAC) : "—"))
    }
}

if let csv = opts["--csv"] {
    var s = "frame,t,mad,blockmax,d_prev_next\n"
    for r in rows { s += String(format: "%d,%.4f,%@,%@,%@\n", fnum(r.t), r.t, r.mad.isFinite ? String(format: "%.3f", r.mad) : "", r.bmax.isFinite ? String(format: "%.2f", r.bmax) : "", r.dAC.isFinite ? String(format: "%.3f", r.dAC) : "") }
    do { try s.write(toFile: csv, atomically: true, encoding: .utf8); print("\ncsv \(csv)") } catch { fail("cannot write \(csv): \(error.localizedDescription)") }
}

// ---------------------------------------------------------------- --out: JPEGs of flagged frames ± 1
if let outDir = opts["--out"] {
    var want: [Int: String] = [:]
    func mark(_ i: Int, _ kind: String) { for j in (i - 1)...(i + 1) where j >= 0 { if want[j] == nil || j == i { want[j] = j == i ? kind : (want[j] ?? "ctx") } } }
    for f in outliers { mark(f.row.i, "outlier") }
    for f in jumps { mark(f.row.i, "jump") }
    for (a, b, _, mid, _, _) in freezes where mid { mark(a.i, "freeze-start"); mark(b.i, "freeze-end") }
    let dir = URL(fileURLWithPath: outDir)
    do { try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true) } catch { fail("cannot create \(outDir)") }
    let (reader, out) = makeReader(kCVPixelFormatType_32BGRA)
    let ctx = CIContext(), cs = CGColorSpace(name: CGColorSpace.sRGB)!
    var idx = 0, written = 0
    let maxIdx = want.keys.max() ?? -1
    while idx <= maxIdx, let sb = out.copyNextSampleBuffer() {
        guard CMSampleBufferGetNumSamples(sb) > 0, let pb = CMSampleBufferGetImageBuffer(sb) else { continue }
        let t = CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(sb))
        if t < FROM - 0.5 - 1e-6 { continue }
        if let kind = want[idx] {
            var ci = CIImage(cvPixelBuffer: pb)
            let w = Double(CVPixelBufferGetWidth(pb))
            if w > 640 { let k = 640 / w; ci = ci.transformed(by: CGAffineTransform(scaleX: k, y: k)) }
            let f = dir.appendingPathComponent(String(format: "f%05d_%@.jpg", fnum(t), kind))
            do { try ctx.writeJPEGRepresentation(of: ci, to: f, colorSpace: cs, options: [kCGImageDestinationLossyCompressionQuality as CIImageRepresentationOption: 0.9]); written += 1 }
            catch { fail("cannot write \(f.path): \(error.localizedDescription)") }
        }
        idx += 1
    }
    reader.cancelReading()
    print("\nstills: \(written) JPEG(s) of flagged frames ± 1 → \(outDir)")
}

let midFreezes = freezes.filter { $0.3 }.count
let bad = outliers.count + midFreezes + timing.count
print(String(format: "\nSUMMARY  outliers %d · jumps %d · freezes %d (mid-motion %d) · dead air longest %.2f s / total %.2f s · timing %@",
             outliers.count, jumps.count, freezes.count, midFreezes, longest, totalDead, timing.isEmpty ? "CFR ok" : "\(timing.count) irregular"))
if flags.contains("--fail") && bad > 0 { print("FAIL: \(bad) finding(s) need a look before this version is sent"); exit(2) }
