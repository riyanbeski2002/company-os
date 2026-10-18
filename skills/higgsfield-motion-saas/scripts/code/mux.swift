// mux <video.mp4> <audio.m4a> <out.mp4> — passthrough H.264 + AAC into one mp4
import AVFoundation
let a = CommandLine.arguments
let v = AVURLAsset(url: URL(fileURLWithPath: a[1])), s = AVURLAsset(url: URL(fileURLWithPath: a[2]))
let comp = AVMutableComposition()
let dur = v.duration
let vt = comp.addMutableTrack(withMediaType: .video, preferredTrackID: kCMPersistentTrackID_Invalid)!
try! vt.insertTimeRange(CMTimeRange(start: .zero, duration: dur), of: v.tracks(withMediaType: .video)[0], at: .zero)
let at = comp.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid)!
let ad = CMTimeMinimum(dur, s.duration)
try! at.insertTimeRange(CMTimeRange(start: .zero, duration: ad), of: s.tracks(withMediaType: .audio)[0], at: .zero)
let out = URL(fileURLWithPath: a[3]); try? FileManager.default.removeItem(at: out)
let ex = AVAssetExportSession(asset: comp, presetName: AVAssetExportPresetPassthrough)!
ex.outputURL = out; ex.outputFileType = .mp4
let sem = DispatchSemaphore(value: 0)
ex.exportAsynchronously { sem.signal() }
sem.wait()
print(ex.status == .completed ? "muxed -> \(a[3])" : "mux failed: \(String(describing: ex.error))")
