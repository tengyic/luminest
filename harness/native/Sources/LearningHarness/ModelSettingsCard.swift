import SwiftUI

/// Settings → Language model.
///
/// The product requires a language model. It used to ship pointed at a deterministic
/// "offline" generator, and the only way to replace it was to edit `tutor.env` and restart
/// the bundled backend — invisible to a customer, and a degraded default. This card is the
/// replacement: choose a preset, type a model id and key, save, and the running backend
/// picks it up on the next call (``PUT /api/v1/settings/model-config``).
///
/// Three deliberate details:
/// * The key is **never** read back. The server reports only `api_key_set`, so the field
///   stays empty after saving and a later save omits it, which keeps the stored one.
/// * A missing model is a visible state with a next action, not a silent fallback. The
///   card says "Model required" and keeps the form available.
/// * Save, test and revert each report what happened. A disabled button with no message
///   reads as a broken app, which is worse than a clear refusal.
struct ModelSettingsCard: View {
    @EnvironmentObject var store: AppStore

    @State private var presets: [JSON] = []
    @State private var preset = "deepseek"
    @State private var provider = "openai"
    @State private var baseURL = ""
    @State private var model = ""
    @State private var apiKey = ""
    @State private var timeout = "30"
    @State private var configured = false
    @State private var keySet = false
    @State private var source = "none"
    @State private var label = "model-required"
    @State private var reason = "No language model is configured."
    @State private var note: String?
    @State private var noteFailed = false
    @State private var busy = false
    @State private var loaded = false

    private var selectedPreset: JSON {
        presets.first(where: { $0["id"].string == preset }) ?? .null
    }

    private var suggestedModels: [String] {
        selectedPreset["models"].array.map(\.string).filter { !$0.isEmpty }
    }

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: 15) {
                SectionHeading(title: "Language model", detail: "REQUIRED")
                Text("A language model is required for model-backed teaching. Choose a provider, enter a model id and your own API key; it takes effect immediately, with no restart. The key is stored on this Mac and is never shown again.")
                    .font(.system(size: 11))
                    .foregroundStyle(Palette.secondary)
                    .lineSpacing(4)
                    .fixedSize(horizontal: false, vertical: true)

                HStack(spacing: 10) {
                    Image(systemName: configured ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                        .foregroundStyle(configured ? Palette.forest : Palette.peachDeep)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(configured ? "Connected: \(label)" : "Model required")
                            .font(.system(size: 12, weight: .semibold))
                            .accessibilityIdentifier("settings.model.state")
                        Text(configured ? "Source: \(source) · API key \(keySet ? "saved" : "not set")" : reason)
                            .font(.system(size: 10))
                            .foregroundStyle(Palette.secondary)
                    }
                    Spacer()
                }

                Divider()

                HStack(alignment: .top, spacing: 12) {
                    Picker("Provider", selection: $preset) {
                        ForEach(presets, id: \.self) { option in
                            Text(option["label"].string).tag(option["id"].string)
                        }
                    }
                    .labelsHidden()
                    .frame(width: 230)
                    .accessibilityIdentifier("settings.model.preset")
                    .onChange(of: preset) { _, newValue in
                        applyPreset(newValue)
                    }
                    VStack(alignment: .leading, spacing: 5) {
                        TextField("Base URL", text: $baseURL)
                            .textFieldStyle(.roundedBorder)
                            .accessibilityIdentifier("settings.model.baseURL")
                        TextField("Model id", text: $model)
                            .textFieldStyle(.roundedBorder)
                            .accessibilityIdentifier("settings.model.model")
                        if !suggestedModels.isEmpty {
                            Menu("Suggested models") {
                                ForEach(suggestedModels, id: \.self) { candidate in
                                    Button(candidate) { model = candidate }
                                }
                            }
                            .font(.system(size: 10))
                            .accessibilityIdentifier("settings.model.suggestions")
                        }
                    }
                    VStack(alignment: .leading, spacing: 5) {
                        SecureField(keySet ? "API key saved (leave blank to keep)" : "API key", text: $apiKey)
                            .textFieldStyle(.roundedBorder)
                            .accessibilityIdentifier("settings.model.key")
                        TextField("Timeout (seconds)", text: $timeout)
                            .textFieldStyle(.roundedBorder)
                            .accessibilityIdentifier("settings.model.timeout")
                        Text("Wire: \(provider)")
                            .font(.system(size: 10))
                            .foregroundStyle(Palette.secondary)
                    }
                }

                HStack(spacing: 10) {
                    Button("Save model") { Task { await save() } }
                        .buttonStyle(LuminfestButtonStyle())
                        .disabled(busy)
                        .accessibilityIdentifier("settings.model.save")
                    Button("Test connection") { Task { await test() } }
                        .buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
                        .disabled(busy || !configured)
                        .accessibilityIdentifier("settings.model.test")
                    Button("Revert to environment") { Task { await revert() } }
                        .buttonStyle(LuminfestButtonStyle(primary: false, compact: true))
                        .disabled(busy)
                        .accessibilityIdentifier("settings.model.revert")
                    if busy { ProgressView().controlSize(.small) }
                }

                if let note {
                    Label(note, systemImage: noteFailed ? "exclamationmark.triangle" : "checkmark.circle")
                        .font(.system(size: 10))
                        .foregroundStyle(noteFailed ? Palette.peachDeep : Palette.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("settings.model.note")
                }
            }
        }
        .onAppear { if !loaded { loaded = true; Task { await refresh() } } }
    }

    @MainActor
    private func applyPreset(_ id: String) {
        guard let option = presets.first(where: { $0["id"].string == id }) else { return }
        provider = option["wire"].string
        let url = option["base_url"].string
        if !url.isEmpty { baseURL = url }
        if let first = option["models"].array.first?.string, !first.isEmpty, model.isEmpty {
            model = first
        }
    }

    @MainActor
    private func refresh() async {
        do {
            let status = try await store.api.json("/settings/model-config")
            apply(status)
            presets = status["catalog"].array
            if !presets.isEmpty, !presets.contains(where: { $0["id"].string == preset }) {
                preset = presets[0]["id"].string
            }
        } catch {
            noteFailed = true
            note = "Could not read the model configuration: " + failureMessage(error)
        }
    }

    @MainActor
    private func apply(_ status: JSON) {
        configured = status["configured"].bool
        keySet = status["api_key_set"].bool
        source = status["source"].string
        label = status["label"].string
        reason = status["reason"].string
        let base = status["base_url"].string
        if !base.isEmpty { baseURL = base }
        let activeModel = status["model"].string
        if !activeModel.isEmpty { model = activeModel }
        let wire = status["provider"].string
        if !wire.isEmpty { provider = wire }
    }

    @MainActor
    private func save() async {
        busy = true
        defer { busy = false }
        do {
            // An empty key means "keep the saved one"; the server never returns a key,
            // so echoing it back is both impossible and unnecessary.
            let status = try await store.api.json("/settings/model-config", method: "PUT", body: [
                "preset": preset, "provider": provider, "base_url": baseURL,
                "model": model, "api_key": apiKey, "timeout": Double(timeout) ?? 30,
            ])
            apply(status)
            apiKey = ""
            noteFailed = false
            note = "Saved. The new model is live without a restart."
        } catch {
            noteFailed = true
            note = "Could not save: " + failureMessage(error)
        }
    }

    @MainActor
    private func test() async {
        busy = true
        defer { busy = false }
        do {
            let result = try await store.api.json("/settings/model-config/test", method: "POST", body: [:])
            noteFailed = !result["ok"].bool
            note = result["ok"].bool
                ? "The model answered (\(result["provider"].string))."
                : result["detail"].string
        } catch {
            noteFailed = true
            note = "The test request failed: " + failureMessage(error)
        }
    }

    @MainActor
    private func revert() async {
        busy = true
        defer { busy = false }
        do {
            let status = try await store.api.json("/settings/model-config", method: "DELETE")
            apply(status)
            noteFailed = false
            note = "Runtime configuration removed; the instance now uses its environment."
        } catch {
            noteFailed = true
            note = "Could not revert: " + failureMessage(error)
        }
    }

    private func failureMessage(_ error: Error) -> String {
        (error as? AppFailure)?.message ?? error.localizedDescription
    }
}
