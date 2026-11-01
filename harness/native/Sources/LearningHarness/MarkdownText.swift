import SwiftUI

/// A tutor reply, drawn as blocks instead of as one run of characters.
///
/// The reply is markdown, and the chat used to hand it to a single `Text`, so a heading
/// arrived as `## Your turn` and a bullet as `- **Property check:** …`. This view parses the
/// reply once, when it is created, and draws each block the way it is meant to read: headings
/// larger, bullets hanging, numbers in a column, code monospaced.
///
/// Parsing happens in `init` rather than in `body` on purpose. A chat row is rebuilt whenever
/// the panel re-renders — every activity chip, every busy toggle — and re-parsing the whole
/// transcript on each of those would be work the learner never sees.
struct MarkdownText: View {
    private let blocks: [MarkdownBlock]
    private let size: CGFloat
    private let colour: Color

    init(_ raw: String, size: CGFloat = 12, colour: Color = Palette.ink) {
        self.size = size
        self.colour = colour
        self.blocks = MarkdownBlocks.parse(raw)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
                MarkdownBlockView(block: block, size: size, colour: colour)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .textSelection(.enabled)
    }
}

private struct MarkdownBlockView: View {
    let block: MarkdownBlock
    let size: CGFloat
    let colour: Color

    @ViewBuilder
    var body: some View {
        switch block {
        case .heading(let level, let text):
            Text(inline(text))
                .font(.system(size: headingSize(level), weight: .semibold))
                .foregroundStyle(colour)
                .fixedSize(horizontal: false, vertical: true)
                // The gap belongs above a heading, not below it: a heading that sits closer to
                // the paragraph before it than to its own text reads as the previous section's
                // last line.
                .padding(.top, level <= 2 ? 4 : 2)

        case .paragraph(let text):
            Text(inline(text))
                .font(.system(size: size))
                .foregroundStyle(colour)
                .lineSpacing(4)
                .fixedSize(horizontal: false, vertical: true)

        case .bullet(let level, let text):
            row(marker: "•", level: level, text: text, mono: false)

        case .numbered(let marker, let level, let text):
            row(marker: marker, level: level, text: text, mono: true)

        case .quote(let text):
            HStack(alignment: .top, spacing: 8) {
                RoundedRectangle(cornerRadius: 1.5)
                    .fill(Palette.forest.opacity(0.35))
                    .frame(width: 3)
                    .frame(maxHeight: .infinity)
                Text(inline(text))
                    .font(.system(size: size))
                    .foregroundStyle(Palette.secondary)
                    .lineSpacing(4)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .fixedSize(horizontal: false, vertical: true)

        case .code(let text):
            Text(text)
                .font(.system(size: max(size - 1, 9), design: .monospaced))
                .foregroundStyle(colour)
                .textSelection(.enabled)
                .padding(9)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Palette.surfaceSubtle, in: RoundedRectangle(cornerRadius: 8))
                .fixedSize(horizontal: false, vertical: true)

        case .rule:
            Rectangle()
                .fill(Palette.line)
                .frame(height: 1)
                .padding(.vertical, 2)
        }
    }

    /// A bullet or a numbered item: the marker hangs in its own column so the wrapped text
    /// lines up under the first line instead of under the marker.
    private func row(marker: String, level: Int, text: String, mono: Bool) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text(marker)
                .font(.system(size: size, weight: .semibold,
                              design: mono ? .monospaced : .default))
                .monospacedDigit()
                .foregroundStyle(Palette.forest)
                .frame(minWidth: 14, alignment: .trailing)
            Text(inline(text))
                .font(.system(size: size))
                .foregroundStyle(colour)
                .lineSpacing(4)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.leading, CGFloat(level) * 12)
    }

    private func headingSize(_ level: Int) -> CGFloat {
        switch level {
        case 1: return size + 4
        case 2: return size + 2
        case 3: return size + 0.5
        default: return size
        }
    }

    /// Inline markdown only. The block above already decided *what* this line is; this decides
    /// how the characters inside it look — bold, italic, a code span, a link.
    ///
    /// `failurePolicy` is what makes this safe on generated prose: a stray `*` or an unclosed
    /// `**` returns the text partially parsed instead of throwing, so the worst case is a
    /// visible asterisk, never a blank message.
    private func inline(_ text: String) -> AttributedString {
        var attributed = (try? AttributedString(markdown: text, options: .init(
            allowsExtendedAttributes: true,
            interpretedSyntax: .inlineOnlyPreservingWhitespace,
            failurePolicy: .returnPartiallyParsedIfPossible))) ?? AttributedString(text)

        // A code span is `inlinePresentationIntent == .code`, which `Text` does not draw
        // monospaced on its own. The runs are collected first: mutating the string while
        // walking its runs would invalidate the ranges being iterated.
        let codeRuns = attributed.runs.compactMap { run -> Range<AttributedString.Index>? in
            guard run.inlinePresentationIntent?.contains(.code) == true else { return nil }
            return run.range
        }
        for range in codeRuns {
            attributed[range].font = .system(size: max(size - 1, 9), design: .monospaced)
            attributed[range].foregroundColor = Palette.forest
        }
        return attributed
    }
}
