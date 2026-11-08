import Foundation

@MainActor final class APIClient {
    var endpoint: String
    var token: String?
    private var session: URLSession
    /// A session for the tutor's streamed turn. Its own on purpose: a turn runs a tool
    /// and then a provider call and then another tool, so it can take minutes, and the
    /// default 45 s resource timeout would abort a healthy lesson mid-sentence.
    private let streamSession: URLSession
    init(endpoint: String) {
        self.endpoint = endpoint
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 25
        config.timeoutIntervalForResource = 45
        session = URLSession(configuration: config)
        let streamConfig = URLSessionConfiguration.ephemeral
        streamConfig.timeoutIntervalForRequest = 300
        streamConfig.timeoutIntervalForResource = 900
        streamSession = URLSession(configuration: streamConfig)
    }
    func cancelAll() {
        session.invalidateAndCancel()
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 25
        session = URLSession(configuration: config)
    }
    static func validateEndpoint(_ text: String) throws -> String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard let u = URL(string: trimmed), let scheme = u.scheme, ["http", "https"].contains(scheme),
              let host = u.host, u.user == nil, u.password == nil, u.query == nil, u.fragment == nil,
              u.path.isEmpty || u.path == "/" else {
            throw AppFailure(message: "Use a server origin such as http://127.0.0.1:8765 (no path or credentials).", status: nil)
        }
        if scheme == "http" && !["127.0.0.1", "localhost", "::1"].contains(host) {
            throw AppFailure(message: "Remote servers must use HTTPS to protect your account.", status: nil)
        }
        return trimmed
    }
    func data(_ path: String, method: String = "GET", body: [String: Any]? = nil, query: [URLQueryItem] = []) async throws -> Data {
        guard var components = URLComponents(string: endpoint + "/api/v1" + path) else { throw AppFailure(message: "Invalid server address.", status: nil) }
        if !query.isEmpty { components.queryItems = query }
        guard let url = components.url else { throw AppFailure(message: "Invalid request URL.", status: nil) }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        // Telling the server which language the learner is reading is what makes generated
        // questions, tutor turns and decks come back in that language rather than English.
        request.setValue(Self.acceptLanguage(preference: UserDefaults.standard.string(forKey: "luminfest.language")),
                         forHTTPHeaderField: "Accept-Language")
        if let token { request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization") }
        if let body { request.httpBody = try JSONSerialization.data(withJSONObject: body); request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw AppFailure(message: "The server returned an invalid response.", status: nil) }
        guard (200..<300).contains(response.statusCode) else {
            let j = (try? JSONDecoder().decode(JSON.self, from: data)) ?? .null
            throw AppFailure(message: Self.failureDetail(j, status: response.statusCode),
                             status: response.statusCode)
        }
        return data
    }
    /// The `Accept-Language` this app sends.
    ///
    /// Read from the stored preference rather than from `Localization.shared`: request
    /// paths run off the main actor, and a background `Task` must not crash on an isolated
    /// access or quietly fall back to English. `nil` means "follow the system", which is
    /// the same promise the language picker makes.
    nonisolated static func acceptLanguage(preference: String?,
                                           system: [String] = Locale.preferredLanguages) -> String {
        switch preference {
        case AppLanguage.simplifiedChinese.rawValue:
            // The q-values are not decoration: without them a server that honours
            // preference order can pick `en` from the tail of the list.
            return "zh-Hans,zh;q=0.9,en;q=0.5"
        case AppLanguage.english.rawValue:
            return "en"
        default:
            return system.first ?? "en"
        }
    }

    func json(_ path: String, method: String = "GET", body: [String: Any]? = nil, query: [URLQueryItem] = []) async throws -> JSON {
        let d = try await data(path, method: method, body: body, query: query)
        return d.isEmpty ? .null : try JSONDecoder().decode(JSON.self, from: d)
    }

    /// The server's own explanation for a non-2xx, or a sentence naming the status.
    ///
    /// A failed validation arrives as ``detail`` = a *list* of `{loc, msg}` objects. Reading
    /// only the string form collapsed every one of them to "Request failed (HTTP 422)",
    /// which is indistinguishable from "the server is down" and sends the reader looking for
    /// a network fault that does not exist. The per-field join is shared by the JSON and the
    /// SSE path on purpose: `/agent/stream` is the endpoint the tutor chat uses, so leaving
    /// the stream on the old code meant the one screen a learner actually stares at kept the
    /// useless message.
    private static func failureDetail(_ body: JSON, status: Int) -> String {
        let problems = body["detail"].array.compactMap { item -> String? in
            let message = item.text("msg", fallback: "")
            guard !message.isEmpty else { return nil }
            let field = item["loc"].array.map(\.string).last(where: { !$0.isEmpty }) ?? ""
            return field.isEmpty ? message : "\(field): \(message)"
        }
        if !problems.isEmpty { return problems.joined(separator: "; ") }
        return body.text("detail", fallback: body["detail"].text("message", fallback: body.text("error", fallback: body.text("message", fallback: "Request failed (HTTP \(status))."))))
    }

    /// POST a body and read the reply as a Server-Sent Events stream.
    ///
    /// ``/agent/stream`` emits one ``event:``/``data:`` pair per agent-loop event, and
    /// the server sends each one at the moment the loop produced it. That is what lets
    /// the tutor chat show "Drawing on the whiteboard" while the tutor is drawing,
    /// instead of a finished transcript that appears all at once. Token-level streaming
    /// would need a streaming provider path; the server does not fake it and neither
    /// does this reader.
    ///
    /// A non-2xx is reported with the server's own sentence, exactly as the JSON path
    /// does, because "the stream failed" tells the learner nothing they can act on.
    func serverEvents(_ path: String, body: [String: Any]) -> AsyncThrowingStream<ServerEvent, Error> {
        AsyncThrowingStream(ServerEvent.self) { continuation in
            guard let components = URLComponents(string: endpoint + "/api/v1" + path),
                  let url = components.url else {
                continuation.finish(throwing: AppFailure(message: "Invalid server address.", status: nil))
                return
            }
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
            request.setValue(Self.acceptLanguage(preference: UserDefaults.standard.string(forKey: "luminfest.language")),
                             forHTTPHeaderField: "Accept-Language")
            if let token { request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization") }
            request.httpBody = try? JSONSerialization.data(withJSONObject: body)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            let work = Task {
                do {
                    let (bytes, response) = try await streamSession.bytes(for: request)
                    guard let http = response as? HTTPURLResponse else {
                        throw AppFailure(message: "The server returned an invalid response.", status: nil)
                    }
                    guard (200..<300).contains(http.statusCode) else {
                        var buffer = Data()
                        for try await byte in bytes { buffer.append(byte) }
                        let j = (try? JSONDecoder().decode(JSON.self, from: buffer)) ?? .null
                        throw AppFailure(message: Self.failureDetail(j, status: http.statusCode),
                                         status: http.statusCode)
                    }
                    var name = "message"
                    var dataLines: [String] = []
                    for try await line in bytes.lines {
                        if line.isEmpty {
                            // A blank line dispatches. A comment line (": keep-alive")
                            // carries no data and is skipped rather than dispatched.
                            if !dataLines.isEmpty {
                                continuation.yield(ServerEvent(name: name, payload: decode(dataLines)))
                            }
                            name = "message"
                            dataLines = []
                            continue
                        }
                        if line.hasPrefix(":") { continue }
                        if line.hasPrefix("event:") {
                            name = String(line.dropFirst("event:".count)).trimmingCharacters(in: .whitespaces)
                        } else if line.hasPrefix("data:") {
                            dataLines.append(String(line.dropFirst("data:".count)).trimmingCharacters(in: .whitespaces))
                        }
                    }
                    // A final event with no terminating blank line still happened.
                    if !dataLines.isEmpty {
                        continuation.yield(ServerEvent(name: name, payload: decode(dataLines)))
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in work.cancel() }
        }
    }

    private func decode(_ dataLines: [String]) -> JSON {
        let text = dataLines.joined(separator: "\n")
        return (try? JSONDecoder().decode(JSON.self, from: Data(text.utf8))) ?? .null
    }

    /// The bytes of a server-relative artifact path, e.g.
    /// `/api/v1/sims/deck-abc/download/v1.pptx`.
    ///
    /// Every artifact route is bearer-protected, so a web view or a browser pointed straight
    /// at the URL gets a 401 and shows the learner nothing. The only way the app can hand
    /// over a file the server actually built is to fetch it through this client, which is
    /// what this does. The path must sit under `/api/v1/`: a server-supplied string cannot
    /// turn this into a request to another host, because an absolute URL does not start with
    /// that prefix.
    func artifact(_ path: String) async throws -> Data {
        guard path.hasPrefix("/api/v1/") else {
            throw AppFailure(message: "That address is not an artifact on this backend.", status: nil)
        }
        return try await data(String(path.dropFirst("/api/v1".count)))
    }
}
