import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var store: ElectionStore
    @State private var searchText = ""
    @State private var selectedChamber = "All"
    @State private var selectedFeed = "Featured"
    @AppStorage("favoriteRaceIDs") private var favoriteRaceIDsStorage = ""

    private let chambers = ["All", "Governor", "House", "Senate"]
    private let feeds = ["Featured", "All Races", "Favorites"]

    private var favoriteRaceIDs: Set<String> {
        Set(favoriteRaceIDsStorage.split(separator: ",").map(String.init))
    }

    private var candidates: [Candidate] {
        let all = store.feed?.candidates ?? []
        return all.filter { candidate in
            let raceInfo = store.feed?.races?.first { $0.name == candidate.race }
            let feedMatches: Bool
            switch selectedFeed {
            case "Featured": feedMatches = raceInfo?.isFeatured ?? true
            case "Favorites": feedMatches = raceInfo.map { favoriteRaceIDs.contains($0.id) } ?? false
            default: feedMatches = true
            }
            let chamberMatches = selectedChamber == "All"
                || candidate.race.hasPrefix(selectedChamber)
                || (selectedChamber == "Governor" && candidate.race == "Oregon Governor")
            let queryMatches = searchText.isEmpty
                || candidate.name.localizedCaseInsensitiveContains(searchText)
                || candidate.race.localizedCaseInsensitiveContains(searchText)
            return feedMatches && chamberMatches && queryMatches
        }
    }

    private var groupedCandidates: [(String, [Candidate])] {
        Dictionary(grouping: candidates, by: \.race)
            .map { ($0.key, $0.value.sorted { $0.party < $1.party }) }
            .sorted { ($0.1.first?.districtOrder ?? 999) < ($1.1.first?.districtOrder ?? 999) }
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Color.appBackground.ignoresSafeArea()
                ScrollView {
                    LazyVStack(spacing: 18) {
                        header
                        feedPicker
                        chamberPicker

                        if let message = store.message {
                            Label(message, systemImage: "wifi.exclamationmark")
                                .font(.footnote)
                                .foregroundStyle(.white.opacity(0.65))
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }

                        ForEach(groupedCandidates, id: \.0) { race, candidates in
                            RaceCard(
                                race: race,
                                candidates: candidates,
                                raceInfo: store.feed?.races?.first { $0.name == race },
                                isFavorite: store.feed?.races?.first { $0.name == race }.map { favoriteRaceIDs.contains($0.id) } ?? false,
                                toggleFavorite: {
                                    guard let id = store.feed?.races?.first(where: { $0.name == race })?.id else { return }
                                    toggleFavorite(id)
                                }
                            )
                        }

                        if groupedCandidates.isEmpty && !store.isLoading {
                            if selectedFeed == "Favorites" && searchText.isEmpty {
                                ContentUnavailableView(
                                    "No Favorite Races",
                                    systemImage: "star",
                                    description: Text("Tap the star on a race to add it to this feed.")
                                )
                                .foregroundStyle(.white)
                            } else {
                                ContentUnavailableView.search(text: searchText)
                                    .foregroundStyle(.white)
                            }
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
        .preferredColorScheme(.dark)
        .tint(.brandOrange)
    }

    private var feedPicker: some View {
        Picker("Race feed", selection: $selectedFeed) {
            ForEach(feeds, id: \.self) { Text($0).tag($0) }
        }
        .pickerStyle(.segmented)
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("STATE OF THE RACES")
                .font(.system(size: 30, weight: .black, design: .rounded))
                .foregroundStyle(.white)
            Text("ORESTAR updates pulled every four hours.")
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
        .background(Color.brandNavy, in: RoundedRectangle(cornerRadius: 24))
    }

    private var chamberPicker: some View {
        Picker("Race type", selection: $selectedChamber) {
            ForEach(chambers, id: \.self) { Text($0).tag($0) }
        }
        .pickerStyle(.segmented)
    }

    private func toggleFavorite(_ id: String) {
        var ids = favoriteRaceIDs
        if ids.contains(id) {
            ids.remove(id)
        } else {
            ids.insert(id)
        }
        favoriteRaceIDsStorage = ids.sorted().joined(separator: ",")
    }

    private var sourceFooter: some View {
        VStack(spacing: 5) {
            Text("Campaign-finance data: Oregon Secretary of State ORESTAR")
            Text("Registration data: Oregon Elections Division; active voters only.")
            Text("Balance/deficit is ORESTAR's reported field and is not necessarily cash on hand.")
            Text("State of the Races is independent and is not affiliated with the state or any campaign.")
        }
        .font(.caption2)
        .multilineTextAlignment(.center)
        .foregroundStyle(.white.opacity(0.55))
        .padding(.vertical, 8)
    }
}

private struct RaceCard: View {
    let race: String
    let candidates: [Candidate]
    let raceInfo: RaceInfo?
    let isFavorite: Bool
    let toggleFavorite: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .firstTextBaseline) {
                    Text(race.uppercased())
                        .font(.caption.weight(.black))
                        .tracking(1.2)
                        .foregroundStyle(Color.brandOrange)
                    Spacer()
                    Button(action: toggleFavorite) {
                        Image(systemName: isFavorite ? "star.fill" : "star")
                            .font(.body.weight(.semibold))
                            .foregroundStyle(isFavorite ? Color.brandOrange : .white.opacity(0.62))
                            .accessibilityLabel(isFavorite ? "Remove \(race) from favorites" : "Add \(race) to favorites")
                    }
                    .buttonStyle(.plain)
                }

                if let raceInfo {
                    Text("Incumbent: \(raceInfo.incumbentName) · \(raceInfo.incumbentParty)")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.white.opacity(0.82))
                }

                if let registration = raceInfo?.registration {
                    RegistrationView(registration: registration, sourceURL: raceInfo?.registrationSourceURL)
                }
            }
            .padding(.horizontal, 18)
            .padding(.vertical, 14)

            Divider().overlay(Color.white.opacity(0.12))

            ForEach(Array(candidates.enumerated()), id: \.element.id) { index, candidate in
                CandidateRow(candidate: candidate)
                if index < candidates.count - 1 {
                    Divider().overlay(Color.white.opacity(0.12)).padding(.leading, 18)
                }
            }

            if let elections = raceInfo?.historicalElections, !elections.isEmpty {
                Divider().overlay(Color.white.opacity(0.12))
                HistoricalResultsView(elections: elections)
                    .padding(18)
            }
        }
        .background(Color.cardSlate, in: RoundedRectangle(cornerRadius: 20))
        .overlay {
            RoundedRectangle(cornerRadius: 20)
                .stroke(Color.white.opacity(0.09), lineWidth: 1)
        }
    }
}

private struct HistoricalResultsView: View {
    let elections: [HistoricalElection]
    @State private var isExpanded = false

    var body: some View {
        DisclosureGroup(isExpanded: $isExpanded) {
            VStack(alignment: .leading, spacing: 16) {
                ForEach(elections) { election in
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text(verbatim: "\(election.year) \(election.title)")
                                .font(.caption.weight(.bold))
                                .foregroundStyle(.white.opacity(0.82))
                            Spacer()
                            if let sourceURL = election.sourceURL {
                                Link("Official results ↗", destination: sourceURL)
                                    .font(.caption2.weight(.semibold))
                            }
                        }

                        ForEach(election.results) { result in
                            HStack(alignment: .firstTextBaseline, spacing: 8) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(result.name)
                                        .font(.caption.weight(.semibold))
                                        .foregroundStyle(.white)
                                    Text(result.party)
                                        .font(.caption2)
                                        .foregroundStyle(.white.opacity(0.52))
                                }
                                Spacer()
                                Text("\(result.votes.formatted()) votes")
                                    .font(.caption.monospacedDigit())
                                    .foregroundStyle(.white.opacity(0.72))
                                Text("\(result.percentage.formatted(.number.precision(.fractionLength(1))))%")
                                    .font(.caption.weight(.bold).monospacedDigit())
                                    .foregroundStyle(.white)
                                    .lineLimit(1)
                                    .minimumScaleFactor(0.8)
                                    .frame(width: 58, alignment: .trailing)
                            }
                        }
                    }
                }
            }
            .padding(.top, 12)
        } label: {
            Label("Past election results", systemImage: "chart.bar.xaxis")
                .font(.caption.weight(.bold))
                .foregroundStyle(.white.opacity(0.78))
        }
        .tint(.brandOrange)
    }
}

private struct RegistrationView: View {
    let registration: RegistrationBreakdown
    let sourceURL: URL?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("Voter registration")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(.white.opacity(0.72))
                Spacer()
                if let sourceURL {
                    Link("As of \(registration.asOf) ↗", destination: sourceURL)
                        .foregroundStyle(.white.opacity(0.55))
                } else {
                    Text("As of \(registration.asOf)")
                        .foregroundStyle(.white.opacity(0.55))
                }
            }
            .font(.system(size: 10, weight: .semibold))

            GeometryReader { geometry in
                HStack(spacing: 2) {
                    Rectangle().fill(Color.partyBlue)
                        .frame(width: max(0, geometry.size.width * registration.democraticPct / 100))
                    Rectangle().fill(Color.partyRed)
                        .frame(width: max(0, geometry.size.width * registration.republicanPct / 100))
                    Rectangle().fill(Color.otherParty)
                }
            }
            .frame(height: 7)
            .clipShape(Capsule())

            HStack(spacing: 12) {
                registrationLabel("D", registration.democraticPct, .partyBlue)
                registrationLabel("R", registration.republicanPct, .partyRed)
                registrationLabel("Other", registration.otherPct, .otherParty)
            }
            .font(.system(size: 10, weight: .semibold))
            .foregroundStyle(.white.opacity(0.72))
        }
    }

    private func registrationLabel(_ name: String, _ value: Double, _ color: Color) -> some View {
        HStack(spacing: 4) {
            Circle().fill(color).frame(width: 6, height: 6)
            Text("\(name) \(value.formatted(.number.precision(.fractionLength(1))))%")
        }
    }
}

private struct CandidateRow: View {
    let candidate: Candidate
    @State private var transactionSheet: TransactionSheet?
    @State private var contributorsExpanded = false
    @State private var videosExpanded = false

    private var partyColor: Color {
        let hasDemocratic = candidate.party.contains("Democratic")
        let hasRepublican = candidate.party.contains("Republican")
        if hasDemocratic && !hasRepublican { return .partyBlue }
        if hasRepublican && !hasDemocratic { return .partyRed }
        return .otherParty
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(candidate.name)
                        .font(.headline)
                        .foregroundStyle(.white)
                    Text(candidate.party)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.white.opacity(0.68))
                        .lineLimit(2)
                }
                Spacer()
                Text(candidate.partyShortName)
                    .font(.caption2.bold())
                    .foregroundStyle(.white)
                    .padding(.horizontal, 8)
                    .frame(minWidth: 28, minHeight: 26)
                    .background(partyColor, in: Capsule())
            }

            HStack(spacing: 14) {
                if let campaignURL = candidate.campaignURL {
                    Link(destination: campaignURL) { Label("Campaign", systemImage: "safari") }
                }
                if let orestarURL = candidate.orestarURL {
                    Link(destination: orestarURL) { Label("ORESTAR", systemImage: "doc.text.magnifyingglass") }
                }
            }
            .font(.caption.weight(.semibold))

            HStack(spacing: 8) {
                metricButton(
                    title: "Contributions",
                    value: candidate.contributionsYTD,
                    transactions: candidate.reportedContributions7Days ?? candidate.recentContributions ?? []
                )
                metricButton(
                    title: "Expenditures",
                    value: candidate.expendituresYTD,
                    transactions: candidate.reportedExpenditures7Days ?? candidate.recentExpenditures ?? []
                )
                MoneyMetric(title: "Balance / Deficit", value: candidate.balanceDeficit, isInteractive: false)
            }

            if let videos = candidate.videos, !videos.isEmpty {
                DisclosureGroup(isExpanded: $videosExpanded) {
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(videos) { video in
                            Link(destination: video.url) {
                                HStack(alignment: .top) {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(video.title).font(.caption.weight(.semibold))
                                        Text(video.source)
                                            .font(.caption2)
                                            .foregroundStyle(.white.opacity(0.55))
                                    }
                                    Spacer()
                                    Image(systemName: "arrow.up.right.square")
                                }
                            }
                        }
                    }
                    .padding(.top, 8)
                } label: {
                    Label("Candidate videos", systemImage: "play.rectangle")
                        .font(.caption.weight(.bold))
                }
                .tint(.brandOrange)
            }

            if let contributors = candidate.topContributorsSince2026, !contributors.isEmpty {
                DisclosureGroup(isExpanded: $contributorsExpanded) {
                    VStack(spacing: 8) {
                        ForEach(Array(contributors.enumerated()), id: \.element.id) { index, contributor in
                            HStack(alignment: .firstTextBaseline) {
                                Text("\(index + 1). \(contributor.name)")
                                    .font(.caption)
                                    .foregroundStyle(.white.opacity(0.78))
                                Spacer()
                                Text(MoneyMetric.currency(contributor.amount))
                                    .font(.caption.weight(.bold).monospacedDigit())
                                    .foregroundStyle(.white)
                            }
                        }
                    }
                    .padding(.top, 8)
                } label: {
                    Label("Top contributors", systemImage: "chart.bar")
                        .font(.caption.weight(.bold))
                        .lineLimit(1)
                }
                .tint(.brandOrange)
            }

            if let dataError = candidate.dataError,
               !dataError.hasPrefix("Refresh failed:") {
                Label(dataError, systemImage: "info.circle")
                    .font(.caption2)
                    .foregroundStyle(.white.opacity(0.58))
            }
        }
        .padding(18)
        .sheet(item: $transactionSheet) { sheet in
            TransactionListView(sheet: sheet)
        }
    }

    private func metricButton(title: String, value: Double?, transactions: [CampaignTransaction]) -> some View {
        Button {
            transactionSheet = TransactionSheet(candidateName: candidate.name, title: title, transactions: transactions)
        } label: {
            MoneyMetric(title: title, value: value, isInteractive: true)
        }
        .buttonStyle(.plain)
    }
}

private struct MoneyMetric: View {
    let title: String
    let value: Double?
    let isInteractive: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 3) {
                Text(title)
                    .lineLimit(1)
                    .minimumScaleFactor(0.68)
                if isInteractive { Image(systemName: "chevron.right").font(.system(size: 7, weight: .bold)) }
            }
            .font(.system(size: 9, weight: .semibold))
            .foregroundStyle(.white.opacity(0.56))

            Text(value.map(Self.currency) ?? "Not reported")
                .font(.system(size: 13, weight: .bold, design: .rounded))
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.58)

        }
        .frame(maxWidth: .infinity, minHeight: 48, alignment: .leading)
        .padding(9)
        .background(Color.metricSlate, in: RoundedRectangle(cornerRadius: 10))
    }

    static func currency(_ value: Double) -> String {
        value.formatted(.currency(code: "USD").precision(.fractionLength(0)))
    }
}

private struct TransactionSheet: Identifiable {
    let id = UUID()
    let candidateName: String
    let title: String
    let transactions: [CampaignTransaction]
}

private struct TransactionListView: View {
    @Environment(\.dismiss) private var dismiss
    let sheet: TransactionSheet

    var body: some View {
        NavigationStack {
            List {
                Section("Reported to ORESTAR in the last 7 days") {
                    if sheet.transactions.isEmpty {
                        Text("No \(sheet.title.lowercased()) were reported to ORESTAR in the last 7 days.")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(sheet.transactions) { transaction in
                            VStack(alignment: .leading, spacing: 5) {
                                HStack(alignment: .firstTextBaseline) {
                                    Text(transaction.name).font(.headline)
                                    Spacer()
                                    Text(MoneyMetric.currency(transaction.amount)).font(.headline)
                                }
                                Text(transactionDescription(transaction))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            .padding(.vertical, 4)
                        }
                    }
                }
                Section {
                    Text("Source: Oregon Secretary of State ORESTAR. Names, dates, categories, and amounts are reproduced from public filings; addresses are not displayed.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("\(sheet.candidateName) \(sheet.title)")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }

    private func transactionDescription(_ transaction: CampaignTransaction) -> String {
        let filed = transaction.filedDate.map { "Reported \($0)" } ?? "Reported date unavailable"
        return "\(filed) · Transaction \(transaction.date) · \(transaction.category)"
    }
}

private extension Color {
    static let brandNavy = Color(red: 0.035, green: 0.105, blue: 0.165)
    static let brandOrange = Color(red: 0.93, green: 0.34, blue: 0.10)
    static let appBackground = Color(red: 0.018, green: 0.055, blue: 0.085)
    static let cardSlate = Color(red: 0.085, green: 0.12, blue: 0.145)
    static let metricSlate = Color(red: 0.12, green: 0.155, blue: 0.18)
    static let partyBlue = Color(red: 0.13, green: 0.37, blue: 0.72)
    static let partyRed = Color(red: 0.72, green: 0.18, blue: 0.20)
    static let otherParty = Color(red: 0.47, green: 0.50, blue: 0.53)
}

#Preview {
    ContentView().environmentObject(ElectionStore())
}
