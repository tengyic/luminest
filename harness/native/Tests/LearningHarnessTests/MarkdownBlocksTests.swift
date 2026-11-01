import XCTest
@testable import LearningHarness

/// The chat used to draw a whole tutor reply in one `Text`, so the learner read the markdown
/// the model wrote: `## Your turn`, `- **Property check:** …`, `*why*`. These tests pin the
/// block split that replaced it, using the reply that exposed the problem.
final class MarkdownBlocksTests: XCTestCase {

    private func tags(_ raw: String) -> [String] {
        MarkdownBlocks.parse(raw).map { block in
            switch block {
            case .heading(let level, let text): return "h\(level)|\(text)"
            case .paragraph(let text): return "p|\(text)"
            case .bullet(let level, let text): return "b\(level)|\(text)"
            case .numbered(let marker, let level, let text): return "n\(level)|\(marker)|\(text)"
            case .quote(let text): return "q|\(text)"
            case .code(let text): return "code|\(text)"
            case .rule: return "hr"
            }
        }
    }

    /// The shape of a real reply, in the order a learner reads it.
    func testTheTutorReplySplitsIntoHeadingsBulletsAndNumbers() {
        let reply = """
        A cP air mass sits over central Canada in January.
        - **Property check:** cP = cold + dry; mT = warm + humid.
        - **Density check:** the cold air is denser, so it wedges *under* the warm air.
        That last line is worth remembering: the front is an inference.
        ## Your turn (before practice)
        1. In your own words: *why* does the cold air end up underneath?
        2. Predict: would the rain band be narrower or wider?
        Answer those two and I'll tell you which part holds.
        """
        XCTAssertEqual(tags(reply), [
            "p|A cP air mass sits over central Canada in January.",
            "b0|**Property check:** cP = cold + dry; mT = warm + humid.",
            "b0|**Density check:** the cold air is denser, so it wedges *under* the warm air.",
            // Unindented after a bullet, so a paragraph — not a fifth list item. CommonMark
            // would swallow it into the list; a learner would read it as one more bullet.
            "p|That last line is worth remembering: the front is an inference.",
            "h2|Your turn (before practice)",
            "n0|1.|In your own words: *why* does the cold air end up underneath?",
            "n0|2.|Predict: would the rain band be narrower or wider?",
            "p|Answer those two and I'll tell you which part holds.",
        ])
    }

    func testAnIndentedLineContinuesTheBulletAboveIt() {
        let reply = """
        - **Content location:** the concept is the node `air_masses_and_fronts`,
          in the `earth_space_science` strand.
        - Second item.
        """
        XCTAssertEqual(tags(reply), [
            "b0|**Content location:** the concept is the node `air_masses_and_fronts`, in the `earth_space_science` strand.",
            "b0|Second item.",
        ])
    }

    func testNestingIsReadFromTheIndent() {
        XCTAssertEqual(tags("- outer\n  - inner\n    - deeper"),
                       ["b0|outer", "b1|inner", "b2|deeper"])
    }

    /// A number the tutor wrote is kept: a list that starts at three must not silently become
    /// a list that starts at one.
    func testAListKeepsTheNumbersItWasGiven() {
        XCTAssertEqual(tags("3. third\n4. fourth"), ["n0|3.|third", "n0|4.|fourth"])
    }

    /// The two characters that most often mean something else. `*why*` is emphasis and
    /// `#hashtag` is not a heading; treating either as a marker would eat the text.
    func testAsterisksAndHashesThatAreNotMarkers() {
        XCTAssertEqual(tags("*why* is the question"), ["p|*why* is the question"])
        XCTAssertEqual(tags("#hashtag no space"), ["p|#hashtag no space"])
        XCTAssertEqual(tags("2 * 3 = 6"), ["p|2 * 3 = 6"])
    }

    func testAFencedBlockStaysVerbatim() {
        XCTAssertEqual(tags("see:\n```swift\nlet x = 1\nlet y = 2\n```\ndone"),
                       ["p|see:", "code|let x = 1\nlet y = 2", "p|done"])
    }

    /// A reply cut off mid-block still shows the lines it contained.
    func testAnUnclosedFenceIsStillACodeBlock() {
        XCTAssertEqual(tags("```python\nx = 1"), ["code|x = 1"])
    }

    func testHeadingsRulesAndQuotes() {
        XCTAssertEqual(tags("# one\n## two\n### three"), ["h1|one", "h2|two", "h3|three"])
        XCTAssertEqual(tags("above\n---\nbelow"), ["p|above", "hr", "p|below"])
        XCTAssertEqual(tags("> quoted"), ["q|quoted"])
    }

    func testPlainTextIsOneParagraph() {
        XCTAssertEqual(tags("Just a sentence\nthat wrapped across two lines."),
                       ["p|Just a sentence that wrapped across two lines."])
    }

    func testAnEmptyReplyHasNoBlocks() {
        XCTAssertEqual(tags("   \n\n "), [])
    }
}
