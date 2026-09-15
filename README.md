# State of the Races

A native SwiftUI iPhone app for tracking selected 2026 Oregon races and four-hour
ORESTAR campaign-finance totals.

## What is included

- Oregon Governor
- House Districts 7, 21, 22, 26, 32, 40, 48, 52, and 53
- Senate Districts 3, 11, 16, and 20
- Candidate name, party, campaign website, ORESTAR balance/deficit, year-to-date
  contributions, and year-to-date expenditures
- Search, race filters, pull-to-refresh, local caching, and a bundled offline copy
- A scheduled GitHub Action that refreshes the data at 6:00 a.m. Oregon time

## Fastest setup

1. Create a **public** GitHub repository named `beyond-the-ballot` and upload
   this entire folder. GitHub Actions will configure the feed URL automatically.
2. On a Mac, open `BeyondTheBallot.xcodeproj` in Xcode. Select the project,
   choose your Apple developer team under **Signing & Capabilities**, connect
   your iPhone, and press **Run**.

The GitHub Action runs at both possible UTC equivalents of 6:00 a.m. and uses
`America/Los_Angeles` to select the correct run during daylight-saving changes.
You can test it immediately from **Actions → Refresh ORESTAR data → Run workflow**.

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
