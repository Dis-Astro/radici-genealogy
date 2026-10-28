# Code signing policy

Current free distribution plan: **Microsoft Store signing of MSIX packages**. See [store/README.md](store/README.md). No Microsoft certification, approval or production signature is claimed before the corresponding Store process has completed. The historical SignPath workflow is inactive and no Foundation certificate has been granted.

## Responsibilities

- Repository owner, committer, reviewer and release approver: [Dis-Astro](https://github.com/Dis-Astro).
- AI-assisted changes remain subject to the maintainer's review and responsibility.
- Contributors cannot approve releases or access signing credentials. The maintainer reviews the exact commit, automated reports, identity and release files before submission.

## Production distribution

The MSIX builder uses the application identity assigned to the developer by Microsoft Partner Center. Empty values, template identities and the development identity are rejected for Store builds. The package is built from published source on GitHub-hosted Windows runners. Official dependencies are pinned by version and SHA-256; their existing publisher signatures are preserved.

The submission file is deliberately unsigned. Microsoft signs the version distributed through the Store after identity verification and certification. Preparing an MSIX or a `.msixupload` does not itself produce a trusted signature or establish that certification will succeed.

Microsoft Store package signing is distinct from Authenticode signing of a standalone EXE installer. An unsigned EXE preview must remain labelled as such. A package is not described as Store-signed until the actual Store version and its signature have been verified.

## Isolated tests

The CI package test creates a temporary development certificate with a non-exportable private key only inside a disposable GitHub-hosted Windows VM. The test signs a separate development copy, installs and opens it, closes it gracefully, removes it and checks archive retention. The certificate and its temporary trust are removed at the end. The private key and test-signed package are never uploaded as release artifacts.

No test certificate is created or trusted on the user's computer by this build workflow. Self-signing is suitable for explicitly trusted private test machines; it does not establish broad publisher trust or guarantee antivirus approval.

## Data and capabilities

Family records, media, backups, logs, keys and user-profile data must never enter public source, build inputs or release artifacts. Tests use only synthetic data. Full upstream and application source and component licences accompany application packages.

The MSIX requests `runFullTrust` for the Win32 host/worker and `unvirtualizedResources` to preserve the genealogy archive outside uninstallable package cache. These declarations require Store review; their presence is not claimed to be an approval. See [certification notes](store/CERTIFICATION.md) and [privacy](PRIVACY.md).

References: [Microsoft Store submission](https://learn.microsoft.com/windows/apps/publish/get-started), [MSIX signing](https://learn.microsoft.com/windows/msix/package/sign-msix-package-guide).
