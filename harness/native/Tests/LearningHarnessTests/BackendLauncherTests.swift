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
