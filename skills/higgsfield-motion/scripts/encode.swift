// Encode a numbered PNG/JPEG frame sequence into an H.264 MP4 using AVFoundation (no third-party deps). Picture only:
// for picture + sound in one pass use encode_av; to add audio to an existing MP4 use mux.
// usage: encode <frames_dir> <fps> <out.mp4> [bitrate_mbps=24] [--lenient]
//   frames  f_<n>.png | f_<n>.jpg (capture.mjs writes f_00000.png …), ordered by the number n; other files are ignored.
//   output  H.264 High, BT.709 primaries/transfer/matrix tags, a keyframe every 2 s, constant frame rate (frame i at i/fps).
// Fails loudly (exit 1, message on stderr) instead of writing a silently broken film:
//   · no f_ frames, an unreadable frame, a frame of a different size than the first;
//   · a gap in the frame index (a missing frame; a uniform step such as --every 2 is accepted);
//   · a frame count that differs from <frames_dir>/_comp.json (written by capture.mjs) — e.g. 483 of 900 frames copied
//     while another agent was still rendering into the folder;
//   · a writer that fails to start, an append that fails, or a writer that stops accepting data.
//   --lenient turns the gap / count / size checks into warnings (other sizes are scaled to the first frame's size).
// Build (macOS): swiftc -O encode.swift -o encode   (scripts/setup.sh builds every tool into ${HFT_BIN:-~/.cache/higgsfield-motion/bin})
// Elsewhere: ffmpeg -framerate 24 -i f_%05d.png -c:v libx264 -profile:v high -pix_fmt yuv420p -b:v 24M -colorspace bt709 \
//            -color_primaries bt709 -color_trc bt709 film.mp4
import AVFoundation
import CoreGraphics
import CoreVideo
import Foundation
import ImageIO

func fail(_ msg: String, code: Int32 = 1) -> Never {
    FileHandle.standardError.write("encode: \(msg)\n".data(using: .utf8)!)
    exit(code)
}
func warn(_ msg: String) { FileHandle.standardError.write("encode: warning: \(msg)\n".data(using: .utf8)!) }

let argv = Array(CommandLine.arguments.dropFirst())
let lenient = argv.contains("--lenient")
let pos = argv.filter { !$0.hasPrefix("--") }
guard pos.count >= 3 else { fail("usage: encode <frames_dir> <fps> <out.mp4> [mbps=24] [--lenient]", code: 2) }
let dir = URL(fileURLWithPath: pos[0])
guard let fps = Int32(pos[1]), fps > 0, fps <= 240 else { fail("fps must be a whole number 1–240, got '\(pos[1])'", code: 2) }
let out = URL(fileURLWithPath: pos[2])
var mbps = 24.0
if pos.count > 3 { guard let m = Double(pos[3]), m > 0, m <= 400 else { fail("bitrate must be Mbps (e.g. 24), got '\(pos[3])'", code: 2) }; mbps = m }

// ---- the frame list: f_<n>.(png|jpg|jpeg), ordered by n
var isDir: ObjCBool = false
guard FileManager.default.fileExists(atPath: dir.path, isDirectory: &isDir), isDir.boolValue else { fail("no such folder: \(dir.path)") }
let names = (try? FileManager.default.contentsOfDirectory(atPath: dir.path)) ?? []
var byIndex: [Int: String] = [:]
for name in names where name.hasPrefix("f_") {
    let ext = (name as NSString).pathExtension.lowercased()
    guard ["png", "jpg", "jpeg"].contains(ext) else { continue }
    let stem = ((name as NSString).deletingPathExtension as NSString).substring(from: 2)
    guard let n = Int(stem), n >= 0 else { continue }
    if let other = byIndex[n] { fail("two files for frame \(n): \(other) and \(name). Render into a freshly cleaned folder.") }
    byIndex[n] = name
}
let idx = byIndex.keys.sorted()
guard !idx.isEmpty else {
    let imgs = names.filter { ["png", "jpg", "jpeg"].contains(($0 as NSString).pathExtension.lowercased()) }
    fail("no f_<n>.png/.jpg frames in \(dir.path)" + (imgs.isEmpty ? "" : " (found \(imgs.count) other images, e.g. \(imgs.sorted()[0]); stills are not a film)"))
}

// gaps: every step must be the same (1 normally; --every N captures give N)
var problems: [String] = []
if idx.count > 1 {
    let diffs = zip(idx.dropFirst(), idx).map { $0 - $1 }
    var counts: [Int: Int] = [:]; diffs.forEach { counts[$0, default: 0] += 1 }
    let step = counts.max { $0.value < $1.value }!.key
    if Set(diffs).count > 1 {
        var missing: [Int] = []
        var k = idx[0]; let have = Set(idx)
        while k <= idx.last! && missing.count < 13 { if !have.contains(k) { missing.append(k) }; k += step }
        let shown = missing.isEmpty ? "irregular steps \(Set(diffs).sorted())" : "missing " + missing.prefix(12).map(String.init).joined(separator: ", ") + (missing.count > 12 ? ", …" : "")
        problems.append("frame index has gaps (step \(step)): \(shown). Re-capture the missing frames before encoding.")
    } else if step != 1 {
        warn("frames step by \(step) (an --every \(step) draft); encoding them back to back at \(fps) fps")
    }
}

// count check against capture's _comp.json
let compURL = dir.appendingPathComponent("_comp.json")
if let data = try? Data(contentsOf: compURL) {
    if let comp = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] {
        func num(_ k: String) -> Double? { (comp[k] as? NSNumber)?.doubleValue }
        // capture.mjs writes { mode, fps, duration, frames, from, to, every, complete, missing, … } (from/to = frame indices, to exclusive)
        let stillsOnly = (comp["mode"] as? String) == "stills"
        var expected: Int? = nil
        let every = max(1, num("every") ?? 1)
        if let v = num("frames") ?? num("expected") ?? num("frameCount") { expected = Int(v.rounded()) }
        else if let a = num("from"), let b = num("to") { expected = Int(ceil((b - a) / every)) }
        else if let f = num("fps"), let d = num("duration") { expected = Int(ceil((d * f).rounded() / every)) }
        if stillsOnly { expected = nil }
        if (comp["complete"] as? Bool) == false { problems.append("_comp.json says the capture is incomplete (capture exited 4)") }
        if let f = num("fps"), abs(f - Double(fps)) > 1e-6 {
            warn("_comp.json says the page runs at \(f) fps but you are encoding at \(fps) fps: the film's duration will change")
        }
        if let miss = comp["missing"] as? [Any], !miss.isEmpty { problems.append("_comp.json lists \(miss.count) missing frames") }
        if let e = expected, e != idx.count {
            problems.append("found \(idx.count) frames, _comp.json expects \(e). Is another process still writing into \(dir.lastPathComponent)?")
        }
    } else {
        warn("could not parse \(compURL.lastPathComponent); skipping the frame-count check")
    }
}
if !problems.isEmpty {
    if lenient { problems.forEach { warn($0 + " (--lenient)") } } else { fail(problems.joined(separator: "\n  ") + "\n  (--lenient encodes anyway)") }
}

// ---- decode helper (ImageIO; no AppKit)
func loadImage(_ name: String) -> CGImage? {
    guard let src = CGImageSourceCreateWithURL(dir.appendingPathComponent(name) as CFURL, [kCGImageSourceShouldCache: false] as CFDictionary)
    else { return nil }
    return CGImageSourceCreateImageAtIndex(src, 0, nil)
}
guard let firstCG = loadImage(byIndex[idx[0]]!) else { fail("cannot decode \(byIndex[idx[0]]!)") }
let W = firstCG.width, H = firstCG.height

// ---- writer
try? FileManager.default.removeItem(at: out)
let writer: AVAssetWriter
do { writer = try AVAssetWriter(outputURL: out, fileType: .mp4) } catch { fail("cannot create \(out.path): \(error.localizedDescription)") }
let settings: [String: Any] = [
    AVVideoCodecKey: AVVideoCodecType.h264,
    AVVideoWidthKey: W, AVVideoHeightKey: H,
    AVVideoCompressionPropertiesKey: [
        AVVideoAverageBitRateKey: Int(mbps * 1_000_000),
        AVVideoProfileLevelKey: AVVideoProfileLevelH264HighAutoLevel,
        AVVideoExpectedSourceFrameRateKey: Int(fps),
        AVVideoMaxKeyFrameIntervalKey: Int(fps) * 2,
    ],
    AVVideoColorPropertiesKey: [
        AVVideoColorPrimariesKey: AVVideoColorPrimaries_ITU_R_709_2,
        AVVideoTransferFunctionKey: AVVideoTransferFunction_ITU_R_709_2,
        AVVideoYCbCrMatrixKey: AVVideoYCbCrMatrix_ITU_R_709_2,
    ],
]
let input = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
input.expectsMediaDataInRealTime = false
let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: [
    kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
    kCVPixelBufferWidthKey as String: W, kCVPixelBufferHeightKey as String: H,
])
guard writer.canAdd(input) else { fail("the writer refuses a \(W)x\(H) H.264 track") }
writer.add(input)
func bail(_ msg: String) -> Never {
    writer.cancelWriting(); try? FileManager.default.removeItem(at: out)
    fail(msg + (writer.error.map { " (\($0.localizedDescription))" } ?? ""))
}
guard writer.startWriting() else { bail("writer did not start for \(W)x\(H) @\(fps) fps") }
writer.startSession(atSourceTime: .zero)
guard let pool = adaptor.pixelBufferPool else { bail("no pixel buffer pool") }

let cs = CGColorSpace(name: CGColorSpace.sRGB)!
var sizeWarned = false
for (i, n) in idx.enumerated() {
    let name = byIndex[n]!
    autoreleasepool {
        guard let cg = (i == 0 ? firstCG : loadImage(name)) else { bail("cannot decode frame \(name)") }
        if cg.width != W || cg.height != H {
            if !lenient { bail("\(name) is \(cg.width)x\(cg.height), the first frame is \(W)x\(H)") }
            if !sizeWarned { warn("\(name) is \(cg.width)x\(cg.height); scaling to \(W)x\(H) (--lenient)"); sizeWarned = true }
        }
        var waited = 0
        while !input.isReadyForMoreMediaData {
            if writer.status == .failed { bail("writer failed at frame \(n)") }
            usleep(2000); waited += 1
            if waited > 30_000 { bail("writer stopped accepting frames at frame \(n) (60 s)") }
        }
        var pb: CVPixelBuffer?
        CVPixelBufferPoolCreatePixelBuffer(nil, pool, &pb)
        guard let buf = pb else { bail("no pixel buffer for frame \(n)") }
        CVPixelBufferLockBaseAddress(buf, [])
        guard let ctx = CGContext(data: CVPixelBufferGetBaseAddress(buf), width: W, height: H, bitsPerComponent: 8,
                                  bytesPerRow: CVPixelBufferGetBytesPerRow(buf), space: cs,
                                  bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue | CGBitmapInfo.byteOrder32Little.rawValue)
        else { bail("no drawing context") }
        ctx.interpolationQuality = .high
        ctx.draw(cg, in: CGRect(x: 0, y: 0, width: W, height: H))
        CVPixelBufferUnlockBaseAddress(buf, [])
        if !adaptor.append(buf, withPresentationTime: CMTime(value: CMTimeValue(i), timescale: fps)) {
            bail("append failed at frame \(n)")
        }
    }
}
input.markAsFinished()
writer.endSession(atSourceTime: CMTime(value: CMTimeValue(idx.count), timescale: fps))
let sem = DispatchSemaphore(value: 0)
writer.finishWriting { sem.signal() }
sem.wait()
if writer.status == .completed {
    let dur = Double(idx.count) / Double(fps)
    print("wrote \(out.path) \(W)x\(H) \(idx.count) frames @\(fps)fps (\(String(format: "%.3f", dur)) s, \(Int(mbps)) Mbps)")
} else {
    try? FileManager.default.removeItem(at: out)
    fail("failed: \(writer.error?.localizedDescription ?? "unknown writer error")")
}
