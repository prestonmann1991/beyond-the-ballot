import Foundation

struct ElectionFeed: Codable {
    let updatedAt: Date
    let source: String
    let candidates: [Candidate]
    let races: [RaceInfo]?
}

struct Candidate: Codable, Identifiable, Hashable {
    let id: String
    let race: String
    let districtOrder: Int
    let name: String
    let party: String
    let campaignURL: URL?
    let orestarURL: URL?
    let filerID: Int?
    let contributionsYTD: Double?
    let expendituresYTD: Double?
    let balanceDeficit: Double?
    let recentContributions: [CampaignTransaction]?
    let recentExpenditures: [CampaignTransaction]?
    let reportedContributions7Days: [CampaignTransaction]?
    let reportedExpenditures7Days: [CampaignTransaction]?
    let topContributorsSince2026: [TopContributor]?
    let videos: [CandidateVideo]?
    let dataError: String?

    var partyShortName: String {
        party.split(separator: "/").map { component in
            let name = String(component).trimmingCharacters(in: .whitespaces)
            switch name {
            case "Democratic": return "D"
            case "Republican": return "R"
            case "Independent": return "I"
            case "Libertarian": return "L"
            case "Working Families": return "WF"
            case "Pacific Green": return "PG"
            case "Progressive": return "P"
            case "Constitution": return "C"
            default: return String(name.prefix(1))
            }
        }.joined(separator: "/")
    }
}

struct CampaignTransaction: Codable, Identifiable, Hashable {
    let id: String
    let date: String
    let name: String
    let category: String
    let amount: Double
    let filedDate: String?
    let filedAt: String?
}

struct TopContributor: Codable, Identifiable, Hashable {
    var id: String { name }
    let name: String
    let amount: Double
}

struct CandidateVideo: Codable, Identifiable, Hashable {
    let id: String
    let title: String
    let date: String
    let source: String
    let url: URL
}

struct RaceInfo: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let districtOrder: Int
    let incumbentName: String
    let incumbentParty: String
    let isFeatured: Bool?
    let registration: RegistrationBreakdown?
    let registrationSourceURL: URL?
    let historicalElections: [HistoricalElection]?
}

struct HistoricalElection: Codable, Identifiable, Hashable {
    var id: String { "\(year)-\(title)" }
    let year: Int
    let title: String
    let results: [HistoricalCandidateResult]
    let sourceURL: URL?
}

struct HistoricalCandidateResult: Codable, Identifiable, Hashable {
    var id: String { "\(name)-\(party)-\(votes)" }
    let name: String
    let party: String
    let votes: Int
    let percentage: Double
}

struct RegistrationBreakdown: Codable, Hashable {
    let asOf: String
    let democraticPct: Double
    let republicanPct: Double
    let otherPct: Double
    let totalActive: Int
}

extension JSONDecoder {
    static var electionDecoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }
}
