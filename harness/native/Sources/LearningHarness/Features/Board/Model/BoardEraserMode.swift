import SwiftUI

// MARK: - Eraser modes

/// What the eraser takes off. Defaults to the whole stroke because that is what a person
/// reaching for an eraser expects; the finer modes exist because scrubbing a whole
/// drawing to fix one mark is the other reason people stop drawing on shared boards.
enum BoardEraserMode: String, CaseIterable, Identifiable {
    case stroke, segment

    var id: String { rawValue }

    var label: String {
        switch self {
        case .stroke: return "Whole stroke"
        case .segment: return "Scrub"
        }
    }

    var help: String {
        switch self {
        case .stroke: return "Remove the stroke you touch."
        case .segment: return "Remove only the samples under the pointer, keeping the rest of the stroke."
        }
    }

    var icon: String {
        switch self {
        case .stroke: return "eraser.fill"
        case .segment: return "scissors"
        }
    }
}
