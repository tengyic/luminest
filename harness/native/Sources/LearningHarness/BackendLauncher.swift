import Foundation
import AppKit
import Darwin

/// What a reachable server says about itself at ``GET /api/v1/health``.
///
/// The payload is parsed in full rather than reduced to a boolean because the boolean
/// used to be the whole story, and the whole story was wrong: a *previous* Luminfest
/// backend - one still running from an earlier install, or from a build someone copied
/// over this one - answers `ready` and the same `service` string, so it was adopted and
/// every later request went to a server with a different request schema. FastAPI then
/// answered 422 (a body that does not match a pydantic model) and the window said the
/// backend could not be reached, which is a different problem with a different fix.
///
/// ``schemaVersion`` is three-valued on purpose. ``absent`` is not the same fact as
/// ``unreadable``: a server that never published the field is old but self-consistent,
/// while a present value this build cannot parse means it is not the build it claims.
struct HealthReport: Equatable {
    /// The version a server publishes in its health payload.
    enum SchemaVersion: Equatable {
        case declared(Int)
        case absent
        /// Published, but not an integer - so not something to compare against.
        case unreadable
    }

    let ready: Bool
    let service: String
    let schemaVersion: SchemaVersion

    /// `nil` when the bytes are not a health payload at all. A body that is not JSON, or
    /// that has no `ready`/`service`, is not a verdict about the server - it is the
    /// absence of one, and the caller keeps looking.
    init?(payload: Data) {
        guard let object = (try? JSONSerialization.jsonObject(with: payload)) as? [String: Any],
              let ready = object["ready"] as? Bool,
              let service = object["service"] as? String else { return nil }
        self.ready = ready
        self.service = service
        if let raw = object["schema_version"] {
            self.schemaVersion = (raw as? Int).map { .declared($0) } ?? .unreadable
        } else {
            self.schemaVersion = .absent
        }
    }
}

/// The decision to make about one ``HealthReport``. Pure, so the adoption policy is
/// testable without a process, a socket or a running server.
enum HealthVerdict: Equatable {
    /// Take this server. The associated value is the schema version it declared, `nil`
    /// when it declared none - the diagnostics panel shows "unknown" rather than a guess.
    case adopt(Int?)
    /// It is Luminfest, but from a build whose requests this one would get 422 from.
    case schemaMismatch(server: Int?, expected: Int)
    /// It says it is not ready; the caller keeps scanning and may still spawn its own.
    case notReady
    /// Something else is on the port. Not ours to reason about.
    case foreignService(String)

    var adoptedVersion: Int? {
        if case .adopt(let version) = self { return version }
        return nil
    }
}

@MainActor final class BackendLauncher {
    static let shared = BackendLauncher()
    private var process: Process?
    private var logHandle: FileHandle?
    private(set) var failure: String?
    private(set) var ready = false
    /// Where the bundled server is actually listening. Usually the default, but a
    /// collision moves it - see ``choosePort`` - and the store rebinds to this.
    private(set) var origin = BackendLauncher.defaultOrigin
    /// The schema version the server actually serving ``origin`` declared, or `nil` when
    /// it declared none. Exposed so diagnostics can show which server this window is
    /// talking to; ``ready`` alone cannot distinguish a matched server from a lucky one.
    private(set) var adoptedSchemaVersion: Int?
    static let defaultOrigin = "http://127.0.0.1:8765"
    private static let defaultPort: UInt16 = 8765

    /// The service string every build of this backend has published, and the one check
    /// that keeps a stranger's server on the port from being adopted.
    nonisolated static let serviceIdentifier = "luminfest-learning-harness"

    /// The database schema this client's request bodies were written against.
    ///
    /// Compile-time, and deliberately so. The frozen backend inside the .app is built
    /// from this same tree and `scripts/package.py` refuses to ship when the frozen
    /// backend's own `SCHEMA_VERSION` disagrees with the sources - so a release carries
    /// one matched pair. The expectation therefore belongs to *this build*, not to
    /// whatever happens to be running on the machine: reading it from the server would
    /// make the check compare the server with itself, which is exactly the bug.
    ///
    /// The tradeoff is drift in the source tree: someone bumps ``db.SCHEMA_VERSION``
    /// without touching this constant. ``BackendLauncherTests`` parses
    /// ``backend/app/db.py`` and fails when the two disagree, so drift is a red test
    /// rather than a shipped mismatch.
    nonisolated static let expectedSchemaVersion = 11

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

    /// The health payload from ``origin``, or `nil` when nothing usable answered.
    ///
    /// A non-200 is reported as nothing. A 503 from this backend means "the database
    /// query failed", which is a server that exists but is not adoptable; the caller
    /// treats both the same way and keeps looking, as it always has.
    private func healthReport(at origin: String) async -> HealthReport? {
        guard let url = URL(string: origin + "/api/v1/health") else { return nil }
        var request = URLRequest(url: url); request.timeoutInterval = 1
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard (response as? HTTPURLResponse)?.statusCode == 200 else { return nil }
            return HealthReport(payload: data)
        } catch { return nil }
    }

    /// Whether ``report`` describes a server this build may talk to.
    ///
    /// The version check is the whole point. Adoption is otherwise decided by facts a
    /// stale backend also tells the truth about - it *is* ready, and it *is* named
    /// Luminfest - so without this a previous install's server is adopted, the new
    /// client sends bodies its models do not know, and FastAPI answers 422 while the
    /// window blames the network. A mismatch is a refusal to adopt, not a downgrade.
    ///
    /// A server that publishes no version is adopted: every build that predates the
    /// field is still this project's server, and refusing them would break installs the
    /// check is meant to protect. The verdict says the version is unknown so the
    /// diagnostics panel can admit it does not know.
    nonisolated static func verdict(for report: HealthReport,
                                   expected: Int = BackendLauncher.expectedSchemaVersion) -> HealthVerdict {
        guard report.ready else { return .notReady }
        guard report.service == serviceIdentifier else { return .foreignService(report.service) }
        switch report.schemaVersion {
        case .absent:
            return .adopt(nil)
        case .declared(let version) where version == expected:
            return .adopt(version)
        case .declared(let version):
            return .schemaMismatch(server: version, expected: expected)
        case .unreadable:
            // Published but not an integer: it is not the version this build was built
            // against, and a value we cannot read is not a value we may wave through.
            return .schemaMismatch(server: nil, expected: expected)
        }
    }

    /// The sentence the window shows instead of "cannot reach the server".
    ///
    /// It has to name the two versions and send the reader to the actual fix - quit the
    /// other copy - because the failure looks like a network fault and is not one.
    /// A schema version as the reader should see it, or an honest "cannot read it".
    nonisolated static func schemaLabel(_ version: Int?) -> String {
        guard let version else { return L10n.t("backend.schema.unreadableVersion") }
        return L10n.tf("backend.schema.versionTag", version)
    }

    nonisolated static func incompatibleSchemaMessage(origin: String,
                                                      server: Int?,
                                                      expected: Int) -> String {
        // `table:` is passed explicitly even though it is nil: the parameter sits before
        // the variadic, so `tf("key", origin, ...)` would bind `origin` to `table`.
        L10n.tf("backend.schema.mismatch", table: nil, origin, schemaLabel(server), expected)
    }

    /// What the port scan concluded.
    private enum ServerDiscovery {
        case none
        case adopted(origin: String, schemaVersion: Int?)
        /// Luminfest servers answered, but none of them speaks this build's schema.
        case incompatible(origin: String, verdict: HealthVerdict)
    }

    /// An already-running bundled server, wherever it landed.
    ///
    /// Scanned rather than assumed. A launch that was force-quit can leave its backend
    /// behind on a fallback port, and probing only the default would start a second one on
    /// the next free port, then a third - each holding the database and a port, with the
    /// app talking to whichever one it happened to spawn. Adopting the live one keeps a
    /// single server per machine, which is the only arrangement the SQLite database and
    /// the learner's session tolerate.
    ///
    /// A server that answers with a *different* schema is not adopted, and is also not
    /// a reason to spawn: it is already holding this install's database, so starting a
    /// second server beside it is the very arrangement described above. The scan keeps
    /// going in case a compatible one is also up, and only when none is does the caller
    /// get ``ServerDiscovery/incompatible`` and stop with an explanation.
    private func runningOrigin() async -> ServerDiscovery {
        var incompatible: (origin: String, verdict: HealthVerdict)?
        for port in Self.defaultPort...(Self.defaultPort + 20) {
            let candidate = "http://127.0.0.1:\(port)"
            guard let report = await healthReport(at: candidate) else { continue }
            let verdict = Self.verdict(for: report)
            switch verdict {
            case .adopt(let version):
                return .adopted(origin: candidate, schemaVersion: version)
            case .schemaMismatch:
                if incompatible == nil { incompatible = (candidate, verdict) }
            case .notReady, .foreignService:
                continue
            }
        }
        if let incompatible { return .incompatible(origin: incompatible.origin, verdict: incompatible.verdict) }
        return .none
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
        // Every attempt starts from a clean slate. ``failure`` used to be set and never
        // cleared, so after a learner quit the incompatible server and pressed Try Again,
        // a healthy launch left the old sentence on screen - an error over a working
        // server. Clearing here rather than at each success path keeps the invariant in
        // one place: "ready" is the only thing a caller may trust.
        failure = nil
        adoptedSchemaVersion = nil
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
        switch await runningOrigin() {
        case .adopted(let origin, let schemaVersion):
            // Ours, already up - possibly on a fallback port from an earlier launch.
            self.origin = origin
            adoptedSchemaVersion = schemaVersion
            ready = true
            return
        case .incompatible(let origin, let verdict):
            // Deliberately no spawn: that server already holds this install's database,
            // and a second one beside it is the arrangement the launcher exists to
            // prevent. Say which versions disagree instead of reporting a server that
            // "did not become ready" or a network that is fine.
            if case .schemaMismatch(let server, let expected) = verdict {
                failure = Self.incompatibleSchemaMessage(origin: origin, server: server, expected: expected)
            }
            return
        case .none:
            break
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
            // Where this launch's own output begins. The log is appended to across launches,
            // so a "Schema upgrade required" from an earlier run must not be allowed to
            // explain a failure that has nothing to do with it.
            let logStart = UInt64((try? FileManager.default.attributesOfItem(atPath: log.path)[.size] as? NSNumber)?.intValue ?? 0)
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
            // An empty provider is *unconfigured*, not an offline mode. The backend now
            // rejects HARNESS_TUTOR_PROVIDER=offline, so writing that legacy value here
            // would stop the app from booting at all. The app boots in a declared
            // "model-required" state and the Settings screen is where the user adds a key.
            var provider = tutorValue("HARNESS_TUTOR_PROVIDER") ?? ""
            if provider == "offline" {
                try? logHandle?.write(contentsOf: Data(
                    "tutor.env sets HARNESS_TUTOR_PROVIDER=offline, which is no longer supported; starting unconfigured so a model can be added in Settings.\n".utf8))
                provider = ""
            }
            // An incomplete tutor.env must not make the app unusable: `Settings` rejects a
            // provider without a URL, model or key, the server exits, and the app reports a
            // server that "did not become ready" - a message pointing at the wrong problem.
            // Stay unconfigured and say why in the log instead.
            if !provider.isEmpty {
                let missing = ["HARNESS_TUTOR_URL", "HARNESS_TUTOR_MODEL"]
                    .filter { tutorValue($0) == nil }
                let needsKey = provider != "ollama" && tutorValue("HARNESS_TUTOR_KEY") == nil
                if !missing.isEmpty || needsKey {
                    let names = missing + (needsKey ? ["HARNESS_TUTOR_KEY"] : [])
                    try? logHandle?.write(contentsOf: Data(
                        "tutor.env asks for HARNESS_TUTOR_PROVIDER=\(provider) but sets no \(names.joined(separator: ", ")); starting unconfigured (model-required).\n".utf8))
                    provider = ""
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
            // ceiling, not a delay: a warm launch still returns as soon as `healthReport` answers.
            let deadline = ProcessInfo.processInfo.systemUptime + 120
            while ProcessInfo.processInfo.systemUptime < deadline {
                if let report = await healthReport(at: origin) {
                    switch Self.verdict(for: report) {
                    case .adopt(let schemaVersion):
                        adoptedSchemaVersion = schemaVersion
                        ready = true
                        return
                    case .schemaMismatch(let server, let expected):
                        // The bundle's own backend disagreeing with the client is a build
                        // error, not a slow start: say so at once instead of waiting out
                        // the 120 s ceiling and blaming the log.
                        failure = Self.incompatibleSchemaMessage(origin: origin, server: server, expected: expected)
                        stopOwnedProcess()
                        return
                    case .notReady, .foreignService:
                        break   // still starting, or a stranger briefly held the port
                    }
                }
                if !child.isRunning { break }
                try await Task.sleep(nanoseconds: 200_000_000)
            }
            // The generic sentence is the last resort, not the first answer. A backend that
            // exits at boot writes the real reason to this log (the schema guard in
            // app.main says why in one line) and nobody ever read it - so the app blamed a
            // slow start for a database it refused to touch. Read what this launch wrote.
            let diagnosis = Self.startupFailure(
                logText: Self.logText(at: log, from: logStart),
                dataDirectory: support.path)
            failure = diagnosis
                ?? "The bundled learning server did not become ready. Check the local server log in Application Support/Luminfest Learning Harness. No progress is being fabricated."
            stopOwnedProcess()
        } catch {
            failure = "The bundled server could not start: " + error.localizedDescription
            stopOwnedProcess()
        }
    }
    /// The text this launch appended to ``url``, capped so a long log cannot stall the
    /// main actor. ``offset`` is the file size captured before the child started - without
    /// it, a "Schema upgrade required" left by an earlier run would be read back and
    /// blamed for an unrelated failure today.
    nonisolated static func logText(at url: URL, from offset: UInt64, limit: Int = 64_000) -> String {
        guard let handle = try? FileHandle(forReadingFrom: url) else { return "" }
        defer { try? handle.close() }
        let end = (try? handle.seekToEnd()) ?? 0
        guard end > offset else { return "" }
        let length = min(UInt64(limit), end - offset)
        guard (try? handle.seek(toOffset: end - length)) != nil,
              let data = try? handle.read(upToCount: Int(length)) else { return "" }
        return String(decoding: data, as: UTF8.self)
    }

    /// Turn a failed start into the reason the server itself gave, when it gave one.
    ///
    /// The one case worth recognising is the schema guard (``app.main``): the bundled
    /// backend refuses to boot on a data directory written by another version and says so
    /// in one line. Seeing that sentence beats "did not become ready", which sends the
    /// reader looking for a network problem that does not exist - the same misdiagnosis as
    /// the 422 this file was changed to stop causing.
    ///
    /// Nothing is migrated, moved or deleted here: the message names the database and the
    /// log and leaves the decision to the person whose data it is.
    nonisolated static func startupFailure(logText: String, dataDirectory: String) -> String? {
        guard logText.contains("Schema upgrade required") else { return nil }
        let database = dataDirectory + "/harness.sqlite3"
        return L10n.tf("backend.schema.upgradeRequired", table: nil,
                       database, dataDirectory + "/backend.log")
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
        adoptedSchemaVersion = nil
        try? logHandle?.close(); logHandle = nil
    }
}
