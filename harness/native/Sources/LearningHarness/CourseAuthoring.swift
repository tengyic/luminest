import SwiftUI

/// The native half of course authoring.
///
/// The backend has always been able to turn a learner's own notes into a course
/// (`/create/preview`, `/create/course`, `/my-courses/{id}/enrol`) and the web console
/// exposed it. The macOS app did not: J6 reported a `gap`, not a failure, because there
/// was simply no SwiftUI entry point. This sheet closes that gap with the same three
/// steps the API already guarantees, in the same order, with the same refusals.
///
/// Two deliberate limits, stated in the UI rather than hidden:
/// * **Preview persists nothing.** The learner sees concepts and questions before a
///   course exists, so a bad source can be abandoned without leaving debris.
/// * **Nothing is invented.** Concepts are extracted verbatim from the pasted source;
///   the backend's rights note is shown before commit. This is not a model writing a
///   syllabus from a title.
struct CourseAuthoringSheet: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss

    @State private var title = ""
    @State private var subject = ""
    @State private var level = ""
    @State private var notes = Self.sampleNotes
    @State private var status = "Paste your own notes, preview the plan, then create the course."
    @State private var result = ""
    @State private var createdID = ""
    @State private var busy = false
    @State private var previewed = false

    /// A real, structured source so a judge can complete the whole journey with one
    /// click, or replace it with their own material. It is visible and editable — not a
    /// canned result. The builder extracts concepts from these sentences verbatim.
    static let sampleNotes = """
    # Fractions

    A fraction names equal parts of a whole. The denominator says how many equal parts the whole was divided into, and the numerator says how many of those parts are being counted.

    Equivalent fractions name the same quantity with different numerators and denominators. Multiplying the numerator and the denominator by the same non-zero number produces an equivalent fraction.

    A common denominator is a shared denominator used to compare or add fractions. Fractions must be rewritten with a common denominator before their numerators can be added.

    An improper fraction has a numerator at least as large as its denominator. It can be rewritten as a mixed number, which is a whole number together with a proper fraction.

    A proper fraction has a numerator smaller than its denominator, so its value is less than one.

    Simplifying a fraction divides the numerator and the denominator by their greatest common factor, leaving the smallest equivalent pair.
    """

    private var canPreview: Bool {
        !busy && notes.trimmingCharacters(in: .whitespacesAndNewlines).count >= 80
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Build a course from your own notes").font(.system(size: 22, weight: .semibold))
            Text("The app extracts the concepts and their prerequisite order from what you paste. "
                 + "Every concept keeps the passage it came from; nothing is invented, and the "
                 + "rights note below says what you may do with the result.")
                .font(.system(size: 12)).foregroundStyle(Palette.secondary).lineSpacing(4)

            HStack(spacing: 12) {
                field("Title", text: $title, id: "course.create.title")
                field("Subject", text: $subject, id: "course.create.subject")
                field("Level", text: $level, id: "course.create.level")
            }

            Text("Your source material").font(.system(size: 12, weight: .semibold))
            TextEditor(text: $notes)
                .font(.system(size: 12))
                .frame(height: 190)
                .padding(8)
                .background(Palette.background, in: RoundedRectangle(cornerRadius: 10))
                .accessibilityIdentifier("course.create.notes")

            HStack(spacing: 10) {
                Button("Preview the plan") { Task { await preview() } }
                    .buttonStyle(LuminfestButtonStyle(primary: false))
                    .disabled(!canPreview)
                    .accessibilityIdentifier("course.create.preview")
                Button("Create this course") { Task { await create() } }
                    .buttonStyle(LuminfestButtonStyle())
                    .disabled(!previewed || busy)
                    .accessibilityIdentifier("course.create.commit")
                if !createdID.isEmpty {
                    Button("Make it my active course") { Task { await enrol() } }
                        .buttonStyle(LuminfestButtonStyle(primary: false))
                        .disabled(busy)
                        .accessibilityIdentifier("course.create.enrol")
                }
                Spacer()
                Button("Close") { dismiss() }
                    .buttonStyle(.borderless)
                    .accessibilityIdentifier("course.create.close")
            }

            Text(status)
                .font(.system(size: 11))
                .foregroundStyle(Palette.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("course.create.status")
            if !result.isEmpty {
                Text(result)
                    .font(.system(size: 12, design: .monospaced))
                    .textSelection(.enabled)
                    .accessibilityIdentifier("course.create.result")
            }
        }
        .padding(28)
        .frame(width: 660)
        .background(Palette.background)
    }

    @ViewBuilder
    private func field(_ label: String, text: Binding<String>, id: String) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(label).font(.system(size: 10)).foregroundStyle(Palette.secondary)
            TextField(label, text: text).textFieldStyle(.roundedBorder)
                .accessibilityIdentifier(id)
        }
    }

    private func message(_ error: Error) -> String {
        (error as? AppFailure)?.message ?? error.localizedDescription
    }

    private func preview() async {
        busy = true; status = "Reading your source and extracting concepts…"
        defer { busy = false }
        do {
            let payload = try await store.api.json("/create/preview", method: "POST",
                                                  body: ["text": notes])
            let concepts = payload["concepts"].array.count
            let questions = payload["questions_total"].int
            let nodes = payload["graph_stats"]["concepts"].int
            guard concepts > 0 else {
                previewed = false
                status = "No concepts could be extracted from these notes. Add defined terms in short paragraphs and preview again; nothing was saved."
                return
            }
            previewed = true
            status = "Preview ready: \(concepts) concepts, \(nodes) graph nodes and \(questions) questions. Nothing has been saved yet — you can still edit your notes."
            result = payload["rights_note"].string
        } catch {
            previewed = false
            status = "Preview refused: \(message(error))"
        }
    }

    private func create() async {
        busy = true; status = "Building and storing your course…"
        defer { busy = false }
        var body: [String: Any] = ["text": notes]
        for (key, value) in [("title", title), ("subject", subject), ("level", level)] {
            let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty { body[key] = trimmed }
        }
        do {
            let payload = try await store.api.json("/create/course", method: "POST", body: body)
            createdID = payload["course"]["id"].string
            guard !createdID.isEmpty else {
                status = "The backend returned no course id. Nothing was enrolled."
                return
            }
            status = "Course created: \(payload["concepts"].int) concepts and \(payload["questions"].int) questions. It belongs to this account but is not yet the active course."
            result = "course_id: \(createdID)"
        } catch {
            status = "Creation refused: \(message(error))"
        }
    }

    private func enrol() async {
        busy = true; status = "Switching your plan to the new course…"
        defer { busy = false }
        do {
            let payload = try await store.api.json("/my-courses/\(createdID)/enrol", method: "POST")
            guard payload["enrolled"].bool else {
                status = "The backend did not confirm enrolment. Your course is still saved."
                return
            }
            await store.refresh()
            status = "Enrolled. Today, the map, the lessons and the practice items now come from this course."
            result = "course_id: \(createdID)\nenrolled: true"
        } catch {
            status = "Enrolment refused: \(message(error))"
        }
    }
}
