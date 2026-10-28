# Notes for Microsoft Store certification

Radici Genealogy is an independent, local genealogy desktop application using the official Gramps 6.0.8 engine. The UI is Italian. There is no paid account or online service required to use it, and the application contains no user genealogy data.

## Requested capabilities

`runFullTrust`: Radici is a Win32 Windows Forms application embedding Microsoft WebView2 and launching its own local genealogy worker. This worker embeds the unmodified Python runtime supplied with Gramps AIO. The private HTTP interface binds exclusively to 127.0.0.1, uses an internal random bootstrap token and CSRF/session protections, and is used only by the app window. No remote server is exposed.

`unvirtualizedResources`: records, photos, printed albums and backups must survive uninstall and remain compatible with the earlier unpackaged Radici desktop application. Their existing location is `%LOCALAPPDATA%\Radici\Archivio`. On Windows 11 the exclusion is limited to this directory; the Windows 10 fallback disables filesystem AppData write virtualization. The app does not request registry write virtualization opt-out. It does not register services or startup items. The user may explicitly choose to copy a closed USB archive on first use, without overwriting existing local trees or deleting the original.

The capability is requested for continuity and retention of genealogy, not for access to other applications' private data. If the Store requires a different retention design, the package must be revised and retested before publication; the request is not represented as already approved.

## Runtime prerequisite

Windows 10 build 19041 or later, x64, .NET Framework 4.6.2 or later, and Microsoft WebView2 Evergreen 131 or later. On Windows 11 and most updated Windows 10 devices the shared WebView2 Runtime is already present. If unavailable, the app shows an installation-help button that opens the official Microsoft WebView2 download page; no runtime is silently downloaded or installed by the app. No fixed-version browser is bundled.

## Test instructions

1. Start Radici from the Start menu. On first use choose No to begin with an empty archive, unless intentionally testing USB copy with synthetic fixtures.
2. Create a first person using the large add-person button; add a partner and a child from the visual tree. Test another union and an unrelated person.
3. Use the horizontal/vertical layout controls, drag a card, lock its position, and use undo. These operations must preserve genealogical relationships.
4. Export a Gramps archive and print an SVG/PDF. In the album mode use 150 × 100 mm; multiple detail pages preserve name readability.
5. Close using Chiudi e salva. Reopen; verify persistence. Remove the app using Windows Settings and verify the genealogy archive is retained. Use only synthetic data for this test.

The automated installation test is a development package test, not a claim of Store certification. Reports identify development signatures separately from Store signatures.

## Licences and data

GPL-2.0-or-later applies to the genealogy adapter and Gramps, MIT to the Windows host and installer, SIL OFL to bundled fonts. Third-party runtime licences are retained. The package includes complete Radici source and the matching upstream Gramps source archive. The public repository is https://github.com/Dis-Astro/radici-genealogy. No new licence replaces the component licences.

The app does not upload family records, media or backups. Logs are local. Microsoft WebView2 can update and process diagnostics under Microsoft's own terms; this is disclosed in the public privacy policy. No advertising, in-app purchases or analytics service is included by Radici.
