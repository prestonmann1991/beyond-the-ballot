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
    let contributionDelta10Days: Double?
    let expenditureDelta10Days: Double?
    let recentContributions: [CampaignTransaction]?
    let recentExpenditures: [CampaignTransaction]?
    let dataError: String?

    var partyShortName: String {
        switch party {
        case "Democratic": return "D"
        case "Republican": return "R"
        default: return String(party.prefix(1))
        }
    }
}

struct CampaignTransaction: Codable, Identifiable, Hashable {
    let id: String
    let date: String
    let name: String
    let category: String
    let amount: Double
}

struct RaceInfo: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let districtOrder: Int
    let incumbentName: String
    let incumbentParty: String
    let registration: RegistrationBreakdown?
    let registrationSourceURL: URL?
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
