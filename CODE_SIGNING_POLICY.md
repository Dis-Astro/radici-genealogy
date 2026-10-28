# Code signing policy

Status: application submitted on 28 October 2026; receipt confirmed by the application form; awaiting review, **not accepted or signed by SignPath Foundation**. This is the proposed policy, subject to Foundation review. The project is new and does not claim established public reputation.

## Responsibilities

- Source repository owner, committer and reviewer: [Dis-Astro](https://github.com/Dis-Astro).
- Release/signing approver: the repository owner, after review of the exact commit, passing CI, dependency licences and release artifacts. AI-assisted changes remain subject to the maintainer's review and responsibility.
- Contributors cannot approve signing or access signing credentials. Maintainers must enable MFA for both GitHub and SignPath before production signing. This document does not assert that MFA or SignPath approval is already configured.

## Intended signing service

Application: [SignPath Foundation](https://signpath.org/apply). If accepted, code signing is intended to be provided free by [SignPath.io](https://signpath.io), with the certificate issued to SignPath Foundation. **That service is not yet active for this project.** On acceptance, the project homepage and download page must display: "Free code signing provided by SignPath.io, certificate by SignPath Foundation".

## Provenance and signing scope

All jobs leading to a signing request run on GitHub-hosted runners. A clean checkout of a recorded commit builds Radici.exe, RadiciMotore.exe, Disinstalla.exe and the installer from the published C# sources. Third-party components are downloaded from official sources at pinned versions, with SHA-256 verification. Their existing signatures are preserved; no upstream DLL is signed under Radici's identity.

The workflow uses two signing requests: first the three Radici executables; then the installer built with those signed executables and their new hashes. Replacing embedded files after installer signing is forbidden. A release requires an exact expected signing certificate thumbprint, trusted Windows signature chain and timestamp. Missing service configuration or verification failures stop the signed release.

Signing is not enabled for pull requests, untrusted branches or automatic pushes. It requires a manual workflow on `main`, approved SignPath production policies and human approval for each request. API tokens belong only in GitHub Actions secrets and must never enter source, logs, artifacts or the genealogy data folder.

Microsoft WebView2 SDK/runtime are proprietary Microsoft system components, included unchanged. Their eligibility under the Foundation's System Libraries exception must be reviewed; this policy does not assume an exception has been granted.

## Privacy

Genealogy is stored locally; family records, media and backups are not submitted to the build or signing services. Only public source and application build artifacts are involved. See [PRIVACY.md](PRIVACY.md) for Microsoft runtime update/diagnostic behaviour.

References: [Foundation conditions](https://signpath.org/terms.html), [trusted GitHub builds](https://docs.signpath.io/trusted-build-systems/github).
