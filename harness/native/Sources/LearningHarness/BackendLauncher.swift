import Foundation
import AppKit
import Darwin

@MainActor final class BackendLauncher {
    static let shared = BackendLauncher()
    private var process: Process?
    private var logHandle: FileHandle?
    private(set) var failure: String?
    private(set) var ready = false
    /// Where the bundled server is actually listening. Usually the default, but a
    /// collision moves it - see ``choosePort`` - and the store rebinds to this.
    private(set) var origin = BackendLauncher.defaultOrigin
    static let defaultOrigin = "http://127.0.0.1:8765"
    private static let defaultPort: UInt16 = 8765

    /// True when nothing is listening on 127.0.0.1:``port``.
    ///
    /// A bind probe, not a connect probe: connecting tells you *something* answers, while
    /// the question here is whether the port can be taken. ``SO_REUSEADDR`` is set because
    /// a socket in TIME_WAIT must not count as an occupant, but an active listener still
    /// makes ``bind`` fail with EADDRINUSE, which is exactly the case to avoid.
    private func portIsFree(_ port: UInt16) -> Bool {
        let fd = socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { return false }
        defer { close(fd) }
        var yes: Int32 = 1
        setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes,
                   socklen_t(MemoryLayout<Int32>.size))
        var address = sockaddr_in()
        address.sin_family = sa_family_t(AF_INET)
        address.sin_port = port.bigEndian
        address.sin_addr.s_addr = inet_addr("127.0.0.1")
        let size = socklen_t(MemoryLayout<sockaddr_in>.size)
        let bound = withUnsafePointer(to: &address) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                bind(fd, $0, size)
            }
        }
        return bound == 0
    }

    /// The port to bind: the default when it is free, otherwise the first free one after.
    ///
    /// Luminfest is not the only thing that can own 8765 - a developer's other server can,
    /// and it often does. A desktop app that refuses to start because of a port collision
    /// is indistinguishable from one that is broken, and the failure text ("the server did
    /// not become ready") sends the reader to the wrong place entirely.
    private func choosePort() -> UInt16 {
        if portIsFree(Self.defaultPort) { return Self.defaultPort }
        for port in (Self.defaultPort + 1)...(Self.defaultPort + 20) where portIsFree(port) {
            return port
        }
        return Self.defaultPort   // let the spawn fail with the real error
    }

    /// Tutor settings an operator leaves beside the server's data, so a double-click from
    /// Finder is still model-backed.
    ///
    /// Exporting `HARNESS_TUTOR_*` into a shell works but means the app only has a real tutor
    /// when it is launched from a terminal, which nobody does with a desktop app. The file is
    /// read from Application Support rather than from inside the .app because the bundle is
    /// code-signed - nothing may be added after signing - and because a metered provider key
    /// shipped inside a distributable bundle is a key handed to every recipient.
    ///
    /// Only tutor keys are honoured. A file able to set `HARNESS_DATA_DIR` or
    /// `HARNESS_ALLOWED_HOSTS` would let a stray line repoint the server's storage or network
    /// policy, which is not a decision a tutor credential should be able to carry.
    ///
    /// The `DEEPSEEK_*` aliases are resolved here, not passed through: ``app.config.load_dotenv``
    /// only aliases them while reading its own file, so the same names arriving in the process
    /// environment would be silently ignored and the tutor would come up with no key.
    static func operatorTutorEnv(at support: URL) -> [String: String] {
        let path = support.appendingPathComponent("tutor.env")
        guard let text = try? String(contentsOf: path, encoding: .utf8) else { return [:] }
        var loaded: [String: String] = [:]
        for line in text.split(whereSeparator: \.isNewline) {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            guard !trimmed.isEmpty, !trimmed.hasPrefix("#"),
                  let equals = trimmed.firstIndex(of: "=") else { continue }
            let key = String(trimmed[trimmed.startIndex..<equals]).trimmingCharacters(in: .whitespaces)
            var value = String(trimmed[trimmed.index(after: equals)...]).trimmingCharacters(in: .whitespaces)
            if value.count >= 2, let first = value.first, let last = value.last,
               (first == "\"" && last == "\"") || (first == "'" && last == "'") {
                value = String(value.dropFirst().dropLast())
            }
            guard !key.isEmpty else { continue }
            loaded[key] = value
        }
        let allowed: Set<String> = ["HARNESS_TUTOR_PROVIDER", "HARNESS_TUTOR_URL",
                                    "HARNESS_TUTOR_MODEL", "HARNESS_TUTOR_KEY",
                                    "HARNESS_TUTOR_TIMEOUT_SECONDS"]
        var result = loaded.filter { allowed.contains($0.key) }
        for (source, target) in [("DEEPSEEK_API_KEY", "HARNESS_TUTOR_KEY"),
                                 ("DEEPSEEK_BASE_URL", "HARNESS_TUTOR_URL")] {
            if let value = loaded[source], !value.isEmpty, result[target] == nil {
                result[target] = value
            }
        }
        return result
    }

    private func health(at origin: String) async -> Bool {
        guard let url = URL(string: origin + "/api/v1/health") else { return false }
        var request = URLRequest(url: url); request.timeoutInterval = 1
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard (response as? HTTPURLResponse)?.statusCode == 200,
                  let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { return false }
            return object["ready"] as? Bool == true && object["service"] as? String == "luminfest-learning-harness"
        } catch { return false }
    }

    private func health() async -> Bool { await health(at: origin) }

    /// An already-running bundled server, wherever it landed.
    ///
    /// Scanned rather than assumed. A launch that was force-quit can leave its backend
    /// behind on a fallback port, and probing only the default would start a second one on
    /// the next free port, then a third - each holding the database and a port, with the
    /// app talking to whichever one it happened to spawn. Adopting the live one keeps a
    /// single server per machine, which is the only arrangement the SQLite database and
    /// the learner's session tolerate.
    private func runningOrigin() async -> String? {
        for port in Self.defaultPort...(Self.defaultPort + 20) {
            let candidate = "http://127.0.0.1:\(port)"
            if await health(at: candidate) { return candidate }
        }
        return nil
    }

    /// Whether an endpoint is this app's own local server rather than one the operator chose.
    ///
    /// ``AppStore`` stores the origin it ends up on, so the first launch that takes a fallback
    /// port writes `…:8766` into the same key an operator would use to point the app at a
    /// server of their own. On the next launch that read as an operator decision, the launcher
    /// returned without spawning anything, and the app came up with no server at all — broken,
    /// with nothing in the window saying why. The ports ``choosePort`` scans are this app's
    /// own; anything outside them is still treated as a deliberate choice.
    static func isOwnLocalEndpoint(_ value: String) -> Bool {
        guard let url = URL(string: value), let host = url.host,
              host == "127.0.0.1" || host == "localhost" else { return false }
        guard let port = url.port else { return false }
        return port >= Int(defaultPort) && port <= Int(defaultPort) + 20
    }

    func startIfBundled() async {
        guard !ProcessInfo.processInfo.arguments.contains("--ui-test"), !ready else { return }
        let configured = UserDefaults.standard.string(forKey: "luminfest.endpoint")
            ?? Self.defaultOrigin
        // A configured endpoint means the user pointed the app at a server of their own;
        // spawning a local one would be answering a different question. A loopback address in
        // the range the launcher itself scans is the exception: that is this app's own
        // fallback port, remembered from a previous launch, and refusing to start a server
        // because of it leaves the app talking to nothing.
        guard configured == Self.defaultOrigin || Self.isOwnLocalEndpoint(configured) else {
            // Publish the operator's origin before returning. ``origin`` defaults to the
            // default port, and AppStore's post-launch rebind compares against it - without
            // this assignment a configured endpoint (say 8766, because another service owns
            // 8765) would be silently stomped back to 8765 and every request would go to a
            // stranger's server.
            origin = configured
            return
        }
        guard let resources = Bundle.main.resourceURL else { return }
        let executable = resources.appendingPathComponent("backend/LuminfestBackend/LuminfestBackend")
        guard FileManager.default.isExecutableFile(atPath: executable.path) else { return }
        if let running = await runningOrigin() {
            // Ours, already up - possibly on a fallback port from an earlier launch.
            origin = running
            ready = true
            return
        }
        let port = choosePort()
        if port != Self.defaultPort { origin = "http://127.0.0.1:\(port)" }
        do {
            let support = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
                .appendingPathComponent("Luminfest Learning Harness", isDirectory: true)
            try FileManager.default.createDirectory(at: support, withIntermediateDirectories: true)
            try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: support.path)
            let log = support.appendingPathComponent("backend.log")
            if !FileManager.default.fileExists(atPath: log.path) { FileManager.default.createFile(atPath: log.path, contents: nil) }
            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: log.path)
            logHandle = try FileHandle(forWritingTo: log); try logHandle?.seekToEnd()
            let child = Process(); child.executableURL = executable
            child.arguments = ["--port", String(port)]
            child.currentDirectoryURL = support
            let inherited = ProcessInfo.processInfo.environment
            var environment = inherited
            // The bundled server owns its own storage and network settings: never inherit those from
            // an arbitrary shell. Tutor provider settings are the exception, because they are the
            // administrator's explicit opt-in to a generated tutor (Ollama or an OpenAI-compatible
            // endpoint). Without them the app stays on the grounded offline tutor.
            environment = environment.filter { !$0.key.hasPrefix("HARNESS_") && !$0.key.hasPrefix("PYTHON") }
            environment["HARNESS_DATA_DIR"] = support.path
            // ``desktop``, not ``development``. The bundle used to ship as development,
            // where the server defaulted to no age gate and switched attention monitoring
            // and outbound media *on* - while privacy.md told the user the activity signal
            // was off by default. ``desktop`` keeps the local single-user assumptions
            // (SQLite, auto-create, first account becomes the operator) but is strict
            // about consent, and leaves media off so the policy's sub-processor table
            // stays true. ``production`` is not an option here: it demands PostgreSQL and
            // a 32-character secret and would simply refuse to boot.
            environment["HARNESS_ENV"] = "desktop"
            environment["HARNESS_AUTO_CREATE"] = "1"
            environment["HARNESS_ALLOWED_HOSTS"] = "localhost,127.0.0.1"
            // The browser presentation of this window is off unless the operator turned it on
            // in Settings. It is read here rather than from the environment because the
            // launcher strips inherited ``HARNESS_*`` keys — and because a capability that
            // captures the screen should be something the person at the Mac chose, not
            // something a shell variable happened to enable.
            if UserDefaults.standard.bool(forKey: "luminfest.streamEnabled") {
                environment["HARNESS_STREAM_ENABLED"] = "1"
            }
            // A real environment variable still wins over the file, the same precedence
            // ``config.load_dotenv`` applies to backend/.env.
            let operatorEnv = Self.operatorTutorEnv(at: support)
            func tutorValue(_ key: String) -> String? {
                if let value = inherited[key], !value.isEmpty { return value }
                if let value = operatorEnv[key], !value.isEmpty { return value }
                return nil
            }
            var provider = tutorValue("HARNESS_TUTOR_PROVIDER") ?? "offline"
            // A typo in tutor.env must not make the app unusable: `Settings` rejects a provider
            // without a URL, model or key, the server exits, and the app reports a server that
            // "did not become ready" - a message pointing at the wrong problem. Stay offline and
            // say why in the log instead, which is where the reader is already sent.
            if provider != "offline" {
                let missing = ["HARNESS_TUTOR_URL", "HARNESS_TUTOR_MODEL", "HARNESS_TUTOR_KEY"]
                    .filter { tutorValue($0) == nil }
                if !missing.isEmpty {
                    try? logHandle?.write(contentsOf: Data(
                        "tutor.env asks for HARNESS_TUTOR_PROVIDER=\(provider) but sets no \(missing.joined(separator: ", ")); staying on the offline tutor.\n".utf8))
                    provider = "offline"
                }
            }
            environment["HARNESS_TUTOR_PROVIDER"] = provider
            for key in ["HARNESS_TUTOR_URL", "HARNESS_TUTOR_MODEL", "HARNESS_TUTOR_KEY", "HARNESS_TUTOR_TIMEOUT_SECONDS"] {
                if let value = tutorValue(key) { environment[key] = value }
            }
            child.environment = environment
            child.standardInput = FileHandle.nullDevice
            child.standardOutput = logHandle; child.standardError = logHandle
            try child.run(); process = child
            // 120 s, not 35. The very first launch of a freshly copied bundle has none of its
            // few hundred MB of collected dylibs in the page cache, and was measured at ~60 s
            // to `ready` on this machine while the same binary took ~18 s warm. A 35 s budget
            // therefore failed the one case it most needs to survive - the bundle handed to
            // someone else, whose first launch is by definition cold - and reported a server
            // that "did not become ready" when it was in fact about to be. The wait is a
            // ceiling, not a delay: a warm launch still returns as soon as `health()` answers.
            let deadline = ProcessInfo.processInfo.systemUptime + 120
            while ProcessInfo.processInfo.systemUptime < deadline {
                if await health() { ready = true; return }
                if !child.isRunning { break }
                try await Task.sleep(nanoseconds: 200_000_000)
            }
            failure = "The bundled learning server did not become ready. Check the local server log in Application Support/Luminfest Learning Harness. No progress is being fabricated."
            stopOwnedProcess()
        } catch {
            failure = "The bundled server could not start: " + error.localizedDescription
            stopOwnedProcess()
        }
    }
    /// Bounded grace between SIGTERM and any escalation. This runs on the main
    /// actor, both during app termination and on the start-failure path, so
    /// shutdown must never be able to hang the UI.
    nonisolated static let terminationGraceSeconds: TimeInterval = 1.2

    /// Pure escalation decision, kept out of the side-effecting code so the contract
    /// is unit-testable without spawning (or signalling) any process. A SIGKILL is
    /// legitimate only for a child this launcher actually owns that is still alive
    /// after the SIGTERM grace. Anything else would mean killing a stranger's process.
    nonisolated static func shouldForceKillAfterGrace(ownsProcess: Bool,
                                                      isRunning: Bool) -> Bool {
        ownsProcess && isRunning
    }

    /// The real shutdown sequence, factored out of ``stopOwnedProcess()`` so a
    /// process-level regression test can drive exactly the code the app runs without
    /// having to expose the private stored property. ``ownsProcess`` must be true only
    /// for a child this launcher spawned itself: an adopted/external backend is never
    /// ours to signal. Both call sites are @MainActor and the grace loop blocks the main
    /// actor synchronously, so nothing can swap ``process`` mid-shutdown; evaluating the
    /// ownership flag at the call site is therefore equivalent to the old inline check.
    static func shutdown(owned: Process,
                         ownsProcess: Bool,
                         grace: TimeInterval = terminationGraceSeconds) {
        guard owned.isRunning else { return }
        // ``terminate()`` is SIGTERM. A backend blocked in a signal handler, or
        // ignoring SIGTERM, otherwise survives app termination and keeps holding
        // its port, so the next launch adopts a stale server. Capture the PID at
        // spawn time and escalate to exactly that PID - never a name or a pattern.
        let pid = owned.processIdentifier
        owned.terminate()
        let deadline = Date().addingTimeInterval(grace)
        while owned.isRunning && Date() < deadline {
            RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.05))
        }
        if shouldForceKillAfterGrace(ownsProcess: ownsProcess,
                                     isRunning: owned.isRunning) {
            _ = kill(pid, SIGKILL)  // ESRCH is harmless: the child exited at the deadline
        }
    }

    /// Acceptance-only hook. The in-process QA driver spawns a real frozen backend on
    /// an isolated port and installs it as the launcher's owned child, so a normal
    /// `NSApp.terminate` drives the exact production path
    /// `applicationWillTerminate -> stopOwnedProcess() -> shutdown(...)`.
    /// It is reachable only when `--qa-owned-shutdown` is passed and is never used by
    /// a normal launch; the launcher still refuses to signal any adopted backend.
    func qaInstallOwnedProcess(_ child: Process) {
        process = child
        ready = true
    }

    func stopOwnedProcess() {
        if let owned = process, owned.isRunning {
            Self.shutdown(owned: owned, ownsProcess: process === owned)
        }
        process = nil; ready = false
        try? logHandle?.close(); logHandle = nil
    }
}
