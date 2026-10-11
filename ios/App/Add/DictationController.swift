import SwiftUI
import Observation
import Speech
import AVFoundation

/// Live dictation with `SFSpeechRecognizer` + `AVAudioEngine`. On a mock launch (Simulator / UI tests) it plays
/// a canned transcript instead of touching the microphone.
@MainActor
@Observable
final class DictationController {
    enum State: Equatable {
        case idle
        case listening
        case denied(PermissionKind)
        case unavailable(String)
    }

    private(set) var state: State = .idle
    var transcript = ""

    private let simulated: Bool
    private let micDenied: Bool
    private var engine: AVAudioEngine?
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var simulation: Task<Void, Never>?

    init(simulated: Bool, micDenied: Bool = false) {
        self.simulated = simulated
        self.micDenied = micDenied
    }

    var isListening: Bool { state == .listening }

    func toggle() {
        if isListening { stop() } else { Task { await start() } }
    }

    func start() async {
        guard !isListening else { return }
        if micDenied { state = .denied(.microphone); return }
        if simulated {
            state = .listening
            simulation = Task {
                try? await Task.sleep(for: .seconds(1.2))
                if Task.isCancelled { return }
                transcript = MockAddText.sampleTranscript
                state = .idle
            }
            return
        }
        guard await Self.requestSpeech() else { state = .denied(.speech); return }
        guard await AVAudioApplication.requestRecordPermission() else { state = .denied(.microphone); return }
        guard let recognizer = SFSpeechRecognizer(locale: Locale.current) ?? SFSpeechRecognizer(), recognizer.isAvailable else {
            state = .unavailable("Speech recognition isn't available right now. You can type it instead.")
            return
        }
        do {
            try begin(recognizer)
            state = .listening
        } catch {
            teardown()
            state = .unavailable("We couldn't start listening. You can type it instead.")
        }
    }

    func stop() {
        simulation?.cancel()
        simulation = nil
        request?.endAudio()
        teardown(keepTask: true)
        if state == .listening { state = .idle }
    }

    /// Clears a denied / unavailable state (after the person chose another way).
    func reset() { state = .idle }

    // MARK: Engine

    private func begin(_ recognizer: SFSpeechRecognizer) throws {
        teardown()
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.record, mode: .measurement, options: .duckOthers)
        try session.setActive(true, options: .notifyOthersOnDeactivation)
        let engine = AVAudioEngine()
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in request.append(buffer) }
        engine.prepare()
        try engine.start()
        self.engine = engine
        self.request = request
        task = recognizer.recognitionTask(with: request) { [weak self] result, error in
            let text = result?.bestTranscription.formattedString
            let finished = result?.isFinal == true || error != nil
            Task { @MainActor [weak self] in
                guard let self else { return }
                if let text, !text.isEmpty { self.transcript = text }
                if finished {
                    self.teardown()
                    if self.state == .listening { self.state = .idle }
                }
            }
        }
    }

    private func teardown(keepTask: Bool = false) {
        if let engine {
            if engine.isRunning { engine.stop() }
            engine.inputNode.removeTap(onBus: 0)
        }
        engine = nil
        request = nil
        if !keepTask { task?.cancel(); task = nil }
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    private static func requestSpeech() async -> Bool {
        switch SFSpeechRecognizer.authorizationStatus() {
        case .authorized: return true
        case .denied, .restricted: return false
        default:
            return await withCheckedContinuation { cont in
                SFSpeechRecognizer.requestAuthorization { cont.resume(returning: $0 == .authorized) }
            }
        }
    }
}
