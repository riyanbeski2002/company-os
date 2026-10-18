// Pull frames out of a reference video with AVFoundation (no ffmpeg needed).
// usage: extract <video> <out_dir> [step_s=0.5] [from_s=0] [to_s=end] [max_px=640]
//   overview of a ref:      extract ref.mp4 refs/r1 0.5
//   dense look at a cut:    extract ref.mp4 refs/r1_t3 0.0667 12.4 13.6 960     (1/15 s around the transition)
// Files: f_<index>_<time>.jpg — feed the folder to sheet.py for a labelled contact sheet.
import AVFoundation
import AppKit
let a = CommandLine.arguments
guard a.count >= 3 else { print("usage: extract <video> <out_dir> [step] [from] [to] [max_px]"); exit(2) }
let asset = AVURLAsset(url: URL(fileURLWithPath: a[1]))
let outDir = a[2]
let step = a.count > 3 ? (Double(a[3]) ?? 0.5) : 0.5
let dur = CMTimeGetSeconds(asset.duration)
let from = a.count > 4 ? (Double(a[4]) ?? 0) : 0
let to = a.count > 5 ? min(Double(a[5]) ?? dur, dur) : dur
let maxPx = a.count > 6 ? (Double(a[6]) ?? 640) : 640
let track = asset.tracks(withMediaType: .video).first!
let size = track.naturalSize.applying(track.preferredTransform)
print("dur=\(dur) size=\(abs(size.width))x\(abs(size.height)) fps=\(track.nominalFrameRate)")
let gen = AVAssetImageGenerator(asset: asset)
gen.appliesPreferredTrackTransform = true
gen.requestedTimeToleranceBefore = .zero
gen.requestedTimeToleranceAfter = .zero
gen.maximumSize = CGSize(width: maxPx, height: maxPx)
try? FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
var t = from, i = 0
while t < to {
  if let cg = try? gen.copyCGImage(at: CMTime(seconds: t, preferredTimescale: 600), actualTime: nil) {
    let data = NSBitmapImageRep(cgImage: cg).representation(using: .jpeg, properties: [.compressionFactor: 0.85])!
    try! data.write(to: URL(fileURLWithPath: String(format: "%@/f_%04d_%07.3f.jpg", outDir, i, t)))
  }
  t += step; i += 1
}
print("\(i) frames -> \(outDir)")
