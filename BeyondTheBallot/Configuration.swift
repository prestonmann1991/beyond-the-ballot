import Foundation

enum AppConfiguration {
#if DEBUG
    private static let feedBranch = "version-1.2"
#else
    private static let feedBranch = "main"
#endif

    static let remoteFeedURL = URL(
        string: "https://raw.githubusercontent.com/prestonmann1991/beyond-the-ballot/\(feedBranch)/data/candidates.json"
    )!
}
