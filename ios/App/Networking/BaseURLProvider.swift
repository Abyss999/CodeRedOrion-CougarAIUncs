import Foundation

/// Resolves the API base URL. Precedence:
/// 1. UserDefaults override (DEBUG builds only; set from the Debug settings sheet),
/// 2. Info.plist `API_BASE_URL` (per configuration, from Config/*.xcconfig),
/// 3. `http://127.0.0.1:5055` (Simulator default).
/// `LiveAPIClient` calls `current` on every request, so changes apply without a rebuild.
final class BaseURLProvider: @unchecked Sendable {
    static let overrideKey = "api_base_url_override"
    static let fallback = URL(string: "http://127.0.0.1:5055")!

    private let defaults: UserDefaults
    private let infoValue: String?

    init(defaults: UserDefaults = .standard,
         infoValue: String? = Bundle.main.object(forInfoDictionaryKey: "API_BASE_URL") as? String) {
        self.defaults = defaults
        self.infoValue = infoValue
    }

    /// The default without any override (Info.plist value, else the fallback).
    var defaultURL: URL {
        if let infoValue, let url = Self.validate(infoValue) { return url }
        return Self.fallback
    }

    var overrideURL: URL? {
        #if DEBUG
        guard let raw = defaults.string(forKey: Self.overrideKey) else { return nil }
        return Self.validate(raw)
        #else
        return nil
        #endif
    }

    var current: URL { overrideURL ?? defaultURL }

    /// Returns the normalised URL, or nil if it isn't an http(s) URL with a host.
    /// Trailing slashes are dropped; whitespace is trimmed.
    static func validate(_ raw: String) -> URL? {
        var text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        while text.hasSuffix("/") { text.removeLast() }
        guard !text.isEmpty,
              let comps = URLComponents(string: text),
              let scheme = comps.scheme?.lowercased(), scheme == "http" || scheme == "https",
              let host = comps.host, !host.isEmpty,
              comps.query == nil, comps.fragment == nil,
              let url = comps.url else { return nil }
        return url
    }

    /// DEBUG only. Returns false (and stores nothing) if `raw` is invalid.
    @discardableResult
    func setOverride(_ raw: String) -> Bool {
        #if DEBUG
        guard let url = Self.validate(raw) else { return false }
        defaults.set(url.absoluteString, forKey: Self.overrideKey)
        return true
        #else
        return false
        #endif
    }

    func resetOverride() { defaults.removeObject(forKey: Self.overrideKey) }
}
