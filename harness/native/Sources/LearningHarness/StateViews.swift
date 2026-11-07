import SwiftUI
import AppKit

// MARK: - What a screen is doing right now
//
// Before this file the app had one way to say "not fine": a `String?` error that every
// surface rendered as a red line, plus a spinner wherever `busy` happened to be true.
// Two failures of that arrangement mattered more than the styling:
//
//   1. A blank pane and a genuinely empty list looked identical. A learner on a second
//      machine saw nothing at all and could not tell whether they had no work or the
//      server was not there.
//   2. Every cause collapsed into one message. The live bug report was "the backend
//      cannot be reached, HTTP 422" - but 422 is FastAPI refusing the *shape* of the
//      request, i.e. the app and the server disagree about a field, not a network
//      problem. Sending someone to check their connection when the server is telling
//      them a field name is how a five-minute fix becomes a support thread.
//
// So the state of a screen becomes a value, and every presentation of that value lives
// here: one place to keep VoiceOver, Reduce Motion and the palette honest.

/// The four-and-a-half states a data-backed surface can be in.
///
/// `idle` is kept separate from `loading` on purpose: "nothing has been asked for yet"
/// is not the same claim as "a request is in flight", and a view that renders a spinner
/// for both ends up lying for a frame at launch. `loaded` with no content is still
/// `loaded`; a caller that means "the server says there is nothing" passes `.empty`,
/// which is the only case the UI is allowed to describe as empty.
enum ViewState<Value> {
    case idle
    case loading
    case loaded(Value)
    case empty
    case failed(Error)

    /// The payload, when there is one. Reads better than a `switch` at every call site.
    var value: Value? {
        if case .loaded(let value) = self { return value }
        return nil
    }

    var isLoading: Bool {
        switch self {
        case .idle, .loading: return true
        case .loaded, .empty, .failed: return false
        }
    }
}

/// Switches on a ``ViewState`` and renders the standard presentation for each case.
///
/// The loaded and empty branches are builders rather than `AnyView`s so the caller keeps
/// its own layout and this container keeps no opinion about what "content" looks like.
/// `retry` is optional because not every failed surface has something to retry (a failed
/// one-shot export, for instance) - but when it is passed, every error presentation
/// routes its button to it instead of inventing a second retry path.
struct StateContainer<Value, Loaded: View, Empty: View>: View {
    let state: ViewState<Value>
    var retry: (() -> Void)?
    let loaded: (Value) -> Loaded
    let empty: () -> Empty

    init(state: ViewState<Value>,
         retry: (() -> Void)? = nil,
         @ViewBuilder loaded: @escaping (Value) -> Loaded,
         @ViewBuilder empty: @escaping () -> Empty) {
        self.state = state
        self.retry = retry
        self.loaded = loaded
        self.empty = empty
    }

    var body: some View {
        Group {
            switch state {
            case .idle, .loading:
                // Idle is the frame before a `.task` fires. Rendering the skeleton rather
                // than an empty rect keeps the page from jumping as content lands, and a
                // skeleton makes no claim that data exists.
                LoadingStateView()
            case .loaded(let value):
                loaded(value)
            case .empty:
                empty()
            case .failed(let error):
                // Passed through as an optional on purpose: a container built without a
                // retry gets a pane without a retry button, not a button that does nothing.
                ErrorStateView(error: error, retry: retry)
            }
        }
    }
}

extension StateContainer where Empty == StandardEmptyState {
    /// The common case: the caller has content of its own but is happy with the shared
    /// "nothing here yet" copy, which is deliberately worded to say the list is genuinely
    /// empty rather than merely broken.
    init(state: ViewState<Value>,
         retry: (() -> Void)? = nil,
         @ViewBuilder loaded: @escaping (Value) -> Loaded) {
        self.init(state: state, retry: retry, loaded: loaded, empty: { StandardEmptyState() })
    }
}

/// `EmptyState` with the shared copy, so the empty branch of a container needs no
/// arguments at all.
struct StandardEmptyState: View {
    var icon = "tray"

    var body: some View {
        EmptyState(icon: icon,
                   title: L10n.t("state.empty.title"),
                   message: L10n.t("state.empty.detail"))
    }
}

// MARK: - Loading

/// Skeleton rows plus one labelled progress line.
///
/// The rows are decorative: they are merged into a single accessibility element with the
/// `a11y.loading` label, because a screen reader walking three empty rectangles is noise,
/// not information. That is also why the container ignores its children rather than
/// hiding each one - the label replaces them, nothing is silently dropped.
struct LoadingStateView: View {
    var rows: Int = 3

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var sweep = false

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            ForEach(0..<max(1, rows), id: \.self) { index in
                SkeletonRow(seed: index, sweep: sweep, animate: !reduceMotion)
            }
            HStack(spacing: 8) {
                // A determinate-less spinner is an animation with no end, and Reduce Motion
                // asks for exactly that to stop. The hourglass says the same thing still.
                if reduceMotion {
                    Image(systemName: "hourglass")
                        .font(Typography.footnote)
                        .foregroundStyle(Palette.secondary)
                } else {
                    ProgressView().controlSize(.small)
                }
                Text(L10n.t("state.loading"))
                    .font(Typography.footnote)
                    .foregroundStyle(Palette.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 6)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text(L10n.t("a11y.loading")))
        .accessibilityValue(Text(L10n.t("state.loading.detail")))
        // Without this VoiceOver announces the skeleton once and then goes quiet, even
        // though the useful information ("still going") is that nothing has changed.
        .accessibilityAddTraits(.updatesFrequently)
        .onAppear {
            guard !reduceMotion else { return }
            // Linear, not `LuminfestMotion.ambient`: an ease-in-out sweep decelerates at
            // each edge and reads as a pulse, which implies a unit of progress. A linear
            // sweep reads as "working". Reduce Motion leaves the fill flat - the state is
            // still named in text, so freezing the decoration loses nothing.
            withAnimation(.linear(duration: 1.6).repeatForever(autoreverses: false)) {
                sweep = true
            }
        }
    }
}

/// Three bars of decreasing length, one of them carrying a travelling highlight.
private struct SkeletonRow: View {
    let seed: Int
    let sweep: Bool
    let animate: Bool

    /// Rotated by `seed` so consecutive rows are not identical - an exactly repeating
    /// block reads as a broken image rather than as a placeholder.
    private var lengths: [CGFloat] {
        let base: [CGFloat] = [0.92, 0.74, 0.52]
        return base.indices.map { base[($0 + seed) % base.count] }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            bar(fraction: lengths[0], height: 13)
            bar(fraction: lengths[1], height: 10)
            bar(fraction: lengths[2], height: 10)
        }
    }

    private func bar(fraction: CGFloat, height: CGFloat) -> some View {
        GeometryReader { geo in
            let width = max(24, geo.size.width * fraction)
            RoundedRectangle(cornerRadius: 5, style: .continuous)
                .fill(Palette.muted)
                .frame(width: width, height: height)
                .overlay {
                    if animate {
                        GeometryReader { inner in
                            LinearGradient(
                                colors: [Color.clear,
                                         Palette.surface.opacity(0.8),
                                         Color.clear],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                            .frame(width: max(48, inner.size.width * 0.45))
                            // Off-screen at both ends, so the repeat loop restarts without
                            // a visible snap when `.repeatForever` wraps around.
                            .offset(x: sweep ? inner.size.width : -inner.size.width * 0.45)
                        }
                        .clipShape(RoundedRectangle(cornerRadius: 5, style: .continuous))
                        .allowsHitTesting(false)
                    }
                }
        }
        .frame(height: height)
    }
}

// MARK: - Offline

/// A compact bar, not a modal.
///
/// The server is local, so being unable to reach it is usually transient (still starting,
/// restarted a second ago). A modal would block work that is already on screen - and the
/// copy says exactly that: what is loaded stays readable.
struct OfflineBanner: View {
    var retry: () -> Void

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 11) {
            Image(systemName: "wifi.exclamationmark")
                .font(Typography.callout)
                .foregroundStyle(Palette.terracotta)
                .symbolEffect(.pulse, isActive: !reduceMotion)
                .accessibilityHidden(true)   // decorative: the label below carries the meaning

            VStack(alignment: .leading, spacing: 3) {
                Text(L10n.t("state.offline.title"))
                    .font(Typography.captionEmphasis)
                    .foregroundStyle(Palette.ink)
                Text(L10n.t("state.offline.detail"))
                    .font(Typography.caption)
                    .foregroundStyle(Palette.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer(minLength: 8)

            Button(L10n.t("action.retry"), action: retry)
                .buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 11)
        .background(Palette.oat.opacity(0.9), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(Palette.line, lineWidth: 1)
        )
        // One element, one sentence. A learner should not hear "Working offline", then a
        // paragraph, then "Try Again" as three unrelated stops while navigating past it.
        .accessibilityElement(children: .combine)
        .accessibilityLabel(Text("\(L10n.t("state.offline.title")). \(L10n.t("state.offline.detail"))"))
        // Combining children can swallow the inner button's action, so the retry is also
        // republished as a named action on the combined element. VoiceOver then offers
        // "Try Again" from the rotor without leaving the sentence.
        .accessibilityAction(named: Text(L10n.t("action.retry"))) { retry() }
    }
}

// MARK: - Classifying a failure

/// Why a request failed, in the terms the learner can act on.
///
/// Derived from the app's *real* failure type, `AppFailure` (`Core.swift`), never from a
/// parallel error model: `APIClient.data(_:)` is what turns a non-2xx into an
/// `AppFailure` carrying the status, and it already flattens FastAPI's `detail` list into
/// "field: message" so the offending field is named.
enum FailureCause {
    case validation
    case unreachable
    case timedOut
    case unauthorized
    case server
    case unknown

    init(_ error: Error) {
        if let failure = error as? AppFailure, let status = failure.status {
            switch status {
            case 422:
                self = .validation
            case 401, 403:
                self = .unauthorized
            case 500...599:
                self = .server
            default:
                self = .unknown
            }
            return
        }
        // A launcher-level refusal reaches the UI as a plain sentence with no status and
        // no URLSession error, so it lands in `.unknown`. That is deliberate: an
        // incompatible server already holding the port must never be classified as
        // `.unreachable`, because "the server is not answering" sends the reader to the
        // network while the actual fix is quitting the other copy of the app. `.unknown`
        // surfaces the sentence verbatim, and that sentence names both versions.
        // A URLSession failure arrives as `URLError`, but the NSError bridge is checked too:
        // an error that crossed an `async` boundary or came out of a completion handler is
        // not always castable, and a missed cast would label an unreachable server
        // "unexpected", which is the exact misdirection this file exists to remove.
        let bridge = error as NSError
        let isURLError = (error is URLError) || bridge.domain == NSURLErrorDomain
        guard isURLError else { self = .unknown; return }
        let code = (error as? URLError)?.code ?? URLError.Code(rawValue: bridge.code)
        switch code {
        case .timedOut:
            self = .timedOut
        case .notConnectedToInternet, .cannotConnectToHost, .cannotFindHost,
             .networkConnectionLost, .dnsLookupFailed, .secureConnectionFailed,
             .appTransportSecurityRequiresSecureConnection, .resourceUnavailable:
            self = .unreachable
        default:
            self = .unknown
        }
    }

    /// Whether a navigation cancellation should be shown at all.
    ///
    /// Mirrors the filter `AppStore.record(_:)` already applies: a request cancelled
    /// because the learner moved on is not a failure, and painting an error card for it
    /// teaches people to ignore error cards.
    static func deservesPresentation(_ error: Error) -> Bool {
        if error is CancellationError { return false }
        if let code = (error as? URLError)?.code,
           code == .cancelled { return false }
        return true
    }

    var icon: String {
        switch self {
        case .validation: return "exclamationmark.triangle"
        case .unreachable: return "wifi.exclamationmark"
        case .timedOut: return "clock"
        case .unauthorized: return "lock"
        case .server: return "server.rack"
        case .unknown: return "questionmark.circle"
        }
    }

    var titleKey: String {
        switch self {
        case .validation: return "state.validation.title"
        case .unreachable: return "state.offline.title"
        case .timedOut, .unauthorized, .server, .unknown: return "state.error.title"
        }
    }

    /// The sentence that says what to do next, in the learner's terms.
    var messageKey: String {
        switch self {
        case .validation: return "state.validation.detail"
        case .unreachable: return "error.network"
        case .timedOut: return "error.timeout"
        case .unauthorized: return "error.unauthorized"
        case .server: return "error.server"
        case .unknown: return "error.unknown"
        }
    }

    /// Whether the server's own sentence adds anything beyond the generic copy.
    ///
    /// True only where the server is the one who knows: a refused request body names the
    /// field, an internal error names the thing that broke. For a timeout or a dead
    /// socket the localized sentence is strictly better than the system's English one.
    var surfacesServerSentence: Bool {
        switch self {
        case .validation, .server, .unknown: return true
        case .unreachable, .timedOut, .unauthorized: return false
        }
    }

    var tint: Color {
        switch self {
        case .validation: return Palette.terracotta
        case .unreachable, .timedOut: return Palette.peachDeep
        case .unauthorized: return Palette.slate
        case .server, .unknown: return Palette.secondary
        }
    }
}

// MARK: - Inline failure bar

/// A one-line failure bar for the top of a page, where a full `.Card` would push the
/// content the learner came for off the screen.
///
/// This exists because `AppStore.error` was rendered as a bare `Text`: every cause arrived
/// as the same red sentence, so a 422 — the server refusing a request it parsed — looked
/// exactly like a dead socket. The classification is the same `FailureCause` the full pane
/// uses, so the two surfaces cannot disagree about what went wrong.
struct InlineFailureBar: View {
    let message: String
    var status: Int? = nil
    var retry: () -> Void = {}
    var dismiss: () -> Void = {}

    private var cause: FailureCause {
        FailureCause(AppFailure(message: message, status: status))
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Image(systemName: cause.icon)
                .font(Typography.footnote)
                .foregroundStyle(cause.tint)
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: 3) {
                Text(L10n.t(cause.titleKey))
                    .font(Typography.captionEmphasis)
                    .accessibilityAddTraits(.isHeader)
                // On a 422 the server's own sentence carries the offending field name, so
                // the generic copy would throw away the only actionable part. For a dead
                // socket the localised sentence is better than the system's English one.
                Text(cause.surfacesServerSentence ? message : L10n.t(cause.messageKey))
                    .font(Typography.caption)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .foregroundStyle(Palette.ink)

            Spacer(minLength: 8)

            Button(L10n.t("action.retry"), action: retry)
                .buttonStyle(LuminfestButtonStyle(primary: false, compact: true))

            Button(action: dismiss) {
                Image(systemName: "xmark").font(Typography.captionEmphasis)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(L10n.t("action.close"))
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 11)
        .background(cause.tint.opacity(0.16), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(cause.tint.opacity(0.35), lineWidth: 1)
        )
    }
}

// MARK: - Error

/// The failure pane: one cause-aware sentence, then the evidence, then the actions.
///
/// `error` takes the real `Error` from `APIClient` so the status survives. The
/// `message:status:` convenience exists for the one place the app currently flattens a
/// failure - `AppStore.error` is a `String?` - so a caller that still holds only text can
/// at least keep the code (`status: 422`) and get the right diagnosis.
struct ErrorStateView: View {
    let error: Error
    /// nil means "nothing to retry", and the button is then omitted rather than shown
    /// doing nothing. A dead button teaches people that buttons in error panes are fake,
    /// which is exactly the lesson this layer exists to unlearn.
    var retry: (() -> Void)?

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var showDetails = false

    init(error: Error, retry: (() -> Void)? = nil) {
        self.error = error
        self.retry = retry
    }

    init(message: String, status: Int? = nil, retry: (() -> Void)? = nil) {
        self.init(error: AppFailure(message: message, status: status), retry: retry)
    }

    private var cause: FailureCause { FailureCause(error) }
    private var status: Int? { (error as? AppFailure)?.status }

    /// The raw server sentence. `APIClient.data(_:)` builds it from FastAPI's `detail`
    /// list - and that list is where the offending field name lives, so this is the line
    /// that turns "422" into "`daily_minutes`: Input should be a valid integer".
    private var diagnosticBody: String {
        let raw = (error as? AppFailure)?.message ?? error.localizedDescription
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return L10n.t("error.unknown") }
        // 2000 characters is a ceiling, not a target: the head of a validation payload is
        // the field list. The tail is usually a repeated traceback that pushes the field
        // off screen, and the full text is always on the pasteboard after Copy Diagnostics.
        if trimmed.count <= 2000 { return trimmed }
        return String(trimmed.prefix(2000)) + "…"
    }

    /// Only shown when it is not simply a duplicate of the localized sentence.
    private var serverSentence: String? {
        guard cause.surfacesServerSentence else { return nil }
        let body = diagnosticBody
        return body == L10n.t(cause.messageKey) ? nil : body
    }

    private var accessibilitySentence: String {
        var parts = [L10n.t("a11y.error"), L10n.t(cause.titleKey), L10n.t(cause.messageKey)]
        if let serverSentence { parts.append(serverSentence) }
        return parts.joined(separator: "\n")
    }

    var body: some View {
        Card(padding: 22, interactive: false) {
            VStack(alignment: .leading, spacing: 15) {
                header
                if status != nil { details }
                actions
            }
        }
    }

    private var header: some View {
        HStack(alignment: .top, spacing: 13) {
            Image(systemName: cause.icon)
                .font(Typography.title)
                .foregroundStyle(cause.tint)
                .frame(width: 38, height: 38)
                .background(Palette.surfaceSubtle, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                .accessibilityHidden(true)   // the element's label carries the cause

            VStack(alignment: .leading, spacing: 6) {
                Text(L10n.t(cause.titleKey))
                    .font(Typography.title)
                    .foregroundStyle(Palette.ink)
                Text(L10n.t(cause.messageKey))
                    .font(Typography.callout)
                    .foregroundStyle(Palette.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                if let serverSentence {
                    Text(serverSentence)
                        .font(Typography.callout)
                        .foregroundStyle(Palette.ink)
                        .textSelection(.enabled)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: 0)
        }
        // The text block is one stop. The buttons below stay outside it: combining three
        // buttons into one element would leave VoiceOver with one ambiguous tap target,
        // which is the opposite of exposing the retry action.
        .accessibilityElement(children: .combine)
        .accessibilityLabel(Text(accessibilitySentence))
    }

    @ViewBuilder
    private var details: some View {
        // Collapsed by default. The learner needs "the server rejected a field", not a
        // wall of JSON; whoever is fixing it needs the body. A disclosure gives both
        // without pretending the body is the headline.
        DisclosureGroup(isExpanded: $showDetails) {
            VStack(alignment: .leading, spacing: 10) {
                StateKeyValueRow(label: L10n.t("diagnostics.endpoint"),
                                 value: StateDiagnostics.endpoint,
                                 monospaced: true)
                if let status {
                    StateKeyValueRow(label: L10n.t("diagnostics.lastError"),
                                     value: "HTTP \(status)",
                                     monospaced: true)
                }
                Text(diagnosticBody)
                    .font(.system(.footnote, design: .monospaced))
                    .foregroundStyle(Palette.secondary)
                    .textSelection(.enabled)
                    .lineLimit(14)
            }
            .padding(.top, 10)
        } label: {
            Text(L10n.t("diagnostics.title"))
                .font(Typography.captionEmphasis)
                .foregroundStyle(Palette.secondary)
        }
        .accessibilityLabel(Text(L10n.t("diagnostics.title")))
        // DisclosureGroup expands with its own implicit animation; the shared fade is nil
        // under Reduce Motion, so the evidence appears rather than sliding open.
        .animation(LuminfestMotion.fade(reduceMotion: reduceMotion), value: showDetails)
    }

    private var actions: some View {
        HStack(spacing: 9) {
            if let retry {
                Button(L10n.t("action.retry"), action: retry)
                    .buttonStyle(LuminfestButtonStyle(primary: true, compact: true))
            }
            Button(L10n.t("action.copyDiagnostics"), action: copyDiagnostics)
                .buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
            if let log = StateDiagnostics.logURL {
                // Hidden, not disabled, when the log is absent: a button that cannot work
                // is an invitation to file a bug about the button.
                Button(L10n.t("action.openLog")) { NSWorkspace.shared.open(log) }
                    .buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
            }
            Spacer(minLength: 0)
        }
    }

    /// Everything a support reply needs, as plain text: which server, which code, what it
    /// said, which build. Deliberately narrower than `AppStore.copyDiagnosticReport()` -
    /// that one asks the server and needs a session; this one must work precisely when
    /// the server refuses to answer.
    private func copyDiagnostics() {
        var lines: [String] = []
        lines.append("\(L10n.t("diagnostics.endpoint")): \(StateDiagnostics.endpoint)")
        if let status { lines.append("HTTP \(status)") }
        lines.append("\(L10n.t("diagnostics.appVersion")): \(StateDiagnostics.appVersion)")
        lines.append("")
        lines.append(diagnosticBody)
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(lines.joined(separator: "\n"), forType: .string)
    }
}

// MARK: - Diagnostics

/// Key/value facts a support reply needs, from the same sources the rest of the app reads.
///
/// `serverVersion` has no default source on purpose: only the server knows its schema, and
/// this app's rule elsewhere is that nothing is fabricated. A caller that has asked the
/// server passes the answer; until then the row shows the same em dash the rest of the UI
/// uses for "not known".
struct DiagnosticsPanel: View {
    var endpoint: String? = nil
    /// Pre-formatted so a caller can add context ("v10, older build"). When omitted the
    /// panel asks the launcher, which is the only truthful source: it records what the
    /// *serving* backend declared at adoption. A backend that published no version is
    /// shown as an em dash, never as 0 - 0 would be a version claim it never made.
    var serverVersion: String? = nil
    var lastError: String? = nil
    var showsHeading: Bool = true

    private var resolvedServerVersion: String {
        if let serverVersion { return serverVersion }
        if let adopted = StateDiagnostics.adoptedSchemaVersion { return String(adopted) }
        return "—"
    }

    var body: some View {
        Card(padding: 20, interactive: false) {
            VStack(alignment: .leading, spacing: 14) {
                if showsHeading {
                    SectionHeading(title: L10n.t("diagnostics.title"))
                }
                StateKeyValueRow(label: L10n.t("diagnostics.endpoint"),
                                 value: endpoint ?? StateDiagnostics.endpoint,
                                 monospaced: true)
                StateKeyValueRow(label: L10n.t("diagnostics.serverVersion"),
                                 value: resolvedServerVersion)
                StateKeyValueRow(label: L10n.t("diagnostics.appVersion"),
                                 value: StateDiagnostics.appVersion)
                StateKeyValueRow(label: L10n.t("diagnostics.lastError"),
                                 value: lastError ?? "—")
            }
        }
    }
}

/// One label/value pair, combined so VoiceOver reads "Endpoint: http://…" instead of
/// stopping twice for what is visually a single fact.
private struct StateKeyValueRow: View {
    let label: String
    let value: String
    var monospaced = false

    private var display: String {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? "—" : trimmed
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label)
                .font(Typography.caption)
                .foregroundStyle(Palette.secondary)
            Text(display)
                .font(monospaced ? .system(.callout, design: .monospaced) : Typography.callout)
                .foregroundStyle(Palette.ink)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(Text("\(label): \(display)"))
    }
}

/// The single place that knows where the endpoint, the build number and the backend log
/// live, so the error pane and the diagnostics panel cannot drift apart.
enum StateDiagnostics {
    /// Read from the same key `AppStore.init` and `BackendLauncher.startIfBundled` read.
    /// `BackendLauncher.defaultOrigin` is the same literal, but referring to it here would
    /// drag the launcher into previews and tests that only need a string.
    static var endpoint: String {
        UserDefaults.standard.string(forKey: "luminfest.endpoint")
            ?? "http://127.0.0.1:8765"
    }

    /// "—" rather than "unknown": a SwiftPM executable has no `Info.plist`, and a support
    /// reply that says "unknown" invites a second round trip to establish nothing.
    static var appVersion: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "—"
    }

    /// The schema version the backend actually serving this window declared, or nil.
    ///
    /// Read from the launcher, not from a request: adoption is the moment the decision was
    /// made, and asking again could describe a different process than the one this window
    /// has been talking to. nil covers both "nothing adopted yet" and "that server
    /// published no version field" - both are facts about what is *known*, not a version.
    static var adoptedSchemaVersion: Int? {
        // The launcher is @MainActor and this accessor is not; the panel only reads it
        // while building a view, so the same main-thread shim `L10n.t` uses is enough and
        // never traps off the main thread.
        guard Thread.isMainThread else { return nil }
        return MainActor.assumeIsolated { BackendLauncher.shared.adoptedSchemaVersion }
    }

    /// The log `BackendLauncher` writes the child process's stdout and stderr into. Nil
    /// when this launch adopted an already-running server and never created the file -
    /// which is why the caller hides the button instead of opening a dead path.
    static var logURL: URL? {
        guard let support = try? FileManager.default.url(for: .applicationSupportDirectory,
                                                         in: .userDomainMask,
                                                         appropriateFor: nil,
                                                         create: false) else { return nil }
        let url = support
            .appendingPathComponent("Luminfest Learning Harness", isDirectory: true)
            .appendingPathComponent("backend.log")
        return FileManager.default.fileExists(atPath: url.path) ? url : nil
    }
}
