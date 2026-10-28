# Build Windows and signing

Use a clean checkout on Windows x64, Python 3.12+, .NET Framework C# compiler and 7-Zip. The hosted `windows-2022` runner supplies the Windows build tools. Dependencies are downloaded at fixed hashes; the build never reads a USB drive or user genealogy profile.

```powershell
python scripts/build_windows.py prepare
python scripts/build_windows.py binaries
python scripts/build_windows.py test
python scripts/build_windows.py installer --development-unsigned
```

The output is `.build/windows/dist/Installa-Radici-Desktop-NON-FIRMATO.exe`, with SHA-256 and a build report. `--development-unsigned` is mandatory for untrusted previews. The production path requires signed internal executables and a pinned expected signer thumbprint. A build from source is auditable; byte-for-byte reproducibility of all Microsoft/platform tools is not claimed.

The native tests execute the newly built genealogy worker, with only temporary test data. They write `native-tests.json` and local logs in `.build/windows/qa`. They must report zero failures, errors and skips. The GUI is not automatically certified by this test.

## SignPath, after project acceptance

1. The maintainer enables MFA and configures the public repository with SignPath's trusted GitHub build integration. This can require installing the SignPath GitHub App and granting access to this repository; review the exact permissions before granting them.
2. Configure the `radici` SignPath project and separate approved artifact configurations for the application executables and installer. XML templates are in `signpath/`; they need Foundation review.
3. Set `SIGNPATH_API_TOKEN` as a GitHub Actions secret. Set repository variables `SIGNPATH_ORGANIZATION_ID`, `SIGNPATH_PROJECT_SLUG`, `SIGNPATH_SIGNING_POLICY_SLUG`, and `SIGNPATH_CERT_THUMBPRINT` to the approved production configuration. Never put the token into a file or a chat.
4. Manually dispatch **Windows desktop** on `main` with `sign=true`. CI checks out that commit, downloads hash-locked dependencies, builds, tests and uploads the unsigned application binaries as a workflow artifact.
5. The first signing request returns signed Radici-owned executables. The workflow verifies signatures against the expected certificate, creates new package hashes and compiles the installer. The second request signs the complete installer. The workflow verifies it again and archives the result. Each request still needs the approval required by the SignPath policy.
6. Review the completed run and publish the actual signed file, source and checksum in a release. Update homepage attribution only when the service is active.

The workflow stops if SignPath credentials, expected certificate, approved policies or verified signatures are missing. It does not generate self-signed certificates or alter Windows/antivirus trust settings.

## Linux / Docker

The Dockerfile fetches and verifies the official Gramps 6.0.8 source. Run `docker build -t radici:test .`, followed by the native test command in `.github/workflows/test.yml`. Docker and Windows builds use the same application sources; their platform dependencies differ.
