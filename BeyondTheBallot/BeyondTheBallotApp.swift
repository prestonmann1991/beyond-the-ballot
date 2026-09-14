import SwiftUI

@main
struct BeyondTheBallotApp: App {
    @StateObject private var store = ElectionStore()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(store)
                .task { await store.load() }
        }
    }
}

