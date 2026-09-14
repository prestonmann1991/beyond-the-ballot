import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var store: ElectionStore
    @State private var searchText = ""
    @State private var selectedChamber = "All"

    private let chambers = ["All", "Governor", "House", "Senate"]

    private var candidates: [Candidate] {
        let all = store.feed?.candidates ?? []
        return all.filter { candidate in
            let chamberMatches = selectedChamber == "All"
                || candidate.race.hasPrefix(selectedChamber)
                || (selectedChamber == "Governor" && candidate.race == "Oregon Governor")
            let queryMatches = searchText.isEmpty
                || candidate.name.localizedCaseInsensitiveContains(searchText)
                || candidate.race.localizedCaseInsensitiveContains(searchText)
            return chamberMatches && queryMatches
        }
    }

    private var groupedCandidates: [(String, [Candidate])] {
        Dictionary(grouping: candidates, by: \.race)
            .map { ($0.key, $0.value.sorted { $0.party < $1.party }) }
            .sorted {
                ($0.1.first?.districtOrder ?? 999) < ($1.1.first?.districtOrder ?? 999)
            }
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Color.appBackground.ignoresSafeArea()
                ScrollView {
                    LazyVStack(spacing: 18) {
                        header
                        chamberPicker

                        if let message = store.message {
                            Label(message, systemImage: "wifi.exclamationmark")
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }

                        ForEach(groupedCandidates, id: \.0) { race, candidates in
                            RaceCard(race: race, candidates: candidates)
                        }

                        if groupedCandidates.isEmpty && !store.isLoading {
                            ContentUnavailableView.search(text: searchText)
                        }

                        sourceFooter
                    }
                    .padding()
                }
                .refreshable { await store.load(forceRefresh: true) }
            }
            .searchable(text: $searchText, prompt: "Candidate or district")
            .toolbarBackground(Color.brandNavy, for: .navigationBar)
            .toolbarColorScheme(.dark, for: .navigationBar)
        }
        .tint(.brandOrange)
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("BEYOND THE BALLOT")
                .font(.system(size: 30, weight: .black, design: .rounded))
                .foregroundStyle(.white)
            Text("Follow the money in Oregon's key 2026 races.")
                .font(.subheadline)
                .foregroundStyle(.white.opacity(0.82))
            if let date = store.feed?.updatedAt {
                Label("Updated \(date.formatted(date: .abbreviated, time: .shortened))", systemImage: "clock")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.white.opacity(0.72))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(22)
        .background(Color.brandNavy.gradient, in: RoundedRectangle(cornerRadius: 24))
    }

    private var chamberPicker: some View {
        Picker("Race type", selection: $selectedChamber) {
            ForEach(chambers, id: \.self) { Text($0).tag($0) }
        }
        .pickerStyle(.segmented)
    }

    private var sourceFooter: some View {
        VStack(spacing: 5) {
            Text("Campaign-finance data: Oregon Secretary of State ORESTAR")
            Text("Balance/deficit is ORESTAR's reported field and is not necessarily cash on hand.")
        }
        .font(.caption2)
        .multilineTextAlignment(.center)
        .foregroundStyle(.secondary)
        .padding(.vertical, 8)
    }
}

private struct RaceCard: View {
    let race: String
    let candidates: [Candidate]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(race.uppercased())
                .font(.caption.weight(.black))
                .tracking(1.2)
                .foregroundStyle(Color.brandOrange)
                .padding(.horizontal, 18)
                .padding(.vertical, 14)

            Divider()

            ForEach(Array(candidates.enumerated()), id: \.element.id) { index, candidate in
                CandidateRow(candidate: candidate)
                if index < candidates.count - 1 { Divider().padding(.leading, 18) }
            }
        }
        .background(.background, in: RoundedRectangle(cornerRadius: 20))
        .overlay {
            RoundedRectangle(cornerRadius: 20)
                .stroke(Color.primary.opacity(0.06), lineWidth: 1)
        }
        .shadow(color: .black.opacity(0.05), radius: 10, y: 4)
    }
}

private struct CandidateRow: View {
    let candidate: Candidate

    var partyColor: Color {
        candidate.party == "Democratic" ? .partyBlue :
        candidate.party == "Republican" ? .partyRed : .secondary
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline) {
                Text(candidate.name)
                    .font(.headline)
                Spacer()
                Text(candidate.partyShortName)
                    .font(.caption.bold())
                    .foregroundStyle(.white)
                    .frame(width: 25, height: 25)
                    .background(partyColor, in: Circle())
            }

            HStack(spacing: 8) {
                if let campaignURL = candidate.campaignURL {
                    Link(destination: campaignURL) {
                        Label("Campaign", systemImage: "safari")
                    }
                }
                if let orestarURL = candidate.orestarURL {
                    Link(destination: orestarURL) {
                        Label("ORESTAR", systemImage: "doc.text.magnifyingglass")
                    }
                }
            }
            .font(.caption.weight(.semibold))

            HStack(spacing: 10) {
                MoneyMetric(title: "Contributions", value: candidate.contributionsYTD)
                MoneyMetric(title: "Expenditures", value: candidate.expendituresYTD)
                MoneyMetric(title: "Balance / Deficit", value: candidate.balanceDeficit)
            }

            if candidate.dataError != nil {
                Label("Latest ORESTAR refresh unavailable", systemImage: "exclamationmark.triangle")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(18)
    }
}

private struct MoneyMetric: View {
    let title: String
    let value: Double?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.75)
            Text(value.map { $0.formatted(.currency(code: "USD").precision(.fractionLength(0))) } ?? "Not reported")
                .font(.system(size: 14, weight: .bold, design: .rounded))
                .lineLimit(1)
                .minimumScaleFactor(0.65)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(Color.primary.opacity(0.045), in: RoundedRectangle(cornerRadius: 10))
    }
}

private extension Color {
    static let brandNavy = Color(red: 0.055, green: 0.13, blue: 0.20)
    static let brandOrange = Color(red: 0.89, green: 0.36, blue: 0.13)
    static let appBackground = Color(uiColor: .systemGroupedBackground)
    static let partyBlue = Color(red: 0.13, green: 0.37, blue: 0.72)
    static let partyRed = Color(red: 0.72, green: 0.18, blue: 0.20)
}

#Preview {
    ContentView().environmentObject(ElectionStore())
}

