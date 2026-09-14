import Foundation

struct ElectionFeed: Codable {
    let updatedAt: Date
    let source: String
    let candidates: [Candidate]
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
    let dataError: String?

    var partyShortName: String {
        switch party {
        case "Democratic": return "D"
        case "Republican": return "R"
        default: return String(party.prefix(1))
        }
    }
}

extension JSONDecoder {
    static var electionDecoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }
}

