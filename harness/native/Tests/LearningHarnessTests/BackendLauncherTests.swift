import XCTest
import Darwin
@testable import LearningHarness

/// The launcher has to tell "the operator pointed the app at their own server" apart from
/// "the app remembered the fallback port it took last time". Both arrive as the same stored
/// string, and getting it wrong is not a cosmetic bug: the app starts no server and shows a
/// window that cannot sign in, with no message saying why.
@MainActor
final class BackendLauncherTests: XCTestCase {

    func testItsOwnFallbackPortsCountAsItsOwn() {
        for port in 8765...8785 {
            XCTAssertTrue(BackendLauncher.isOwnLocalEndpoint("http://127.0.0.1:\(port)"),
                          "\(port) is a port the launcher scans, so it is the app's own")
        }
    }

    func testLocalhostSpellingIsTheSameMachine() {
        XCTAssertTrue(BackendLauncher.isOwnLocalEndpoint("http://localhost:8766"))
    }

    /// Outside the scan range the operator meant something: a different local service, a
    /// server on the LAN, or one on the internet. None of those may be replaced by a
    /// locally spawned backend.
    func testAnythingElseIsAnOperatorsChoice() {
        XCTAssertFalse(BackendLauncher.isOwnLocalEndpoint("http://127.0.0.1:9000"))
        XCTAssertFalse(BackendLauncher.isOwnLocalEndpoint("https://luminfest.example.com"))
        XCTAssertFalse(BackendLauncher.isOwnLocalEndpoint("http://192.168.1.20:8766"))
        XCTAssertFalse(BackendLauncher.isOwnLocalEndpoint("not a url"))
        XCTAssertFalse(BackendLauncher.isOwnLocalEndpoint("http://127.0.0.1"))
    }

    /// ``stopOwnedProcess()`` escalates to SIGKILL only when a SIGTERM-ignoring
    /// backend is still alive after the grace period. The decision is a pure function
    /// so this test proves the contract without spawning or signalling any process.
    /// The acceptance failure being guarded against: with SIGTERM alone, a backend
    /// that ignores it survived app termination and kept its port bound.
    func testForceKillOnlyForAnOwnedStillRunningChild() {
        XCTAssertTrue(BackendLauncher.shouldForceKillAfterGrace(ownsProcess: true,
                                                                isRunning: true))
        XCTAssertFalse(BackendLauncher.shouldForceKillAfterGrace(ownsProcess: true,
                                                                 isRunning: false),
                       "a child that honoured SIGTERM must never be signalled again")
        XCTAssertFalse(BackendLauncher.shouldForceKillAfterGrace(ownsProcess: false,
                                                                 isRunning: true),
                       "an adopted/external backend is not ours to kill")
        XCTAssertFalse(BackendLauncher.shouldForceKillAfterGrace(ownsProcess: false,
                                                                 isRunning: false))
    }

    func testTerminationGraceIsBounded() {
        XCTAssertGreaterThan(BackendLauncher.terminationGraceSeconds, 0)
        XCTAssertLessThanOrEqual(BackendLauncher.terminationGraceSeconds, 3.0,
                                 "shutdown must not stall the main actor")
    }

    // MARK: - Which server may be adopted
    //
    // The reported bug: on a second machine the window said the backend could not be
    // reached while the server was answering 422. 422 is FastAPI refusing the *shape* of
    // a request, i.e. the app and the server were different builds. The launcher caused
    // it by adopting whatever server answered /api/v1/health - a previous install's
    // backend answers `ready: true` and the same `service` string, so nothing in the old
    // check could tell them apart. These cases pin the rule that fixes it, with no
    // process spawned and no port bound.

    private func report(_ json: String) throws -> HealthReport {
        try XCTUnwrap(HealthReport(payload: Data(json.utf8)), "payload should parse: \(json)")
    }

    func testAdoptsAServerReportingTheExpectedSchema() throws {
        let health = try report(#"{"ready":true,"service":"luminfest-learning-harness","schema_version":11}"#)
        XCTAssertEqual(BackendLauncher.verdict(for: health, expected: 11), .adopt(11))
    }

    /// The bug itself: the same service string, a different schema. Adopting this is what
    /// produced 422 on every request afterwards.
    func testRefusesAServerReportingAnOlderSchema() throws {
        let health = try report(#"{"ready":true,"service":"luminfest-learning-harness","schema_version":10}"#)
        XCTAssertEqual(BackendLauncher.verdict(for: health, expected: 11),
                       .schemaMismatch(server: 10, expected: 11))
    }

    /// A newer server is just as unusable from this build: the disagreement is symmetric.
    func testRefusesAServerReportingANewerSchema() throws {
        let health = try report(#"{"ready":true,"service":"luminfest-learning-harness","schema_version":12}"#)
        XCTAssertEqual(BackendLauncher.verdict(for: health, expected: 11),
                       .schemaMismatch(server: 12, expected: 11))
    }

    /// Builds that predate the field are still this project's server. Refusing them would
    /// break installs this check exists to protect - but the verdict must say it is a
    /// guess, so diagnostics can print "unknown" instead of inventing a version.
    func testAdoptsAServerThatPublishesNoVersionAndReportsItUnknown() throws {
        let health = try report(#"{"ready":true,"service":"luminfest-learning-harness"}"#)
        XCTAssertEqual(health.schemaVersion, .absent)
        XCTAssertEqual(BackendLauncher.verdict(for: health, expected: 11), .adopt(nil))
        XCTAssertNil(BackendLauncher.verdict(for: health, expected: 11).adoptedVersion)
    }

    /// A version we cannot read is not a version we wave through: treating `"11"` as
    /// "absent" would silently adopt the very server this check is meant to refuse.
    func testRefusesAVersionItCannotRead() throws {
        let health = try report(#"{"ready":true,"service":"luminfest-learning-harness","schema_version":"11"}"#)
        XCTAssertEqual(health.schemaVersion, .unreadable)
        XCTAssertEqual(BackendLauncher.verdict(for: health, expected: 11),
                       .schemaMismatch(server: nil, expected: 11))
    }

    func testDoesNotAdoptAServerThatSaysItIsNotReady() throws {
        let health = try report(#"{"ready":false,"service":"luminfest-learning-harness","schema_version":11}"#)
        XCTAssertEqual(BackendLauncher.verdict(for: health, expected: 11), .notReady)
    }

    /// The service name is the only thing standing between the app and a stranger's
    /// server on 8765 - a proxy, a dev server, another app. It must keep that job now
    /// that the schema check sits behind it.
    func testDoesNotAdoptAForeignServiceEvenOnTheRightPort() throws {
        let health = try report(#"{"ready":true,"service":"some-other-service","schema_version":11}"#)
        XCTAssertEqual(BackendLauncher.verdict(for: health, expected: 11),
                       .foreignService("some-other-service"))
    }

    /// A 200 whose body is not a health payload is the absence of an answer, not a
    /// refusal: the scan must keep looking rather than stop on it.
    func testABodyThatIsNotAHealthPayloadIsNotAReport() {
        XCTAssertNil(HealthReport(payload: Data("not json".utf8)))
        XCTAssertNil(HealthReport(payload: Data(#"{"ok":true}"#.utf8)),
                     "a report needs ready and service; without them it is a stranger")
    }

    /// The failure has to send the reader to the real fix. "Cannot reach the server" is
    /// what made this a support thread: nothing is unreachable.
    func testMismatchMessageNamesBothVersionsAndTheFix() {
        let message = BackendLauncher.incompatibleSchemaMessage(
            origin: "http://127.0.0.1:8765", server: 10, expected: 11)
        XCTAssertTrue(message.contains("http://127.0.0.1:8765"))
        XCTAssertTrue(message.contains("schema v10"))
        XCTAssertTrue(message.contains("schema v11"))
        XCTAssertTrue(message.contains("Quit the other copy"))
        XCTAssertTrue(message.contains("no second server was started"),
                      "the reader must know nothing was spawned or migrated behind their back")
    }

    func testMismatchMessageCoversAValueItCannotRead() {
        let message = BackendLauncher.incompatibleSchemaMessage(
            origin: "http://127.0.0.1:8766", server: nil, expected: 11)
        XCTAssertTrue(message.contains("cannot read"))
        XCTAssertTrue(message.contains("schema v11"))
    }

    // MARK: - Reading the server's own reason for a failed start
    //
    // Second half of the reported bug: on a machine with a previous install the bundled
    // backend exits at boot because the data directory is from another version (the
    // schema guard in app.main), and the old code reported "did not become ready". The
    // log already said why; nobody read it. These cases are pure string/file work.

    private let schemaGuardTrace = """
    Traceback (most recent call last):
      File "app/main.py", line 718, in create_app
        raise RuntimeError('Schema upgrade required; run scripts/init_db.py explicitly. '
    RuntimeError: Schema upgrade required; run scripts/init_db.py explicitly. Startup never migrates existing tables.
    """

    func testSchemaGuardInTheLogBecomesTheFailureReason() throws {
        let message = try XCTUnwrap(BackendLauncher.startupFailure(
            logText: schemaGuardTrace, dataDirectory: "/Users/x/Library/Application Support/Luminfest Learning Harness"))
        XCTAssertTrue(message.contains("Schema upgrade required"), message)
        XCTAssertTrue(message.contains("different Luminfest version"), message)
        XCTAssertTrue(message.contains("harness.sqlite3"), message)
        XCTAssertTrue(message.contains("backend.log"), message)
        XCTAssertTrue(message.contains("back that database up"), message)
    }

    /// Any other way a start fails must not be dressed up as a schema problem.
    func testAnUnrelatedStartFailureIsNotBlamedOnTheSchema() {
        XCTAssertNil(BackendLauncher.startupFailure(
            logText: "ModuleNotFoundError: No module named 'uvicorn'", dataDirectory: "/tmp"))
        XCTAssertNil(BackendLauncher.startupFailure(logText: "", dataDirectory: "/tmp"))
    }

    /// The log is appended to across launches. Only what this launch wrote may explain
    /// this launch's failure, otherwise an old "Schema upgrade required" line would keep
    /// misdiagnosing unrelated starts for the life of the install.
    func testOnlyTheCurrentLaunchsLogIsRead() throws {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("lf-log-\(UUID().uuidString).txt")
        defer { try? FileManager.default.removeItem(at: url) }
        let earlier = "RuntimeError: Schema upgrade required; old run\n"
        try (earlier + "starting fine\n").write(to: url, atomically: true, encoding: .utf8)
        let offset = UInt64(earlier.utf8.count)

        XCTAssertEqual(BackendLauncher.logText(at: url, from: 0).hasPrefix("RuntimeError"), true)
        XCTAssertEqual(BackendLauncher.logText(at: url, from: offset), "starting fine\n")
        XCTAssertNil(BackendLauncher.startupFailure(
            logText: BackendLauncher.logText(at: url, from: offset), dataDirectory: "/tmp"),
            "a previous launch's schema error must not explain this one")
    }

    // MARK: - Drift guard

    /// ``expectedSchemaVersion`` is a compile-time constant, so nothing stops it from
    /// going stale when the backend's ``SCHEMA_VERSION`` moves. This reads the backend
    /// source beside the package and fails on drift, which is the cheapest place to
    /// catch it: at `swift test`, not on a user's second machine as a 422.
    func testExpectedSchemaVersionMatchesTheBackendSource() throws {
        // .../Tests/LearningHarnessTests/BackendLauncherTests.swift -> .../harness
        let harness = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // LearningHarnessTests
            .deletingLastPathComponent()   // Tests
            .deletingLastPathComponent()   // native
            .deletingLastPathComponent()   // harness
        let db = harness.appendingPathComponent("backend/app/db.py")
        guard let text = try? String(contentsOf: db, encoding: .utf8) else {
            throw XCTSkip("backend sources are not beside this package: \(db.path)")
        }
        let declared = text.split(whereSeparator: \.isNewline)
            .first { $0.hasPrefix("SCHEMA_VERSION") }
            .flatMap { line -> Int? in
                let value = line.split(separator: "=").last.map(String.init) ?? ""
                return Int(value.trimmingCharacters(in: .whitespaces))
            }
        XCTAssertEqual(declared, BackendLauncher.expectedSchemaVersion,
                       "BackendLauncher.expectedSchemaVersion must be bumped with \(db.path)")
    }

    // MARK: - Acceptance test 2.5: real process-level regression

    /// Spawn exactly ONE child process. ``trap '' TERM`` installs SIG_IGN, which POSIX
    /// preserves across ``exec``, so ``exec sleep 20`` leaves a single PID that ignores
    /// SIGTERM - no forked ``sleep`` orphan to leak. The shell writes a sentinel file
    /// only AFTER installing SIG_IGN; the caller must wait for it, otherwise a SIGTERM
    /// sent immediately after ``Process.run()`` lands on a shell that has not yet run
    /// ``trap`` and the fixture is silently invalid. Every signal below is sent only to
    /// the PID returned by this test's own ``Process.run()``.
    private func spawnChild(ignoringTerm: Bool) throws -> (Process, URL) {
        let sentinel = FileManager.default.temporaryDirectory
            .appendingPathComponent("lf-launcher-fixture-\(UUID().uuidString).ready")
        try? FileManager.default.removeItem(at: sentinel)

        let child = Process()
        child.executableURL = URL(fileURLWithPath: "/bin/sh")
        child.arguments = ["-c", ignoringTerm
                           ? "trap '' TERM; : > \"$1\"; exec sleep 20"
                           : ": > \"$1\"; exec sleep 20",
                           "sh", sentinel.path]
        try child.run()
        XCTAssertGreaterThan(child.processIdentifier, 0)

        let deadline = Date().addingTimeInterval(2.0)
        while !FileManager.default.fileExists(atPath: sentinel.path) && Date() < deadline {
            Thread.sleep(forTimeInterval: 0.02)
        }
        XCTAssertTrue(FileManager.default.fileExists(atPath: sentinel.path),
                      "fixture never reported that SIG_IGN was installed")
        return (child, sentinel)
    }

    private func cleanup(_ child: Process, _ sentinel: URL) {
        if child.isRunning { _ = kill(child.processIdentifier, SIGKILL) }
        try? FileManager.default.removeItem(at: sentinel)
    }

    /// The exact failure found by acceptance test 2.5: with SIGTERM alone, a backend
    /// that ignores it survived app termination and kept its port bound. This drives the
    /// real ``BackendLauncher.shutdown(owned:ownsProcess:grace:)`` with a live child,
    /// not a Python re-implementation and not the pure predicate.
    func testSigtermIgnoringOwnedChildIsForceKilled() throws {
        let (child, sentinel) = try spawnChild(ignoringTerm: true)
        let pid = child.processIdentifier
        defer { cleanup(child, sentinel) }

        // Prove the fixture is genuine. If SIGTERM already killed it, the old
        // SIGTERM-only implementation would also "pass" and this test would be vacuous.
        XCTAssertEqual(kill(pid, SIGTERM), 0)
        Thread.sleep(forTimeInterval: 0.2)
        XCTAssertTrue(child.isRunning, "fixture must survive SIGTERM")

        let started = Date()
        BackendLauncher.shutdown(owned: child, ownsProcess: true)
        let elapsed = Date().timeIntervalSince(started)
        child.waitUntilExit()

        XCTAssertFalse(child.isRunning,
                       "a SIGTERM-ignoring owned backend must not survive shutdown")
        XCTAssertEqual(child.terminationReason, .uncaughtSignal)
        XCTAssertEqual(child.terminationStatus, 9,
                       "death must come from SIGKILL - not SIGTERM, not a normal exit")
        XCTAssertEqual(kill(pid, 0), -1,
                       "no process may remain at the PID recorded at spawn")
        XCTAssertLessThan(elapsed, 3.0, "shutdown must stay bounded on the main actor")
    }

    /// Escalation is a fallback, not the default: a cooperative child must die from
    /// SIGTERM (15) and never receive a second, stronger signal.
    func testCooperativeOwnedChildIsNotForceKilled() throws {
        let (child, sentinel) = try spawnChild(ignoringTerm: false)
        defer { cleanup(child, sentinel) }

        BackendLauncher.shutdown(owned: child, ownsProcess: true)
        child.waitUntilExit()

        XCTAssertFalse(child.isRunning)
        XCTAssertEqual(child.terminationReason, .uncaughtSignal)
        XCTAssertEqual(child.terminationStatus, 15,
                       "SIGTERM alone must suffice; a cooperative child must not be SIGKILLed")
    }

    /// Safety contract: anything the launcher does NOT own (an adopted/external
    /// backend) must never be force-killed, even if it ignores SIGTERM. Only SIGTERM
    /// is sent; the child is cleaned up by this test's own teardown block.
    func testUnownedChildIsNeverForceKilled() throws {
        let (child, sentinel) = try spawnChild(ignoringTerm: true)
        defer { cleanup(child, sentinel) }

        BackendLauncher.shutdown(owned: child, ownsProcess: false)

        XCTAssertTrue(child.isRunning,
                      "an unowned process must survive: SIGKILL is never allowed for it")
    }
}
