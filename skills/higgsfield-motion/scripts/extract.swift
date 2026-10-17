// extract — turn generated footage (Seedance / Kling / any H.264 or HEVC clip) into an image sequence a __seek page can
// address frame-accurately. Headless Chromium has no H.264, and <video> seeking is not frame-deterministic.
// usage: extract <clip.mp4> <out_dir> [fps=native] [maxW=1920] [quality=0.9]
//   fps      "native" (default) = the clip's own rate (Seedance: 24): every source frame exactly once, no duplicates.
//            A number resamples (frame i is sampled at (i + 0.5) / fps, zero tolerance).
//   out      <out_dir>/f_0000.jpg … f_<n-1>.jpg (0-based, JPEG), plus <out_dir>/_clip.json:
//            {"frames":n,"fps":…,"duration":…,"srcFps":…,"w":…,"h":…,"outW":…,"outH":…,"first":0,"pattern":"f_%04d.jpg"}
//            Old f_*.jpg in out_dir are removed first, so a re-extract never mixes two takes.
// In the page: read the REAL frame count from _clip.json (a 5 s clip had 120 frames, f_0120 does not exist), clamp the
// index to [0, n−1] and hold the last frame — never loop (see assets/templates/shared/clips.js).
// Build (macOS): swiftc -O extract.swift -o extract   (or scripts/setup.sh)
// Elsewhere: ffmpeg -i clip.mp4 -vf "scale='min(1920,iw)':-2" -q:v 2 -start_number 0 out/f_%04d.jpg
import AVFoundation
import Foundation
import ImageIO
import UniformTypeIdentifiers

func fail(_ msg: String, code: Int32 = 1) -> Never {
    FileHandle.standardError.write("extract: \(msg)\n".data(using: .utf8)!)
    exit(code)
}
final class Box<T>: @unchecked Sendable { var value: T?; init() {} }
func blocking<T>(_ body: @escaping @Sendable () async throws -> T) throws -> T {
    let box = Box<Result<T, Error>>(), sem = DispatchSemaphore(value: 0)
    Task.detached { do { box.value = .success(try await body()) } catch { box.value = .failure(error) }; sem.signal() }
    sem.wait()
    return try box.value!.get()
}

let a = CommandLine.arguments
guard a.count >= 3 else { fail("usage: extract <clip.mp4> <out_dir> [fps=native] [maxW=1920] [quality=0.9]", code: 2) }
let src = URL(fileURLWithPath: a[1]), outDir = URL(fileURLWithPath: a[2])
guard FileManager.default.fileExists(atPath: src.path) else { fail("no such file: \(src.path)") }
let fpsArg = a.count > 3 ? a[3] : "native"
let maxW = a.count > 4 ? (Double(a[4]) ?? 1920) : 1920
let quality = a.count > 5 ? min(1, max(0.1, Double(a[5]) ?? 0.9)) : 0.9

let asset = AVURLAsset(url: src)
let track: AVAssetTrack?
do { track = try blocking { try await asset.loadTracks(withMediaType: .video).first } } catch { fail("cannot read \(src.path): \(error.localizedDescription)") }
guard let vt = track else { fail("\(src.lastPathComponent) has no video track") }
let dur = CMTimeGetSeconds(try blocking { try await asset.load(.duration) })
let natural = try blocking { try await vt.load(.naturalSize) }
let xf = try blocking { try await vt.load(.preferredTransform) }
let srcFps = Double(try blocking { try await vt.load(.nominalFrameRate) })
let shown = natural.applying(xf), w0 = abs(shown.width), h0 = abs(shown.height)
var fps: Double
if fpsArg == "native" {
    guard srcFps > 0 else { fail("the clip reports no frame rate; pass one, e.g. extract clip.mp4 out 24") }
    fps = srcFps
} else {
    guard let f = Double(fpsArg), f > 0, f <= 240 else { fail("fps must be 'native' or a number, got '\(fpsArg)'", code: 2) }
    fps = f
}
let scale = min(1, maxW / Double(w0))
let outW = Int((Double(w0) * scale).rounded()), outH = Int((Double(h0) * scale).rounded())

try? FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)
for old in (try? FileManager.default.contentsOfDirectory(atPath: outDir.path)) ?? [] where (old.hasPrefix("f_") && old.hasSuffix(".jpg")) || old == "_clip.json" {
    try? FileManager.default.removeItem(at: outDir.appendingPathComponent(old))
}

let gen = AVAssetImageGenerator(asset: asset)
gen.requestedTimeToleranceBefore = .zero
gen.requestedTimeToleranceAfter = .zero
gen.appliesPreferredTrackTransform = true
gen.maximumSize = CGSize(width: outW, height: outH)
let genBox = Box<AVAssetImageGenerator>(); genBox.value = gen

let n = Int((dur * fps + 1e-6).rounded(.down))
guard n > 0 else { fail("the clip is shorter than one frame (\(dur) s)") }
var written = 0
for i in 0..<n {
    let t = CMTime(seconds: (Double(i) + 0.5) / fps, preferredTimescale: 60000)
    let img: CGImage
    do { img = try blocking { try await genBox.value!.image(at: t).image } } catch {
        if i >= n - 2 { break }   // the very last sample can fall past the final frame of a short track
        fail("frame \(i) at \(String(format: "%.3f", CMTimeGetSeconds(t))) s: \(error.localizedDescription)")
    }
    let url = outDir.appendingPathComponent(String(format: "f_%04d.jpg", i))
    guard let dst = CGImageDestinationCreateWithURL(url as CFURL, UTType.jpeg.identifier as CFString, 1, nil) else { fail("cannot write \(url.path)") }
    CGImageDestinationAddImage(dst, img, [kCGImageDestinationLossyCompressionQuality: quality] as CFDictionary)
    guard CGImageDestinationFinalize(dst) else { fail("cannot write \(url.path)") }
    written += 1
}
let info: [String: Any] = [
    "frames": written, "fps": fps, "duration": dur, "srcFps": srcFps, "w": Int(w0), "h": Int(h0),
    "outW": outW, "outH": outH, "first": 0, "pattern": "f_%04d.jpg", "source": src.lastPathComponent,
]
let json = try JSONSerialization.data(withJSONObject: info, options: [.sortedKeys])
try json.write(to: outDir.appendingPathComponent("_clip.json"))
print(String(data: json, encoding: .utf8)!)
if fpsArg != "native" && srcFps > 0 && abs(fps - srcFps) > 0.01 {
    FileHandle.standardError.write("extract: note: resampled \(srcFps) fps → \(fps) fps (frames are repeated or dropped)\n".data(using: .utf8)!)
}
