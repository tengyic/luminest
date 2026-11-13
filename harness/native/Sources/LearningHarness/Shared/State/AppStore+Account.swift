import Foundation
import AppKit

extension AppStore {
    func updateTrainingConsent(_ enabled: Bool) async {
        let version = epoch
        do {
            _ = try await api.json("/training/consent", method: "POST", body: ["enabled": enabled])
            guard epoch == version else { return }
            await load("/me") { self.user = $0["user"].isNull ? $0 : $0["user"] }
            notice = enabled ? "Training consent recorded. New model candidates require offline validation before activation." : "Future training exports exclude this account. Existing models cannot be claimed to be untrained."
        } catch { if epoch == version { record(error) } }
    }
    func signOut() async {
        do { _ = try await api.data("/auth/logout", method: "POST") }
        catch { notice = "The server could not revoke the session. The local Keychain session was removed." }
        logout()
    }
    func updateSettings(goal: String, minutes: Int, consent: Bool) async {
        let version = epoch
        busy = true; error = nil
        defer { if epoch == version { busy = false } }
        let trimmed = goal.trimmingCharacters(in: .whitespacesAndNewlines)
        var body: [String: Any] = ["daily_minutes": max(1, min(240, minutes)), "telemetry_consent": consent]
        // A blank goal is rejected by the server rather than stored, so an empty field keeps
        // the goal already on record instead of failing the whole save.
        if !trimmed.isEmpty { body["goal"] = trimmed }
        do {
            let result = try await api.json("/me", method: "PATCH", body: body)
            guard epoch == version else { return }
            user = result["user"].isNull ? result : result["user"]
            activeSeconds = 0
            notice = trimmed.isEmpty && user["goal"].string.isEmpty
                ? "Your pace has been saved. Add a goal whenever you want one."
                : "Your preferences have been saved. Your plan has been re-derived."
            await refresh()
        } catch { if epoch == version { record(error) } }
    }
    func submitProject(id: String, text: String, disclosure: Bool, reflection: String) async {
        let version = epoch
        busy = true; error = nil
        defer { if epoch == version { busy = false } }
        do {
            _ = try await api.json("/projects/" + id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed)! + "/submit", method: "POST", body: ["text": text, "ai_disclosure": disclosure ? "AI assistance was used; the learner remains responsible for the submitted explanation." : "No AI assistance was used in this project.", "reflection": reflection])
            guard epoch == version else { return }
            await load("/projects") { self.projects = $0 }
            guard epoch == version, authenticated else { return }
            notice = "Project submitted. Your feedback is ready."
        } catch { if epoch == version { record(error) } }
    }
    func exportAccount() async {
        let version = epoch
        do {
            let data = try await api.data("/export")
            guard epoch == version, authenticated else { return }
            let panel = NSSavePanel(); panel.nameFieldStringValue = "luminfest-learning-export.json"; panel.allowedContentTypes = [.json]
            guard panel.runModal() == .OK, let url = panel.url else { return }
            try data.write(to: url, options: .atomic)
            notice = "Your learning data was exported."
        } catch { if epoch == version { record(error) } }
    }
    /// A support report the learner can paste into a message.
    ///
    /// The service's `/diagnostics` route is deliberately narrow — configuration and the
    /// tail of the local log, never the learner's work — and this adds the two facts only
    /// the client knows: which build is running, and which macOS it runs on. Without this
    /// there is no support channel at all, which is what the legal text used to promise
    /// and the app did not have.
    func copyDiagnosticReport() async {
        let version = epoch
        do {
            let data = try await api.data("/diagnostics")
            guard epoch == version, authenticated else { return }
            let body = String(data: data, encoding: .utf8) ?? "(the service returned no report)"
            let build = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown"
            let system = ProcessInfo.processInfo.operatingSystemVersionString
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString("Luminfest \(build) on \(system)\n\n" + body, forType: .string)
            notice = "A diagnostic report was copied to the clipboard."
        } catch { if epoch == version { record(error) } }
    }

    func deleteAccount() async {
        let version = epoch
        let account = user["id"].string
        let knownProjects = projects["items"].array.map { $0["id"].string }.filter { !$0.isEmpty }
        do {
            _ = try await api.json("/me", method: "DELETE", body: ["confirmation": "DELETE MY ACCOUNT"])
            guard epoch == version else { return }
            // Unsubmitted writing lives in UserDefaults, outside the server export and
            // erasure ledger. Only a confirmed deletion may remove it; logout retains it.
            ProjectDrafts.clearAccount(account, knownProjects: knownProjects)
            logout()
        } catch { if epoch == version { record(error) } }
    }
    func changeEndpoint(_ value: String) throws {
        let origin = try APIClient.validateEndpoint(value)
        guard origin != endpoint else { return }
        // logout() clears the vault *before* endpoint changes, so credentials scoped to
        // the old origin are removed and cannot be replayed against the new one.
        logout(); endpoint = origin; api.endpoint = origin
        UserDefaults.standard.set(origin, forKey: "luminfest.endpoint")
    }
}
