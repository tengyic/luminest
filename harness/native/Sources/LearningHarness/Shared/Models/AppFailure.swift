import Foundation

struct AppFailure: LocalizedError {
    let message: String
    let status: Int?
    var errorDescription: String? { message }
}
