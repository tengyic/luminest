import Foundation

// -------------------------------------------------- external media surfaces
//
// Three concept-scoped media surfaces beyond the lesson payload: the narrated deck
// (NotebookLM-style, assembled server-side), the external simulation map for this
// concept, and curated video. All three are data from the same licence-gated
// pipeline; the client renders status honestly and never upgrades a withheld card.

extension AppStore {
    var deckData: JSON { deck["ok"].bool ? deck["data"] : .null }

    func buildDeck() async {
        guard authenticated, !selectedConcept.isEmpty, !deckBusy else { return }
        let version = epoch, id = selectedConcept
        deckBusy = true
        defer { if epoch == version { deckBusy = false } }
        do {
            let result = try await api.json("/presentations", method: "POST",
                                            body: ["concept_id": id, "options": [String: Any]()])
            guard epoch == version, id == selectedConcept else { return }
            deck = result
            showDeck = result["ok"].bool
            connected = true
        } catch { if epoch == version { record(error) } }
    }

    func loadConceptSimulations() async {
        guard authenticated, !selectedConcept.isEmpty, !conceptSimulationsBusy else { return }
        let version = epoch, id = selectedConcept
        conceptSimulationsBusy = true
        defer { if epoch == version { conceptSimulationsBusy = false } }
        do {
            let path = "/simulations/" + id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed)! + "/external"
            let result = try await api.json(path)
            guard epoch == version, id == selectedConcept else { return }
            conceptSimulations = result
            connected = true
        } catch { if epoch == version { record(error) } }
    }

    /// Load the playground catalogue, so the entry point can list real games rather than
    /// describe them in the abstract. The gallery page fetches the same endpoint for itself;
    /// this copy is for the native card, and the two cannot disagree because they read the
    /// one catalogue.
    func loadPlayground() async {
        guard authenticated, !playgroundBusy else { return }
        let version = epoch
        playgroundBusy = true
        defer { if epoch == version { playgroundBusy = false } }
        do {
            let result = try await api.json("/playground")
            guard epoch == version else { return }
            playground = result
            connected = true
        } catch { if epoch == version { record(error) } }
    }

    /// Open the gallery sheet, optionally on one game. The slug is only a hint for the page;
    /// if it cannot be honoured the gallery is shown on its own list.
    func openPlayground(slug: String? = nil) {
        playgroundSlug = slug
        showPlayground = true
    }

    /// The one honest telemetry fact about an external simulation: the learner opened it.
    /// A PhET embed reports no parameters back, so this event carries only the concept id -
    /// it never fabricates an interaction value the app cannot observe. Consent-gated like
    /// every other telemetry path; rejected outright when consent is off.
    func recordExternalSimulationOpened(concept: String) async {
        guard authenticated, user["telemetry_consent"].bool, !concept.isEmpty else { return }
        let body: [String: Any] = ["events": [["id": UUID().uuidString,
                                               "type": "external_simulation_opened",
                                               "occurred_at": ISO8601DateFormatter().string(from: Date()),
                                               "payload": ["concept_id": concept]]]]
        do { _ = try await api.json("/events", method: "POST", body: body) }
        catch { record(error) }
    }

    func loadMediaPosture() async {
        guard authenticated else { return }
        let version = epoch
        do {
            let result = try await api.json("/media/sources")
            guard epoch == version else { return }
            // The image pipeline reports whether network media is enabled at all; the
            // client uses it to say "offline by configuration" rather than guessing.
            mediaOnline = result["image_pipeline"]["enabled"].bool
        } catch { if epoch == version { record(error) } }
    }
}
