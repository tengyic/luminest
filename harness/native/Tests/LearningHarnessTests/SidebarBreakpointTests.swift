import XCTest
@testable import LearningHarness

/// Spec 4.4 — the expanded sidebar breakpoint is exactly 1,120 points.
/// These are pure predicate tests; the real GUI width sweep is driven separately by
/// NativeQA's responsive-width phase (screenshots at 1,120 and 1,119 points).
final class SidebarBreakpointTests: XCTestCase {
    func testExpandedAtAndAbove1120Points() {
        for width: CGFloat in [1400, 1200, 1120] {
            XCTAssertTrue(SidebarLayout.isExpanded(width: width),
                          "\(width) pt must keep the expanded labelled sidebar")
            XCTAssertEqual(SidebarLayout.sidebarWidth(for: width), 207)
        }
    }

    func testCompactBelow1120Points() {
        for width: CGFloat in [1119, 1000, 900] {
            XCTAssertFalse(SidebarLayout.isExpanded(width: width),
                           "\(width) pt must use the compact icon rail")
            XCTAssertEqual(SidebarLayout.sidebarWidth(for: width), 68)
        }
    }

    func testThresholdIsExclusiveAt1119() {
        XCTAssertTrue(SidebarLayout.isExpanded(width: SidebarLayout.expandedBreakpoint))
        XCTAssertFalse(SidebarLayout.isExpanded(width: SidebarLayout.expandedBreakpoint - 1))
        XCTAssertEqual(SidebarLayout.expandedBreakpoint, 1120)
    }

    func testMinimumWindowWidthDoesNotMake900Unreachable() {
        XCTAssertLessThanOrEqual(SidebarLayout.minimumWindowWidth, 900)
        XCTAssertEqual(SidebarLayout.minimumWindowWidth, 900)
    }

    func testCompactRailHasLabelledIdentifiersForEveryPage() {
        for page in Page.allCases {
            XCTAssertFalse(page.title.isEmpty, "compact icon for \(page.rawValue) needs a label")
            XCTAssertFalse(page.icon.isEmpty, "compact icon for \(page.rawValue) needs an SF Symbol")
            XCTAssertEqual(SidebarLayout.compactIdentifier(for: page),
                           "nav.compact." + page.rawValue)
        }
        XCTAssertEqual(Page.allCases.count, 8)
    }

    func testCompactRailIsNarrowerThanExpandedSidebar() {
        XCTAssertLessThan(SidebarLayout.compactWidth, SidebarLayout.expandedWidth)
        XCTAssertGreaterThan(SidebarLayout.compactWidth, 0)
    }
}
