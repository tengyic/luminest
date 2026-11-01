import Foundation

/// One rendered unit of a tutor reply.
///
/// The tutor writes markdown — `## Your turn`, `- **Property check:** …`, `*why*` — because
/// that is what a language model emits. The chat used to draw the whole reply as a single
/// `Text`, so the learner read the asterisks and the hashes as literal characters. Splitting
/// the reply into blocks is what lets a heading be a heading and a bullet be a bullet.
///
/// The grammar is deliberately smaller than CommonMark. It covers what a tutor actually
/// writes, and it makes two choices CommonMark would not:
///
/// * A plain, unindented line after a bullet starts a **new paragraph**, not a lazy
///   continuation. A model ends a list and then writes a summary sentence with no blank line
///   between them; CommonMark would swallow that sentence into the last bullet, and the
///   learner would read it as one more list item.
/// * An *indented* line after a bullet continues that bullet, because that is what a
///   model's own line wrapping looks like when it indents the remainder of a long item.
///
/// Both rules exist because the input is generated prose, not hand-written markdown. Where
/// CommonMark is strict and the model is loose, this follows the model.
enum MarkdownBlock: Equatable {
    case heading(level: Int, text: String)
    case paragraph(String)
    case bullet(level: Int, text: String)
    case numbered(marker: String, level: Int, text: String)
    case quote(String)
    case code(String)
    case rule
}

enum MarkdownBlocks {

    /// Split a reply into blocks. Never throws: anything unrecognised is a paragraph, so a
    /// reply that is not markdown at all comes back as one paragraph and renders as before.
    static func parse(_ raw: String) -> [MarkdownBlock] {
        let normalised = raw
            .replacingOccurrences(of: "\r\n", with: "\n")
            .replacingOccurrences(of: "\r", with: "\n")
            .replacingOccurrences(of: "\u{00A0}", with: " ")
        guard !normalised.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return []
        }

        var blocks: [MarkdownBlock] = []
        var paragraph: [String] = []
        var codeLines: [String] = []
        var inFence = false

        func flushParagraph() {
            guard !paragraph.isEmpty else { return }
            blocks.append(.paragraph(paragraph.joined(separator: " ")))
            paragraph.removeAll()
        }

        func closeFence() {
            blocks.append(.code(codeLines.joined(separator: "\n")))
            codeLines.removeAll()
            inFence = false
        }

        for line in normalised.components(separatedBy: "\n") {
            let trimmed = line.trimmingCharacters(in: .whitespaces)

            if inFence {
                if trimmed.hasPrefix("```") { closeFence() } else { codeLines.append(line) }
                continue
            }
            if trimmed.hasPrefix("```") {
                flushParagraph()
                inFence = true
                codeLines.removeAll()
                continue
            }
            if trimmed.isEmpty {
                flushParagraph()
                continue
            }
            if let (level, text) = heading(trimmed) {
                flushParagraph()
                blocks.append(.heading(level: level, text: text))
                continue
            }
            if isRule(trimmed) {
                flushParagraph()
                blocks.append(.rule)
                continue
            }
            // The bullet and number checks take the *raw* line, not the trimmed one: the
            // leading spaces are the nesting level, and trimming first would flatten every
            // sub-list into its parent.
            if let (level, text) = bullet(line) {
                flushParagraph()
                blocks.append(.bullet(level: level, text: text))
                continue
            }
            if let (marker, level, text) = numbered(line) {
                flushParagraph()
                blocks.append(.numbered(marker: marker, level: level, text: text))
                continue
            }
            if let text = quote(trimmed) {
                flushParagraph()
                blocks.append(.quote(text))
                continue
            }

            // A plain line. If it is indented and the last block is a list item, it is the
            // wrapped remainder of that item; otherwise it joins (or starts) a paragraph.
            if paragraph.isEmpty, isIndented(line), let last = blocks.last {
                switch last {
                case .bullet(let level, let text):
                    blocks[blocks.count - 1] = .bullet(level: level, text: text + " " + trimmed)
                    continue
                case .numbered(let marker, let level, let text):
                    blocks[blocks.count - 1] = .numbered(marker: marker, level: level,
                                                        text: text + " " + trimmed)
                    continue
                case .quote(let text):
                    blocks[blocks.count - 1] = .quote(text + " " + trimmed)
                    continue
                default:
                    break
                }
            }
            paragraph.append(trimmed)
        }

        // An unclosed fence is still a code block: the reply was cut off mid-block, and the
        // lines it did contain are what the learner was meant to read.
        if inFence { closeFence() }
        flushParagraph()
        return blocks
    }

    // MARK: - Line recognisers

    private static func heading(_ line: String) -> (Int, String)? {
        let hashes = line.prefix { $0 == "#" }.count
        guard (1...6).contains(hashes) else { return nil }
        let rest = line.dropFirst(hashes)
        // `#hashtag` is not a heading; the space is what makes it one.
        guard rest.isEmpty || rest.first == " " || rest.first == "\t" else { return nil }
        let text = rest.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return nil }
        return (hashes, text)
    }

    private static func isRule(_ line: String) -> Bool {
        let tight = line.replacingOccurrences(of: " ", with: "")
        guard tight.count >= 3 else { return false }
        if tight.allSatisfy({ $0 == "-" }) { return true }
        if tight.allSatisfy({ $0 == "*" }) { return true }
        return tight.allSatisfy({ $0 == "_" })
    }

    private static func bullet(_ line: String) -> (Int, String)? {
        let level = indentLevel(line)
        let rest = line.drop { $0 == " " || $0 == "\t" }
        guard let first = rest.first, first == "-" || first == "*" || first == "•" else {
            return nil
        }
        let afterMarker = rest.dropFirst()
        guard afterMarker.first == " " || afterMarker.first == "\t" else { return nil }
        let text = afterMarker.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return nil }
        return (level, text)
    }

    private static func numbered(_ line: String) -> (String, Int, String)? {
        let level = indentLevel(line)
        let rest = line.drop { $0 == " " || $0 == "\t" }
        let digits = rest.prefix { $0.isNumber }
        guard !digits.isEmpty, digits.count <= 3 else { return nil }
        let afterDigits = rest.dropFirst(digits.count)
        guard let separator = afterDigits.first, separator == "." || separator == ")" else {
            return nil
        }
        let afterSeparator = afterDigits.dropFirst()
        guard afterSeparator.first == " " || afterSeparator.first == "\t" else { return nil }
        let text = afterSeparator.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return nil }
        // The marker keeps the number the tutor wrote, so a list that starts at 3 still reads
        // as 3, 4, 5 rather than being silently renumbered from one.
        return (String(digits) + ".", level, text)
    }

    private static func quote(_ line: String) -> String? {
        guard line.hasPrefix(">") else { return nil }
        let text = line.dropFirst().trimmingCharacters(in: .whitespaces)
        return text.isEmpty ? nil : text
    }

    private static func indentLevel(_ line: String) -> Int {
        var spaces = 0
        for character in line {
            if character == " " { spaces += 1 }
            else if character == "\t" { spaces += 2 }
            else { break }
        }
        return min(spaces / 2, 3)
    }

    private static func isIndented(_ line: String) -> Bool {
        guard let first = line.first else { return false }
        return first == " " || first == "\t"
    }
}
