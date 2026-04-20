# coding: utf-8
"""
git_client.py
Fetches branch diffs from an Oracle Visual Builder Studio Git repository.

Oracle VBS hosts standard Git repos accessible via HTTPS with HTTP Basic Auth
using (username, PAT).  This module:
  1. Authenticates the clone/fetch URL by embedding credentials.
  2. Uses GitPython to produce a unified diff between two branches.
  3. Returns structured data (diff text, changed file list, commit metadata).
"""

import os
import tempfile
import shutil
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urlparse, urlunparse, quote

import git  # GitPython

from config import GIT_PAT, GIT_USERNAME
from logger import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ChangedFile:
    """Represents a single file changed between two branches."""
    path: str
    change_type: str          # "A"dded, "D"eleted, "M"odified, "R"enamed
    diff_text: str            # Unified diff for this file
    source_content: str = "" # Full content on the target (prod) branch
    target_content: str = "" # Full content on the source (feature) branch


@dataclass
class PRMetadata:
    """High-level metadata about the merge request."""
    source_branch: str
    target_branch: str
    repo_url: str
    pr_id: Optional[str] = None
    title: Optional[str] = None
    commit_count: int = 0
    commits: List[str] = field(default_factory=list)  # short SHA list


@dataclass
class DiffResult:
    """Full result of comparing two branches."""
    metadata: PRMetadata
    full_diff: str             # Entire unified diff as a single string
    changed_files: List[ChangedFile] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helper: embed PAT into a Git HTTPS URL
# ---------------------------------------------------------------------------

def _authenticated_url(repo_url: str, username: str, pat: str) -> str:
    """
    Embed the username and PAT into the HTTPS clone URL so GitPython
    can authenticate without an interactive prompt.

    Handles two tricky cases:
      1. The input URL may already contain embedded credentials (stripped first).
      2. Email usernames containing '@' are percent-encoded to '%40' so git
         does not misinterpret them as a host delimiter.

    Example:
        username = "me@example.com", pat = "abc"
        https://vbs.oracle.com/org/repo.git
        → https://me%40example.com:abc@vbs.oracle.com/org/repo.git
    """
    parsed = urlparse(repo_url)

    # ── Build clean host (no userinfo, keep port if present) ──────────────
    host = parsed.hostname   # lowercase hostname only, no userinfo
    if parsed.port:
        host = f"{host}:{parsed.port}"

    # ── Percent-encode special characters in username and PAT ─────────────
    # '@' in an email must become '%40', ':' must become '%3A', etc.
    safe_username = quote(username, safe="")
    safe_pat      = quote(pat, safe="")

    authed_netloc = f"{safe_username}:{safe_pat}@{host}"
    return urlunparse(parsed._replace(netloc=authed_netloc))


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------

class OracleVBSGitClient:
    """
    Connects to an Oracle Visual Builder Studio Git repository and produces
    a diff between two branches.

    Usage::

        client = OracleVBSGitClient(
            repo_url="https://vbs.example.com/org/project.git",
        )
        result = client.get_diff("feature/my-feature", "main")
    """

    def __init__(
        self,
        repo_url: str,
        pat: str = GIT_PAT,
        username: str = GIT_USERNAME,
    ):
        log.info("Initialising OracleVBSGitClient for repo: %s", repo_url)

        if not pat:
            log.critical(
                "GIT_PAT is not set.\n"
                "  WHAT WENT WRONG : The Personal Access Token (PAT) is missing.\n"
                "  WHAT TO DO      : Open your .env file and set GIT_PAT=<your_token>. "
                "Generate a PAT from Oracle VBS → User Preferences → Personal Access Tokens."
            )
            raise ValueError("GIT_PAT is not set. Add it to your .env file.")

        if not username:
            log.critical(
                "GIT_USERNAME is not set.\n"
                "  WHAT WENT WRONG : The VBS username/email is missing.\n"
                "  WHAT TO DO      : Open your .env file and set GIT_USERNAME=<your_vbs_email>."
            )
            raise ValueError("GIT_USERNAME is not set. Add it to your .env file.")

        self.repo_url = repo_url
        self._auth_url = _authenticated_url(repo_url, username, pat)
        self._work_dir: Optional[str] = None
        self._repo: Optional[git.Repo] = None

        log.debug(
            "Authenticated URL constructed (credentials redacted): https://****:****@%s…",
            urlparse(repo_url).hostname,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_diff(self, source_branch: str, target_branch: str,
                 pr_id: Optional[str] = None) -> DiffResult:
        """
        Clone the repo and compute a unified diff between *source_branch* and
        *target_branch*.

        Args:
            source_branch: The feature/MR branch.
            target_branch: The production/base branch.
            pr_id:         Optional merge-request ID for metadata.

        Returns:
            A :class:`DiffResult` with full diff text and per-file details.
        """
        log.info(
            "Computing diff: %s → %s%s",
            source_branch, target_branch,
            f" (PR #{pr_id})" if pr_id else "",
        )
        try:
            self._clone()
            return self._compute_diff(source_branch, target_branch, pr_id)
        except Exception:
            raise
        finally:
            self._cleanup()

    def get_single_branch(self, branch: str) -> DiffResult:
        """
        Clone the repo and extract all files from a single branch, returning
        them as a DiffResult where all files are marked as 'A' (Added).
        """
        log.info("Extracting single branch: %s", branch)
        try:
            self._clone()
            return self._compute_single_branch(branch)
        except Exception:
            raise
        finally:
            self._cleanup()

    def get_remote_branches(self) -> List[str]:
        """
        Fetch a list of all remote branch names without cloning via git ls-remote.
        """
        import subprocess
        log.info("Fetching remote branches for %s", self.repo_url)
        # We can use git ls-remote on the authenticated URL
        try:
            output = subprocess.check_output(
                ["git", "ls-remote", "--heads", self._auth_url],
                stderr=subprocess.STDOUT,
                text=True
            )
            branches = []
            for line in output.splitlines():
                if not line.strip(): continue
                # Example line: 1234abcd... refs/heads/main
                parts = line.split()
                if len(parts) >= 2 and parts[1].startswith("refs/heads/"):
                    branches.append(parts[1].replace("refs/heads/", "", 1))
            return branches
        except subprocess.CalledProcessError as exc:
            log.error("Failed to fetch remote branches: %s\n%s", exc, exc.output)
            raise ValueError(f"Could not fetch branches from {self.repo_url}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _clone(self) -> None:
        """Clone the repository into a temporary directory (all remote branches)."""
        self._work_dir = tempfile.mkdtemp(prefix="code_review_")
        log.info("Cloning repository into temporary directory: %s", self._work_dir)
        log.debug("Clone options: no_single_branch=True, no-tags")

        try:
            git.Repo.clone_from(
                self._auth_url,
                self._work_dir,
                no_single_branch=True,
                multi_options=["--no-tags"],
            )
            self._repo = git.Repo(self._work_dir)
            log.info("Repository cloned successfully.")

        except git.exc.GitCommandError as exc:
            stderr = str(exc.stderr).strip()
            if "Authentication failed" in stderr or "could not read Username" in stderr:
                log.error(
                    "Git clone failed due to authentication error.\n"
                    "  WHAT WENT WRONG : Git rejected the credentials (username + PAT).\n"
                    "  WHAT TO DO      : \n"
                    "    1. Verify GIT_USERNAME in .env is your exact VBS login email.\n"
                    "    2. Verify GIT_PAT in .env is a valid, unexpired token with read access.\n"
                    "    3. Generate a new PAT at: Oracle VBS → User Preferences → "
                    "Personal Access Tokens → Create Token."
                )
            elif "Repository not found" in stderr or "not found" in stderr.lower():
                log.error(
                    "Git clone failed — repository not found.\n"
                    "  WHAT WENT WRONG : The repository URL does not exist or is inaccessible.\n"
                    "  WHAT TO DO      : \n"
                    "    1. Double-check the --repo URL in your command.\n"
                    "    2. Ensure the PAT has at least Read access to the repository.\n"
                    "    3. Confirm the project is not archived or deleted in Oracle VBS."
                )
            elif "unable to access" in stderr:
                log.error(
                    "Git clone failed — could not reach the server.\n"
                    "  WHAT WENT WRONG : Network error or the VBS instance is unreachable.\n"
                    "  STDERR          : %s\n"
                    "  WHAT TO DO      : \n"
                    "    1. Check your internet / VPN connection.\n"
                    "    2. Verify the VBS instance URL is correct.\n"
                    "    3. Try opening the URL in a browser to confirm it responds.",
                    stderr,
                )
            else:
                log.error(
                    "Git clone failed.\n"
                    "  WHAT WENT WRONG : %s\n"
                    "  STDERR          : %s\n"
                    "  WHAT TO DO      : Check the full error above. Common causes: wrong URL, "
                    "expired PAT, or network issues.",
                    exc, stderr,
                )
            raise

    def _compute_diff(
        self,
        source_branch: str,
        target_branch: str,
        pr_id: Optional[str],
    ) -> DiffResult:
        """Produce a DiffResult by comparing the two branch tips."""
        repo = self._repo

        # List available remote refs for debugging
        available_refs = [r.name for r in repo.remotes.origin.refs]
        log.debug("Available remote refs: %s", available_refs)

        def resolve_commit(branch: str):
            """Resolve a branch name to a commit using remote-tracking refs."""
            for ref in [f"origin/{branch}", branch]:
                try:
                    commit = repo.commit(ref)
                    log.debug("Resolved '%s' → commit %s via ref '%s'.", branch, commit.hexsha[:8], ref)
                    return commit
                except Exception:
                    continue
            log.error(
                "Branch '%s' not found in repository.\n"
                "  WHAT WENT WRONG : The branch name does not match any remote ref.\n"
                "  AVAILABLE REFS  : %s\n"
                "  WHAT TO DO      : \n"
                "    1. Check spelling — branch names are case-sensitive.\n"
                "    2. Confirm the branch exists in Oracle VBS under the repository's "
                "Branches tab.",
                branch, available_refs,
            )
            raise ValueError(
                f"Branch '{branch}' not found. Available: {available_refs}"
            )

        source_commit = resolve_commit(source_branch)
        target_commit = resolve_commit(target_branch)

        log.info(
            "Comparing commits: %s (%s) → %s (%s)",
            target_branch, target_commit.hexsha[:8],
            source_branch, source_commit.hexsha[:8],
        )

        # Full unified diff (all files combined)
        full_diff_text: str = repo.git.diff(
            target_commit.hexsha,
            source_commit.hexsha,
            unified=5,
        )

        if not full_diff_text.strip():
            log.warning(
                "Diff is empty — the two branches appear identical.\n"
                "  WHAT WENT WRONG : No differences detected between '%s' and '%s'.\n"
                "  WHAT TO DO      : Verify the correct branches were specified. "
                "If the branches were recently synced, there may genuinely be nothing to review.",
                source_branch, target_branch,
            )

        # Per-file diffs
        diffs = target_commit.diff(source_commit)
        changed_files: List[ChangedFile] = []

        for d in diffs:
            file_path = d.b_path or d.a_path
            try:
                file_diff = repo.git.diff(
                    target_commit.hexsha,
                    source_commit.hexsha,
                    "--",
                    file_path,
                    unified=5,
                )
                source_content = _read_blob(d.a_blob)
                target_content = _read_blob(d.b_blob)

                changed_files.append(ChangedFile(
                    path=file_path,
                    change_type=d.change_type,
                    diff_text=file_diff,
                    source_content=source_content,
                    target_content=target_content,
                ))
                log.debug("Processed file: [%s] %s", d.change_type, file_path)

            except Exception as exc:
                log.warning(
                    "Skipping file '%s' — could not read diff.\n"
                    "  REASON : %s\n"
                    "  NOTE   : This usually happens for binary files or files with "
                    "encoding issues. Review this file manually.",
                    file_path, exc,
                )
                continue

        # Commit metadata — use hex SHAs since local branch refs may not exist
        commits_between = list(
            repo.iter_commits(f"{target_commit.hexsha}..{source_commit.hexsha}")
        )
        commit_shas = [c.hexsha[:8] for c in commits_between]

        log.info(
            "Diff complete → %d file(s) changed, %d commit(s), %d diff line(s).",
            len(changed_files), len(commits_between), len(full_diff_text.splitlines()),
        )

        metadata = PRMetadata(
            source_branch=source_branch,
            target_branch=target_branch,
            repo_url=self.repo_url,
            pr_id=pr_id,
            commit_count=len(commits_between),
            commits=commit_shas,
        )

        return DiffResult(
            metadata=metadata,
            full_diff=full_diff_text,
            changed_files=changed_files,
        )

    def _compute_single_branch(self, branch: str) -> DiffResult:
        """Produce a DiffResult for a single branch, treating all files as added."""
        repo = self._repo
        available_refs = [r.name for r in repo.remotes.origin.refs]

        def resolve_commit(branch_name: str):
            for ref in [f"origin/{branch_name}", branch_name]:
                try:
                    return repo.commit(ref)
                except Exception:
                    continue
            raise ValueError(f"Branch '{branch_name}' not found. Available: {available_refs}")

        commit = resolve_commit(branch)
        
        # Build "diff" from scratch
        changed_files: List[ChangedFile] = []
        full_diff_lines = []
        
        # Traverse the tree for all blobs
        for item in commit.tree.traverse():
            if item.type == "blob":
                content = _read_blob(item)
                file_path = item.path
                
                # Mock a diff text just in case rules look for it
                content_lines = content.splitlines()
                mock_diff = [f"--- /dev/null", f"+++ b/{file_path}", f"@@ -0,0 +1,{len(content_lines)} @@"]
                for line in content_lines:
                    mock_diff.append(f"+{line}")
                diff_text = "\n".join(mock_diff)
                
                full_diff_lines.append(diff_text)
                
                changed_files.append(ChangedFile(
                    path=file_path,
                    change_type="A",
                    diff_text=diff_text,
                    source_content="",
                    target_content=content,
                ))

        metadata = PRMetadata(
            source_branch=branch,
            target_branch="",
            repo_url=self.repo_url,
            pr_id=None,
            commit_count=1,
            commits=[commit.hexsha[:8]],
        )

        return DiffResult(
            metadata=metadata,
            full_diff="\n".join(full_diff_lines),
            changed_files=changed_files,
        )

    def _cleanup(self) -> None:
        """Remove the temporary clone directory."""
        if self._work_dir and os.path.exists(self._work_dir):
            log.debug("Cleaning up temporary directory: %s", self._work_dir)
            shutil.rmtree(self._work_dir, ignore_errors=True)
        self._work_dir = None
        self._repo = None


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _read_blob(blob) -> str:
    """Safely read file content from a git blob; returns empty string on failure."""
    if blob is None:
        return ""
    try:
        raw = blob.data_stream.read()
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return ""
