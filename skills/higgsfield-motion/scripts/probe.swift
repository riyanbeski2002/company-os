// probe — check the ENCODED deliverable before sending it: what the viewer gets, not what the frames folder says.
// usage: probe <video.mp4> [out_dir [t1 t2 … | auto]] [--fps N] [--dur S] [--audio]
//   prints  file size · container duration
//           video: size · codec + H.264 profile · nominal and measured fps · frame count · constant-frame-rate check
//                  (min/max frame duration: one 8 ms frame at an unaligned seam shows up here) · bitrate · colour tags
//           audio: codec · rate · channels · duration · bitrate (or "audio none")
//   out_dir writes check frames decoded FROM THE MP4 as <out_dir>/v_<t>.png (encoder artefacts, colour, the exact last
//           frame). No times or "auto" = six frames: first, 15 %, 30 %, 55 %, 80 %, last.
//   --fps N / --dur S / --audio   expectations: exit 1 unless the file is N fps CFR / S seconds (±half a frame) / has
//           an audio track as long as the picture.
// Exit 1 on: no video track, a variable frame rate, or an unmet expectation. Non-BT.709 tags and short audio are warnings.
// Build (macOS): swiftc -O probe.swift -o probe   (or scripts/setup.sh)
// Elsewhere: ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate,nb_frames,duration -of compact f.mp4
import AVFoundation
import Foundation
import ImageIO
import UniformTypeIdentifiers

func fail(_ msg: String, code: Int32 = 1) -> Never {
    FileHandle.standardError.write("probe: \(msg)\n".data(using: .utf8)!)
    exit(code)
}
final class Box<T>: @unchecked Sendable { var value: T?; init() {} }
func blocking<T>(_ body: @escaping @Sendable () async throws -> T) throws -> T {
    let box = Box<Result<T, Error>>(), sem = DispatchSemaphore(value: 0)
    Task.detached { do { box.value = .success(try await body()) } catch { box.value = .failure(error) }; sem.signal() }
    sem.wait()
    return try box.value!.get()
}
func fourcc(_ c: FourCharCode) -> String {
    String(bytes: [24, 16, 8, 0].map { UInt8((c >> $0) & 0xff) }, encoding: .ascii)?.trimmingCharacters(in: .whitespaces) ?? "?"
}

var argv = Array(CommandLine.arguments.dropFirst())
func flagValue(_ k: String) -> Double? {
    guard let i = argv.firstIndex(of: k) else { return nil }
    guard i + 1 < argv.count, let v = Double(argv[i + 1]) else { fail("\(k) needs a number", code: 2) }
    argv.removeSubrange(i...(i + 1)); return v
}
let wantFps = flagValue("--fps"), wantDur = flagValue("--dur")
let wantAudio = argv.contains("--audio"); argv.removeAll { $0 == "--audio" }
guard argv.count >= 1 else { fail("usage: probe <video.mp4> [out_dir [t1 t2 … | auto]] [--fps N] [--dur S] [--audio]", code: 2) }
let url = URL(fileURLWithPath: argv[0])
guard let attrs = try? FileManager.default.attributesOfItem(atPath: url.path) else { fail("no such file: \(url.path)") }
let bytes = (attrs[.size] as? NSNumber)?.doubleValue ?? 0

var hard: [String] = [], warns: [String] = []
let asset = AVURLAsset(url: url)
let dur = CMTimeGetSeconds(try blocking { try await asset.load(.duration) })
print(String(format: "file   %@ · %.1f MB · %.3f s · %.1f Mbps overall", url.lastPathComponent, bytes / 1e6, dur, dur > 0 ? bytes * 8 / dur / 1e6 : 0))

guard let vt = try blocking({ try await asset.loadTracks(withMediaType: .video).first }) else { fail("no video track in \(url.lastPathComponent)") }
let size = try blocking { try await vt.load(.naturalSize) }
let nominal = Double(try blocking { try await vt.load(.nominalFrameRate) })
let vRate = Double(try blocking { try await vt.load(.estimatedDataRate) })
let vRange = try blocking { try await vt.load(.timeRange) }
let fmt = try blocking { try await vt.load(.formatDescriptions) }.first
var codec = fmt.map { fourcc(CMFormatDescriptionGetMediaSubType($0)) } ?? "?"
var tags = "no colour tags"
if let f = fmt, let ext = CMFormatDescriptionGetExtensions(f) as? [String: Any] {
    if let atoms = ext[kCMFormatDescriptionExtension_SampleDescriptionExtensionAtoms as String] as? [String: Any],
       let avcC = atoms["avcC"] as? Data, avcC.count > 3 {
        let p = Int(avcC[avcC.startIndex + 1]), lv = Int(avcC[avcC.startIndex + 3])
        let name = [66: "Baseline", 77: "Main", 88: "Extended", 100: "High", 110: "High 10", 122: "High 4:2:2"][p] ?? "profile \(p)"
        codec += " (H.264 \(name) @ L\(lv / 10).\(lv % 10))"
    }
    let prim = ext[kCMFormatDescriptionExtension_ColorPrimaries as String] as? String
    let trc = ext[kCMFormatDescriptionExtension_TransferFunction as String] as? String
    let mat = ext[kCMFormatDescriptionExtension_YCbCrMatrix as String] as? String
    if prim != nil || trc != nil || mat != nil {
        tags = "primaries \(prim ?? "–") · transfer \(trc ?? "–") · matrix \(mat ?? "–")"
        let is709 = [prim, trc, mat].allSatisfy { ($0 ?? "").contains("709") }
        if !is709 { warns.append("colour tags are not all BT.709 (\(tags))") } else { tags = "BT.709 ✓ (\(tags))" }
    } else { warns.append("no colour tags: players may guess the colour space") }
}

// frame timing from the compressed samples (no decode)
var pts: [Double] = []
do {
    let reader = try AVAssetReader(asset: asset)
    let ro = AVAssetReaderTrackOutput(track: vt, outputSettings: nil); ro.alwaysCopiesSampleData = false
    reader.add(ro); reader.startReading()
    while let sb = ro.copyNextSampleBuffer() {
        if CMSampleBufferGetNumSamples(sb) > 0 { pts.append(CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(sb))) }
    }
    if reader.status == .failed { warns.append("could not read every video sample: \(reader.error?.localizedDescription ?? "?")") }
} catch { warns.append("frame timing unavailable: \(error.localizedDescription)") }
pts.sort()
// frame durations from consecutive presentation times (the first PTS can sit after 0 when the encoder reorders frames)
let durs = zip(pts.dropFirst(), pts).map { $0 - $1 }
let median = durs.isEmpty ? 0 : durs.sorted()[durs.count / 2]
let measured = median > 0 ? 1 / median : 0
let trackSec = CMTimeGetSeconds(vRange.duration)
var cfr = "CFR ?"
if let mn = durs.min(), let mx = durs.max() {
    if mx - mn <= 0.0005 { cfr = String(format: "CFR ✓ (every frame %.3f ms)", mn * 1000) }
    else {
        let at = durs.firstIndex(of: mn).map { pts[$0] } ?? 0
        cfr = String(format: "VFR ✗ (frame durations %.3f–%.3f ms; shortest at %.3f s)", mn * 1000, mx * 1000, at)
        hard.append("variable frame rate: frame-align every clip's in/out to 1/fps before composing")
    }
}
if measured > 0 && trackSec > 0 && abs(Double(pts.count) - trackSec * measured) > 0.6 {
    warns.append(String(format: "%d frames in %.3f s is %.3f fps on average, not %.3f: frames are missing or held", pts.count, trackSec, Double(pts.count) / trackSec, measured))
}
print(String(format: "video  %dx%d · %@ · %.3f fps nominal, %.3f measured · %d frames · %.3f s · %@ · %.1f Mbps",
             Int(size.width), Int(size.height), codec, nominal, measured, pts.count, CMTimeGetSeconds(vRange.duration), cfr, vRate / 1e6))
print("colour \(tags)")

var audioSec = 0.0
if let at = try blocking({ try await asset.loadTracks(withMediaType: .audio).first }) {
    let af = try blocking { try await at.load(.formatDescriptions) }.first
    let asbd = af.flatMap { CMAudioFormatDescriptionGetStreamBasicDescription($0)?.pointee }
    let ar = Double(try blocking { try await at.load(.estimatedDataRate) })
    audioSec = CMTimeGetSeconds(try blocking { try await at.load(.timeRange) }.duration)
    print(String(format: "audio  %@ · %d Hz · %d ch · %.3f s · %d kbps", af.map { fourcc(CMFormatDescriptionGetMediaSubType($0)) } ?? "?",
                 Int(asbd?.mSampleRate ?? 0), Int(asbd?.mChannelsPerFrame ?? 0), audioSec, Int(ar / 1000)))
    let frame = measured > 0 ? 1 / measured : 0.04
    if audioSec + frame < CMTimeGetSeconds(vRange.duration) { warns.append(String(format: "audio (%.3f s) is shorter than the picture (%.3f s)", audioSec, CMTimeGetSeconds(vRange.duration))) }
} else {
    print("audio  none")
    if wantAudio { hard.append("no audio track (films ship with sound)") }
}
if wantAudio && audioSec > 0 && audioSec + 0.05 < CMTimeGetSeconds(vRange.duration) { hard.append("audio shorter than the picture") }
if let f = wantFps, abs(measured - f) > 0.01 || abs(nominal - f) > 0.01 { hard.append(String(format: "expected %.3f fps, got %.3f nominal / %.3f measured", f, nominal, measured)) }
if let d = wantDur, abs(CMTimeGetSeconds(vRange.duration) - d) > 0.5 / max(1, measured) {
    hard.append(String(format: "expected %.3f s, got %.3f s", d, CMTimeGetSeconds(vRange.duration)))
}

// check frames from the encoded file
if argv.count >= 2 {
    let outDir = URL(fileURLWithPath: argv[1])
    try? FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)
    let half = measured > 0 ? 0.5 / measured : 0.02
    let vDur = CMTimeGetSeconds(vRange.duration)
    var times = argv.dropFirst(2).filter { $0 != "auto" }.map { s -> Double in
        guard let v = Double(s) else { fail("check-frame times are seconds, got '\(s)'", code: 2) }; return v
    }
    if times.isEmpty { times = [0, 0.15, 0.30, 0.55, 0.80].map { $0 * vDur } + [vDur] }
    let gen = AVAssetImageGenerator(asset: asset)
    gen.requestedTimeToleranceBefore = .zero; gen.requestedTimeToleranceAfter = .zero; gen.appliesPreferredTrackTransform = true
    let gb = Box<AVAssetImageGenerator>(); gb.value = gen
    var written: [String] = []
    for t0 in times {
        let t = min(max(0, t0), vDur - half) + (t0 <= 0 ? half : 0)  // sample mid-frame at both ends
        do {
            let img = try blocking { try await gb.value!.image(at: CMTime(seconds: t, preferredTimescale: 60000)).image }
            let name = String(format: "v_%.3f.png", t0)
            let dst = CGImageDestinationCreateWithURL(outDir.appendingPathComponent(name) as CFURL, UTType.png.identifier as CFString, 1, nil)!
            CGImageDestinationAddImage(dst, img, nil)
            if CGImageDestinationFinalize(dst) { written.append(name) }
        } catch { warns.append(String(format: "no frame at %.3f s: %@", t, error.localizedDescription)) }
    }
    print("frames \(outDir.path)/ \(written.joined(separator: " "))")
}
for w in warns { print("WARN   \(w)") }
for h in hard { print("FAIL   \(h)") }
if !hard.isEmpty { exit(1) }
print("ok")
