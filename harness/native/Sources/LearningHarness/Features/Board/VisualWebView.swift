import Foundation
import SwiftUI
import WebKit
import AppKit

// MARK: - WKWebView host for one structured visual node
//
// One node owns one WebView. The page is shared (`Visuals/index.html`) but each node gets
// its own JS context, so a broken TikZ compile cannot blank another node's chart.
//
// Native -> Web is a single call, `renderFromNative`. Web -> Native is the `luminest`
// message handler carrying `ready` / `rendered` / `error`. The page decides whether a
// renderer can run; Swift never substitutes a placeholder drawing and calls it success.

final class VisualSchemeHandler: NSObject, WKURLSchemeHandler {
    private func finish(_ task: WKURLSchemeTask, url: URL, status: Int) {
        let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: "HTTP/1.1",
                                       headerFields: ["Content-Type": "text/plain"])!
        task.didReceive(response)
        task.didReceive(Data())
        task.didFinish()
    }

    func webView(_ webView: WKWebView, start task: WKURLSchemeTask) {
        guard let url = task.request.url, let root = VisualResources.root else {
            if let url = task.request.url { finish(task, url: url, status: 503) }
            return
        }
        var path = url.path
        if path.hasPrefix("/") { path.removeFirst() }
        if path.isEmpty { path = "index.html" }
        // Refuse traversal and NULs. The custom scheme is a private filesystem gateway,
        // so this check is a real boundary, not defensive decoration.
        guard !path.contains(".."), !path.contains("\0"), !path.hasPrefix("/") else {
            finish(task, url: url, status: 403)
            return
        }
        let file = root.appendingPathComponent(path)
        guard let data = try? Data(contentsOf: file) else {
            finish(task, url: url, status: 404)
            return
        }
        let headers = [
            "Content-Type": VisualResources.mime(for: file.pathExtension),
            "Cache-Control": "no-store",
            "Access-Control-Allow-Origin": "*",
        ]
        let response = HTTPURLResponse(url: url, statusCode: 200, httpVersion: "HTTP/1.1",
                                       headerFields: headers)!
        task.didReceive(response)
        task.didReceive(data)
        task.didFinish()
    }

    func webView(_ webView: WKWebView, stop task: WKURLSchemeTask) { }
}

final class VisualMessageBridge: NSObject, WKScriptMessageHandler {
    var onReady: (() -> Void)?
    var onEvent: (([String: Any]) -> Void)?

    func userContentController(_ controller: WKUserContentController,
                               didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any] else { return }
        onEvent?(body)
        if (body["event"] as? String) == "ready" { onReady?() }
    }
}

struct VisualWebView: NSViewRepresentable {
    let node: BoardNode
    var onStatus: ((String, String) -> Void)?

    final class Coordinator: NSObject {
        var bridge: VisualMessageBridge?
        var schemeHandler: VisualSchemeHandler?
        weak var webView: WKWebView?
        var isReady = false
        var pending: String?
        var signature = ""
        var statusHandler: ((String, String) -> Void)?

        func submit(_ expression: String) {
            guard isReady, let webView else { pending = expression; return }
            webView.evaluateJavaScript(expression) { _, _ in }
        }

        func markReady() {
            isReady = true
            if let queued = pending { pending = nil; submit(queued) }
        }
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    private func jsQuote(_ value: String) -> String {
        guard let data = try? JSONSerialization.data(withJSONObject: [value]),
              let array = String(data: data, encoding: .utf8), array.count >= 2 else {
            return "\"\""
        }
        return String(array.dropFirst().dropLast())
    }

    /// The payload is produced by the backend's fail-close validator. Encoding it with
    /// JSONEncoder and embedding the literal (rather than splicing strings) keeps quotes,
    /// backslashes and LaTeX from ever becoming executable JavaScript.
    private func expression(for node: BoardNode) -> String? {
        guard let payloadData = try? JSONEncoder().encode(node.payload),
              let payloadJSON = String(data: payloadData, encoding: .utf8),
              let configData = try? JSONSerialization.data(withJSONObject: VisualResources.runtimeConfig),
              let configJSON = String(data: configData, encoding: .utf8) else { return nil }
        return "window.LuminestVisuals && window.LuminestVisuals.renderFromNative("
            + "Object.assign(\(payloadJSON), {config: \(configJSON), "
            + "requestId: \(jsQuote(node.id))}))"
    }

    func makeNSView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        let handler = VisualSchemeHandler()
        configuration.setURLSchemeHandler(handler, forURLScheme: VisualResources.scheme)
        let bridge = VisualMessageBridge()
        configuration.userContentController.add(bridge, name: "luminest")
        if #available(macOS 11.0, *) {
            configuration.defaultWebpagePreferences.allowsContentJavaScript = true
        }
        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.setValue(false, forKey: "drawsBackground")
        webView.allowsBackForwardNavigationGestures = false

        let coordinator = context.coordinator
        coordinator.schemeHandler = handler
        coordinator.bridge = bridge
        coordinator.webView = webView
        coordinator.statusHandler = onStatus
        bridge.onEvent = { body in
            let event = body["event"] as? String ?? ""
            if event == "error" {
                coordinator.statusHandler?(body["code"] as? String ?? "RENDER_FAILED",
                                           body["detail"] as? String ?? "")
            }
        }
        bridge.onReady = { [weak coordinator] in coordinator?.markReady() }

        if let url = VisualResources.indexURL, VisualResources.root != nil {
            webView.load(URLRequest(url: url))
        } else {
            // Explicit failure surface: never a silently blank node.
            webView.loadHTMLString(
                "<html><body style=\"font:12px -apple-system;padding:10px;color:#7a3f10\">"
                + "RENDERER_ASSETS_NOT_INSTALLED — Visuals bundle missing</body></html>",
                baseURL: nil)
            onStatus?("RENDERER_ASSETS_NOT_INSTALLED", "Visuals bundle missing from the app")
        }
        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        let coordinator = context.coordinator
        coordinator.statusHandler = onStatus
        guard let js = expression(for: node) else { return }
        let signature = "\(node.id)|\(js)"
        guard signature != coordinator.signature else { return }
        coordinator.signature = signature
        coordinator.submit(js)
    }

    static func dismantleNSView(_ webView: WKWebView, coordinator: Coordinator) {
        webView.configuration.userContentController.removeScriptMessageHandler(forName: "luminest")
        webView.stopLoading()
        coordinator.webView = nil
    }
}
