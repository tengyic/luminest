import Foundation

enum Page: String, CaseIterable, Identifiable {
    case today, studio, map, review, teacher, projects, insights, settings
    var id: String { rawValue }
    /// Localized through `L10n` rather than a switch over English literals.
    ///
    /// The sidebar, the window title and the `Learning` menu all render this one
    /// property, so a single lookup keeps three surfaces in step when the language
    /// changes — a switch here would leave the menu in English after a switch to Chinese.
    /// Keys are `nav.<case>`; see Localizable.strings.
    var title: String { L10n.t("nav.\(rawValue)") }
    var icon: String {
        switch self { case .today: return "sun.max"; case .studio: return "book.closed"; case .map: return "point.3.connected.trianglepath.dotted"; case .review: return "arrow.trianglehead.clockwise"; case .teacher: return "bubble.left.and.text.bubble.right"; case .projects: return "square.stack.3d.up"; case .insights: return "chart.xyaxis.line"; case .settings: return "slider.horizontal.3" }
    }
    var eyebrow: String {
        switch self { case .today: return "YOUR LEARNING, IN FOCUS"; case .studio: return "UNDERSTAND. EXPLORE. APPLY."; case .map: return "CONNECT THE IDEAS"; case .review: return "MAKE IT STICK"; case .teacher: return "A LITTLE GUIDANCE"; case .projects: return "FROM KNOWING TO MAKING"; case .insights: return "EVIDENCE, NOT ASSUMPTIONS"; case .settings: return "MAKE LUMINFEST YOURS" }
    }
    var subtitle: String {
        switch self { case .today: return "Small steps. Deeper understanding. A little progress, every day."; case .studio: return "A quiet space to read, experiment, and work through an idea."; case .map: return "See how your understanding grows, one connection at a time."; case .review: return "Revisit the right ideas at the right time."; case .teacher: return "Ask a question. Find a grounded explanation."; case .projects: return "Put your learning into something you can call your own."; case .insights: return "An honest picture of the practice you have actually done."; case .settings: return "Your goals, your privacy, and your learning environment." }
    }
}
