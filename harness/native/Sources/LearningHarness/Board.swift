import Foundation
import SwiftUI
import AppKit

// The interactive board: a node canvas the learner, the tutor and the tools share.
//
// Server facts stay server facts. Node ids and the z-order index are assigned by the
// backend and are opaque here; writes are optimistic (local apply, then PATCH with the
// base_version the client last saw) and a 409 reloads the board rather than stomping it.

struct BoardNode: Identifiable, Equatable {
    let id: String
    let kind: String
    var x: Double
    var y: Double
    var w: Double
    var h: Double
    let z: String
    /// Mutable because the editor rewrites payloads in place: resizing a path scales its
    /// points, dragging a connector moves its endpoints, and restyling changes a colour.
    /// Keeping those edits on the node means a drag never has to round-trip to the server
    /// before the canvas can show the result.
    var payload: JSON

    static func parse(_ json: JSON) -> BoardNode? {
        let kind = json["kind"].string
        guard !json["id"].string.isEmpty, BoardKind.all.contains(kind) else { return nil }
        let x = json["x"].double, y = json["y"].double
        guard x.isFinite, y.isFinite else { return nil }
        return BoardNode(id: json["id"].string, kind: kind, x: x, y: y,
                         w: json["w"].double.isFinite ? json["w"].double : 0,
                         h: json["h"].double.isFinite ? json["h"].double : 0,
                         z: json["z"].string, payload: json["payload"])
    }

    /// Where the client needs geometry, the flat x/y/w/h is the frame. This is the one
    /// mapping the merged plan allows: frame ↔ x/y, never a client-side schema rewrite.
    var frame: CGRect { CGRect(x: x, y: y, width: max(w, 8), height: max(h, 8)) }
}

enum BoardKind {
    static let all: Set<String> = ["path", "shape", "connector", "text", "image",
                                   "video", "simulation", "answer", "visual"]
    static let ink: Set<String> = ["path"]
}

struct BoardSnapshot: Equatable {
    var id: String
    var title: String
    var version: Int
    var nodes: [BoardNode]
    var rollup: JSON

    static func parse(_ json: JSON) -> BoardSnapshot? {
        let id = json["board"]["id"].string.isEmpty ? json["id"].string : json["board"]["id"].string
        guard !id.isEmpty else { return nil }
        let doc = json["board"].isNull ? json : json["board"]
        let nodes = doc["nodes"].array.compactMap(BoardNode.parse).sorted { $0.z < $1.z }
        return BoardSnapshot(id: id, title: doc["title"].string, version: doc["version"].int,
                             nodes: nodes, rollup: json["licence_rollup"])
    }
}

@MainActor
final class BoardStore: ObservableObject {
    @Published private(set) var boardID = ""
    @Published private(set) var title = ""
    @Published private(set) var version = 0
    /// Mutable for optimistic local edits (the pen must not wait on the network);
    /// every write reconciles with the server's authoritative document.
    @Published var nodes: [BoardNode] = []
    @Published private(set) var rollup: JSON = .null
    @Published var error: String?
    @Published var busy = false
    /// Surfaced so the toolbar can disable Undo/Redo rather than offer a dead control.
    @Published private(set) var canUndo = false
    @Published private(set) var canRedo = false
    private var history = BoardHistory()
    private weak var api: APIClient?
    private var syncTask: Task<Void, Never>?
    /// Sequence number so out-of-order PATCH responses cannot overwrite newer state.
    private var syncSequence = 0
    /// The id this store was asked to open. ``boardID`` stays empty until the
    /// document exists; ``wantedID`` is what a bootstrap creates.
    private var wantedID = ""
    private var bootstrapping = false
    /// Live polling of the shared board.
    ///
    /// The tutor's ``whiteboard_*`` tools write to this same document, so a learner
    /// watching the Stage has to see the diagram form. The store used to load once and
    /// sync only on its own writes, which meant a tutor's drawing stayed invisible
    /// until the learner happened to draw something themselves - on a surface whose
    /// whole point is that two people share it.
    ///
    /// Two guards keep the poll from fighting the learner. It yields to an in-flight
    /// local sync, because an optimistic edit must never be stomped by a remote
    /// snapshot that arrived first; and it is version-gated, so a board that has not
    /// changed costs nothing but the read.
    private var pollTask: Task<Void, Never>?

    init(api: APIClient) { self.api = api }

    // ---------------------------------------------------------------- read

    func loadExisting(_ id: String) async {
        guard let api else { return }
        wantedID = id
        do {
            let value = try await api.json("/boards/" + id)
            apply(BoardSnapshot.parse(value))
        } catch {
            if (error as? AppFailure)?.status == 404 {
                // A missing board is a fresh board — and it must be *created*, not
                // just tolerated. Leaving boardID empty here meant every later
                // ``sync`` hit its ``!boardID.isEmpty`` guard and dropped the
                // learner's strokes on the floor, so the canvas looked like it
                // worked and remembered nothing.
                await create(id: id, title: id)
            } else {
                self.error = error.localizedDescription
            }
        }
    }

    func create(title: String) async {
        await create(id: "", title: title)
    }

    /// Create the board, optionally at the deterministic concept id the tutor's
    /// tools address. ``POST /boards`` accepts ``board_id`` for exactly this: the
    /// client and the tutor must meet on the same document, and a learner who
    /// draws first is the one who has to bring it into existence.
    func create(id: String, title: String) async {
        guard let api else { return }
        do {
            var body: [String: Any] = ["title": title]
            if !id.isEmpty { body["board_id"] = id }
            let value = try await api.json("/boards", method: "POST", body: body)
            apply(BoardSnapshot.parse(value))
            self.error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// The concept's standing board: `board-<concept_id>`, deterministic so the tutor
    /// and the canvas always meet on the same surface.
    static func id(forConcept conceptID: String) -> String {
        let safe = conceptID.filter { $0.isLetter || $0.isNumber || $0 == "-" || $0 == "_" }
        return "board-" + String(safe.prefix(60))
    }

    private func apply(_ snapshot: BoardSnapshot?) {
        guard let snapshot else { return }
        boardID = snapshot.id
        title = snapshot.title
        version = snapshot.version
        nodes = snapshot.nodes
        rollup = snapshot.rollup
    }

    // ---------------------------------------------------------------- live polling

    func startPolling(interval: UInt64 = 2_500_000_000) {
        guard pollTask == nil, let api else { return }
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: interval)
                guard !Task.isCancelled else { return }
                await self?.poll()
            }
        }
    }

    func stopPolling() {
        pollTask?.cancel()
        pollTask = nil
    }

    /// One read of the shared document. A failed poll is silent on purpose: the
    /// learner's own edits still work offline, the next poll picks the tutor's drawing
    /// up, and an error banner over the canvas for a transient read would be noise.
    private func poll() async {
        guard let api, !boardID.isEmpty, syncTask == nil else { return }
        guard let value = try? await api.json("/boards/" + boardID) else { return }
        guard let snapshot = BoardSnapshot.parse(value), snapshot.version != version else { return }
        apply(snapshot)
    }

    // ---------------------------------------------------------------- writes

    /// Optimistic mutation: apply locally at once (the pen must not wait on the network),
    /// then reconcile with the server's authoritative document. A 409 reloads: the board
    /// changed underneath and the server version wins, never the client's.
    func add(node: BoardNode) {
        addMany(nodes: [node])
    }

    /// Add a related group as one versioned mutation. A generated diagram is one teacher
    /// action, so it must be one undo step and one server write, not dozens of racing PATCHes.
    func addMany(nodes additions: [BoardNode]) {
        let additions = Array(additions.prefix(128))
        guard !additions.isEmpty else { return }
        beginEdit()
        var mutations: [[String: Any]] = []
        for node in additions {
            let local = BoardNode(id: "local-" + UUID().uuidString, kind: node.kind,
                                  x: node.x, y: node.y, w: node.w, h: node.h, z: "local",
                                  payload: node.payload)
            nodes.append(local)
            mutations.append(["action": "add", "node": nodeDictionary(node)])
        }
        sync(mutations: mutations)
    }

    /// Move a node. The caller records the undo step once, when the drag begins, via
    /// ``beginEdit()`` — recording here instead would push a snapshot per pointer sample.
    func move(id: String, to point: CGPoint, size: CGSize? = nil) {
        guard let index = nodes.firstIndex(where: { $0.id == id }) else { return }
        nodes[index].x = point.x
        nodes[index].y = point.y
        if let size, size.width > 0, size.height > 0 {
            nodes[index].w = size.width
            nodes[index].h = size.height
        }
        var mutation: [String: Any] = ["action": "move", "id": id, "x": point.x, "y": point.y]
        if let size, size.width > 0, size.height > 0 {
            mutation["w"] = size.width
            mutation["h"] = size.height
        }
        sync(mutations: [mutation])
    }

    /// Move several nodes in **one** round trip.
    ///
    /// Calling ``move(id:to:)`` in a loop is not equivalent: each call cancels the
    /// previous in-flight sync, so a five-node group drag would send the first four
    /// mutations into a cancelled task and only the last would reach the server. A
    /// selection drag is one gesture and therefore one mutation batch.
    func moveMany(_ updates: [(id: String, x: Double, y: Double, w: Double, h: Double)]) {
        guard !updates.isEmpty else { return }
        var mutations: [[String: Any]] = []
        for update in updates {
            guard let index = nodes.firstIndex(where: { $0.id == update.id }) else { continue }
            nodes[index].x = update.x
            nodes[index].y = update.y
            if update.w > 0 { nodes[index].w = update.w }
            if update.h > 0 { nodes[index].h = update.h }
            var mutation: [String: Any] = ["action": "move", "id": update.id,
                                          "x": update.x, "y": update.y]
            mutation["w"] = update.w
            mutation["h"] = update.h
            mutations.append(mutation)
        }
        sync(mutations: Array(mutations.prefix(128)))
    }

    /// Resize one node, keeping the geometry that a path or connector stores inside its
    /// own payload in step with the frame the server keeps.
    ///
    /// The frame alone is enough for a shape or a text box, and enough to *move* a path,
    /// but not to scale one: a path whose points were not scaled would keep its old
    /// coordinates and visibly snap back to them on the next reload. So the scaled points
    /// ride along as an ``update`` in the same batch, which the server accepts — ``points``
    /// is presentation data, not one of the media-status keys it refuses.
    func resize(id: String, to rect: CGRect) {
        guard let index = nodes.firstIndex(where: { $0.id == id }) else { return }
        var node = nodes[index]
        node.resize(to: rect)
        nodes[index] = node
        var mutations: [[String: Any]] = [["action": "move", "id": id,
                                          "x": Double(rect.minX), "y": Double(rect.minY),
                                          "w": Double(rect.width), "h": Double(rect.height)]]
        if case .object(let object) = node.payload {
            var fields: [String: Any] = [:]
            if node.kind == "path", case .array(let raw) = object["points"] {
                fields["points"] = raw.compactMap { pair -> [Double]? in
                    let values = pair.array
                    guard values.count >= 2 else { return nil }
                    return [values[0].double, values[1].double]
                }
            } else if node.kind == "connector" {
                for key in ["x", "y", "x2", "y2"] {
                    if case .number(let value) = object[key] { fields[key] = value }
                }
            }
            if !fields.isEmpty {
                mutations.append(["action": "update", "id": id, "fields": fields])
            }
        }
        sync(mutations: Array(mutations.prefix(128)))
    }

    /// Remove the samples of a path that fall near a point, leaving the rest intact.
    ///
    /// This is what makes an eraser an eraser rather than a delete button: most strokes
    /// are worth keeping except for the bit you scrubbed over, and deleting the whole
    /// stroke because you touched it is the behaviour that makes people avoid drawing on
    /// a shared board. A stroke that ends up with a single sample is deleted outright,
    /// because a one-point path is invisible and would sit in the document forever.
    func eraseStroke(id: String, near point: CGPoint, radius: CGFloat = 16) -> Bool {
        guard let index = nodes.firstIndex(where: { $0.id == id }) else { return false }
        var node = nodes[index]
        let kept = BoardGeometry.points(of: node).filter {
            hypot($0.x - point.x, $0.y - point.y) > radius
        }
        guard kept.count >= 2 else {
            delete(id: id)
            return true
        }
        // Pressure rides along so the surviving stroke keeps its taper.
        let pressure = BoardGeometry.pressure(of: node)
        let aligned = pressure.count == BoardGeometry.points(of: node).count ? pressure : nil
        var payload = nodeDictionary(node)
        payload["points"] = kept.map { [Double($0.x), Double($0.y)] }
        if let aligned { payload["pressure"] = aligned.map(Double.init) }
        let bounds = CGRect(points: kept).insetBy(dx: -20, dy: -20)
        node.payload = (try? JSON.make(payload)) ?? node.payload
        node.x = Double(bounds.minX)
        node.y = Double(bounds.minY)
        node.w = Double(bounds.width)
        node.h = Double(bounds.height)
        nodes[index] = node
        var fields: [String: Any] = ["points": payload["points"] as Any]
        if let aligned { fields["pressure"] = aligned.map(Double.init) }
        sync(mutations: [["action": "update", "id": id, "fields": fields],
                         ["action": "move", "id": id, "x": Double(bounds.minX), "y": Double(bounds.minY),
                          "w": Double(bounds.width), "h": Double(bounds.height)]])
        return true
    }

    func delete(id: String) {
        beginEdit()
        nodes.removeAll { $0.id == id }
        sync(mutations: [["action": "delete", "id": id]])
    }

    /// Restyle a node's payload without moving it.
    ///
    /// The server refuses an `update` that carries media-status fields (see
    /// ``board.apply_mutations``), so this only ever sends presentation keys. A refusal is
    /// therefore a genuine error rather than a silently-dropped edit, which is why the
    /// failure is surfaced instead of swallowed.
    func restyle(id: String, fields: [String: Any]) {
        guard let index = nodes.firstIndex(where: { $0.id == id }) else { return }
        beginEdit()
        if case .object(var object) = nodes[index].payload {
            for (key, value) in fields {
                switch value {
                case let s as String: object[key] = .string(s)
                case let n as Double: object[key] = .number(n)
                case let n as Int: object[key] = .number(Double(n))
                case let b as Bool: object[key] = .bool(b)
                default: break
                }
            }
            nodes[index].payload = .object(object)
        }
        sync(mutations: [["action": "update", "id": id, "fields": fields]])
    }

    /// Reorder within the stack by naming the node it should sit after. The server owns
    /// the z index itself (``_z_between_neighbors``), so the client only states intent.
    func reorder(id: String, afterID: String?, beforeID: String?) {
        var mutation: [String: Any] = ["action": "move", "id": id]
        if let afterID { mutation["after_id"] = afterID }
        if let beforeID { mutation["before_id"] = beforeID }
        beginEdit()
        sync(mutations: [mutation])
    }

    // ---------------------------------------------------------------- history

    /// Snapshot the current state so the next edit can be undone.
    ///
    /// Called at the *start* of a gesture rather than per sample: a drag emits sixty
    /// positions a second, and recording each one would make a single undo step back by
    /// two pixels. The view calls this once when the drag begins.
    func beginEdit() {
        guard boardID.isEmpty == false else { return }
        history.record(BoardState(nodes: nodes, version: version))
        refreshHistoryFlags()
    }

    func undo() {
        guard let previous = history.undo(current: BoardState(nodes: nodes, version: version)) else { return }
        reconcile(to: previous)
        refreshHistoryFlags()
    }

    func redo() {
        guard let next = history.redo(current: BoardState(nodes: nodes, version: version)) else { return }
        reconcile(to: next)
        refreshHistoryFlags()
    }

    private func refreshHistoryFlags() {
        canUndo = history.canUndo
        canRedo = history.canRedo
    }

    /// Move the document to `target` by emitting the smallest mutation batch that gets
    /// there: delete what is gone, add what is new, and move only what actually changed.
    ///
    /// A full-document replace would be simpler, but it would also mean an undo rewrites
    /// every node id on the board — losing selection, invalidating any tutor answer pinned
    /// to a node, and turning a one-stroke undo into a whole-board write.
    private func reconcile(to target: BoardState) {
        let targetIDs = Set(target.nodes.map(\.id))
        let currentIDs = Set(nodes.map(\.id))
        var mutations: [[String: Any]] = []

        for node in nodes where !targetIDs.contains(node.id) {
            mutations.append(["action": "delete", "id": node.id])
        }
        for node in target.nodes where !currentIDs.contains(node.id) {
            mutations.append(["action": "add", "node": nodeDictionary(node)])
        }
        // A tolerance of half a board unit absorbs the server's 0.1-unit rounding without
        // treating a genuine one-pixel nudge as unchanged.
        let tolerance = 0.5
        for node in target.nodes where currentIDs.contains(node.id) {
            guard let current = nodes.first(where: { $0.id == node.id }) else { continue }
            let moved = abs(current.x - node.x) > tolerance || abs(current.y - node.y) > tolerance
            let resized = abs(current.w - node.w) > tolerance || abs(current.h - node.h) > tolerance
            let restyled = current.payload != node.payload
            if moved || resized {
                var mutation: [String: Any] = ["action": "move", "id": node.id,
                                               "x": node.x, "y": node.y]
                if node.w > 0 || node.h > 0 {
                    mutation["w"] = node.w
                    mutation["h"] = node.h
                }
                mutations.append(mutation)
            }
            if restyled, case .object(let object) = node.payload {
                var fields: [String: Any] = [:]
                for (key, value) in object {
                    switch value {
                    case .string(let s): fields[key] = s
                    case .number(let n): fields[key] = n
                    case .bool(let b): fields[key] = b
                    default: break
                    }
                }
                if !fields.isEmpty {
                    mutations.append(["action": "update", "id": node.id, "fields": fields])
                }
            }
        }

        // Apply locally first so the canvas never lags the gesture, then tell the server.
        nodes = target.nodes
        guard !mutations.isEmpty else { return }
        sync(mutations: Array(mutations.prefix(128)))
    }

    /// Anchor the tutor's lasso answer where the question was asked.
    func pinAnswer(text: String, question: String, imageSHA: String, at point: CGPoint) {
        var payload: [String: Any] = ["text": text, "question": question]
        if !imageSHA.isEmpty { payload["image_sha256"] = imageSHA }
        add(node: BoardNode(id: "", kind: "answer", x: point.x, y: point.y, w: 480, h: 0,
                            z: "", payload: (try? JSON.make(payload)) ?? .null))
    }

    private func nodeDictionary(_ node: BoardNode) -> [String: Any] {
        // A generic JSON → Any bridge rather than a hand-written switch per key. The
        // earlier version special-cased `points` as pairs of doubles, which silently
        // mangled any other array — and a stroke's parallel `pressure` array is exactly
        // that, so every stroke lost its pressure on the way to the server.
        var payload: [String: Any] = [:]
        if case .object(let object) = node.payload {
            for (key, value) in object {
                if let converted = Self.anyValue(value) { payload[key] = converted }
            }
        }
        var dictionary: [String: Any] = ["kind": node.kind, "x": node.x, "y": node.y,
                                         "payload": payload]
        if node.w > 0 || node.h > 0 {
            dictionary["w"] = node.w
            dictionary["h"] = node.h
        }
        return dictionary
    }

    /// Unwrap a ``JSON`` value into something ``JSONSerialization`` accepts.
    private static func anyValue(_ value: JSON) -> Any? {
        switch value {
        case .string(let text): return text
        case .number(let number): return number
        case .bool(let flag): return flag
        case .array(let items): return items.compactMap { anyValue($0) }
        case .object(let object): return object.compactMapValues { anyValue($0) }
        case .null: return nil
        }
    }

    private func sync(mutations: [[String: Any]]) {
        guard let api else { return }
        if boardID.isEmpty {
            // First strokes of a board that does not exist yet. They are already in
            // ``nodes`` (the pen never waits on the network); bring the document
            // into existence and then send, instead of dropping the batch.
            bootstrapThenSync(mutations)
            return
        }
        sendMutations(mutations)
    }

    private func bootstrapThenSync(_ mutations: [[String: Any]]) {
        guard !bootstrapping else { return }
        bootstrapping = true
        syncTask?.cancel()
        syncTask = Task { [weak self] in
            guard let self else { return }
            await self.create(id: self.wantedID, title: self.wantedID)
            self.bootstrapping = false
            if !self.boardID.isEmpty { self.sendMutations(mutations) }
        }
    }

    private func sendMutations(_ mutations: [[String: Any]]) {
        guard let api, !boardID.isEmpty else { return }
        syncSequence += 1
        let sequence = syncSequence
        let baseVersion = version
        syncTask?.cancel()
        syncTask = Task { [weak self] in
            guard let self else { return }
            do {
                let value = try await api.json("/boards/" + boardID, method: "PATCH",
                                               body: ["base_version": baseVersion,
                                                      "mutations": mutations])
                guard sequence == self.syncSequence else { return }
                self.apply(BoardSnapshot.parse(value))
            } catch let failure as AppFailure where failure.status == 409 {
                guard sequence == self.syncSequence else { return }
                await self.loadExisting(self.boardID)  // server truth wins
            } catch {
                guard sequence == self.syncSequence else { return }
                self.error = error.localizedDescription
            }
        }
    }

    // ---------------------------------------------------------------- export & share

    func exportURL(format: String) -> String {
        api?.endpoint.appending("/api/v1/boards/\(boardID)/export?format=\(format)") ?? ""
    }

    func createShare(ttlDays: Int = 7) async -> URL? {
        guard let api else { return nil }
        do {
            let value = try await api.json("/boards/\(boardID)/share", method: "POST",
                                           body: ["ttl_days": ttlDays])
            return URL(string: value["url"].string)
        } catch {
            self.error = error.localizedDescription
            return nil
        }
    }

    func revokeShares() async {
        guard let api else { return }
        do { _ = try await api.data("/boards/\(boardID)/share", method: "DELETE") }
        catch { self.error = error.localizedDescription }
    }
}

// ---------------------------------------------------------------- snapshot compositor
//
// One renderer for both export formats: the lasso snapshot (PNG) and the PDF export
// draw the same truth. All drawing is AppKit-level (NSBezierPath, NSAttributedString,
// NSImage) into a flipped NSGraphicsContext, so board coordinates (y down) map directly
// and glyphs stay upright for both the bitmap and the PDF back end. Embedded media
// (video/simulation) is deliberately rendered as a labelled chip, not a frame grab:
// an embed is licence-bound to its provider and a rasterised copy would be an
// unlicensed redistribution pretending to be a preview.

enum BoardRenderer {
    /// The context every draw call sees: flipped, translated so board coordinates work.
    private static func withContext<T>(_ cg: CGContext, size: CGSize, body: () -> T?) -> T? {
        let context = NSGraphicsContext(cgContext: cg, flipped: true)
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = context
        defer { NSGraphicsContext.restoreGraphicsState() }
        cg.setFillColor(NSColor.white.cgColor)
        cg.fill(CGRect(origin: .zero, size: size))
        return body()
    }

    static func image(of nodes: [BoardNode], in rect: CGRect, scale: CGFloat = 2) -> NSImage? {
        guard rect.width > 4, rect.height > 4 else { return nil }
        guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil,
                                         pixelsWide: Int(rect.width * scale),
                                         pixelsHigh: Int(rect.height * scale),
                                         bitsPerSample: 8, samplesPerPixel: 4,
                                         hasAlpha: true, isPlanar: false,
                                         colorSpaceName: .deviceRGB,
                                         bytesPerRow: 0, bitsPerPixel: 0),
              let appKit = NSGraphicsContext(bitmapImageRep: rep) else { return nil }
        let cg = appKit.cgContext
        rep.size = NSSize(width: rect.width, height: rect.height)
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = appKit  // bitmap-rep contexts are already flipped
        defer { NSGraphicsContext.restoreGraphicsState() }
        cg.setFillColor(NSColor.white.cgColor)
        cg.fill(CGRect(origin: .zero, size: rep.size))
        cg.translateBy(x: -rect.minX, y: -rect.minY)
        draw(nodes: nodes)
        return NSImage(data: rep.representation(using: .png, properties: [:]) ?? Data())
    }

    static func pdfData(of nodes: [BoardNode], pageSize: CGSize) -> Data? {
        var mediaBox = CGRect(origin: .zero, size: pageSize)
        guard let consumer = CGDataConsumer(data: NSMutableData()),
              let cg = CGContext(consumer: consumer, mediaBox: &mediaBox,
                                 [kCGPDFContextCreator: "Luminfest Learning Harness"] as CFDictionary) else { return nil }
        cg.beginPDFPage(nil)
        let bounds = boundsOf(nodes).insetBy(dx: -40, dy: -40)
        withContext(cg, size: pageSize) { () -> Bool in
            guard bounds.width > 0, bounds.height > 0 else { return false }
            let scale = min(pageSize.width / bounds.width, pageSize.height / bounds.height, 1)
            cg.scaleBy(x: scale, y: scale)
            cg.translateBy(x: -bounds.minX, y: -bounds.minY)
            draw(nodes: nodes)
            return true
        }
        cg.endPDFPage()
        cg.closePDF()
        return (cg.data as? NSMutableData) as Data?
    }

    static func boundsOf(_ nodes: [BoardNode]) -> CGRect {
        var rect = CGRect.null
        for node in nodes {
            let frame: CGRect
            switch node.kind {
            case "path":
                let points = strokePoints(node)
                frame = points.isEmpty ? node.frame : CGRect(points: points).insetBy(dx: -20, dy: -20)
            case "connector":
                let a = CGPoint(x: node.payload["x"].double, y: node.payload["y"].double)
                let b = CGPoint(x: node.payload["x2"].double, y: node.payload["y2"].double)
                frame = CGRect(points: [a, b]).insetBy(dx: -10, dy: -10)
            default:
                frame = node.frame
            }
            rect = rect.union(frame)
        }
        return rect.isNull ? CGRect(x: 0, y: 0, width: 1200, height: 800) : rect
    }

    // ---------------------------------------------------------------- primitives

    private static func strokePoints(_ node: BoardNode) -> [CGPoint] {
        node.payload["points"].array.compactMap { pair -> CGPoint? in
            let values = pair.array
            guard values.count == 2 else { return nil }
            return CGPoint(x: values[0].double, y: values[1].double)
        }
    }

    private static func inkColour(_ node: BoardNode, fallback: NSColor = .textColor) -> NSColor {
        let raw = node.payload["colour"].string
        return raw.isEmpty ? fallback : NSColor(Color(hexString: raw))
    }

    /// Draw in board coordinates (y down). The current context must be flipped and
    /// translated into board space by the caller.
    static func draw(nodes: [BoardNode]) {
        for node in nodes {
            switch node.kind {
            case "path": drawPath(node)
            case "shape": drawShape(node)
            case "connector": drawConnector(node)
            case "text": drawText(node)
            case "answer": drawAnswer(node)
            case "image": drawImage(node)
            case "video", "simulation": drawChip(node)
            case "visual": drawVisualPlaceholder(node)
            default: break
            }
        }
    }

    /// Static exports (PNG/PDF) cannot contain a WKWebView. Draw an explicit labelled
    /// placeholder rather than a blank rectangle that would look like a rendering bug.
    private static func drawVisualPlaceholder(_ node: BoardNode) {
        let box = node.frame
        let card = NSBezierPath(roundedRect: box, xRadius: 8, yRadius: 8)
        NSColor.white.setFill()
        card.fill()
        NSColor(calibratedRed: 0.28, green: 0.32, blue: 0.61, alpha: 1).setStroke()
        card.lineWidth = 1.2
        card.stroke()
        let kind = node.payload["type"].string.uppercased()
        let heading = node.payload["title"].string.isEmpty ? kind : node.payload["title"].string
        let titleAttributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 13, weight: .semibold),
            .foregroundColor: NSColor.labelColor,
        ]
        heading.draw(at: NSPoint(x: box.minX + 12, y: box.minY + 12),
                     withAttributes: titleAttributes)
        let noteAttributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 10),
            .foregroundColor: NSColor.secondaryLabelColor,
        ]
        ("Interactive visual (\(kind)) — rendered in the app, not in this export" as NSString)
            .draw(at: NSPoint(x: box.minX + 12, y: box.minY + 34),
                  withAttributes: noteAttributes)
    }

    private static func drawPath(_ node: BoardNode) {
        let points = BoardGeometry.points(of: node)
        guard points.count > 1 else { return }
        let width = CGFloat(min(48, max(0.3, node.payload["width"].double.isFinite ? node.payload["width"].double : 2.5)))
        // Per-point pressure, not one scalar: a stroke whose width never varies is the
        // difference between a marker and a rubber stamp, and the export has to show the
        // same line the canvas did.
        let pressures = BoardGeometry.pressure(of: node)
        var options = PerfectFreehand.Options()
        options.size = width * 4
        options.thinning = 0.6
        options.simulatePressure = false
        let inputs = zip(points, pressures).map {
            PerfectFreehand.InputPoint(point: $0.0, pressure: $0.1)
        }
        let outline = PerfectFreehand.stroke(inputs, options: options)
        guard outline.count > 2 else { return }
        let path = NSBezierPath()
        path.move(to: outline[0])
        for point in outline.dropFirst() { path.line(to: point) }
        path.close()
        let colour = inkColour(node)
        // A highlighter is a translucent wash rather than a solid stroke, so it must be
        // drawn at reduced alpha instead of the pen's full opacity.
        (node.payload["highlight"].bool ? colour.withAlphaComponent(0.34) : colour).setFill()
        path.fill()
    }

    private static func drawShape(_ node: BoardNode) {
        let frame = node.frame
        let colour = inkColour(node)
        let fill = node.payload["fill"].string.isEmpty
            ? nil
            : NSColor(Color(hexString: node.payload["fill"].string))
        switch node.payload["shape"].string {
        case "ellipse":
            let path = NSBezierPath(ovalIn: frame)
            if let fill { fill.setFill(); path.fill() }
            path.lineWidth = 2
            colour.setStroke()
            path.stroke()
        case "sticky":
            // A sticky is a filled note, so the fill is the shape and the border is only
            // a hint at the edge — drawing it like a stroked rectangle would make a note
            // read as a box someone drew.
            let path = NSBezierPath(roundedRect: frame, xRadius: 6, yRadius: 6)
            (fill ?? NSColor.systemYellow.withAlphaComponent(0.5)).setFill()
            path.fill()
            NSColor.black.withAlphaComponent(0.12).setStroke()
            path.lineWidth = 1
            path.stroke()
        case "line", "arrow":
            let a = CGPoint(x: frame.minX, y: frame.minY)
            let b = CGPoint(x: frame.maxX, y: frame.maxY)
            let path = NSBezierPath()
            path.move(to: a)
            path.line(to: b)
            path.lineWidth = CGFloat(min(48, max(0.3, node.payload["width"].double.isFinite ? node.payload["width"].double : 2)))
            path.lineCapStyle = .round
            colour.setStroke()
            path.stroke()
            if node.payload["shape"].string == "arrow" { drawArrowHead(from: a, to: b, colour: colour) }
        case "triangle":
            let path = NSBezierPath()
            path.move(to: CGPoint(x: frame.midX, y: frame.minY))
            path.line(to: CGPoint(x: frame.maxX, y: frame.maxY))
            path.line(to: CGPoint(x: frame.minX, y: frame.maxY))
            path.close()
            if let fill { fill.setFill(); path.fill() }
            path.lineWidth = 2
            colour.setStroke()
            path.stroke()
        case "diamond":
            let path = NSBezierPath()
            path.move(to: CGPoint(x: frame.midX, y: frame.minY))
            path.line(to: CGPoint(x: frame.maxX, y: frame.midY))
            path.line(to: CGPoint(x: frame.midX, y: frame.maxY))
            path.line(to: CGPoint(x: frame.minX, y: frame.midY))
            path.close()
            if let fill { fill.setFill(); path.fill() }
            path.lineWidth = 2
            colour.setStroke()
            path.stroke()
        default:
            let path = NSBezierPath(roundedRect: frame, xRadius: 3, yRadius: 3)
            if let fill { fill.setFill(); path.fill() }
            path.lineWidth = 2
            colour.setStroke()
            path.stroke()
        }
    }

    private static func drawConnector(_ node: BoardNode) {
        let a = CGPoint(x: node.payload["x"].double, y: node.payload["y"].double)
        let b = CGPoint(x: node.payload["x2"].double, y: node.payload["y2"].double)
        let colour = inkColour(node, fallback: .systemGray)
        let path = NSBezierPath()
        path.move(to: a)
        path.line(to: b)
        path.lineWidth = CGFloat(min(48, max(0.3, node.payload["width"].double.isFinite ? node.payload["width"].double : 1.5)))
        path.lineCapStyle = .round
        if node.payload["dashed"].bool {
            path.setLineDash([7, 5], count: 2, phase: 0)
        }
        colour.setStroke()
        path.stroke()
        // An arrowhead is opt-in: a plain connector is a relationship, and putting a head
        // on it would assert a direction the author did not draw.
        if node.payload["arrow"].bool { drawArrowHead(from: a, to: b, colour: colour) }
        let label = node.payload["label"].string
        if !label.isEmpty {
            draw(string: label, at: CGPoint(x: a.x + 8, y: a.y - 18), size: 12, colour: colour)
        }
    }

    private static func drawArrowHead(from: CGPoint, to: CGPoint, colour: NSColor) {
        let angle = atan2(to.y - from.y, to.x - from.x)
        let length: CGFloat = 10
        let path = NSBezierPath()
        path.move(to: to)
        path.line(to: CGPoint(x: to.x - length * cos(angle - 0.45), y: to.y - length * sin(angle - 0.45)))
        path.line(to: CGPoint(x: to.x - length * cos(angle + 0.45), y: to.y - length * sin(angle + 0.45)))
        path.close()
        colour.setFill()
        path.fill()
    }

    private static func drawText(_ node: BoardNode) {
        let size = CGFloat(min(96, max(9, node.payload["size"].double.isFinite ? node.payload["size"].double : 16)))
        // A sticky note is a filled shape with text on it; drawing the text without the
        // note would put words on bare canvas and lose the note entirely.
        if node.payload["sticky"].bool || node.payload["shape"].string == "sticky" {
            let frame = CGRect(x: node.x, y: node.y,
                               width: max(node.w, 140), height: max(node.h, 110))
            let box = NSBezierPath(roundedRect: frame, xRadius: 6, yRadius: 6)
            let fill = node.payload["fill"].string.isEmpty
                ? NSColor(Color(hexString: "#FCEBA4"))
                : NSColor(Color(hexString: node.payload["fill"].string))
            fill.setFill()
            box.fill()
            NSColor.black.withAlphaComponent(0.12).setStroke()
            box.lineWidth = 1
            box.stroke()
            draw(string: node.payload["text"].string,
                 at: CGPoint(x: frame.minX + 10, y: frame.minY + 10),
                 size: size, colour: .textColor, wrap: frame.width - 20)
            return
        }
        let colour = node.payload["colour"].string.isEmpty
            ? NSColor.textColor
            : NSColor(Color(hexString: node.payload["colour"].string))
        draw(string: node.payload["text"].string, at: CGPoint(x: node.x, y: node.y),
             size: size, colour: colour,
             wrap: node.w > 20 ? CGFloat(node.w) : 0,
             weight: node.payload["weight"].string)
    }

    private static func drawAnswer(_ node: BoardNode) {
        let frame = CGRect(x: node.x, y: node.y, width: max(node.w, 320), height: max(node.h, 56))
        let box = NSBezierPath(roundedRect: frame, xRadius: 10, yRadius: 10)
        NSColor.systemIndigo.withAlphaComponent(0.12).setFill()
        NSColor.systemIndigo.setStroke()
        box.lineWidth = 1.5
        box.fill()
        box.stroke()
        let question = node.payload["question"].string
        var y = frame.minY + 10
        if !question.isEmpty {
            draw(string: "Q: " + question, at: CGPoint(x: frame.minX + 12, y: y), size: 12,
                 colour: .systemIndigo, wrap: frame.width - 24)
            y += 22
        }
        draw(string: node.payload["text"].string, at: CGPoint(x: frame.minX + 12, y: y + 6),
             size: 15, colour: .textColor, wrap: frame.width - 24)
    }

    private static func drawImage(_ node: BoardNode) {
        let frame = node.frame
        let sha = node.payload["sha256"].string
        if let data = ImageCache.shared.data(sha: sha), let image = NSImage(data: data) {
            image.draw(in: frame)
        } else {
            NSColor.lightGray.withAlphaComponent(0.25).setFill()
            NSBezierPath(rect: frame).fill()
            draw(string: "image unavailable", at: CGPoint(x: frame.minX + 8, y: frame.minY + 8),
                 size: 12, colour: .systemGray)
        }
        let credit = node.payload["credit"].string
        if !credit.isEmpty {
            draw(string: credit, at: CGPoint(x: frame.minX, y: frame.maxY + 4), size: 9,
                 colour: .systemGray)
        }
    }

    private static func drawChip(_ node: BoardNode) {
        let frame = node.frame
        let box = NSBezierPath(roundedRect: frame, xRadius: 10, yRadius: 10)
        NSColor.systemOrange.withAlphaComponent(0.14).setFill()
        NSColor.systemOrange.setStroke()
        box.fill()
        box.stroke()
        let icon = node.kind == "video" ? "▶ " : "⚙ "
        draw(string: icon + node.payload["title"].string, at: CGPoint(x: frame.minX + 12, y: frame.minY + 12),
             size: 14, colour: .systemOrange)
        draw(string: "link chip — embed not redistributable", at: CGPoint(x: frame.minX + 12, y: frame.minY + 36),
             size: 10, colour: .systemOrange)
    }

    private static func draw(string: String, at point: CGPoint, size: CGFloat,
                             colour: NSColor, wrap: CGFloat = 0, weight: String = "") {
        guard !string.isEmpty else { return }
        let font: NSFont
        switch weight {
        case "medium": font = .systemFont(ofSize: size, weight: .medium)
        case "semibold": font = .systemFont(ofSize: size, weight: .semibold)
        case "bold": font = .systemFont(ofSize: size, weight: .bold)
        default: font = .systemFont(ofSize: size)
        }
        let attributes: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: colour]
        var lines: [String]
        if wrap > 20 {
            lines = string.components(separatedBy: "\n").flatMap { line -> [String] in
                var out: [String] = [], current = ""
                for word in line.split(separator: " ", omittingEmptySubsequences: false).map(String.init) {
                    let candidate = current.isEmpty ? word : current + " " + word
                    if NSAttributedString(string: candidate, attributes: attributes).size().width > wrap,
                       !current.isEmpty {
                        out.append(current)
                        current = word
                    } else {
                        current = candidate
                    }
                }
                out.append(current)
                return out
            }
        } else {
            lines = string.components(separatedBy: "\n")
        }
        for (index, line) in lines.enumerated() {
            (line as NSString).draw(at: CGPoint(x: point.x, y: point.y + CGFloat(index) * size * 1.3),
                                    withAttributes: attributes)
        }
    }
}

/// Content-addressed image cache reads: sha → bytes, served by the backend and kept
/// in memory only for the session. A miss renders as "unavailable", never a substitute.
/// Not actor-isolated on purpose: the export renderer calls it from nonisolated code,
/// and the lock makes the dictionary safe from both sides.
final class ImageCache {
    static let shared = ImageCache()
    private var cache: [String: Data] = [:]
    private let lock = NSLock()
    private weak var api: APIClient?

    func bind(api: APIClient) { self.api = api }

    func data(sha: String) -> Data? {
        guard sha.count == 64 else { return nil }
        lock.lock()
        if let cached = cache[sha] {
            lock.unlock()
            return cached
        }
        lock.unlock()
        guard let api else { return nil }
        let semaphore = DispatchSemaphore(value: 0)
        var fetched: Data?
        Task.detached { [weak self] in
            fetched = try? await api.data("/media/images/\(sha)/bytes")
            semaphore.signal()
        }
        semaphore.wait()
        if let fetched {
            lock.lock()
            cache[sha] = fetched
            lock.unlock()
        }
        return fetched
    }
}

extension CGRect {
    init(points: [CGPoint]) {
        guard let first = points.first else { self = .null; return }
        var rect = CGRect(x: first.x, y: first.y, width: 0, height: 0)
        for point in points.dropFirst() { rect = rect.union(CGRect(x: point.x, y: point.y, width: 0, height: 0)) }
        self = rect
    }
}

extension Color {
    init(hexString: String) {
        var value: UInt64 = 0
        let scanner = Scanner(string: hexString.replacingOccurrences(of: "#", with: ""))
        scanner.scanHexInt64(&value)
        self.init(.sRGB, red: Double((value >> 16) & 0xff) / 255,
                  green: Double((value >> 8) & 0xff) / 255,
                  blue: Double(value & 0xff) / 255, opacity: 1)
    }
}
