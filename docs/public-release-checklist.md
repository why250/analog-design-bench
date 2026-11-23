# Public release check

This repository is developed in a checkout that also holds private PDK and
customer material.  Only a subset is intended for a public remote.  Run the
checks below before every push to a public repository, and before exporting a
snapshot or archive.

## Before every push

1. Review what Git would publish:

   ```powershell
   git status --short
   ```

2. Scan the publishable working-tree set (tracked files plus untracked files
   that are not ignored):

   ```powershell
   python scripts/check_public_release.py --check-ignores
   ```

3. Scan the history reachable from local branches and remote-tracking refs:

   ```powershell
   python scripts/check_public_release.py --history
   ```

4. For a deeper local-only check (stash and tool checkpoint refs):

   ```powershell
   python scripts/check_public_release.py --history --all-refs
   ```

5. Fix every high/medium finding, or record a narrow exception with a reason in
   the ignored `.local/release-policy.toml`.  Do not put a real private term in a
   tracked file just to make the checker pass.

6. Stage the intended files, review the staged set with `git status`, then let
   the pre-commit hook scan only the index:

   ```powershell
   python scripts/check_public_release.py --staged
   ```

7. Push only the intended branch:

   ```powershell
   git push origin <branch>
   ```

Never use `git push --mirror`, `git bundle --all`, or `git clone --mirror`
for a public remote.  Local checkpoint refs and `refs/stash` can contain private
material.  The checker prints a `local-only-refs` note when such refs exist.
`git push --all` publishes every local branch, so use an explicit branch name.

Commit author names, email addresses and commit messages are part of the
published history.  Use a GitHub noreply address if a personal email should not
be exposed, and keep confidential details out of commit messages.

## Policy file

The tracked script contains only generic detection rules.  Put project-specific
forbidden terms in the ignored `.local/release-policy.toml`:

```toml
[scan]
ignore_paths = [".local/", ".mcp.json", ".codex/config.toml", ".cursor/mcp.json", "results/"]

[[sensitive]]
label = "private-pdk-kit"
pattern = "(?i)EXAMPLE_PDK_NAME"
severity = "high"

[[allow]]
path_glob = "tests/fixtures/**"
rules = ["credential-assignment"]
```

`pattern` is a Python regular expression.  `path_glob` uses `pathlib`
semantics, so `**` matches across directories.  An allow entry should name one
rule and one narrow path; it should not disable a whole category.

The example policy is also available as
[templates/release-policy.example.toml](templates/release-policy.example.toml).

## Never publish

- API keys, access tokens, passwords, cookies, session identifiers, `.env`
  files, private keys, SSH keys and credential files.
- Vendor license files and their contents: `license.dat`, `*.lic`, lines with
  `SERVER`, `VENDOR`, `INCREMENT` or `USE_SERVER`, license-server names and host
  identifiers.
- Company PDK files, technology files, device models, DRC/LVS decks, PCell
  libraries and PDK-derived dimensions or model parameters.
- Protected design data, customer names, unreleased specifications, internal
  hostnames or IP addresses, local user names and absolute checkout paths.
- Links to private tasks, workspaces or evidence that are excluded from the
  public set.
- Internal model-relay endpoints, cloud credentials and private evaluation
  traces.

## Safe to publish

- Open PDK content such as the pinned SKY130 tasks and their results, when the
  task itself declares them public.
- Open-source license texts, including the Apache-2.0 and CC BY-NC 4.0 files in
  `LICENSES/` and the retained MIT notice for an open toolkit dependency.
- Generic, parameterized workflows, templates and tooling.
- Synthetic or ideal-only results that contain no PDK-derived values and no
  private task references.

Vendor license files are not the same as open-source license texts.  Keep the
former out of Git; keep the latter when the license requires redistribution.

## Cloud LLM and evaluation data

- Public benchmark material may use public model APIs.
- Company PDK or protected design data may use only approved company endpoints
  and relays, under the company's data-security rules.
- Keep API keys, relay URLs and model configuration in environment variables or
  ignored local files.  Do not put them in task packages, public prompts or
  tracked evaluation records.
- Blind solver input must not contain operator-only instructions, hidden
  verifiers, reference answers or private results.

## If a secret or protected item was committed

1. Revoke or rotate the credential first; assume a public commit is already
   disclosed.
2. Remove it from the working tree and add the file or pattern to `.gitignore`.
3. Rewrite history across every affected branch with `git filter-repo` or BFG.
4. Coordinate any force-push with collaborators.  A public commit can survive
   in forks, caches and clones even after a rewrite.
5. Follow the company's security-incident process for PDK or protected design
   data.  A history rewrite does not undo the disclosure.
6. Re-run `python scripts/check_public_release.py --history` on a fresh clone.

## Pre-commit hook

Enable the tracked hook once per clone:

```powershell
git config core.hooksPath .githooks
```

The hook runs `python scripts/check_public_release.py --staged` and fails closed
when Python is unavailable.  It is a convenience, not a substitute for the full
working-tree and history checks.  `git commit --no-verify` bypasses it; do not
use that on a public branch.

## CI backstop

`.github/workflows/public-release-check.yml` runs the generic scan on pushes and
pull requests.  CI cannot see the ignored policy file, so project-specific terms
are checked only in the local run.  Keep the local `--check-ignores --history`
run as the authoritative gate.

## Limits

- Pattern matching cannot prove the absence of proprietary content.  Review new
  task and workspace data manually before adding it to the public set.
- `.oa`, `.oalib` and other binary files are scanned as printable strings only.
  Review new native PDK, technology and layout files manually.
- History scanning covers branches and remote-tracking refs by default.
  `--all-refs` includes local stash and tool checkpoint refs.
- The checker does not upload anything and does not contact external services.
