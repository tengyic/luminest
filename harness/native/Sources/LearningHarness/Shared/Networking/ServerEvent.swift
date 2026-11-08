import Foundation

/// One Server-Sent Event: the wire name plus the decoded JSON payload.
///
/// Both halves travel because a client that only reads the data cannot tell an
/// ``error`` from a ``tool_result``, and both matter: one is a failure to report and
/// the other is work the tutor did.
struct ServerEvent: Equatable {
    let name: String
    let payload: JSON
}
