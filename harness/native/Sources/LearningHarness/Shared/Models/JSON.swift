import Foundation

indirect enum JSON: Codable, Equatable, Hashable {
    case object([String: JSON]), array([JSON]), string(String), number(Double), bool(Bool), null
    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let v = try? c.decode(Bool.self) { self = .bool(v) }
        else if let v = try? c.decode(Double.self) { self = .number(v) }
        else if let v = try? c.decode(String.self) { self = .string(v) }
        else if let v = try? c.decode([JSON].self) { self = .array(v) }
        else { self = .object(try c.decode([String: JSON].self)) }
    }
    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .object(let v): try c.encode(v)
        case .array(let v): try c.encode(v)
        case .string(let v): try c.encode(v)
        case .number(let v): try c.encode(v)
        case .bool(let v): try c.encode(v)
        case .null: try c.encodeNil()
        }
    }
    subscript(_ key: String) -> JSON { if case .object(let v) = self { return v[key] ?? .null }; return .null }
    var array: [JSON] { if case .array(let v) = self { return v }; return [] }
    var object: [String: JSON] { if case .object(let v) = self { return v }; return [:] }
    /// String values of an object, ignoring non-string entries.
    var stringMap: [String: String] {
        var out: [String: String] = [:]
        for (key, value) in object where !value.string.isEmpty { out[key] = value.string }
        return out
    }
    var string: String {
        switch self { case .string(let v): return v; case .number(let v): return v.formatted(); default: return "" }
    }
    var double: Double { if case .number(let v) = self { return v }; return Double(string) ?? 0 }
    var int: Int { let v = double; return v.isFinite && abs(v) < Double(Int.max) ? Int(v) : 0 }
    var bool: Bool { if case .bool(let v) = self { return v }; return false }
    var isNull: Bool { self == .null }
    func text(_ key: String, fallback: String = "") -> String { let v = self[key].string; return v.isEmpty ? fallback : v }
    static func make(_ value: [String: Any]) throws -> JSON { try JSONDecoder().decode(JSON.self, from: JSONSerialization.data(withJSONObject: value)) }
}
