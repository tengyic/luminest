import Foundation

/// The assessment book and written perspective observations.
///
/// The client is a thin renderer here on purpose. Both the unit grade and every
/// perspective value are decided by the server from persisted evidence; a second
/// grader in SwiftUI would eventually disagree with the one truth the learner's
/// learning state uses. The only decisions the app makes are which unit to freeze
/// and which artifact a self-observation is attached to.
extension AppStore {
    /// Freeze one unit's grade. The server refuses (409) when any declared standard
    /// still lacks evidence, and the failure text is shown rather than swallowed:
    /// a disabled button with no message reads as a broken app.
    func finaliseUnitGrade(key: String) async {
        let version = epoch
        busy = true; error = nil
        defer { if epoch == version { busy = false } }
        do {
            let encoded = key.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? key
            _ = try await api.json("/gradebook/\(encoded)/grade", method: "POST", body: [:])
            guard epoch == version, authenticated else { return }
            await load("/gradebook") { self.gradebook = $0 }
            guard epoch == version else { return }
            notice = "Unit grade recorded. It is scored against this course's declared standards."
        } catch { if epoch == version { record(error) } }
    }

    /// Record a learner's own written observation about one of their projects.
    ///
    /// ``artifactID`` must be a real project row. The server refuses an invented id,
    /// a bare score with no written evidence, and any attempt to score someone else's
    /// work — so the form's disabled state is a convenience, not the boundary.
    func recordSelfObservation(projectID: String, dimension: String, score: Int,
                               note: String) async {
        let version = epoch
        busy = true; error = nil
        defer { if epoch == version { busy = false } }
        let subject = user["id"].string
        guard !subject.isEmpty else {
            error = "Your account is still loading. Try again in a moment."
            return
        }
        do {
            _ = try await api.json("/perspectives/reviews", method: "POST", body: [
                "subject_id": subject,
                "artifact_type": "project",
                "artifact_id": projectID,
                "dimension": dimension,
                "score": score,
                "evidence_note": note,
                "reviewer_role": "self",
            ])
            guard epoch == version, authenticated else { return }
            await load("/perspectives") { self.perspectives = $0 }
            await load("/analytics") { self.analytics = $0 }
            guard epoch == version else { return }
            notice = "Observation saved. You can withdraw it at any time."
        } catch { if epoch == version { record(error) } }
    }

    /// Withdraw an observation this account wrote. Consent includes taking it back.
    func withdrawObservation(id: String) async {
        let version = epoch
        busy = true; error = nil
        defer { if epoch == version { busy = false } }
        do {
            let encoded = id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? id
            _ = try await api.json("/perspectives/reviews/\(encoded)", method: "DELETE")
            guard epoch == version, authenticated else { return }
            await load("/perspectives") { self.perspectives = $0 }
            await load("/analytics") { self.analytics = $0 }
        } catch { if epoch == version { record(error) } }
    }
}
