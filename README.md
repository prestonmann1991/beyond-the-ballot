# State of the Races

A native SwiftUI iPhone app for tracking Oregon's 2026 statewide and legislative
races, with four-hour ORESTAR campaign-finance updates.

## What is included

- Oregon Governor
- All 60 Oregon House districts
- All 15 Oregon Senate districts on the 2026 ballot
- Candidate name, party, campaign website, ORESTAR balance/deficit, year-to-date
  contributions, and year-to-date expenditures
- Featured, All Races, and user-selected Favorites feeds
- Official prior-election results: 2024 and 2022 for House races, the most recent
  election for Senate races, and 2022 for governor
- Search, race filters, pull-to-refresh, local caching, and a bundled offline copy
- A scheduled GitHub Action that refreshes the data every four hours

## Fastest setup

1. Create a **public** GitHub repository named `beyond-the-ballot` and upload
   this entire folder. GitHub Actions will configure the feed URL automatically.
2. On a Mac, open `BeyondTheBallot.xcodeproj` in Xcode. Select the project,
   choose your Apple developer team under **Signing & Capabilities**, connect
   your iPhone, and press **Run**.

You can test the updater immediately from **Actions → Refresh Oregon election
data → Run workflow**.

## Before App Store submission

- Change the bundle identifier if `com.prestonmann.BeyondTheBallot` is already
  registered to another Apple developer account.
- Review the candidate website list in `backend/candidates_source.json`.
- Use `PRIVACY.md` and `SUPPORT.md` as the public App Store privacy and support pages.
- Copy the prepared listing from `APP_STORE_METADATA.md` into App Store Connect.

## Data notes

ORESTAR totals are public records provided by the Oregon Secretary of State.
The app displays the `Balance Deficit` field exactly as ORESTAR reports it; it
should not be treated as the same thing as cash on hand. If ORESTAR is
temporarily unavailable, the updater preserves the last successful value and
records an error for that candidate instead of replacing data with zero.
