// mux — put an audio track on an existing MP4. The video samples are copied untouched (passthrough: no re-encode, colour
// tags and frame timing kept); the audio is decoded and encoded once to AAC-LC 256 kbps, 48 kHz stereo, and trimmed to the
// picture. Use it when the picture is already encoded (encode) and the music arrives later; for a fresh master,
// encode_av writes picture + sound in one pass.
// usage: mux <video.mp4> <audio.wav|.m4a|.aif|.mp3> <out.mp4> [--offset s]
//   audio    any file AVFoundation reads; no afconvert step needed. (An AAC passthrough export cuts the last 44 ms of
//            encoder priming, so the audio is always re-encoded to cover the picture exactly.)
//   --offset positive: the audio starts s seconds into the film (silence before); negative: skip the first |s| seconds of
//            the audio. Fix a late or early beat by shifting the music, never the picture.
// Fails with a clear message when either file has no track or the writer stops; warns when the audio ends before the
// picture. Check the result with probe <out.mp4> --audio before sending.
// Build (macOS): swiftc -O mux.swift -o mux   (or scripts/setup.sh)
// Elsewhere: ffmpeg -i film.mp4 -i music.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 256k -shortest out.mp4
import AVFoundation
import Foundation

func fail(_ msg: String, code: Int32 = 1) -> Never {
    FileHandle.standardError.write("mux: \(msg)\n".data(using: .utf8)!)
    exit(code)
}
func warn(_ msg: String) { FileHandle.standardError.write("mux: warning: \(msg)\n".data(using: .utf8)!) }
final class Box<T>: @unchecked Sendable { var value: T?; init() {} }
func blocking<T>(_ body: @escaping @Sendable () async throws -> T) throws -> T {
    let box = Box<Result<T, Error>>(), sem = DispatchSemaphore(value: 0)
    Task.detached { do { box.value = .success(try await body()) } catch { box.value = .failure(error) }; sem.signal() }
    sem.wait()
    return try box.value!.get()
}

var argv = Array(CommandLine.arguments.dropFirst())
var offset = 0.0
if let i = argv.firstIndex(of: "--offset") {
    guard i + 1 < argv.count, let v = Double(argv[i + 1]) else { fail("--offset needs seconds, e.g. --offset -0.12", code: 2) }
    offset = v; argv.removeSubrange(i...(i + 1))
}
guard argv.count >= 3 else { fail("usage: mux <video.mp4> <audio> <out.mp4> [--offset s]", code: 2) }
let videoURL = URL(fileURLWithPath: argv[0]), audioURL = URL(fileURLWithPath: argv[1]), out = URL(fileURLWithPath: argv[2])
for u in [videoURL, audioURL] where !FileManager.default.fileExists(atPath: u.path) { fail("no such file: \(u.path)") }
if out.standardizedFileURL == videoURL.standardizedFileURL || out.standardizedFileURL == audioURL.standardizedFileURL {
    fail("the output must be a new file, not one of the inputs")
}

// ---- inputs (the assets stay alive for the whole run: a track only lives as long as its asset)
let v = AVURLAsset(url: videoURL), a = AVURLAsset(url: audioURL)
guard let vt = try? blocking({ try await v.loadTracks(withMediaType: .video).first }) else { fail("\(videoURL.lastPathComponent) has no video track") }
guard let at = try? blocking({ try await a.loadTracks(withMediaType: .audio).first }) else { fail("\(audioURL.lastPathComponent) has no audio track") }
let vRange = try blocking { try await vt.load(.timeRange) }
let vTransform = try blocking { try await vt.load(.preferredTransform) }
guard let vFormat = try blocking({ try await vt.load(.formatDescriptions) }).first else { fail("cannot read the video format") }
let vSegs = try blocking { try await vt.load(.segments) }
let aRange = try blocking { try await at.load(.timeRange) }
// media time of the first shown frame (encoders that reorder frames start their media timeline a few frames late)
let S = vSegs.first(where: { !$0.isEmpty })?.timeMapping.source.start ?? vRange.start
let vDur = vRange.duration, vSec = CMTimeGetSeconds(vDur)
let SR = 48000
let srcStart = max(0, -offset), dstStart = max(0, offset)
let take = min(vSec - dstStart, CMTimeGetSeconds(aRange.duration) - srcStart)
guard take > 0 else { fail(String(format: "with --offset %.3f no audio overlaps the %.3f s video", offset, vSec)) }

let vReader: AVAssetReader, aReader: AVAssetReader
do { vReader = try AVAssetReader(asset: v); aReader = try AVAssetReader(asset: a) } catch { fail("cannot open the inputs: \(error.localizedDescription)") }
let vOut = AVAssetReaderTrackOutput(track: vt, outputSettings: nil)        // compressed samples, untouched
vOut.alwaysCopiesSampleData = false
vReader.add(vOut)
aReader.timeRange = CMTimeRange(start: CMTimeAdd(aRange.start, CMTime(seconds: srcStart, preferredTimescale: 48000)),
                                duration: CMTime(seconds: take, preferredTimescale: 48000))
let aOut = AVAssetReaderTrackOutput(track: at, outputSettings: [
    AVFormatIDKey: kAudioFormatLinearPCM, AVLinearPCMBitDepthKey: 32, AVLinearPCMIsFloatKey: true,
    AVLinearPCMIsBigEndianKey: false, AVLinearPCMIsNonInterleaved: false, AVSampleRateKey: SR, AVNumberOfChannelsKey: 2,
])
guard aReader.canAdd(aOut) else { fail("cannot decode \(audioURL.lastPathComponent) to 48 kHz stereo PCM") }
aReader.add(aOut)

// ---- writer
try? FileManager.default.removeItem(at: out)
let writer: AVAssetWriter
do { writer = try AVAssetWriter(outputURL: out, fileType: .mp4) } catch { fail("cannot create \(out.path): \(error.localizedDescription)") }
writer.shouldOptimizeForNetworkUse = true
let vin = AVAssetWriterInput(mediaType: .video, outputSettings: nil, sourceFormatHint: vFormat)
vin.transform = vTransform; vin.expectsMediaDataInRealTime = false
var layout = AudioChannelLayout(); layout.mChannelLayoutTag = kAudioChannelLayoutTag_Stereo
let ain = AVAssetWriterInput(mediaType: .audio, outputSettings: [
    AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: SR, AVNumberOfChannelsKey: 2, AVEncoderBitRateKey: 256_000,
    AVChannelLayoutKey: Data(bytes: &layout, count: MemoryLayout<AudioChannelLayout>.size),
])
ain.expectsMediaDataInRealTime = false
guard writer.canAdd(vin), writer.canAdd(ain) else { fail("the writer refuses these tracks") }
writer.add(vin); writer.add(ain)
func bail(_ msg: String) -> Never {
    vReader.cancelReading(); aReader.cancelReading(); writer.cancelWriting(); try? FileManager.default.removeItem(at: out)
    fail(msg + (writer.error.map { " (\($0.localizedDescription))" } ?? ""))
}
guard vReader.startReading() else { bail("cannot read the video: \(vReader.error?.localizedDescription ?? "?")") }
guard aReader.startReading() else { bail("cannot decode the audio: \(aReader.error?.localizedDescription ?? "?")") }
guard writer.startWriting() else { bail("writer did not start") }
writer.startSession(atSourceTime: S)

final class State: @unchecked Sendable { var failure: String? = nil; var written = 0; var silenceLeft = 0; var fmt: CMAudioFormatDescription? = nil }
let st = State()
st.silenceLeft = Int((dstStart * Double(SR)).rounded())
/// zeros in the decoder's own format, for the --offset lead-in
func silence(_ frames: Int, at pts: CMTime, _ fmt: CMAudioFormatDescription) -> CMSampleBuffer? {
    let bytes = frames * 8
    var block: CMBlockBuffer?
    guard CMBlockBufferCreateWithMemoryBlock(allocator: nil, memoryBlock: nil, blockLength: bytes, blockAllocator: nil, customBlockSource: nil,
                                             offsetToData: 0, dataLength: bytes, flags: kCMBlockBufferAssureMemoryNowFlag, blockBufferOut: &block) == noErr,
          let b = block, CMBlockBufferFillDataBytes(with: 0, blockBuffer: b, offsetIntoDestination: 0, dataLength: bytes) == noErr else { return nil }
    var sb: CMSampleBuffer?
    CMAudioSampleBufferCreateReadyWithPacketDescriptions(allocator: nil, dataBuffer: b, formatDescription: fmt, sampleCount: frames,
                                                         presentationTimeStamp: pts, packetDescriptions: nil, sampleBufferOut: &sb)
    return sb
}
func filmTime(_ samples: Int) -> CMTime { CMTimeAdd(S, CMTime(value: CMTimeValue(samples), timescale: CMTimeScale(SR))) }
let group = DispatchGroup()
group.enter()
ain.requestMediaDataWhenReady(on: DispatchQueue(label: "audio")) {
    while ain.isReadyForMoreMediaData {
        if st.failure != nil { ain.markAsFinished(); group.leave(); return }
        guard let sb = aOut.copyNextSampleBuffer() else {
            if aReader.status == .failed { st.failure = "audio decode failed: \(aReader.error?.localizedDescription ?? "?")" }
            ain.markAsFinished(); group.leave(); return
        }
        let n = CMSampleBufferGetNumSamples(sb)
        if n == 0 { continue }
        if st.fmt == nil { st.fmt = CMSampleBufferGetFormatDescription(sb) }
        while st.silenceLeft > 0, st.failure == nil, let f = st.fmt {   // lead-in for a positive --offset
            let k = min(4096, st.silenceLeft)
            guard let z = silence(k, at: filmTime(st.written), f) else { st.failure = "cannot build the silent lead-in"; break }
            while !ain.isReadyForMoreMediaData && writer.status == .writing { usleep(1000) }
            if !ain.append(z) { st.failure = "audio append failed (lead-in)"; break }
            st.written += k; st.silenceLeft -= k
        }
        var timing = CMSampleTimingInfo(duration: CMTime(value: 1, timescale: CMTimeScale(SR)), presentationTimeStamp: filmTime(st.written), decodeTimeStamp: .invalid)
        var moved: CMSampleBuffer?
        CMSampleBufferCreateCopyWithNewTiming(allocator: nil, sampleBuffer: sb, sampleTimingEntryCount: 1, sampleTimingArray: &timing, sampleBufferOut: &moved)
        guard st.failure == nil, let m = moved, ain.append(m) else { st.failure = st.failure ?? "audio append failed"; ain.markAsFinished(); group.leave(); return }
        st.written += n
    }
}
group.enter()
vin.requestMediaDataWhenReady(on: DispatchQueue(label: "video")) {
    while vin.isReadyForMoreMediaData {
        if st.failure != nil { vin.markAsFinished(); group.leave(); return }
        guard let sb = vOut.copyNextSampleBuffer() else {
            if vReader.status == .failed { st.failure = "video read failed: \(vReader.error?.localizedDescription ?? "?")" }
            vin.markAsFinished(); group.leave(); return
        }
        if CMSampleBufferGetNumSamples(sb) == 0 { continue }
        if !vin.append(sb) { st.failure = "video append failed"; vin.markAsFinished(); group.leave(); return }
    }
}
while group.wait(timeout: .now() + 0.5) == .timedOut {
    if writer.status == .failed { bail("writer failed") }
}
if let f = st.failure { bail(f) }
writer.endSession(atSourceTime: CMTimeAdd(S, vDur))
let sem = DispatchSemaphore(value: 0)
writer.finishWriting { sem.signal() }
sem.wait()
guard writer.status == .completed else { try? FileManager.default.removeItem(at: out); fail("failed: \(writer.error?.localizedDescription ?? "unknown writer error")") }
let endAt = min(vSec, Double(st.written) / Double(SR))
if endAt + 0.02 < vSec { warn(String(format: "audio ends at %.3f s, the video at %.3f s: silence after", endAt, vSec)) }
print(String(format: "wrote %@ · video %.3f s (copied) · audio %.3f–%.3f s of the film (AAC 256 kbps)", out.path, vSec, dstStart, endAt))
