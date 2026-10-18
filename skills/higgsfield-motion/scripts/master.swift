// master — measure a mix and master it to the social-video target: −14 LUFS integrated, true peak ≤ −1.2 dBTP, 0 clipped
// samples. You cannot hear the film: these numbers are what you report.
// usage: master <in.wav|.aif|.m4a|…> [out.wav|out.m4a] [--lufs -14] [--tp -1.2] [--sections a-b,c-d,…]
//   no out    measure only: integrated loudness, LRA, true peak, sample peak, clipped samples (and --sections).
//   out.wav   24-bit PCM at the input rate (feed it to encode_av); out.m4a = AAC-LC 256 kbps (feed it to mux). An .m4a is
//             decoded again and re-measured, because AAC overshoots: ship at −1.2/−1.3 dBTP, not −1.0.
//   --sections  loudness of film-time ranges (ungated LUFS), e.g. to prove that loudness rises through the build.
// How: ITU-R BS.1770-4 (K-weighting, 400 ms blocks, 75 % overlap, −70 LUFS absolute and −10 LU relative gates; LRA per
// EBU Tech 3342), true peak from 4× polyphase oversampling (193-tap Kaiser sinc). One static gain moves the mix to the
// target; a 3 ms look-ahead true-peak limiter catches what would cross the ceiling, iterated until the integrated
// loudness lands within ±0.02 LU. If the limiter has to work hard (> 3 dB), the mix is too spiky: turn the impacts down
// in the mix instead of squashing them here. Mix dialogue first; this tool only sets the final level.
// Build (macOS): swiftc -O master.swift -o master   (or scripts/setup.sh)
// Elsewhere: ffmpeg -i mix.wav -af loudnorm=I=-14:TP=-1.2:LRA=11:print_format=summary out.wav (two-pass for accuracy)
import AVFoundation
import Foundation

func fail(_ msg: String, code: Int32 = 1) -> Never {
    FileHandle.standardError.write("master: \(msg)\n".data(using: .utf8)!)
    exit(code)
}
var argv = Array(CommandLine.arguments.dropFirst())
func flag(_ k: String) -> String? {
    guard let i = argv.firstIndex(of: k) else { return nil }
    guard i + 1 < argv.count else { fail("\(k) needs a value", code: 2) }
    let v = argv[i + 1]; argv.removeSubrange(i...(i + 1)); return v
}
let target = Double(flag("--lufs") ?? "-14") ?? -14
let ceilingDb = Double(flag("--tp") ?? "-1.2") ?? -1.2
let sectionsArg = flag("--sections")
guard argv.count >= 1 else { fail("usage: master <in> [out.wav|out.m4a] [--lufs -14] [--tp -1.2] [--sections a-b,…]", code: 2) }
let inURL = URL(fileURLWithPath: argv[0])
let outURL = argv.count > 1 ? URL(fileURLWithPath: argv[1]) : nil
if let o = outURL, !["wav", "m4a"].contains(o.pathExtension.lowercased()) { fail("output must be .wav or .m4a", code: 2) }

// ---- I/O
func readAudio(_ url: URL) -> (ch: [[Float]], sr: Double) {
    let f: AVAudioFile
    do { f = try AVAudioFile(forReading: url) } catch { fail("cannot read \(url.path): \(error.localizedDescription)") }
    let fmt = f.processingFormat, n = AVAudioFrameCount(f.length)
    guard n > 0, let buf = AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: n) else { fail("\(url.lastPathComponent) is empty") }
    do { try f.read(into: buf) } catch { fail("cannot decode \(url.lastPathComponent): \(error.localizedDescription)") }
    guard let data = buf.floatChannelData else { fail("unsupported sample format in \(url.lastPathComponent)") }
    let len = Int(buf.frameLength)
    let ch = (0..<Int(fmt.channelCount)).map { c in Array(UnsafeBufferPointer(start: data[c], count: len)) }
    return (ch, fmt.sampleRate)
}
func writeAudio(_ url: URL, _ ch: [[Float]], _ sr: Double) {
    try? FileManager.default.removeItem(at: url)
    let isAAC = url.pathExtension.lowercased() == "m4a"
    var settings: [String: Any] = [AVSampleRateKey: sr, AVNumberOfChannelsKey: ch.count]
    if isAAC {
        settings[AVFormatIDKey] = kAudioFormatMPEG4AAC; settings[AVEncoderBitRateKey] = 256_000
    } else {
        settings[AVFormatIDKey] = kAudioFormatLinearPCM; settings[AVLinearPCMBitDepthKey] = 24
        settings[AVLinearPCMIsFloatKey] = false; settings[AVLinearPCMIsBigEndianKey] = false; settings[AVLinearPCMIsNonInterleaved] = false
    }
    let n = ch[0].count
    guard let fmt = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: sr, channels: AVAudioChannelCount(ch.count), interleaved: false),
          let buf = AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: AVAudioFrameCount(n)) else { fail("cannot allocate the output buffer") }
    buf.frameLength = AVAudioFrameCount(n)
    for c in 0..<ch.count { ch[c].withUnsafeBufferPointer { buf.floatChannelData![c].update(from: $0.baseAddress!, count: n) } }
    do {
        let f = try AVAudioFile(forWriting: url, settings: settings, commonFormat: .pcmFormatFloat32, interleaved: false)
        try f.write(from: buf)
    } catch { fail("cannot write \(url.path): \(error.localizedDescription)") }   // the file closes when f goes out of scope
}

// ---- BS.1770-4
func kCoefs(_ sr: Double) -> [[Double]] {   // [b0,b1,b2,a1,a2] for the shelf and the RLB high-pass; exact table values at 48 kHz
    var f0 = 1681.974450955533, G = 3.999843853973347, Q = 0.7071752369554196
    var K = tan(Double.pi * f0 / sr)
    let Vh = pow(10, G / 20), Vb = pow(Vh, 0.4996667741545416), a0 = 1 + K / Q + K * K
    let shelf = [(Vh + Vb * K / Q + K * K) / a0, 2 * (K * K - Vh) / a0, (Vh - Vb * K / Q + K * K) / a0, 2 * (K * K - 1) / a0, (1 - K / Q + K * K) / a0]
    f0 = 38.13547087602444; Q = 0.5003270373238773; K = tan(Double.pi * f0 / sr); G = 0
    let d = 1 + K / Q + K * K
    return [shelf, [1, -2, 1, 2 * (K * K - 1) / d, (1 - K / Q + K * K) / d]]
}
let LK = { (z: Double) -> Double in -0.691 + 10 * log10(z + 1e-30) }
struct Meter { let integrated: Double; let lra: Double; let cs: [Double]; let sr: Double
    func window(_ a: Double, _ b: Double) -> Double {
        let n = cs.count - 1, i = max(0, min(n, Int((a * sr).rounded()))), j = max(0, min(n, Int((b * sr).rounded())))
        return j > i ? LK((cs[j] - cs[i]) / Double(j - i)) : -.infinity
    }
}
func meter(_ ch: [[Float]], _ sr: Double) -> Meter {
    let n = ch[0].count, co = kCoefs(sr)
    var power = [Double](repeating: 0, count: n)
    for x in ch {
        var a1 = 0.0, a2 = 0.0, b1 = 0.0, b2 = 0.0, c1 = 0.0, c2 = 0.0, d1 = 0.0, d2 = 0.0
        let s = co[0], r = co[1]
        x.withUnsafeBufferPointer { xp in
            for i in 0..<n {
                let xi = Double(xp[i])
                let u = s[0] * xi + s[1] * a1 + s[2] * a2 - s[3] * b1 - s[4] * b2; a2 = a1; a1 = xi; b2 = b1; b1 = u
                let v = r[0] * u + r[1] * c1 + r[2] * c2 - r[3] * d1 - r[4] * d2; c2 = c1; c1 = u; d2 = d1; d1 = v
                power[i] += v * v
            }
        }
    }
    var cs = [Double](repeating: 0, count: n + 1)
    for i in 0..<n { cs[i + 1] = cs[i] + power[i] }
    func ms(_ a: Int, _ b: Int) -> Double { b > a ? (cs[b] - cs[a]) / Double(b - a) : 0 }
    let blk = Int((0.4 * sr).rounded()), hop = Int((0.1 * sr).rounded())
    var z: [Double] = []
    var s = 0; while s + blk <= n { z.append(ms(s, s + blk)); s += hop }
    let absG = z.filter { LK($0) > -70 }
    let mean = { (a: [Double]) -> Double in a.reduce(0, +) / Double(max(1, a.count)) }
    let rel = absG.isEmpty ? -70 : LK(mean(absG)) - 10
    let gated = absG.filter { LK($0) > rel }
    let integrated = gated.isEmpty ? -Double.infinity : LK(mean(gated))
    var st: [Double] = []; let w3 = Int(3 * sr)
    s = 0; while s + w3 <= n { st.append(ms(s, s + w3)); s += hop }
    let stA = st.filter { LK($0) > -70 }, stRel = stA.isEmpty ? -70 : LK(mean(stA)) - 20
    let stG = stA.filter { LK($0) > stRel }.map(LK).sorted()
    let pct = { (p: Double) -> Double in stG[min(stG.count - 1, max(0, Int((p * Double(stG.count - 1)).rounded())))] }
    return Meter(integrated: integrated, lra: stG.isEmpty ? 0 : pct(0.95) - pct(0.10), cs: cs, sr: sr)
}
func besselI0(_ x: Double) -> Double { var s = 1.0, t = 1.0; for k in 1..<50 { t *= pow(x / (2 * Double(k)), 2); s += t; if t < 1e-12 * s { break } }; return s }
/// per-sample max |4× interpolated value| across channels, aligned to the input timeline
func truePeakEnv(_ ch: [[Float]], _ sr: Double) -> [Float] {
    let L = 4, taps = 48 * L + 1, M = taps - 1, fc = min(23000, 0.479 * sr) / (sr * Double(L)), beta = 8.0
    var h = [Double](repeating: 0, count: taps)
    for k in 0..<taps {
        let m = Double(k) - Double(M) / 2
        let s = m == 0 ? 2 * fc : sin(2 * Double.pi * fc * m) / (Double.pi * m)
        h[k] = s * besselI0(beta * sqrt(max(0, 1 - pow(2 * Double(k) / Double(M) - 1, 2)))) / besselI0(beta)
    }
    let phases: [[Double]] = (0..<L).map { p in let a = stride(from: p, to: taps, by: L).map { h[$0] }; let s = a.reduce(0, +); return a.map { $0 / s } }
    let delay = M / 2 / L, pad = 64, n = ch[0].count
    var env = [Float](repeating: 0, count: n)
    for x in ch {
        var xp = [Double](repeating: 0, count: n + 2 * pad + 64)
        for j in 0..<n { xp[j + pad] = Double(x[j]) }
        xp.withUnsafeBufferPointer { X in
            env.withUnsafeMutableBufferPointer { E in
                for j in 0..<n {
                    let i = j + delay + pad
                    var mx = abs(X[j + pad])
                    for ph in phases {
                        var s = 0.0
                        for k in 0..<ph.count { s += ph[k] * X[i - k] }
                        if abs(s) > mx { mx = abs(s) }
                    }
                    if Float(mx) > E[j] { E[j] = Float(mx) }
                }
            }
        }
    }
    return env
}
func db(_ v: Double) -> Double { 20 * log10(max(v, 1e-12)) }
struct Stats { let lufs: Double; let lra: Double; let tp: Double; let sp: Double; let clipped: Int; let m: Meter }
func stats(_ ch: [[Float]], _ sr: Double) -> Stats {
    let m = meter(ch, sr), env = truePeakEnv(ch, sr)
    var sp: Float = 0, clipped = 0
    for x in ch { for v in x { let a = abs(v); if a > sp { sp = a }; if a >= 0.99997 { clipped += 1 } } }
    return Stats(lufs: m.integrated, lra: m.lra, tp: db(Double(env.max() ?? 0)), sp: db(Double(sp)), clipped: clipped, m: m)
}
func line(_ tag: String, _ s: Stats) -> String {
    String(format: "%@ integrated %.2f LUFS · LRA %.1f LU · true peak %.2f dBTP · sample peak %.2f dBFS · clipped samples %d",
           tag, s.lufs, s.lra, s.tp, s.sp, s.clipped)
}
func printSections(_ s: Stats) {
    guard let arg = sectionsArg else { return }
    for r in arg.split(separator: ",") {
        let p = r.split(separator: "-").compactMap { Double($0) }
        guard p.count == 2, p[1] > p[0] else { print("section '\(r)' ignored (use a-b in seconds)"); continue }
        print(String(format: "section %6.2f–%-6.2f %7.2f LUFS", p[0], p[1], s.m.window(p[0], p[1])))
    }
}

// ---- measure
let (X, sr) = readAudio(inURL)
let n = X[0].count
print(String(format: "in     %@ · %.0f Hz · %d ch · %.3f s", inURL.lastPathComponent, sr, X.count, Double(n) / sr))
let before = stats(X, sr)
print(line("before", before))
if before.clipped > 0 { print("WARN   the input already clips (\(before.clipped) samples at full scale): render the mix with headroom") }
guard let outFile = outURL else {
    let okL = abs(before.lufs - target) <= 0.5, okT = before.tp <= ceilingDb + 0.05
    printSections(before)
    print(okL && okT && before.clipped == 0 ? "ok     within \(target) ±0.5 LUFS and ≤ \(ceilingDb) dBTP" : String(format: "check  target %.1f LUFS / %.1f dBTP: %@%@", target, ceilingDb, okL ? "" : "loudness off ", okT ? "" : "peaks too high"))
    exit(0)
}
guard before.lufs.isFinite, before.lufs > -70 else { fail("the input is silent (below −70 LUFS)") }

// ---- gain + look-ahead true-peak limiter, iterated onto the target
let P = truePeakEnv(X, sr)
let ceilLin = pow(10, ceilingDb / 20)
let la = max(1, Int(0.003 * sr))
func limiterGain(_ g: Double) -> [Float] {
    var r = [Float](repeating: 1, count: n)
    for i in 0..<n { r[i] = Float(min(1, ceilLin / (g * Double(P[i]) + 1e-12))) }
    var m = [Float](repeating: 1, count: n)            // min over [i, i + la] (monotone deque, right to left)
    var dq = [Int](repeating: 0, count: n); var h = 0, t = 0
    var i = n - 1
    while i >= 0 {
        while t > h && r[dq[t - 1]] >= r[i] { t -= 1 }
        dq[t] = i; t += 1
        while dq[h] > i + la { h += 1 }
        m[i] = r[dq[h]]; i -= 1
    }
    let aR = Float(1 - exp(-1 / (0.07 * sr)))           // instant attack, 70 ms release
    var prev: Float = 1
    for k in 0..<n { let v = m[k]; prev = v < prev ? v : prev + (v - prev) * aR; m[k] = prev }
    var out = [Float](repeating: 1, count: n); var acc: Double = 0   // smooth the attack over the look-ahead window
    for k in 0..<n { acc += Double(m[k]); if k > la { acc -= Double(m[k - la - 1]) }; out[k] = Float(acc / Double(min(k + 1, la + 1))) }
    return out
}
var g = pow(10, (target - before.lufs) / 20)
var lim = [Float](), Y = X
for _ in 0..<8 {
    lim = limiterGain(g)
    Y = X.map { x in (0..<n).map { x[$0] * Float(g) * lim[$0] } }
    let L = meter(Y, sr).integrated
    if abs(L - target) < 0.02 { break }
    g *= pow(10, (target - L) / 20)
}
var after = stats(Y, sr)
if after.tp > ceilingDb {   // inter-sample residue after a time-varying gain: one small static trim
    let k = Float(pow(10, (ceilingDb - 0.03 - after.tp) / 20))
    Y = Y.map { $0.map { $0 * k } }; lim = lim.map { $0 * k }
    after = stats(Y, sr)
}
var minLim: Float = 1, minAt = 0, over1 = 0
for i in 0..<n { if lim[i] < minLim { minLim = lim[i]; minAt = i }; if lim[i] < 0.891 { over1 += 1 } }
print(String(format: "gain   %+.2f dB · limiter max %.2f dB at %.3f s · %.2f %% of the time over 1 dB", db(g), max(0, -db(Double(minLim))), Double(minAt) / sr, 100 * Double(over1) / Double(n)))
print(line("after ", after))
if -db(Double(minLim)) > 3 { print("WARN   the limiter takes more than 3 dB: lower the loudest hits in the mix rather than squashing them here") }
if abs(after.lufs - target) > 0.1 { print(String(format: "WARN   landed at %.2f LUFS (target %.1f): the ceiling leaves no room; lower the peaks in the mix", after.lufs, target)) }
writeAudio(outFile, Y, sr)
if outFile.pathExtension.lowercased() == "m4a" {
    let (D, dsr) = readAudio(outFile)
    let enc = stats(D, dsr)
    print(line("aac   ", enc))
    if enc.tp > ceilingDb + 0.1 { print(String(format: "WARN   the AAC overshoots to %.2f dBTP: re-run with --tp %.1f", enc.tp, ceilingDb - (enc.tp - ceilingDb) - 0.1)) }
    print("wrote  \(outFile.path) (AAC 256 kbps)")
} else {
    print("wrote  \(outFile.path) (24-bit PCM)")
}
printSections(after)
