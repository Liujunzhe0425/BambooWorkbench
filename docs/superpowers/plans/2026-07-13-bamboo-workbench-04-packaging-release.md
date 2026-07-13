# BambooWorkbench CI, Packaging, Handoff, and Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the verified local framework into a reproducible private-GitHub workflow, portable build, Windows installer, module handoff kit, customer demonstration package, and tagged `v0.1.0` release.

**Architecture:** GitHub Actions runs the same contract, unit, integration, UI smoke, and packaging commands used locally. PyInstaller creates a self-contained directory containing the framework and three mock modules; Inno Setup installs that directory while user data remains under platformdirs outside the installation tree. Handoff documentation is generated only after the contract CLI and mock modules are real, so module developers can copy, validate, and submit a package without framework internals.

**Tech Stack:** Git/GitHub private repository, GitHub Actions Windows runner, Python 3.12, pytest, ruff, PyInstaller, Inno Setup 6, PowerShell.

## Global Constraints

- Complete Plans 1–3 first and start this plan from a green `integration` branch.
- Do not commit enterprise workbooks, generated customer reports, API keys, local databases, logs, caches, or installation output.
- `main` is stable and protected; framework integration occurs on `integration`; module work begins from the frozen-contract `integration` commit.
- The first release bundles the three mock modules and exposes no customer-facing plugin installer.
- Installer upgrades and uninstalls preserve `%LOCALAPPDATA%\BambooWorkbench` unless the user deliberately deletes it.
- Creating the private GitHub repository, inviting collaborators, changing branch protection, pushing, or publishing a release requires the user’s authenticated GitHub context and explicit approval at that checkpoint.
- Use TDD or executable verification for every artifact and commit after each independently testable task.

---

## File Map

| Path | Responsibility |
|---|---|
| `.github/workflows/quality.yml` | Windows quality and contract checks |
| `.github/workflows/package.yml` | Reproducible portable build artifact |
| `.github/pull_request_template.md` | PR evidence checklist |
| `.github/CODEOWNERS` | Framework and module review ownership |
| `scripts/verify_repo.ps1` | One-command local quality gate |
| `scripts/build_portable.ps1` | Clean PyInstaller build |
| `scripts/verify_portable.ps1` | Packaged smoke and file-layout checks |
| `packaging/BambooWorkbench.spec` | PyInstaller entry point and data files |
| `packaging/BambooWorkbench.iss` | Inno Setup installer and upgrade policy |
| `docs/handoff/module-development-guide.md` | Exact module contributor contract |
| `docs/handoff/module-acceptance-checklist.md` | Team lead acceptance checklist |
| `docs/handoff/github-workflow.md` | Branch, commit, PR, and integration flow |
| `docs/demo/customer-demo-script.md` | Customer-facing demonstration route |
| `docs/release/release-checklist.md` | Repeatable internal release gate |
| `CHANGELOG.md` | Versioned user-visible changes |

### Task 1: Freeze repository hygiene and local verification

**Files:**
- Modify: `.gitignore`
- Create: `.gitattributes`
- Create: `scripts/verify_repo.ps1`
- Test: `tests/repository/test_repository_hygiene.py`

- [ ] **Step 1: Write the failing hygiene test**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_repository_ignores_local_and_sensitive_artifacts():
    rules = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for required in (".venv/", "*.db", "*.log", "data/", "dist/", "build/", ".env", "*.key"):
        assert required in rules


def test_repository_has_no_tracked_enterprise_spreadsheets():
    forbidden = [p for p in ROOT.rglob("*") if p.suffix.lower() in {".xlsx", ".xls"} and "tests/fixtures" not in p.as_posix()]
    assert forbidden == []
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/repository/test_repository_hygiene.py -q`
Expected: FAIL until all required ignore rules exist.

- [ ] **Step 3: Add deterministic text and ignore policies**

`.gitattributes`:

```gitattributes
* text=auto
*.py text eol=lf
*.md text eol=lf
*.json text eol=lf
*.yml text eol=lf
*.yaml text eol=lf
*.ps1 text eol=crlf
*.bat text eol=crlf
```

Add the tested entries plus `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `htmlcov/`, `*.sqlite*`, `*.tmp`, `*.bak`, `installer-output/`, and `credentials/` to `.gitignore`.

- [ ] **Step 4: Create the single local gate**

```powershell
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
python -m ruff check app core ui mock_modules tests
python -m pytest -q
python -m app.tools.module_contract_cli validate mock_modules/moisture
python -m app.tools.module_contract_cli validate mock_modules/boiling
python -m app.tools.module_contract_cli validate mock_modules/after_sales
git diff --check
```

- [ ] **Step 5: Run the test and gate, then commit**

Run: `python -m pytest tests/repository/test_repository_hygiene.py -q`
Expected: PASS.

Run: `powershell -ExecutionPolicy Bypass -File scripts/verify_repo.ps1`
Expected: exit code 0.

```powershell
git add .gitignore .gitattributes scripts/verify_repo.ps1 tests/repository/test_repository_hygiene.py
git commit -m "chore: freeze repository quality gate"
```

### Task 2: Add private-repository collaboration files and Windows CI

**Files:**
- Create: `.github/workflows/quality.yml`
- Create: `.github/pull_request_template.md`
- Create: `.github/CODEOWNERS`
- Test: `tests/repository/test_github_configuration.py`

- [ ] **Step 1: Write the failing workflow structure test**

```python
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_quality_workflow_runs_windows_contract_and_test_gates():
    workflow = yaml.safe_load((ROOT / ".github/workflows/quality.yml").read_text(encoding="utf-8"))
    assert workflow["jobs"]["quality"]["runs-on"] == "windows-latest"
    run_steps = "\n".join(step.get("run", "") for step in workflow["jobs"]["quality"]["steps"])
    assert "scripts/verify_repo.ps1" in run_steps
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/repository/test_github_configuration.py -q`
Expected: FAIL because the workflow is absent.

- [ ] **Step 3: Add the Windows workflow**

```yaml
name: quality
on:
  pull_request:
  push:
    branches: [integration, main]
jobs:
  quality:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: pip
      - run: python -m pip install --upgrade pip
      - run: python -m pip install -e ".[dev]"
      - shell: powershell
        run: powershell -ExecutionPolicy Bypass -File scripts/verify_repo.ps1
```

- [ ] **Step 4: Add ownership and PR evidence requirements**

`.github/CODEOWNERS` initially assigns `*`, `/app/`, `/core/`, `/ui/`, `/contracts/`, and `/.github/` to the repository owner. Add module paths after the three GitHub usernames are known. The PR template requires: scope, tests run, contract validation output, screenshots for UI changes, data/security review, and rollback notes.

- [ ] **Step 5: Run, commit, and stop at the external-action checkpoint**

Run: `python -m pytest tests/repository/test_github_configuration.py -q`
Expected: PASS.

```powershell
git add .github tests/repository/test_github_configuration.py
git commit -m "ci: add Windows quality workflow"
```

External checkpoint after user approval and authenticated GitHub access:

```powershell
gh repo create BambooWorkbench --private --source . --remote origin
git push -u origin integration
```

Then configure `main` protection to require PRs, one approval, and the `quality` check; invite the three collaborators; create `module/moisture`, `module/boiling`, and `module/after-sales` from the same frozen `integration` commit. Never run these remote mutations without approval.

### Task 3: Produce and verify the portable Windows build

**Files:**
- Create: `packaging/BambooWorkbench.spec`
- Create: `scripts/build_portable.ps1`
- Create: `scripts/verify_portable.ps1`
- Create: `.github/workflows/package.yml`
- Test: `tests/packaging/test_spec_configuration.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write the failing packaging configuration test**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_spec_bundles_contracts_assets_and_mock_modules():
    spec = (ROOT / "packaging/BambooWorkbench.spec").read_text(encoding="utf-8")
    for path in ("contracts", "assets", "mock_modules"):
        assert path in spec
    assert "console=False" in spec
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/packaging/test_spec_configuration.py -q`
Expected: FAIL because the spec is absent.

- [ ] **Step 3: Add the deterministic PyInstaller spec**

```python
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent.parent
datas = [
    (str(ROOT / "contracts"), "contracts"),
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "mock_modules"), "mock_modules"),
]
a = Analysis(
    [str(ROOT / "app" / "__main__.py")], pathex=[str(ROOT)], datas=datas,
    hiddenimports=collect_submodules("keyring.backends"), excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="BambooWorkbench", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="BambooWorkbench")
```

`SPECPATH` resolves to `packaging/`, so `.parent.parent` is the repository root. Add the approved `.ico` in a later branding commit only after the asset exists; the first reproducible build has no optional icon dependency.

- [ ] **Step 4: Add clean build and packaged smoke scripts**

`scripts/build_portable.ps1` removes only repository-local `build/` and `dist/` after resolving and asserting both paths are descendants of the repository, installs the `packaging` extra, runs `python -m PyInstaller --noconfirm packaging/BambooWorkbench.spec`, then invokes `scripts/verify_portable.ps1`.

`scripts/verify_portable.ps1` asserts:

```powershell
$Root = Split-Path -Parent $PSScriptRoot
$Bundle = Join-Path $Root 'dist\BambooWorkbench'
$Required = @(
  'BambooWorkbench.exe',
  'contracts\schemas\module-manifest.schema.json',
  'mock_modules\moisture\module.json',
  'mock_modules\boiling\module.json',
  'mock_modules\after_sales\module.json'
)
foreach ($Item in $Required) {
  if (-not (Test-Path -LiteralPath (Join-Path $Bundle $Item))) { throw "Missing packaged file: $Item" }
}
& (Join-Path $Bundle 'BambooWorkbench.exe') --smoke-test
if ($LASTEXITCODE -ne 0) { throw "Packaged smoke test failed: $LASTEXITCODE" }
```

Add a `--smoke-test` branch in `app/__main__.py` that initializes paths/database/module registry without showing a window and exits 0 only when all three mock modules are healthy.

- [ ] **Step 5: Add artifact-only package workflow**

```yaml
name: package
on:
  workflow_dispatch:
  push:
    tags: ['v*']
jobs:
  portable:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.12', cache: pip}
      - run: python -m pip install -e ".[dev,packaging]"
      - shell: powershell
        run: powershell -ExecutionPolicy Bypass -File scripts/build_portable.ps1
      - uses: actions/upload-artifact@v4
        with:
          name: BambooWorkbench-windows-portable
          path: dist/BambooWorkbench
```

- [ ] **Step 6: Build, verify, and commit**

Run: `python -m pytest tests/packaging/test_spec_configuration.py -q`
Expected: PASS.

Run: `powershell -ExecutionPolicy Bypass -File scripts/build_portable.ps1`
Expected: `dist\BambooWorkbench\BambooWorkbench.exe` exists and smoke test exits 0.

```powershell
git add packaging/BambooWorkbench.spec scripts/build_portable.ps1 scripts/verify_portable.ps1 .github/workflows/package.yml app/__main__.py pyproject.toml tests/packaging/test_spec_configuration.py
git commit -m "build: create verified portable Windows package"
```

### Task 4: Build an upgrade-safe Windows installer

**Files:**
- Create: `packaging/BambooWorkbench.iss`
- Create: `scripts/build_installer.ps1`
- Create: `scripts/verify_installer.ps1`
- Test: `tests/packaging/test_installer_policy.py`

- [ ] **Step 1: Write the failing data-preservation policy test**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_installer_has_stable_app_id_and_never_deletes_localappdata():
    source = (ROOT / "packaging/BambooWorkbench.iss").read_text(encoding="utf-8")
    assert "AppId={{B4A7CF5E-99C0-4CD9-9A30-B5D574A0F012}" in source
    assert "PrivilegesRequired=lowest" in source
    assert "[UninstallDelete]" not in source
    assert "{localappdata}\\BambooWorkbench" not in source
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/packaging/test_installer_policy.py -q`
Expected: FAIL because the installer script is absent.

- [ ] **Step 3: Add the per-user installer**

```ini
#define MyAppName "竹简工作台"
#define MyAppVersion "0.1.0"
[Setup]
AppId={{B4A7CF5E-99C0-4CD9-9A30-B5D574A0F012}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\BambooWorkbench
DefaultGroupName={#MyAppName}
OutputDir=..\installer-output
OutputBaseFilename=BambooWorkbench-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
[Files]
Source: "..\dist\BambooWorkbench\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\BambooWorkbench.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\BambooWorkbench.exe"; Tasks: desktopicon
[Tasks]
Name: desktopicon; Description: "创建桌面快捷方式"
[Run]
Filename: "{app}\BambooWorkbench.exe"; Description: "启动{#MyAppName}"; Flags: nowait postinstall skipifsilent
```

- [ ] **Step 4: Add build and isolated verification scripts**

`build_installer.ps1` first runs the portable build, locates `ISCC.exe` from the standard Inno Setup 6 locations, and invokes it with `packaging/BambooWorkbench.iss`.

`verify_installer.ps1` performs a silent install into a temporary per-user directory using `/VERYSILENT /DIR=<temp>`, runs `BambooWorkbench.exe --smoke-test`, creates a sentinel file under a temporary `LOCALAPPDATA\BambooWorkbench`, silently uninstalls, and verifies the sentinel remains. It removes only its resolved temporary directories.

- [ ] **Step 5: Run, verify, and commit**

Run: `python -m pytest tests/packaging/test_installer_policy.py -q`
Expected: PASS.

Run: `powershell -ExecutionPolicy Bypass -File scripts/build_installer.ps1`
Expected: `installer-output\BambooWorkbench-Setup-0.1.0.exe` exists.

Run: `powershell -ExecutionPolicy Bypass -File scripts/verify_installer.ps1`
Expected: install, smoke, uninstall, and preservation checks pass.

```powershell
git add packaging/BambooWorkbench.iss scripts/build_installer.ps1 scripts/verify_installer.ps1 tests/packaging/test_installer_policy.py
git commit -m "build: add upgrade-safe Windows installer"
```

### Task 5: Write the code-accurate module handoff kit

**Files:**
- Create: `docs/handoff/module-development-guide.md`
- Create: `docs/handoff/module-acceptance-checklist.md`
- Create: `docs/handoff/github-workflow.md`
- Test: `tests/documentation/test_handoff_docs.py`

- [ ] **Step 1: Write a failing link-and-command audit**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_handoff_guide_references_executable_contract_assets():
    guide = (ROOT / "docs/handoff/module-development-guide.md").read_text(encoding="utf-8")
    required = [
        "contracts/schemas/module-manifest.schema.json",
        "contracts/examples/job.json",
        "mock_modules/moisture",
        "python -m app.tools.module_contract_cli validate",
        "phase=finalize",
        "service_response_file",
    ]
    for item in required:
        assert item in guide
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/documentation/test_handoff_docs.py -q`
Expected: FAIL because the final handoff guide is absent.

- [ ] **Step 3: Write the module developer guide from real artifacts**

The guide must contain these exact sections and no conceptual placeholders:

1. clone private repository and switch to the assigned `module/*` branch;
2. copy the matching mock package into `modules/<module_id>/`;
3. allowed edit scope and forbidden framework/database/key/UI access;
4. every `module.json` field with link to the generated schema;
5. `job.json`, stdout JSONL, `result.json`, `confirmation.json`, and `service-response.json` examples;
6. draft→confirmation/service resolution→finalize sequence;
7. mandatory success, partial, validation-error, confirmation, timeout/cancel, and malformed-input tests;
8. the exact local validator and focused pytest commands;
9. fixture-data anonymization rules;
10. commit/PR procedure and evidence screenshots.

- [ ] **Step 4: Write the acceptance and GitHub checklists**

The acceptance checklist must separate:

- package completeness;
- contract validity;
- module-owned business expectations supplied by its developer;
- framework integration and UI rendering;
- isolation/fault behavior;
- data/security boundaries;
- regression of the other two modules;
- reviewer sign-off and customer acceptance still pending.

The GitHub guide maps:

| Owner | Branch | Primary path |
|---|---|---|
| Framework lead | `integration` | `app/`, `core/`, `ui/`, `contracts/` |
| Moisture member | `module/moisture` | `modules/moisture/` |
| Boiling member | `module/boiling` | `modules/boiling/` |
| After-sales member | `module/after-sales` | `modules/after_sales/` |

It must explain that module branches are not merged directly to `main`; each opens a PR to `integration`, passes `quality`, is accepted with the checklist, and only then enters the combined release PR.

- [ ] **Step 5: Run executable documentation checks and commit**

Run: `python -m pytest tests/documentation/test_handoff_docs.py -q`
Expected: PASS.

Run each validator command copied from the guide against its mock module.
Expected: all three return exit code 0.

```powershell
git add docs/handoff tests/documentation/test_handoff_docs.py
git commit -m "docs: add executable module handoff kit"
```

### Task 6: Create the customer demonstration and acceptance package

**Files:**
- Create: `docs/demo/customer-demo-script.md`
- Create: `docs/demo/customer-acceptance-record.md`
- Create: `docs/release/release-checklist.md`
- Test: `tests/documentation/test_demo_release_docs.py`

- [ ] **Step 1: Write the failing scenario-coverage test**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_demo_covers_three_modules_confirmation_and_offline_boundary():
    script = (ROOT / "docs/demo/customer-demo-script.md").read_text(encoding="utf-8")
    for phrase in ("竹丝水分", "水煮实验", "售后分析", "待确认", "模拟AI", "拒绝联网", "结果目录"):
        assert phrase in script
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/documentation/test_demo_release_docs.py -q`
Expected: FAIL because the demo package is absent.

- [ ] **Step 3: Write a 20-minute executable demo route**

The script uses only bundled anonymized fixtures and fixes the sequence:

1. identify 湖南桃花江竹材科技股份有限公司 and “湖大智竹实践团队” branding;
2. show all three installed mock-module cards and their versions;
3. run a successful moisture task and open its generated workbook/report placeholders;
4. run a boiling task that pauses for confirmation, explain the human boundary, then finalize;
5. run an after-sales task requesting knowledge and mock AI, show priority/source and audit record;
6. decline one outbound request and show local workflow remains available;
7. open history, result trace, logs, settings, and local data directory;
8. demonstrate a module error without crashing the desktop app;
9. state clearly that mock output is not a real quality judgment;
10. collect customer usability, correctness, boundary, and extension feedback.

- [ ] **Step 4: Add acceptance records and the release gate**

`customer-acceptance-record.md` records version, machine, date, attendees, each scenario’s observed result, customer comments, severity, owner, deadline, and customer decision (`可试用 / 修改后复验 / 暂不可用`). It contains no pre-filled acceptance claim.

`release-checklist.md` requires: clean tree; quality workflow green; portable and installer hashes; clean-machine smoke; upgrade preservation; three-module journey; AI refusal; no sensitive sample; docs links; known limitations; approval to tag.

- [ ] **Step 5: Run and commit**

Run: `python -m pytest tests/documentation/test_demo_release_docs.py -q`
Expected: PASS.

```powershell
git add docs/demo docs/release tests/documentation/test_demo_release_docs.py
git commit -m "docs: add customer demo and release acceptance kit"
```

### Task 7: Prepare and publish `v0.1.0`

**Files:**
- Modify: `app/__init__.py`
- Create: `CHANGELOG.md`
- Modify: `README.md`
- Test: `tests/repository/test_release_metadata.py`

- [ ] **Step 1: Write the failing version-consistency test**

```python
from pathlib import Path
from app import __version__

ROOT = Path(__file__).resolve().parents[2]


def test_release_metadata_uses_v010_everywhere():
    assert __version__ == "0.1.0"
    assert "## [0.1.0]" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "竹简工作台" in (ROOT / "README.md").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/repository/test_release_metadata.py -q`
Expected: FAIL until release metadata is synchronized.

- [ ] **Step 3: Add release metadata and limitations**

Set `__version__ = "0.1.0"`. `CHANGELOG.md` lists the unified desktop shell, three mock modules, contract SDK, confirmation flow, local history, mock AI/knowledge services, diagnostics, portable build, installer, and documentation. README must clearly label this version as the empty framework: real moisture, boiling, and after-sales business algorithms are not included.

- [ ] **Step 4: Run all local release checks**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_repo.ps1
powershell -ExecutionPolicy Bypass -File scripts/build_installer.ps1
powershell -ExecutionPolicy Bypass -File scripts/verify_installer.ps1
git status --short
```

Expected: all scripts exit 0 and `git status --short` shows only the intentional release-metadata changes before commit.

- [ ] **Step 5: Commit release metadata**

```powershell
git add app/__init__.py CHANGELOG.md README.md tests/repository/test_release_metadata.py
git commit -m "chore: prepare BambooWorkbench v0.1.0"
```

- [ ] **Step 6: Stop for user approval before remote publication**

After the user confirms the private repository, branch protections, green CI, clean-machine installer result, and release checklist:

```powershell
git push origin integration
gh pr create --base main --head integration --title "Release BambooWorkbench v0.1.0" --body-file docs/release/release-checklist.md
```

Merge only after required review/checks. Then:

```powershell
git switch main
git pull --ff-only origin main
git tag -a v0.1.0 -m "BambooWorkbench v0.1.0"
git push origin v0.1.0
gh release create v0.1.0 installer-output/BambooWorkbench-Setup-0.1.0.exe --title "竹简工作台 v0.1.0" --notes-file CHANGELOG.md
```

Expected: private GitHub release `v0.1.0` contains the verified installer. These commands are external mutations and must not run without explicit approval.

## Plan 4 Completion Gate

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_repo.ps1
powershell -ExecutionPolicy Bypass -File scripts/build_portable.ps1
powershell -ExecutionPolicy Bypass -File scripts/build_installer.ps1
powershell -ExecutionPolicy Bypass -File scripts/verify_installer.ps1
git diff --check
git status --short
```

Expected:

- repository tests, contract tests, app tests, and UI smoke tests pass on Windows;
- the portable app and installer pass smoke checks without Python installed;
- upgrade/uninstall checks preserve local user data;
- handoff commands work exactly as written against all three mock modules;
- demo and acceptance records distinguish mock behavior from real quality decisions;
- remote repository/release actions remain paused until their explicit user-approval checkpoints.
