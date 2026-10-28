# Dependencies and source availability

`windows.lock.json` records exact downloads and SHA-256 hashes. Build scripts reject mismatches, including a changed file at an otherwise unchanged vendor URL. Never silently replace a hash to make an unexpected download pass.

- Gramps AIO 6.0.8--1 x64: official [Gramps release](https://github.com/gramps-project/gramps/releases/tag/v6.0.8), used without altering its libraries. Gramps is GPL-2.0-or-later. The complete matching official source is downloaded and included with the installer. The AIO distribution contains Python, GTK and other dependencies with their own notices and sources; preserve its `src`, `share` and licence directories. [AIO build source](https://github.com/gramps-project/gramps-packaging).
- Python 3.14.4 `timeit.py`: unmodified standard-library file, with the [Python licence](https://github.com/python/cpython/blob/v3.14.4/LICENSE).
- CairoSVG / cairocffi, cssselect2, defusedxml, tinycss2, webencodings, pycparser, FontTools and pypdf: exact pure Python wheels from PyPI with licence metadata preserved. Native CFFI/Cairo come from the pinned AIO, not from incompatible CPython wheels.
- Microsoft.Web.WebView2 SDK 1.0.2903.40: original NuGet package, original signed DLLs and Microsoft terms.
- Microsoft WebView2 Evergreen x64 runtime installer: original Microsoft-signed redistributable from a locked download URL. It is installed only if missing and continues to receive Microsoft security updates. Both WebView2 components remain under Microsoft licences, not GPL or MIT. Foundation eligibility is subject to review of the System Libraries exception.
- Font files in `app/fonts`: Crimson Text and Marck Script, SIL Open Font License 1.1; full notices included.

Windows build tools are the platform .NET Framework C# compiler and 7-Zip on the GitHub-hosted Windows runner. The build does not install Gramps globally or run its installer; it extracts the official installer into a build-only directory.

No user tree, photo, export, credential or local dependency cache is part of this repository. Installed source archives include only tracked public repository files and the upstream source archive.
