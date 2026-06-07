#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import socket
import stat
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


LOG = logging.getLogger("github-backup")
GITHUB_API_URL = "https://api.github.com"
TRANSIENT_HTTP_STATUSES = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class Config:
    token: str
    data_dir: Path
    repos_dir: Path
    wikis_dir: Path
    manifests_dir: Path
    home_dir: Path
    repo_affiliation: str
    backup_wikis: bool
    backup_lfs: bool
    http_timeout_seconds: int
    command_timeout_seconds: int
    max_attempts: int
    retry_base_delay_seconds: int
    manifest_snapshot_retention: int


@dataclass(frozen=True)
class GitHubRepository:
    full_name: str
    clone_url: str
    has_wiki: bool
    private: bool
    fork: bool
    archived: bool
    disabled: bool
    default_branch: str | None
    pushed_at: str | None
    updated_at: str | None


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass
class RunSummary:
    repos_discovered: int = 0
    repos_mirrored: int = 0
    repos_failed: int = 0
    repos_disabled: int = 0
    wikis_mirrored: int = 0
    wikis_skipped: int = 0
    wikis_failed: int = 0
    failures: list[str] = field(default_factory=list)


class BackupError(RuntimeError):
    pass


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    if value.lower() in {"1", "true", "yes", "on"}:
        return True
    if value.lower() in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return parsed


def load_config() -> Config:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise ValueError("GITHUB_TOKEN is required")

    data_dir = Path(os.environ.get("DATA_DIR", "/data"))
    home_dir = Path(os.environ.get("HOME", "/tmp/home"))

    return Config(
        token=token,
        data_dir=data_dir,
        repos_dir=Path(os.environ.get("REPOS_DIR", str(data_dir / "repositories"))),
        wikis_dir=Path(os.environ.get("WIKIS_DIR", str(data_dir / "wikis"))),
        manifests_dir=Path(
            os.environ.get("MANIFESTS_DIR", str(data_dir / "manifests"))
        ),
        home_dir=home_dir,
        repo_affiliation=os.environ.get(
            "REPO_AFFILIATION", "owner,collaborator,organization_member"
        ),
        backup_wikis=env_bool("BACKUP_WIKIS", True),
        backup_lfs=env_bool("BACKUP_LFS", True),
        http_timeout_seconds=env_int("HTTP_TIMEOUT_SECONDS", 30),
        command_timeout_seconds=env_int("COMMAND_TIMEOUT_SECONDS", 3600),
        max_attempts=env_int("MAX_ATTEMPTS", 3),
        retry_base_delay_seconds=env_int("RETRY_BASE_DELAY_SECONDS", 5),
        manifest_snapshot_retention=env_int("MANIFEST_SNAPSHOT_RETENTION", 30),
    )


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )


def prepare_filesystem(config: Config) -> None:
    for path in (
        config.repos_dir,
        config.wikis_dir,
        config.manifests_dir,
        config.home_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)

    netrc_path = config.home_dir / ".netrc"
    netrc_path.write_text(
        "\n".join(
            [
                "machine github.com",
                "  login x-access-token",
                f"  password {config.token}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    netrc_path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def sleep_before_retry(config: Config, attempt: int) -> None:
    delay = config.retry_base_delay_seconds * (3 ** (attempt - 1))
    LOG.warning("Retrying after %s seconds", delay)
    time.sleep(delay)


def github_request(
    config: Config, url: str
) -> tuple[list[dict[str, object]], str | None]:
    for attempt in range(1, config.max_attempts + 1):
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {config.token}",
                "User-Agent": "homeserver-github-source-mirror",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

        try:
            with urllib.request.urlopen(
                request, timeout=config.http_timeout_seconds
            ) as response:
                body = response.read()
                if response.status < 200 or response.status >= 300:
                    raise BackupError(
                        f"GitHub API returned status {response.status}: url={url}"
                    )
                next_url = parse_next_link(response.headers.get("Link"))
                return parse_github_response(body, url), next_url
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            if exc.code in TRANSIENT_HTTP_STATUSES and attempt < config.max_attempts:
                LOG.warning(
                    "GitHub API transient failure: status=%s attempt=%s/%s url=%s",
                    exc.code,
                    attempt,
                    config.max_attempts,
                    url,
                )
                sleep_before_retry(config, attempt)
                continue
            raise BackupError(
                f"GitHub API request failed: status={exc.code} url={url} "
                f"body={error_body}"
            ) from exc
        except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
            if attempt < config.max_attempts:
                LOG.warning(
                    "GitHub API transient failure: attempt=%s/%s url=%s reason=%s",
                    attempt,
                    config.max_attempts,
                    url,
                    exc,
                )
                sleep_before_retry(config, attempt)
                continue
            raise BackupError(
                f"GitHub API request failed: url={url} reason={exc}"
            ) from exc

    raise BackupError(f"GitHub API request failed after retries: url={url}")


def parse_github_response(body: bytes, url: str) -> list[dict[str, object]]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise BackupError(f"GitHub API returned invalid JSON: url={url}") from exc

    if not isinstance(payload, list):
        raise BackupError(f"GitHub API returned unexpected payload shape: url={url}")

    return payload


def parse_next_link(link_header: str | None) -> str | None:
    if not link_header:
        return None

    for part in link_header.split(","):
        match = re.match(r'\s*<([^>]+)>;\s*rel="([^"]+)"\s*', part)
        if match and match.group(2) == "next":
            return match.group(1)

    return None


def list_repositories(config: Config) -> list[GitHubRepository]:
    query = urllib.parse.urlencode(
        {
            "visibility": "all",
            "affiliation": config.repo_affiliation,
            "per_page": "100",
        }
    )
    next_url: str | None = f"{GITHUB_API_URL}/user/repos?{query}"
    repositories: list[GitHubRepository] = []

    while next_url:
        payload, next_url = github_request(config, next_url)
        repositories.extend(parse_repository(item) for item in payload)

    if not repositories:
        raise BackupError("GitHub repository listing returned no repositories")

    return repositories


def parse_repository(item: dict[str, object]) -> GitHubRepository:
    try:
        full_name = item["full_name"]
        clone_url = item["clone_url"]
    except KeyError as exc:
        raise BackupError(f"GitHub repository payload is missing key: {exc}") from exc

    if not isinstance(full_name, str) or not full_name:
        raise BackupError("GitHub repository payload has invalid full_name")
    if not isinstance(clone_url, str) or not clone_url:
        raise BackupError(f"Repository {full_name} has invalid clone_url")

    return GitHubRepository(
        full_name=full_name,
        clone_url=clone_url,
        has_wiki=bool(item.get("has_wiki", False)),
        private=bool(item.get("private", False)),
        fork=bool(item.get("fork", False)),
        archived=bool(item.get("archived", False)),
        disabled=bool(item.get("disabled", False)),
        default_branch=optional_string(item.get("default_branch")),
        pushed_at=optional_string(item.get("pushed_at")),
        updated_at=optional_string(item.get("updated_at")),
    )


def optional_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def write_discovery_manifest(
    config: Config, repositories: Iterable[GitHubRepository]
) -> None:
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    tmp_path = config.manifests_dir / "discovered_repositories.jsonl.tmp"
    current_path = config.manifests_dir / "discovered_repositories.jsonl"
    snapshot_path = config.manifests_dir / f"discovered_repositories-{timestamp}.jsonl"

    with tmp_path.open("w", encoding="utf-8") as manifest:
        for repo in repositories:
            manifest.write(json.dumps(asdict(repo), sort_keys=True))
            manifest.write("\n")

    snapshot_path.write_bytes(tmp_path.read_bytes())
    tmp_path.replace(current_path)
    prune_manifest_snapshots(config)


def prune_manifest_snapshots(config: Config) -> None:
    snapshots = sorted(
        config.manifests_dir.glob("discovered_repositories-*.jsonl"),
        key=lambda path: path.name,
        reverse=True,
    )
    for snapshot in snapshots[config.manifest_snapshot_retention :]:
        snapshot.unlink()


def write_run_summary(config: Config, summary: RunSummary) -> None:
    tmp_path = config.manifests_dir / "last_run_summary.json.tmp"
    current_path = config.manifests_dir / "last_run_summary.json"
    tmp_path.write_text(
        json.dumps(asdict(summary), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(current_path)


def run_command(
    config: Config,
    command: list[str],
    *,
    redactions: Iterable[str],
    retry_on_failure: bool = True,
) -> CommandResult:
    redacted = redact_command(command, redactions)
    max_attempts = config.max_attempts if retry_on_failure else 1
    last_result: CommandResult | None = None

    for attempt in range(1, max_attempts + 1):
        LOG.debug("Running command: %s", " ".join(redacted))
        try:
            completed = subprocess.run(
                command,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=config.command_timeout_seconds,
                env=git_env(),
            )
            result = CommandResult(
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        except subprocess.TimeoutExpired as exc:
            result = CommandResult(
                returncode=124,
                stdout=exc.stdout or "",
                stderr=(
                    f"command timed out after {config.command_timeout_seconds} "
                    f"seconds: {' '.join(redacted)}"
                ),
            )

        if result.returncode == 0:
            return result

        last_result = result
        if attempt < max_attempts:
            LOG.warning(
                "Command failed: attempt=%s/%s command=%s",
                attempt,
                max_attempts,
                " ".join(redacted),
            )
            sleep_before_retry(config, attempt)

    if last_result is None:
        raise BackupError(f"Command did not run: {' '.join(redacted)}")
    return last_result


def git_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    return env


def redact_command(command: Iterable[str], redactions: Iterable[str]) -> list[str]:
    values = [value for value in redactions if value]
    redacted: list[str] = []

    for part in command:
        cleaned = part
        for value in values:
            cleaned = cleaned.replace(value, "<redacted>")
        redacted.append(cleaned)

    return redacted


def ensure_success(command_name: str, result: CommandResult) -> None:
    if result.returncode == 0:
        return

    details = result.stderr.strip() or result.stdout.strip()
    if details:
        raise BackupError(f"{command_name} failed: {details}")
    raise BackupError(f"{command_name} failed with exit code {result.returncode}")


def is_valid_bare_repo(config: Config, target: Path) -> bool:
    if not target.is_dir():
        return False

    result = run_command(
        config,
        ["git", "-C", str(target), "rev-parse", "--is-bare-repository"],
        redactions=[],
        retry_on_failure=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def update_mirror(config: Config, name: str, url: str, target: Path) -> None:
    if target.exists():
        if not is_valid_bare_repo(config, target):
            raise BackupError(
                f"Existing path for {name} is not a valid bare git repository: {target}"
            )

        LOG.info("Updating %s", name)
        result = run_command(
            config,
            ["git", "-C", str(target), "remote", "set-url", "origin", url],
            redactions=[config.token],
        )
        ensure_success(f"git remote set-url for {name}", result)

        result = run_command(
            config,
            ["git", "-C", str(target), "remote", "update", "--prune"],
            redactions=[config.token],
        )
        ensure_success(f"git remote update for {name}", result)
    else:
        clone_mirror(config, name, url, target)

    if config.backup_lfs:
        result = run_command(
            config,
            ["git", "-C", str(target), "lfs", "fetch", "--all", "origin"],
            redactions=[config.token],
        )
        ensure_success(f"git lfs fetch for {name}", result)


def clone_mirror(config: Config, name: str, url: str, target: Path) -> None:
    LOG.info("Cloning %s", name)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_target = target.with_name(f".{target.name}.tmp-{os.getpid()}")
    last_result: CommandResult | None = None

    for attempt in range(1, config.max_attempts + 1):
        if temp_target.exists():
            shutil.rmtree(temp_target)

        result = run_command(
            config,
            ["git", "clone", "--mirror", url, str(temp_target)],
            redactions=[config.token],
            retry_on_failure=False,
        )
        if result.returncode == 0:
            break

        last_result = result
        if attempt < config.max_attempts:
            LOG.warning(
                "Clone failed: attempt=%s/%s repository=%s",
                attempt,
                config.max_attempts,
                name,
            )
            sleep_before_retry(config, attempt)
    else:
        if last_result is None:
            raise BackupError(f"git clone --mirror for {name} did not run")
        ensure_success(f"git clone --mirror for {name}", last_result)

    try:
        if not is_valid_bare_repo(config, temp_target):
            raise BackupError(
                f"Temporary clone for {name} is not a valid bare repository"
            )

        temp_target.rename(target)
    except Exception:
        if temp_target.exists():
            shutil.rmtree(temp_target)
        raise


def wiki_url(repo_url: str) -> str:
    if repo_url.endswith(".git"):
        return f"{repo_url[:-4]}.wiki.git"
    return f"{repo_url}.wiki.git"


def backup_wiki(config: Config, repo: GitHubRepository, summary: RunSummary) -> None:
    name = f"{repo.full_name}.wiki"
    url = wiki_url(repo.clone_url)
    target = config.wikis_dir / f"{name}.git"

    probe = run_command(
        config,
        ["git", "ls-remote", "--exit-code", url],
        redactions=[config.token],
        retry_on_failure=False,
    )
    if probe.returncode != 0:
        if is_missing_or_empty_wiki(probe):
            LOG.info("Skipping %s; wiki repository is empty or unavailable", name)
            summary.wikis_skipped += 1
            return
        ensure_success(f"git ls-remote for {name}", probe)

    update_mirror(config, name, url, target)
    summary.wikis_mirrored += 1


def is_missing_or_empty_wiki(result: CommandResult) -> bool:
    details = f"{result.stdout}\n{result.stderr}".lower()
    return result.returncode == 2 or any(
        marker in details
        for marker in (
            "repository not found",
            "not found",
            "does not appear to be a git repository",
            "could not read from remote repository",
        )
    )


def backup_repositories(
    config: Config, repositories: list[GitHubRepository]
) -> RunSummary:
    summary = RunSummary(repos_discovered=len(repositories))

    for repo in repositories:
        if repo.disabled:
            LOG.info("Skipping disabled repository %s", repo.full_name)
            summary.repos_disabled += 1
            continue

        try:
            update_mirror(
                config=config,
                name=repo.full_name,
                url=repo.clone_url,
                target=config.repos_dir / f"{repo.full_name}.git",
            )
            summary.repos_mirrored += 1
        except BackupError as exc:
            summary.repos_failed += 1
            summary.failures.append(f"{repo.full_name}: {exc}")
            LOG.error("Repository backup failed: %s: %s", repo.full_name, exc)
            continue

        if config.backup_wikis and repo.has_wiki:
            try:
                backup_wiki(config, repo, summary)
            except BackupError as exc:
                summary.wikis_failed += 1
                summary.failures.append(f"{repo.full_name}.wiki: {exc}")
                LOG.error("Wiki backup failed: %s.wiki: %s", repo.full_name, exc)

    log_summary(summary)
    return summary


def log_summary(summary: RunSummary) -> None:
    LOG.info(
        "GitHub source mirror summary: repos_discovered=%s repos_mirrored=%s "
        "repos_failed=%s repos_disabled=%s wikis_mirrored=%s wikis_skipped=%s "
        "wikis_failed=%s",
        summary.repos_discovered,
        summary.repos_mirrored,
        summary.repos_failed,
        summary.repos_disabled,
        summary.wikis_mirrored,
        summary.wikis_skipped,
        summary.wikis_failed,
    )


def main() -> int:
    setup_logging()

    try:
        config = load_config()
        prepare_filesystem(config)
        LOG.info("Starting GitHub source mirror backup")
        repositories = list_repositories(config)
        LOG.info("Found %s repositories", len(repositories))
        write_discovery_manifest(config, repositories)
        summary = backup_repositories(config, repositories)
        write_run_summary(config, summary)
        if summary.failures:
            raise BackupError("; ".join(summary.failures))
        LOG.info("GitHub source mirror backup completed")
        return 0
    except (BackupError, ValueError) as exc:
        LOG.error("GitHub source mirror backup failed: %s", exc)
        return 1
    except Exception:
        LOG.exception("Unexpected GitHub source mirror backup failure")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
