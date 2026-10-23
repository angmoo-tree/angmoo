# Windows installer language and EXE-only distribution

## Installer behavior and distribution

The Windows installer is one NSIS EXE containing English and Korean.
Interactive installation asks you to choose **English / 한국어**. This choice
applies to installation, update, recovery and removal instructions. Angmoo's
separately saved app language stays unchanged. Interactive reinstall offers
the choice again; the uninstaller uses NSIS's saved installer language.
NSIS page controls follow that choice. Native Windows MessageBox buttons
(OK/Yes/No) follow the Windows display language; their translated message
body uses the chosen installer language. No OS language setting is changed.
Silent installation with `/S` remains noninteractive and preserves its existing
data and exit-code contract. No undocumented `/LANG` option is advertised.

The current Windows distribution is the NSIS EXE. Keep historical installer
files and user data; documentation cleanup does not authorize their removal.

Build with the pinned tools and locked dependencies using
`npm run build:installer` in `desktop`. This builds the real sidecar and
`tauri build --bundles nsis`. Candidate metadata accepts exactly one current
`nsis/Angmoo_{version}_x64-setup.exe`. It rejects stale installers, MSI files,
duplicates, helpers, private data, links and a different source/version.
Checksums, SPDX SBOM and provenance identify the same EXE. A dirty local
worktree is labelled in provenance and is not a final release candidate.

Use an isolated Windows VM or a dedicated test user with synthetic data for
installation, app launch, updates and uninstall. Verify the actual EXE in both
languages, cancellation, repeat language selection, long messages, scaling,
recovery success/failure and the account-wide irreversible deletion warning.
Cancellation, an unchecked deletion box, silent/update removal or final No
must preserve data. Final deletion still requires validation of every allowed
path and reparse rejection before deleting owned children.

Static checks, a compiled translation probe and silent fixture success are
separate from actual candidate GUI verification. If no isolated UI environment
is available, record missing GUI cases as unmeasured. Do not mark them passed.
PR/hosted CI, platform review, candidate verification and publication remain
separate evidence. The published [0.1.0 release](https://github.com/angmoo-tree/angmoo/releases/tag/release-v0.1.0)
does not certify a newly rebuilt installer.

## Resource ownership and focused verification

Installer UI belongs to desktop, not the app's frontend catalog or backend DB.
`installer-languages.nsh` uses official NSIS LangString declarations with
Windows language IDs 1033/1042. The pinned Tauri hook include precedes
MUI_LANGUAGE registration, so resources must be global declarations:
LangString inside an Install section fails NSIS compilation.
The selected/restored `$LANGUAGE` is available before our MessageBox instructions
execute. A dedicated AngmooMessagePath supplies the reparse warning's path
without reusing a shared register or a compile-time macro argument.

The standard dialog uses MUI_LANGDLL_ALWAYSSHOW for interactive reinstall.
The pinned MUI macro's Silent guard and MUI_UNGETLANGUAGE preserve silent
behavior and saved removal language. No new dialog/template or app locale
write is added. Standard translations and original legal notices remain
owned by the framework and their original authors.
Korean welcome and license guidance uses the official MUI_WELCOMEPAGE_TEXT, MUI_PAGE_HEADER_SUBTEXT and
MUI_LICENSEPAGE_TEXT_BOTTOM options with paired LangString resources.
The pinned page order places License after Welcome (which has no page header).
License consumes and unsets the header override; later pages retain their defaults.
Generated-page ordering is checked. The original GPL text and consent stay intact.

Focused commands from the repository root:

```powershell
backend\.venv\Scripts\python.exe scripts\ci\check_windows_installer_i18n.py
backend\.venv\Scripts\python.exe scripts\ci\check_desktop_installer_contract.py
backend\.venv\Scripts\python.exe scripts\ci\check_er6_desktop_supply_chain.py
backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_windows_installer_i18n.py backend\tests\test_l3_er6_interactive_remove_data.py backend\tests\test_l3_er6_installer_supply_chain.py
backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_installer_update.py backend\tests\test_l3_er5_desktop_sidecar_security.py
```

After building, also pass `--generated <target>/release/nsis/x64/installer.nsi`
to the language checker. CI runs these checks and retains its existing actual
NSIS installation, rollback, supported upgrade and Defender gates.

Installer CLI verification must set `--installer-result-path` to a file directly inside
the selected `data-root/runtime` directory. A successful process exit alone is insufficient:
also verify the durable result status and payload identity. Console output in a
windowed EXE is optional; invalid output handles must not hide a failure or change
its nonzero exit. The normal desktop readiness pipe remains mandatory.

Use a candidate output separate from historical bundles. An NSIS-only build
does not remove an old MSI from an existing output directory; the metadata
checker intentionally rejects that mixed directory. Preserve the old files and
use a clean checkout or separately configured candidate output instead.

The Windows product version must agree in Tauri configuration, the desktop
package and its lockfile root, and the Cargo package and its lockfile root.
CI reads the version from Tauri configuration when generating release metadata;
the generator refuses disagreement before writing checksums or provenance.
A version transition rebuilds the host and installer. Dependency package versions
and supported data schema versions are separate from this product version.
Keep downgrade protection and installation identity. A lower product version
does not authorize overwriting a higher-numbered development installation.

Official references: [Tauri multilingual installer](https://v2.tauri.app/distribute/windows-installer/#internationalization),
[NSIS LangString](https://nsis.sourceforge.io/Docs/Chapter4.html#langstring).
