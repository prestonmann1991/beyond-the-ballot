import Foundation
import Combine

@MainActor
final class ElectionStore: ObservableObject {
    @Published private(set) var feed: ElectionFeed?
    @Published private(set) var isLoading = false
    @Published private(set) var message: String?

    private let cacheURL: URL = {
        FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("candidates-v1.1.json")
    }()

    func load(forceRefresh: Bool = false) async {
        guard !isLoading else { return }
        isLoading = true
        defer { isLoading = false }

        if feed == nil {
            feed = loadCachedFeed() ?? loadBundledFeed()
        }

        if !forceRefresh, let feed, Date().timeIntervalSince(feed.updatedAt) < 900 {
            return
        }

        do {
            var request = URLRequest(url: AppConfiguration.remoteFeedURL)
            request.cachePolicy = .reloadIgnoringLocalCacheData
            request.timeoutInterval = 20
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, 200..<300 ~= http.statusCode else {
                throw URLError(.badServerResponse)
            }
            let fresh = try JSONDecoder.electionDecoder.decode(ElectionFeed.self, from: data)
            feed = fresh
            try data.write(to: cacheURL, options: .atomic)
            message = nil
        } catch {
            message = "Showing the most recent saved update."
        }
    }

    private func loadCachedFeed() -> ElectionFeed? {
        guard let data = try? Data(contentsOf: cacheURL) else { return nil }
        return try? JSONDecoder.electionDecoder.decode(ElectionFeed.self, from: data)
    }

    private func loadBundledFeed() -> ElectionFeed? {
        guard let url = Bundle.main.url(forResource: "candidates", withExtension: "json"),
              let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder.electionDecoder.decode(ElectionFeed.self, from: data)
    }
}
