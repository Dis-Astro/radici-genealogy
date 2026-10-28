# Contributing

Use synthetic genealogy only. Do not commit user databases, exports, media, backups, logs, credentials or signing certificates. Keep source and data directories separate.

Genealogy mutations must use the official Gramps object and transaction APIs. Preserve unknown/adoptive relationships and multiple unions. A layout change must never rewrite relationships.

Run the relevant tests and the native Gramps suite before submitting a change. Changes to signing workflows, dependency locks and installer path handling require review by the maintainer. The signing workflow never runs on pull requests and no contributor receives signing credentials.

The application is GPL-2.0-or-later; Windows desktop host/installer code is MIT. Contributions must be compatible with the applicable licence. The project accepts useful changes without requiring assignment of ownership.
