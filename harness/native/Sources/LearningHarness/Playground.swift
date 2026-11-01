import SwiftUI
import WebKit
import AppKit

// The playground, reachable from the lesson.
//
// The 45 bundled games, their correctness oracle and their evidence path all existed but
// nothing in the app pointed at them: a learner had to know the URL `/playground`. This
// file is the entry point, and it is deliberately thin, because the interesting part of
// the playground is not a native view - it is the served gallery page, and that page owns
// the evidence path.
//
// How the pieces fit, and why the app hosts the page rather than re-implementing it:
//
//   * `GET /playground` serves a first-party page that lists the games, injects the chosen
//     one into a sandboxed iframe (`sandbox="allow-scripts"`, opaque origin), listens for
//     the game's `luminfest:outcome` message and POSTs it back with the learner's bearer token.
//     That listener is the trust boundary between generated game code and the record, and
//     it lives in exactly one place.
//   * A native re-implementation would have to reproduce that bridge - sandboxed iframe,
//     postMessage shape checks, the at-most-once sequence watermark, the outcome POST - and
//     two copies of a trust boundary is one copy too many. So the app hosts the page.
//   * The page reads its token from `sessionStorage['luminfest.token']` (the same key the web
//     workbench uses). The app injects it there, never in the URL, where it would leak into
//     history, logs and referrers. In exchange the web view is pinned to the backend origin.
//
// This is the same call `app/simulation_map.py` draws for PhET and Gizmos, in reverse: those
// are third-party and unobservable, so they open in the learner's own browser; the playground
// is first-party and observable, so it runs here, under a session the app controls.

// MARK: - The hosted gallery

/// The playground gallery page, hosted with the learner's session attached.
struct PlaygroundWebView: NSViewRepresentable {
    /// The backend origin, e.g. `http://127.0.0.1:8765`.
    let endpoint: String
    /// The learner's bearer token. Empty means the page shows its own paste-a-token notice.
    let token: String
    /// A game to open on arrival, or nil to leave the gallery on its own list.
    let openSlug: String?

    func makeCoordinator() -> Coordinator { Coordinator(endpoint: endpoint, slug: openSlug) }

    func makeNSView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        // Injected before the page's own script runs, so its first read of `luminfest.token`
        // already sees the session. A token containing a quote or a newline cannot break out
        // of the literal - it is JSON-encoded below.
        if !token.isEmpty {
            configuration.userContentController.addUserScript(
                WKUserScript(source: Self.tokenScript(token), injectionTime: .atDocumentStart,
                             forMainFrameOnly: true))
        }
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.navigationDelegate = context.coordinator
        view.allowsBackForwardNavigationGestures = false
        if let url = Self.galleryURL(endpoint) { view.load(URLRequest(url: url)) }
        return view
    }

    func updateNSView(_ view: WKWebView, context: Context) {
        // The gallery loads once. Only a different server reloads it - never a redraw, which
        // would otherwise discard a game the learner is midway through.
        guard let url = Self.galleryURL(endpoint), context.coordinator.endpoint != endpoint else { return }
        context.coordinator.endpoint = endpoint
        context.coordinator.applied = false
        view.load(URLRequest(url: url))
    }

    static func galleryURL(_ endpoint: String) -> URL? {
        let origin = endpoint.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard !origin.isEmpty else { return nil }
        return URL(string: origin + "/playground")
    }

    /// A JS statement that seeds the page's session token. The value is encoded as a JSON
    /// string literal, so the token cannot terminate the string and inject code.
    static func tokenScript(_ token: String) -> String {
        "try { sessionStorage.setItem('luminfest.token', \(jsonLiteral(token))); } catch (e) {}"
    }

    /// A JSON string literal for `value`, safe to paste into an injected script.
    static func jsonLiteral(_ value: String) -> String {
        (try? JSONSerialization.data(withJSONObject: value, options: [.fragmentsAllowed]))
            .flatMap { String(data: $0, encoding: .utf8) } ?? "\"\""
    }

    final class Coordinator: NSObject, WKNavigationDelegate {
        var endpoint: String
        let slug: String?
        var applied = false

        private var host: String { URL(string: endpoint)?.host?.lowercased() ?? "" }
        private var scheme: String { URL(string: endpoint)?.scheme?.lowercased() ?? "http" }

        init(endpoint: String, slug: String?) { self.endpoint = endpoint; self.slug = slug }

        /// Only the backend origin may load here. Any other navigation - a link out of a
        /// game, a stray redirect - is cancelled and opened in the browser instead, so no
        /// page the app does not serve can ever read the token this view holds.
        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let url = navigationAction.request.url,
                  url.host?.lowercased() == host, url.scheme?.lowercased() == scheme else {
                if let url = navigationAction.request.url { NSWorkspace.shared.open(url) }
                decisionHandler(.cancel)
                return
            }
            decisionHandler(.allow)
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            guard let slug, !slug.isEmpty, !applied else { return }
            applied = true
            webView.evaluateJavaScript(Self.openScript(slug), completionHandler: nil)
        }

        /// Click the gallery's own card for `slug`, once it exists.
        ///
        /// The gallery renders its cards after it has fetched the catalogue, so the card may
        /// not be present when the page finishes loading. Poll briefly for it, then click it -
        /// the exact gesture a learner makes. The lookup walks the cards and compares
        /// `data-slug` rather than building a CSS selector, so a slug can never be read as
        /// selector syntax. If the card never appears the gallery is simply left on screen:
        /// honest degradation rather than a spinner that never resolves.
        static func openScript(_ slug: String) -> String {
            """
            (function () {
              var slug = \(jsonLiteral(slug)), tries = 0;
              function go() {
                var cards = document.querySelectorAll('.card');
                for (var i = 0; i < cards.length; i++) {
                  if (cards[i].getAttribute('data-slug') === slug) { cards[i].click(); return; }
                }
                if (tries++ < 40) { setTimeout(go, 150); }
              }
              go();
            })();
            """
        }
    }
}

/// The sheet that hosts the gallery. A sheet rather than a page, because the playground is
// a thing a learner steps into from a lesson and steps back out of - it is not a destination
// in the app's own navigation.
struct PlaygroundSheet: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 4) {
                    Eyebrow(text: "PLAYGROUND · FIRST-PARTY SIMULATIONS")
                    Text("Playground")
                        .font(.system(size: 22, weight: .semibold, design: .rounded))
                }
                Spacer()
                Button("Done") { dismiss() }.keyboardShortcut(.cancelAction)
            }
            .padding(.horizontal, 22).padding(.vertical, 16)
            Divider()
            if PlaygroundWebView.galleryURL(store.endpoint) == nil {
                VStack(spacing: 10) {
                    Image(systemName: "network.slash").font(.system(size: 28)).foregroundStyle(Palette.tertiary)
                    Text("No server is configured, so the playground cannot be opened.")
                        .font(.system(size: 12)).foregroundStyle(Palette.secondary)
                }.frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                PlaygroundWebView(endpoint: store.endpoint, token: store.api.token ?? "",
                                  openSlug: store.playgroundSlug)
            }
        }
        .frame(minWidth: 900, minHeight: 700)
        .background(Palette.background)
    }
}

// MARK: - The entry point

/// The lesson's way into the playground.
///
/// It sits beside `ExternalSimulationsCard` because both offer an experiment, but it says the
/// opposite thing about the record: a playground game is first-party, it checks the learner's
/// answer and reports it, so it *is* evidence - which is exactly what a PhET or Gizmos card is
/// not. The two disclosures have to read differently or one of them is a lie.
struct PlaygroundCard: View {
    @EnvironmentObject var store: AppStore

    private var payload: JSON { store.playground }
    private var games: [JSON] { payload["games"].array }
    private var withheld: [JSON] { payload["withheld"].array }
    /// How many games the card previews before the learner opens the full gallery.
    private let previewLimit = 6

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                SectionHeading(title: "Playground")
                Spacer()
                if store.playgroundBusy {
                    ProgressView().controlSize(.small)
                } else {
                    Button(games.isEmpty ? "Load games" : "Open the playground") { store.openPlayground() }
                        .buttonStyle(LuminfestButtonStyle(primary: false))
                        .accessibilityIdentifier("playground.open")
                }
            }
            Text("Interactive games built from this course's own interactions. Unlike a PhET or "
                 + "Gizmos simulation, a playground game checks your answer and reports the "
                 + "result, so it counts toward your progress.")
                .font(.system(size: 11)).foregroundStyle(Palette.secondary).lineSpacing(3)

            if !games.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(Array(games.prefix(previewLimit).enumerated()), id: \.offset) { _, game in
                        gameRow(game)
                    }
                }
                let more = games.count - previewLimit
                Text(more > 0
                     ? "\(games.count) games in all; the gallery has the other \(more), plus filters and your run history."
                     : "\(games.count) games; the gallery has filters and your run history.")
                    .font(.system(size: 10)).foregroundStyle(Palette.tertiary)
            } else if store.playgroundBusy {
                Text("Loading the games…").font(.system(size: 11)).foregroundStyle(Palette.secondary)
            } else if payload.isNull {
                Text(store.error ?? "Load the games to see what this course can play.")
                    .font(.system(size: 11)).foregroundStyle(Palette.secondary)
            } else {
                Text("No games are bundled for this build. That is a packaging gap, not an empty "
                     + "course: the catalogue reports \(payload["catalogue_total"].int) games.")
                    .font(.system(size: 11)).foregroundStyle(Palette.secondary)
            }
            if !withheld.isEmpty {
                // A withheld game is a content bug the operator should see, not a silent hole.
                Text("\(withheld.count) game(s) were withheld for a content problem and are not "
                     + "listed; the gallery shows each reason.")
                    .font(.system(size: 10)).foregroundStyle(Palette.peachDeep)
            }
        }
        // Fetch once, on first sight. Guarded on the payload so switching concepts - which
        // re-renders this card - does not re-request a catalogue that has not changed.
        .task { if store.playground.isNull { await store.loadPlayground() } }
    }

    private func gameRow(_ game: JSON) -> some View {
        let scored = game["scored"].bool
        return Button { store.openPlayground(slug: game["slug"].string) } label: {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: scored ? "checkmark.seal" : "cube")
                    .foregroundStyle(scored ? Palette.forest : Palette.tertiary)
                VStack(alignment: .leading, spacing: 3) {
                    Text(game.text("title", fallback: game["slug"].string))
                        .font(.system(size: 12, weight: .medium)).foregroundStyle(Palette.ink)
                    Text(subtitle(game)).font(.system(size: 10)).foregroundStyle(Palette.tertiary)
                }
                Spacer()
                Tag(text: scored ? "SCORED" : "SANDBOX",
                    color: scored ? Palette.sage : Palette.muted)
            }
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.white.opacity(0.9), in: RoundedRectangle(cornerRadius: 11))
            .overlay(RoundedRectangle(cornerRadius: 11).strokeBorder(Palette.line))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("playground.game." + game["slug"].string)
    }

    private func subtitle(_ game: JSON) -> String {
        var parts: [String] = []
        let subjects = game["subjects"].array.map { $0.string }.filter { !$0.isEmpty }
        if !subjects.isEmpty { parts.append(subjects.joined(separator: ", ")) }
        let difficulty = game["difficulty"].string
        if !difficulty.isEmpty { parts.append(difficulty) }
        let minutes = game["minutes"].int
        if minutes > 0 { parts.append("~\(minutes) min") }
        let concept = game["concept"].string
        if !concept.isEmpty { parts.append(concept) }
        return parts.joined(separator: " · ")
    }
}
