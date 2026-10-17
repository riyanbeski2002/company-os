// encode_av — the master encoder: numbered frames + an audio file → one H.264 + AAC MP4 in a single pass (AVFoundation only).
// usage: encode_av <frames_dir> <fps> <audio.wav|.aif|.m4a|.mp3 | -> <out.mp4> [bitrate_mbps=24] [--lenient]
//   frames  f_<n>.png | f_<n>.jpg ordered by n, with the same checks as encode (gaps, size, _comp.json count; --lenient relaxes them).
//   audio   any file AVFoundation reads (PCM WAV 16/24/32-bit or float, AIFF, M4A, MP3); "-" = picture only.
//           Re-encoded to AAC-LC 256 kbps, 48 kHz stereo, and trimmed to the picture: film length = frames / fps.
//           Shorter audio is allowed (silence after it, with a warning). Master the WAV first (master: −14 LUFS, −1.2 dBTP).
//   output  H.264 High, BT.709 tags, keyframe every 2 s, constant frame rate.
// Each track pulls its own data on its own requestMediaDataWhenReady queue, joined by a DispatchGroup. Interleaving the two
// inputs by hand deadlocks (the muxer waits for the other track: "2 s CPU, 33 KB output, hung").
// Build (macOS): swiftc -O encode_av.swift -o encode_av   (or scripts/setup.sh)
// Elsewhere: ffmpeg -framerate 24 -i f_%05d.png -i mix.wav -c:v libx264 -profile:v high -pix_fmt yuv420p -b:v 24M \
//            -c:a aac -b:a 256k -ar 48000 -shortest film.mp4
import AVFoundation
import CoreGraphics
import CoreVideo
import Foundation
import ImageIO

func fail(_ msg: String, code: Int32 = 1) -> Never {
    FileHandle.standardError.write("encode_av: \(msg)\n".data(using: .utf8)!)
    exit(code)
}
func warn(_ msg: String) { FileHandle.standardError.write("encode_av: warning: \(msg)\n".data(using: .utf8)!) }
final class Box<T>: @unchecked Sendable { var value: T?; init() {} }
/// Runs an async AVFoundation load from synchronous script code.
func blocking<T>(_ body: @escaping @Sendable () async throws -> T) throws -> T {
    let box = Box<Result<T, Error>>(), sem = DispatchSemaphore(value: 0)
    Task.detached { do { box.value = .success(try await body()) } catch { box.value = .failure(error) }; sem.signal() }
    sem.wait()
    return try box.value!.get()
}

let argv = Array(CommandLine.arguments.dropFirst())
let lenient = argv.contains("--lenient")
let pos = argv.filter { !$0.hasPrefix("--") }
guard pos.count >= 4 else { fail("usage: encode_av <frames_dir> <fps> <audio|-> <out.mp4> [mbps=24] [--lenient]", code: 2) }
let dir = URL(fileURLWithPath: pos[0])
guard let fps = Int32(pos[1]), fps > 0, fps <= 240 else { fail("fps must be a whole number 1–240, got '\(pos[1])'", code: 2) }
let audioPath = pos[2]
let out = URL(fileURLWithPath: pos[3])
var mbps = 24.0
if pos.count > 4 { guard let m = Double(pos[4]), m > 0, m <= 400 else { fail("bitrate must be Mbps (e.g. 24), got '\(pos[4])'", code: 2) }; mbps = m }

// ---- frames (same rules as encode.swift)
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
guard !idx.isEmpty else { fail("no f_<n>.png/.jpg frames in \(dir.path)") }
var problems: [String] = []
if idx.count > 1 {
    let diffs = zip(idx.dropFirst(), idx).map { $0 - $1 }
    var counts: [Int: Int] = [:]; diffs.forEach { counts[$0, default: 0] += 1 }
    let step = counts.max { $0.value < $1.value }!.key
    if Set(diffs).count > 1 {
        var missing: [Int] = []; var k = idx[0]; let have = Set(idx)
        while k <= idx.last! && missing.count < 13 { if !have.contains(k) { missing.append(k) }; k += step }
        let shown = missing.isEmpty ? "irregular steps \(Set(diffs).sorted())" : "missing " + missing.prefix(12).map(String.init).joined(separator: ", ") + (missing.count > 12 ? ", …" : "")
        problems.append("frame index has gaps (step \(step)): \(shown). Re-capture the missing frames before encoding.")
    } else if step != 1 { warn("frames step by \(step) (an --every \(step) draft); encoding them back to back at \(fps) fps") }
}
if let data = try? Data(contentsOf: dir.appendingPathComponent("_comp.json")),
   let comp = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] {
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
    if let f = num("fps"), abs(f - Double(fps)) > 1e-6 { warn("_comp.json says \(f) fps, encoding at \(fps) fps: picture and sound will drift apart") }
    if let miss = comp["missing"] as? [Any], !miss.isEmpty { problems.append("_comp.json lists \(miss.count) missing frames") }
    if let e = expected, e != idx.count { problems.append("found \(idx.count) frames, _comp.json expects \(e). Is another process still writing into \(dir.lastPathComponent)?") }
}
if !problems.isEmpty {
    if lenient { problems.forEach { warn($0 + " (--lenient)") } } else { fail(problems.joined(separator: "\n  ") + "\n  (--lenient encodes anyway)") }
}
func loadImage(_ name: String) -> CGImage? {
    guard let src = CGImageSourceCreateWithURL(dir.appendingPathComponent(name) as CFURL, [kCGImageSourceShouldCache: false] as CFDictionary) else { return nil }
    return CGImageSourceCreateImageAtIndex(src, 0, nil)
}
guard let firstCG = loadImage(byIndex[idx[0]]!) else { fail("cannot decode \(byIndex[idx[0]]!)") }
let W = firstCG.width, H = firstCG.height
let filmDur = CMTime(value: CMTimeValue(idx.count), timescale: fps)

// ---- audio source: AVAssetReader decodes any format to 48 kHz stereo float PCM, limited to the film's length
let SR = 48000
var reader: AVAssetReader? = nil
var readerOut: AVAssetReaderTrackOutput? = nil
var audioSeconds = 0.0
if audioPath != "-" {
    let aURL = URL(fileURLWithPath: audioPath)
    guard FileManager.default.fileExists(atPath: aURL.path) else { fail("no such audio file: \(audioPath)") }
    let aAsset = AVURLAsset(url: aURL)
    let track: AVAssetTrack?
    do { track = try blocking { try await aAsset.loadTracks(withMediaType: .audio).first } } catch { fail("cannot read \(audioPath): \(error.localizedDescription)") }
    guard let aTrack = track else { fail("\(audioPath) has no audio track") }
    audioSeconds = CMTimeGetSeconds((try? blocking { try await aTrack.load(.timeRange) })?.duration ?? .zero)
    do { reader = try AVAssetReader(asset: aAsset) } catch { fail("cannot open \(audioPath): \(error.localizedDescription)") }
    reader!.timeRange = CMTimeRange(start: .zero, duration: filmDur)
    let ro = AVAssetReaderTrackOutput(track: aTrack, outputSettings: [
        AVFormatIDKey: kAudioFormatLinearPCM, AVLinearPCMBitDepthKey: 32, AVLinearPCMIsFloatKey: true,
        AVLinearPCMIsBigEndianKey: false, AVLinearPCMIsNonInterleaved: false,
        AVSampleRateKey: SR, AVNumberOfChannelsKey: 2,
    ])
    ro.alwaysCopiesSampleData = false
    guard reader!.canAdd(ro) else { fail("cannot decode \(audioPath) to 48 kHz stereo PCM") }
    reader!.add(ro); readerOut = ro
    let film = CMTimeGetSeconds(filmDur)
    if audioSeconds + 0.5 / Double(fps) < film {
        warn(String(format: "audio is %.3f s, the film %.3f s: the last %.3f s will be silent", audioSeconds, film, film - audioSeconds))
    }
}

// ---- writer
try? FileManager.default.removeItem(at: out)
let writer: AVAssetWriter
do { writer = try AVAssetWriter(outputURL: out, fileType: .mp4) } catch { fail("cannot create \(out.path): \(error.localizedDescription)") }
let vin = AVAssetWriterInput(mediaType: .video, outputSettings: [
    AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: W, AVVideoHeightKey: H,
    AVVideoCompressionPropertiesKey: [
        AVVideoAverageBitRateKey: Int(mbps * 1_000_000), AVVideoProfileLevelKey: AVVideoProfileLevelH264HighAutoLevel,
        AVVideoExpectedSourceFrameRateKey: Int(fps), AVVideoMaxKeyFrameIntervalKey: Int(fps) * 2,
    ],
    AVVideoColorPropertiesKey: [
        AVVideoColorPrimariesKey: AVVideoColorPrimaries_ITU_R_709_2, AVVideoTransferFunctionKey: AVVideoTransferFunction_ITU_R_709_2,
        AVVideoYCbCrMatrixKey: AVVideoYCbCrMatrix_ITU_R_709_2,
    ],
])
vin.expectsMediaDataInRealTime = false
let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: vin, sourcePixelBufferAttributes: [
    kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA, kCVPixelBufferWidthKey as String: W, kCVPixelBufferHeightKey as String: H,
])
guard writer.canAdd(vin) else { fail("the writer refuses a \(W)x\(H) H.264 track") }
writer.add(vin)
var ain: AVAssetWriterInput? = nil
if readerOut != nil {
    var layout = AudioChannelLayout(); layout.mChannelLayoutTag = kAudioChannelLayoutTag_Stereo
    let a = AVAssetWriterInput(mediaType: .audio, outputSettings: [
        AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: SR, AVNumberOfChannelsKey: 2, AVEncoderBitRateKey: 256_000,
        AVChannelLayoutKey: Data(bytes: &layout, count: MemoryLayout<AudioChannelLayout>.size),
    ])
    a.expectsMediaDataInRealTime = false
    guard writer.canAdd(a) else { fail("the writer refuses an AAC 256 kbps track") }
    writer.add(a); ain = a
}
func bail(_ msg: String) -> Never {
    reader?.cancelReading(); writer.cancelWriting(); try? FileManager.default.removeItem(at: out)
    fail(msg + (writer.error.map { " (\($0.localizedDescription))" } ?? ""))
}
if let r = reader, !r.startReading() { bail("cannot start decoding the audio: \(r.error?.localizedDescription ?? "?")") }
guard writer.startWriting() else { bail("writer did not start") }
writer.startSession(atSourceTime: .zero)
guard let pool = adaptor.pixelBufferPool else { bail("no pixel buffer pool") }

final class State: @unchecked Sendable { var failure: String? = nil; var audioFrames = 0; var videoFrames = 0 }
let st = State()
let group = DispatchGroup()
if let a = ain, let ro = readerOut, let r = reader {
    group.enter()
    a.requestMediaDataWhenReady(on: DispatchQueue(label: "audio")) {
        while a.isReadyForMoreMediaData {
            if st.failure != nil { a.markAsFinished(); group.leave(); return }
            guard let sb = ro.copyNextSampleBuffer() else {
                if r.status == .failed { st.failure = "audio decode failed: \(r.error?.localizedDescription ?? "?")" }
                a.markAsFinished(); group.leave(); return
            }
            st.audioFrames += CMSampleBufferGetNumSamples(sb)
            if !a.append(sb) { st.failure = "audio append failed"; a.markAsFinished(); group.leave(); return }
        }
    }
}
group.enter()
let cs = CGColorSpace(name: CGColorSpace.sRGB)!
var vi = 0
vin.requestMediaDataWhenReady(on: DispatchQueue(label: "video")) {
    while vin.isReadyForMoreMediaData {
        if vi >= idx.count || st.failure != nil { vin.markAsFinished(); group.leave(); return }
        let n = idx[vi], name = byIndex[n]!
        let ok: Bool = autoreleasepool {
            guard let cg = (vi == 0 ? firstCG : loadImage(name)) else { st.failure = "cannot decode frame \(name)"; return false }
            if (cg.width != W || cg.height != H) && !lenient { st.failure = "\(name) is \(cg.width)x\(cg.height), the first frame is \(W)x\(H)"; return false }
            var pb: CVPixelBuffer?
            CVPixelBufferPoolCreatePixelBuffer(nil, pool, &pb)
            guard let buf = pb else { st.failure = "no pixel buffer for frame \(n)"; return false }
            CVPixelBufferLockBaseAddress(buf, [])
            let ctx = CGContext(data: CVPixelBufferGetBaseAddress(buf), width: W, height: H, bitsPerComponent: 8,
                                bytesPerRow: CVPixelBufferGetBytesPerRow(buf), space: cs,
                                bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue | CGBitmapInfo.byteOrder32Little.rawValue)!
            ctx.interpolationQuality = .high
            ctx.draw(cg, in: CGRect(x: 0, y: 0, width: W, height: H))
            CVPixelBufferUnlockBaseAddress(buf, [])
            if !adaptor.append(buf, withPresentationTime: CMTime(value: CMTimeValue(vi), timescale: fps)) { st.failure = "video append failed at frame \(n)"; return false }
            return true
        }
        if !ok { vin.markAsFinished(); group.leave(); return }
        vi += 1; st.videoFrames = vi
    }
}
// a writer that fails stops calling the blocks: watch for it instead of hanging
while group.wait(timeout: .now() + 0.5) == .timedOut {
    if writer.status == .failed { bail("writer failed after \(st.videoFrames) frames") }
}
if let f = st.failure { bail(f) }
writer.endSession(atSourceTime: filmDur)
let sem = DispatchSemaphore(value: 0)
writer.finishWriting { sem.signal() }
sem.wait()
guard writer.status == .completed else { try? FileManager.default.removeItem(at: out); fail("failed: \(writer.error?.localizedDescription ?? "unknown writer error")") }
let film = CMTimeGetSeconds(filmDur)
let audioNote = ain == nil ? "no audio" : String(format: "AAC 256 kbps 48 kHz stereo, %.3f s of audio", min(audioSeconds, film))
print("wrote \(out.path) \(W)x\(H) \(idx.count) frames @\(fps)fps (\(String(format: "%.3f", film)) s, \(Int(mbps)) Mbps) + \(audioNote)")
