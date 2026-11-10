import Foundation

extension AppStore {
    func loadChat() async {
        let id = selectedConcept, version = epoch
        guard !id.isEmpty else { return }
        do {
            let result = try await api.json("/chat", query: [URLQueryItem(name: "concept_id", value: id)])
            guard version == epoch, id == selectedConcept, authenticated else { return }
            messages = result["messages"].isNull ? result.array : result["messages"].array
            chatMedia = []
        } catch { if epoch == version && id == selectedConcept { record(error) } }
    }
    func sendMessage(_ text: String) async {
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, !selectedConcept.isEmpty, !chatBusy else { return }
        // Asking is the clearest evidence there is that the learner is here; without this
        // the interval check would keep asking the server about someone who is talking.
        noteLearnerAction()
        let version = epoch, id = selectedConcept
        chatBusy = true
        chatActivities = []
        speechStatus = ""
        speech.stop()
        defer { if epoch == version { chatBusy = false } }
        do {
            // The agentic turn: the tutor runs the full tool loop (curriculum lookups,
            // licence-cleared image search, workspace, ...) and the response carries the
            // media it surfaced, so the chat can show real pictures instead of prose-only.
            //
            // `board_id` names the Stage's shared whiteboard for this concept, which is
            // what tells the tutor it has a board to draw on; without it the draw-aloud
            // section of its instructions never fires and the lesson stays text.
            var request: [String: Any] = ["message": text, "developer_mode": false,
                                          "context": ["concept_id": id, "role": "learner",
                                                      "board_id": "wb-\(id)"],
                                          "speak": speakEnabled,
                                          // Resolved on this Mac, not stored on the account.
                                          // Both /agent/stream and the /agent/chat fallback
                                          // take the same body, so one selection covers both.
                                          "voice": effectiveVoice,
                                          "tone": effectiveTone]
            if !teacherStyleProfile.isEmpty { request["teacher_profile"] = teacherStyleProfile }

            // The streamed turn first: each event arrives as the loop produces it, so the
            // activity chips are live rather than a finished trace. `/agent/chat` is the
            // fallback for a backend without the SSE route - same reply, no live chips.
            var reply = ""
            var reason = ""
            var speechDescriptor: JSON = .null
            // A declared fallback from a turn that could not answer: it carries the
            // reason and the learner's next action. It is deliberately not `reply` -
            // showing it as an assistant message would turn a status notice into a
            // fabricated answer.
            var notice: JSON = .null
            var events: [JSON] = []
            var streamed = false
            do {
                for try await event in api.serverEvents("/agent/stream", body: request) {
                    guard epoch == version, id == selectedConcept else { return }
                    events.append(event.payload)
                    switch event.name {
                    case "tool_call":
                        let label = event.payload["label"].string
                        if !label.isEmpty {
                            chatActivities.append(ChatActivity(id: event.payload["id"].string,
                                                               label: label, state: .running))
                        }
                    case "tool_result":
                        if let index = chatActivities.lastIndex(where: { $0.id == event.payload["id"].string }) {
                            chatActivities[index].state = event.payload["ok"].bool ? .done : .failed
                        }
                    case "message_delta":
                        reply += event.payload["text"].string
                    case "turn_end":
                        reason = event.payload["reason"].string
                        speechDescriptor = event.payload["speech"]
                        notice = event.payload["notice"]
                    default:
                        break
                    }
                }
                streamed = true
            } catch {
                // A backend without `/agent/stream`, or a connection that dropped
                // mid-turn. The JSON route carries the same answer, so fall through to
                // it rather than reporting a failure the learner does not have.
            }
            if !streamed {
                let result = try await api.json("/agent/chat", method: "POST", body: request)
                guard epoch == version, id == selectedConcept else { return }
                reply = result["message"].string
                reason = result["finish_reason"].string
                speechDescriptor = result["speech"]
                notice = result["notice"]
                events = result["events"].array
                for event in events {
                    switch event["type"].string {
                    case "tool_call":
                        let label = event["label"].string
                        if !label.isEmpty {
                            chatActivities.append(ChatActivity(id: event["id"].string,
                                                               label: label, state: .running))
                        }
                    case "tool_result":
                        if let index = chatActivities.lastIndex(where: { $0.id == event["id"].string }) {
                            chatActivities[index].state = event["ok"].bool ? .done : .failed
                        }
                    default:
                        break
                    }
                }
            }
            guard epoch == version, id == selectedConcept else { return }
            messages.append(try JSON.make(["role": "user", "content": text]))
            if !reply.isEmpty {
                messages.append(try JSON.make(["role": "assistant", "content": reply]))
            }
            // The media the tutor's own tools surfaced, read off the turn's events.
            // Taken from the events rather than a second search: what the trace says the
            // tutor found is what the learner should be shown, and re-searching would
            // produce a different list than the one the reply is grounded in.
            chatMedia = mediaFromTurnEvents(events)
            if reply.isEmpty && reason != "completed" {
                let why = notice["reason"].string
                let next = notice["next_action"].string
                let detail = why.isEmpty
                    ? "The tutor turn finished without a reply (finish_reason: \(reason.isEmpty ? "unknown" : reason))."
                    : "\(why)\n\(next)"
                record(AppFailure(message: detail, status: nil))
            }
            connected = true
            if !speechDescriptor.isNull { playSpeech(speechDescriptor, version: version) }
        } catch { if epoch == version { record(error) } }
    }

    /// The licence-cleared media a turn surfaced, from its own event trace.
    ///
    /// Two shapes arrive: ``image_search`` returns an ``images`` list of embed-posture
    /// URLs, and ``find_image`` returns one ``asset`` this instance already downloaded.
    /// Both are rendered from the trace so the grid can never show a picture the tutor
    /// did not actually find.
    private func mediaFromTurnEvents(_ events: [JSON]) -> [[String: String]] {
        var out: [[String: String]] = []
        var seen = Set<String>()
        for event in events where event["type"].string == "tool_result" && event["ok"].bool {
            let inner = event["data"]["data"]
            guard !inner.isNull else { continue }
            for candidate in inner["images"].array {
                let url = candidate["thumb_url"].string.isEmpty ? candidate["file_url"].string : candidate["thumb_url"].string
                guard !url.isEmpty, !seen.contains(url) else { continue }
                seen.insert(url)
                out.append(["thumb_url": url, "title": candidate["title"].string,
                            "licence": candidate["licence"].string,
                            "source_page": candidate["landing_page_url"].string])
            }
            let asset = inner["asset"]
            if !asset.isNull, !asset["title"].isNull {
                let url = asset["file_url"].string
                guard !url.isEmpty, !seen.contains(url) else { continue }
                seen.insert(url)
                out.append(["thumb_url": url, "title": asset["title"].string,
                            "licence": asset["licence_code"].string,
                            "source_page": asset["landing_page_url"].string])
            }
        }
        return Array(out.prefix(8))
    }

    /// Speak the tutor's reply through the local VoiceStudio backend.
    ///
    /// The clip is rendered off the request path - a local synthesis costs 20-40 s for a
    /// paragraph, and a learner must not wait that long to read the answer - so the
    /// descriptor usually says ``pending`` and this polls until the bytes exist. A
    /// refusal (voice output switched off, an engine that is not running) is reported
    /// with the server's own sentence rather than silently doing nothing.
    /// `internal`, not `private`: the silent supervisor in `AppStore.swift` speaks a notice
    /// through the same path. See ADR-0003, "access-level changes".
    func playSpeech(_ descriptor: JSON, version: UUID) {
        let url = descriptor["url"].string
        guard !url.isEmpty else { return }
        switch descriptor["state"].string {
        case "ready":
            loadAndSpeak(url, version: version)
        case "unavailable", "failed":
            speechStatus = descriptor["reason"].string
        default:
            speechStatus = "Preparing the tutor's voice…"
            Task { [weak self] in
                guard let self else { return }
                for _ in 0..<120 {           // up to ~60 s, one poll every half second
                    if self.epoch != version { return }
                    if let data = try? await self.api.artifact(url), !data.isEmpty {
                        self.speechStatus = ""
                        self.speech.play(data)
                        return
                    }
                    try? await Task.sleep(nanoseconds: 500_000_000)
                }
                self.speechStatus = "The tutor's voice did not finish rendering."
            }
        }
    }

    private func loadAndSpeak(_ url: String, version: UUID) {
        Task { [weak self] in
            guard let self else { return }
            guard let data = try? await self.api.artifact(url), !data.isEmpty else {
                if self.epoch == version { self.speechStatus = "The recording could not be read." }
                return
            }
            if self.epoch == version { self.speech.play(data) }
        }
    }
}
