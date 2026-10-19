"""Tests of the bash installer skeleton: options, prompts, platform, conda.

Every call runs in the isolated harness of ``harness.py``: no real conda,
network tool or terminal is ever reached.
"""

import json
import os
import re
import shutil
import subprocess
import sys

import pytest

from swane.tests.installer.harness import (
    BASH,
    SCRIPT,
    bash_quote,
    make_conda_root,
    make_executable,
)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="bash installer")

MINIFORGE_VERSION = "26.7.2-0"
RELEASES = "https://github.com/conda-forge/miniforge/releases"


# ---------------------------------------------------------------------------
# Script shape and command line
# ---------------------------------------------------------------------------


def test_script_is_executable_and_parses():
    assert os.access(SCRIPT, os.X_OK)
    assert subprocess.run([BASH, "-n", str(SCRIPT)]).returncode == 0


def test_sourcing_does_not_run_main(sh):
    result = sh("true")
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_executing_the_file_runs_main(sh):
    result = subprocess.run(
        [BASH, str(SCRIPT), "--help"],
        env=sh.environment(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert result.stdout.startswith("Usage: install_swane.sh")


def test_piped_script_runs_main(sh):
    """``curl ... | bash -s -- --help``: the script arrives on stdin."""
    result = subprocess.run(
        [BASH, "-s", "--", "--help"],
        input=SCRIPT.read_text(),
        env=sh.environment(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert result.stdout.startswith("Usage: install_swane.sh")


def test_usage_explains_the_swane_spec_forms(sh):
    """--swane-spec goes verbatim to pip; each accepted form has an example."""
    result = sh("usage")
    assert result.returncode == 0
    text = " ".join(result.stdout.split())
    assert 'passed verbatim to "pip install -U"' in text
    assert "(default: swane, the latest release on PyPI)" in text
    assert "SWANe 0.2.5 or newer is required" in text
    for example in (
        "a PyPI version swane==0.2.5",
        "a local checkout /path/to/swane",
        "a git URL git+https://github.com/LICE-dev/swane.git@<branch>",
        "a wheel file /path/to/swane-0.2.5-py3-none-any.whl",
    ):
        assert example in text


@pytest.mark.parametrize(
    "args, message",
    [
        (["--bogus"], "Unknown option: --bogus"),
        (["--swane-spec"], "--swane-spec needs a value"),
        (["--miniforge-prefix"], "--miniforge-prefix needs a value"),
        (["--install-dir"], "--install-dir needs a value"),
    ],
)
def test_bad_command_line_exits_2_with_usage(sh, args, message):
    result = sh("main", *args)
    assert result.returncode == 2
    assert message in result.stderr
    assert "Usage: install_swane.sh" in result.stderr
    assert result.stdout == ""


def test_parse_args_sets_every_option(sh):
    result = sh.code(
        "parse_args --yes --accept-fsl-license --no-fsl --swane-spec /x/y "
        '--miniforge-prefix "/p q" --install-dir "/e f"; '
        'printf "%s|" "$ASSUME_YES" "$ACCEPT_FSL_LICENSE" "$NO_FSL" '
        '"$SWANE_SPEC" "$MINIFORGE_PREFIX" "$SWANE_INSTALL_DIR"'
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "1|1|1|/x/y|/p q|/e f|"


@pytest.mark.parametrize(
    "given, expected",
    [
        ("./envs", "{cwd}/envs"),
        ("envs", "{cwd}/envs"),
        ("/abs/envs", "/abs/envs"),
        ("/abs/envs///", "/abs/envs"),
        ("rel/envs/", "{cwd}/rel/envs"),
    ],
)
def test_parse_args_makes_the_install_dir_absolute_without_trailing_slash(
    sh, given, expected
):
    """The envs are INSTALL_DIR/NAME and the launcher pins their prefix."""
    result = sh.code(
        'parse_args --install-dir "$P"; printf "%s" "$SWANE_INSTALL_DIR"',
        env={"P": given},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected.replace("{cwd}", str(sh.tmp))


def test_install_dir_defaults_to_conda_envs_dir(sh):
    """main forgets an inherited SWANE_INSTALL_DIR, like the other options."""
    result = sh.code('parse_args --yes; printf "%s" "$SWANE_INSTALL_DIR"')
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_usage_documents_install_dir(sh):
    result = sh("usage")
    text = " ".join(result.stdout.split())
    assert "--install-dir DIR" in text
    assert "DIR/swane-env" in text
    assert "DIR/swane-fsl" in text


@pytest.mark.parametrize(
    "given, expected",
    [
        ("./mf", "{cwd}/mf"),
        ("mf", "{cwd}/mf"),
        (".//a b/c", "{cwd}/a b/c"),
        (".", "{cwd}"),
        ("/abs/mf", "/abs/mf"),
    ],
)
def test_parse_args_makes_the_miniforge_prefix_absolute(sh, given, expected):
    """A relative prefix would be pinned as is in the launcher."""
    result = sh.code(
        'parse_args --miniforge-prefix "$P"; printf "%s" "$MINIFORGE_PREFIX"',
        env={"P": given},
    )
    assert result.returncode == 0, result.stderr
    # The harness runs every call in the test's tmp directory.
    assert result.stdout == expected.replace("{cwd}", str(sh.tmp))


def test_main_defaults_ignore_the_environment(sh):
    """Options come from the command line only, not from inherited variables."""
    result = sh.code(
        # A no-op install flow: only main's option handling is under test.
        "install_flow() { :; }; "
        'main; printf "%s|" "$ASSUME_YES" "$ACCEPT_FSL_LICENSE" "$NO_FSL" '
        '"$SWANE_SPEC" "$MINIFORGE_PREFIX"',
        env={
            "ASSUME_YES": "1",
            "ACCEPT_FSL_LICENSE": "1",
            "NO_FSL": "1",
            "SWANE_SPEC": "other",
            "MINIFORGE_PREFIX": "/elsewhere",
        },
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "0|0|0|swane|%s/miniforge3|" % sh.home


def test_original_path_is_recorded_at_source_time(sh):
    result = sh.code('PATH="/changed"; printf "%s" "$ORIGINAL_PATH"')
    assert result.stdout == sh.path


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def test_log_warn_is_recorded_for_the_summary(sh):
    result = sh.code(
        'log_info hello; log_warn "first one"; log_warn second; '
        'printf "%s" "$SUMMARY_WARNINGS"'
    )
    assert result.returncode == 0
    assert result.stdout == "first one\nsecond"
    assert "==> hello" in result.stderr
    assert "WARNING: first one" in result.stderr


def test_die_exits_1_on_stderr(sh):
    result = sh.code('die "broken thing"; echo unreachable')
    assert result.returncode == 1
    assert result.stdout == ""
    assert "ERROR: broken thing" in result.stderr


# ---------------------------------------------------------------------------
# Platform
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "system, machine, expected",
    [
        ("Linux", "x86_64", "linux-64"),
        ("Linux", "aarch64", "linux-aarch64"),
        ("Darwin", "x86_64", "macos-64"),
        ("Darwin", "arm64", "macos-M1"),
        ("MINGW64_NT-10.0", "x86_64", None),
        ("Linux", "ppc64le", None),
    ],
)
def test_detect_platform(sh, stub, system, machine, expected):
    stub.platform(system, machine)
    result = sh("detect_platform")
    if expected is None:
        assert result.returncode == 1
        assert result.stdout == ""
        assert "Unsupported" in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert result.stdout == expected + "\n"


@pytest.mark.parametrize(
    "system, machine, intel",
    [
        ("Darwin", "x86_64", True),
        ("Darwin", "arm64", False),
        ("Linux", "x86_64", False),
    ],
)
def test_is_macos_intel(sh, stub, system, machine, intel):
    stub.platform(system, machine)
    assert (sh("is_macos_intel").returncode == 0) is intel


ROSETTA_ERROR = (
    "ERROR: This terminal runs under Rosetta (x86_64 emulation on an Apple "
    "Silicon Mac): open a native (arm64) terminal and rerun the installer"
)


def test_refuse_rosetta_dies_when_translated(sh, stub):
    """A sysctl.proc_translated of 1 is an x86_64 shell on Apple Silicon."""
    stub("sysctl", "echo 1")
    result = sh("refuse_rosetta")
    assert result.returncode == 1
    assert result.stderr.strip() == ROSETTA_ERROR
    assert stub.calls("sysctl") == ["sysctl -n sysctl.proc_translated"]


@pytest.mark.parametrize(
    "body",
    [
        # Native process on Apple Silicon.
        "echo 0",
        # Intel Mac: the key does not exist.
        "echo \"sysctl: unknown oid 'sysctl.proc_translated'\" >&2; exit 1",
    ],
)
def test_refuse_rosetta_passes_when_not_translated(sh, stub, body):
    stub("sysctl", body)
    result = sh("refuse_rosetta")
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_refuse_rosetta_passes_without_sysctl(sh):
    # SWANE_SYSCTL is the harness's stub path, absent here.
    assert sh("refuse_rosetta").returncode == 0


def test_refuse_rosetta_runs_swane_sysctl(sh, stub):
    other = stub.script(sh.tmp / "bin" / "my-sysctl", "my-sysctl", "echo 1")
    result = sh("refuse_rosetta", env={"SWANE_SYSCTL": other})
    assert result.returncode == 1
    assert result.stderr.strip() == ROSETTA_ERROR
    assert stub.calls() == ["my-sysctl -n sysctl.proc_translated"]


def test_refuse_rosetta_takes_sysctl_from_path_by_default(sh, stub):
    """An empty SWANE_SYSCTL: "sysctl" from PATH (here the stub directory)."""
    stub("sysctl", "echo 1")
    result = sh("refuse_rosetta", env={"SWANE_SYSCTL": ""})
    assert result.returncode == 1
    assert stub.calls() == ["sysctl -n sysctl.proc_translated"]


@pytest.mark.parametrize(
    "env, active",
    [
        (
            {"CONDA_PREFIX": "/c/envs/swane-env", "CONDA_SHLVL": "2"},
            "/c/envs/swane-env",
        ),
        (
            {"CONDA_PREFIX": "/c/envs/swane-fsl", "CONDA_SHLVL": "2"},
            "/c/envs/swane-fsl",
        ),
        ({"CONDA_PREFIX": "/c/envs/swane-env-dev/"}, "/c/envs/swane-env-dev"),
        # Named once, trailing slashes or not.
        (
            {
                "CONDA_PREFIX": "/c/envs/swane-env/",
                "CONDA_PREFIX_1": "/c/envs/swane-env",
                "CONDA_SHLVL": "2",
            },
            "/c/envs/swane-env",
        ),
        # A huge CONDA_SHLVL is capped at 100 levels.
        (
            {
                "CONDA_PREFIX": "/c",
                "CONDA_PREFIX_100": "/c/envs/swane-env",
                "CONDA_SHLVL": "99999999999999999999",
            },
            "/c/envs/swane-env",
        ),
        # Stacked below a non-swane environment.
        (
            {
                "CONDA_PREFIX": "/c/envs/other",
                "CONDA_PREFIX_1": "/c",
                "CONDA_PREFIX_2": "/c/envs/swane-env",
                "CONDA_SHLVL": "3",
            },
            "/c/envs/swane-env",
        ),
        # A missing level in the stack does not stop the search.
        (
            {
                "CONDA_PREFIX": "/c/envs/other",
                "CONDA_PREFIX_3": "/x/swane-old",
                "CONDA_SHLVL": "4",
            },
            "/x/swane-old",
        ),
        # The same environment at two levels is named once.
        (
            {
                "CONDA_PREFIX": "/c/envs/swane-env",
                "CONDA_PREFIX_1": "/c/envs/swane-env",
                "CONDA_SHLVL": "2",
            },
            "/c/envs/swane-env",
        ),
        (
            {
                "CONDA_PREFIX": "/c/envs/swane-env",
                "CONDA_PREFIX_1": "/c/envs/swane-fsl",
                "CONDA_SHLVL": "2",
            },
            "/c/envs/swane-env, /c/envs/swane-fsl",
        ),
    ],
)
def test_refuse_swane_conda_env_dies(sh, env, active):
    """No active or stacked swane* environment."""
    result = sh("refuse_swane_conda_env", env=env)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.strip() == (
        "ERROR: The installer cannot run inside a SWANe conda environment "
        '(active: %s): run "conda deactivate" until no swane* environment is '
        "active (or open a new terminal), then rerun the installer" % active
    )


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"CONDA_PREFIX": "/home/u/miniforge3", "CONDA_SHLVL": "1"},
        # The name must start with "swane".
        {"CONDA_PREFIX": "/c/envs/myswane", "CONDA_SHLVL": "1"},
        {"CONDA_PREFIX": "/swane-root/envs/other", "CONDA_SHLVL": "1"},
        {"CONDA_PREFIX": "/c/envs/other", "CONDA_PREFIX_1": "/c", "CONDA_SHLVL": "2"},
        # Levels above CONDA_SHLVL are not active.
        {
            "CONDA_PREFIX": "/c",
            "CONDA_PREFIX_5": "/c/envs/swane-env",
            "CONDA_SHLVL": "1",
        },
        {"CONDA_PREFIX": "/c", "CONDA_SHLVL": "not-a-number"},
        {
            "CONDA_PREFIX": "/c",
            "CONDA_PREFIX_101": "/c/envs/swane-env",
            "CONDA_SHLVL": "99999999999999999999",
        },
    ],
)
def test_refuse_swane_conda_env_passes(sh, env):
    result = sh("refuse_swane_conda_env", env=env)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tty, code",
    [("n\n", 1), ("y\n", 0), ("yes\n", 0), ("  Y \n", 0), ("\n", 1), ("", 1)],
)
def test_prompt_reads_tty_not_stdin(sh, tty, code):
    """Review Focus 1: under ``curl | bash`` stdin is the script body."""
    result = sh("prompt_yes_no", "Continue?", tty=tty, input="yes\n")
    assert result.returncode == code
    assert "Continue? [y/N]" in result.stderr
    assert result.stdout == ""


def test_prompt_without_tty_dies(sh):
    result = sh(
        "prompt_yes_no", "Continue?", env={"SWANE_TTY": "/nonexistent"}, input="y\n"
    )
    assert result.returncode == 1
    assert "No terminal available" in result.stderr
    assert "--yes" in result.stderr


def test_prompt_assume_yes_does_not_need_a_tty(sh):
    result = sh(
        "prompt_yes_no",
        "Continue?",
        env={"ASSUME_YES": "1", "SWANE_TTY": "/nonexistent"},
    )
    assert result.returncode == 0
    assert "Continue? yes (--yes)" in result.stderr


def test_consecutive_prompts_read_consecutive_lines(sh):
    result = sh.code(
        "for q in a b c; do "
        'if prompt_yes_no "$q"; then echo "$q=y"; else echo "$q=n"; fi; '
        "done",
        tty="n\ny\n",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "a=n\nb=y\nc=n\n"


def test_read_tty_keeps_a_last_line_without_newline(sh):
    result = sh.code('read_tty answer "Type yes: "; printf "[%s]" "$answer"', tty="yes")
    assert result.returncode == 0
    assert result.stdout == "[yes]"
    assert "Type yes: " in result.stderr


# ---------------------------------------------------------------------------
# Conda discovery
# ---------------------------------------------------------------------------


def _fsl_with_conda(fsl_root):
    """A fake FSL install, which ships its own conda (and conda.sh)."""
    make_conda_root(fsl_root)
    (fsl_root / "etc" / "fslversion").write_text("6.0.7.16\n")
    return fsl_root


def test_find_conda_skips_fsl_conda(sh):
    """Review Focus 2: FSL sourced in the shell puts FSL's conda first on PATH."""
    fsl = _fsl_with_conda(sh.home / "fsl")
    miniforge = make_conda_root(sh.home / "miniforge3")
    result = sh("find_conda", env={"PATH": "%s:%s" % (fsl / "bin", sh.path)})
    assert result.returncode == 0, result.stderr
    assert result.stdout == "%s\n" % miniforge


def test_find_conda_skips_conda_exe_inside_fsl(sh):
    fsl = _fsl_with_conda(sh.home / "fsl")
    miniforge = make_conda_root(sh.home / "miniforge3")
    result = sh("find_conda", env={"CONDA_EXE": fsl / "bin" / "conda"})
    assert result.stdout == "%s\n" % miniforge


def test_find_conda_skips_fsldir_without_fslversion(sh):
    """A root equal to $FSLDIR is rejected even without etc/fslversion."""
    fsl = make_conda_root(sh.home / "fsl-conda")
    miniforge = make_conda_root(sh.home / "miniforge3")
    result = sh(
        "find_conda",
        env={"CONDA_EXE": fsl / "bin" / "conda", "FSLDIR": str(fsl) + "/"},
    )
    assert result.stdout == "%s\n" % miniforge


def test_find_conda_prefers_conda_exe(sh):
    anaconda = make_conda_root(sh.home / "anaconda3")
    make_conda_root(sh.home / "miniforge3")
    result = sh("find_conda", env={"CONDA_EXE": anaconda / "bin" / "conda"})
    assert result.returncode == 0, result.stderr
    assert result.stdout == "%s\n" % anaconda


@pytest.mark.parametrize("bindir", ["bin", "condabin"])
def test_find_conda_uses_conda_on_path(sh, bindir):
    root = make_conda_root(sh.tmp / "elsewhere" / "conda")
    make_executable(root / "condabin" / "conda", "exit 0")
    make_conda_root(sh.home / "miniforge3")
    result = sh("find_conda", env={"PATH": "%s:%s" % (root / bindir, sh.path)})
    assert result.stdout == "%s\n" % root


def test_find_conda_user_roots_in_order(sh):
    make_conda_root(sh.home / "anaconda3")
    miniconda = make_conda_root(sh.home / "miniconda3")
    assert sh("find_conda").stdout == "%s\n" % miniconda
    miniforge = make_conda_root(sh.home / "miniforge3")
    assert sh("find_conda").stdout == "%s\n" % miniforge


def test_find_conda_ignores_dir_without_conda_sh(sh):
    (sh.home / "miniforge3" / "bin").mkdir(parents=True)
    anaconda = make_conda_root(sh.home / "anaconda3")
    assert sh("find_conda").stdout == "%s\n" % anaconda


def test_find_conda_custom_miniforge_prefix(sh):
    custom = make_conda_root(sh.tmp / "custom-forge")
    result = sh("find_conda", env={"MINIFORGE_PREFIX": custom})
    assert result.stdout == "%s\n" % custom


def test_find_conda_system_roots(sh):
    system = make_conda_root(sh.tmp / "opt" / "conda")
    result = sh(
        "find_conda",
        env={"SWANE_SYSTEM_CONDA_ROOTS": "%s %s" % (sh.tmp / "missing", system)},
    )
    assert result.stdout == "%s\n" % system


def test_find_conda_none(sh):
    result = sh("find_conda")
    assert result.returncode == 1
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# Miniforge
# ---------------------------------------------------------------------------

#: The SHA-256 of the four pinned Miniforge installers, written out here on
#: purpose (not read back from the script): a bump must change both.
MINIFORGE_HASHES = {
    "Linux-x86_64": "281b0ac7d550802efc81af633225a5e6116d29ae72f3ab4eae7168c3931a4c05",
    "Linux-aarch64": "89b786c8d2c8b0fda7553914c1314ae4ddaa094503802f279377b19ac4463cb2",
    "MacOSX-x86_64": "b00e7798658f92721a3ae2f6b9832695ffc6baf07758894d726268055359f6c5",
    "MacOSX-arm64": "d70bfa2e97afcda96927c9b9ca0e2316cb7750e4ce651c94388267cbe9588711",
}


def _fake_miniforge_installer(sh):
    """A stand-in for the downloaded installer: logs its argv, creates PREFIX."""
    path = sh.tmp / "fake-miniforge.sh"
    path.write_text(
        'printf "miniforge-installer %%s\\n" "$*" >> %s\n'
        'echo "installer chatter on stdout"\n'
        'prefix=""\n'
        'while [ "$#" -gt 0 ]; do\n'
        '    case "$1" in -p) prefix="$2"; shift ;; esac\n'
        "    shift\n"
        "done\n"
        'mkdir -p "$prefix/etc/profile.d" "$prefix/bin"\n'
        'echo "# conda.sh" > "$prefix/etc/profile.d/conda.sh"\n'
        % bash_quote(str(sh.stubs.calls_log))
    )
    return path


def _stub_curl(sh, stub, installer=None):
    """``curl -fsSL -o OUT URL`` copies the fake installer into OUT."""
    installer = installer or _fake_miniforge_installer(sh)
    stub(
        "curl",
        'out=""\n'
        'while [ "$#" -gt 0 ]; do\n'
        '    case "$1" in -o) out="$2"; shift ;; esac\n'
        "    shift\n"
        "done\n"
        'cp %s "$out"' % bash_quote(str(installer)),
    )


def _stub_wget(sh, stub):
    """``wget -qO OUT URL`` copies the fake installer into OUT."""
    stub("wget", 'cp %s "$2"' % bash_quote(str(_fake_miniforge_installer(sh))))


def _stub_sha256sum(stub, digest=MINIFORGE_HASHES["Linux-x86_64"]):
    stub("sha256sum", 'printf "%%s  %%s\\n" %s "$1"' % digest)


def _installer_name(asset):
    return "Miniforge3-%s-%s.sh" % (MINIFORGE_VERSION, asset)


def _installer_url(asset):
    return "%s/download/%s/%s" % (RELEASES, MINIFORGE_VERSION, _installer_name(asset))


def test_miniforge_is_pinned_with_the_four_hashes(sh):
    result = sh.code('printf "%s" "$MINIFORGE_VERSION"')
    assert result.stdout == MINIFORGE_VERSION
    for asset, digest in MINIFORGE_HASHES.items():
        result = sh("miniforge_sha256", _installer_name(asset))
        assert result.returncode == 0, asset
        assert result.stdout == digest + "\n"
    for name in (
        "Miniforge3-26.7.1-0-Linux-x86_64.sh",
        "Miniforge3-latest-Linux-x86_64.sh",
    ):
        assert sh("miniforge_sha256", name).returncode == 1


@pytest.mark.parametrize(
    "system, machine, asset",
    [
        ("Linux", "x86_64", "Linux-x86_64"),
        ("Linux", "amd64", "Linux-x86_64"),
        ("Linux", "aarch64", "Linux-aarch64"),
        ("Linux", "arm64", "Linux-aarch64"),
        ("Darwin", "x86_64", "MacOSX-x86_64"),
        ("Darwin", "arm64", "MacOSX-arm64"),
        ("Darwin", "aarch64", "MacOSX-arm64"),
    ],
)
def test_miniforge_asset_normalises_the_machine_name(sh, stub, system, machine, asset):
    """The aliases detect_platform accepts name the right installer."""
    stub.platform(system, machine)
    result = sh("miniforge_asset")
    assert result.returncode == 0, result.stderr
    assert result.stdout == _installer_name(asset) + "\n"


@pytest.mark.parametrize(
    "system, machine",
    [("Linux", "ppc64le"), ("Darwin", "i386"), ("FreeBSD", "amd64")],
)
def test_install_miniforge_unknown_platform_dies_before_downloading(
    sh, stub, system, machine
):
    stub.platform(system, machine)
    _stub_curl(sh, stub)
    result = sh("install_miniforge", sh.home / "miniforge3")
    assert result.returncode == 1
    assert "No Miniforge installer for this platform: %s %s" % (
        system,
        machine,
    ) in (result.stderr)
    assert stub.calls("curl") == []


@pytest.mark.parametrize(
    "machine, asset", [("x86_64", "Linux-x86_64"), ("amd64", "Linux-x86_64")]
)
def test_install_miniforge_downloads_verifies_and_installs(sh, stub, machine, asset):
    stub.platform("Linux", machine)
    _stub_curl(sh, stub)
    _stub_sha256sum(stub, MINIFORGE_HASHES[asset])
    prefix = sh.home / "miniforge3"
    result = sh("install_miniforge", prefix)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "%s\n" % prefix, "installer output must not reach stdout"
    assert (prefix / "etc" / "profile.d" / "conda.sh").is_file()
    # One download, the pinned installer itself: no "latest" lookup and no
    # .sha256 file (the hash is in the script).
    curl = stub.calls("curl")
    assert len(curl) == 1, curl
    assert curl[0].startswith("curl -fsSL -o ")
    assert curl[0].endswith(" " + _installer_url(asset))
    assert stub.calls("miniforge-installer") == [
        "miniforge-installer -b -p %s" % prefix
    ]
    assert not any("init" in call for call in stub.calls())
    assert list(sh.tmpdir.iterdir()) == [], "the download directory is removed"


def test_install_miniforge_macos_uses_shasum(sh, stub):
    stub.platform("Darwin", "arm64")
    _stub_curl(sh, stub)
    stub("shasum", 'printf "%%s  %%s\\n" %s "$3"' % MINIFORGE_HASHES["MacOSX-arm64"])
    prefix = sh.tmp / "forge"
    result = sh("install_miniforge", prefix)
    assert result.returncode == 0, result.stderr
    assert stub.calls("curl")[0].endswith(" " + _installer_url("MacOSX-arm64"))
    assert stub.calls("shasum")[0].startswith("shasum -a 256 ")


@pytest.mark.parametrize(
    "digest",
    [
        "b" * 64,
        # The right hash, but of another platform's installer.
        MINIFORGE_HASHES["Linux-aarch64"],
    ],
)
def test_install_miniforge_refuses_checksum_mismatch(sh, stub, digest):
    stub.platform("Linux", "x86_64")
    _stub_curl(sh, stub)
    _stub_sha256sum(stub, digest)
    prefix = sh.home / "miniforge3"
    result = sh("install_miniforge", prefix)
    assert result.returncode == 1
    assert "checksum mismatch" in result.stderr
    assert MINIFORGE_HASHES["Linux-x86_64"] in result.stderr
    assert result.stdout == ""
    assert not prefix.exists()
    assert stub.calls("miniforge-installer") == []
    assert list(sh.tmpdir.iterdir()) == [], "the download is deleted"


def test_install_miniforge_falls_back_to_wget(sh, stub):
    stub.platform("Linux", "arm64")
    _stub_wget(sh, stub)
    _stub_sha256sum(stub, MINIFORGE_HASHES["Linux-aarch64"])
    prefix = sh.home / "miniforge3"
    result = sh("install_miniforge", prefix)
    assert result.returncode == 0, result.stderr
    wget = stub.calls("wget")
    assert len(wget) == 1, wget
    assert wget[0].startswith("wget -qO ")
    assert wget[0].endswith(" " + _installer_url("Linux-aarch64"))
    assert (prefix / "etc" / "profile.d" / "conda.sh").is_file()


def test_install_miniforge_download_failure_dies(sh, stub):
    stub.platform("Linux", "x86_64")
    stub("curl", "exit 22")
    _stub_sha256sum(stub)
    result = sh("install_miniforge", sh.home / "miniforge3")
    assert result.returncode == 1
    assert "Could not download Miniforge from %s" % _installer_url("Linux-x86_64") in (
        result.stderr
    )
    assert stub.calls("sha256sum") == []
    assert list(sh.tmpdir.iterdir()) == []


def test_install_miniforge_reuses_existing_prefix(sh, stub):
    prefix = make_conda_root(sh.home / "miniforge3")
    result = sh("install_miniforge", prefix)
    assert result.returncode == 0
    assert result.stdout == "%s\n" % prefix
    assert stub.calls() == []


def test_install_miniforge_refuses_non_conda_prefix(sh, stub):
    prefix = sh.home / "miniforge3"
    (prefix / "something").mkdir(parents=True)
    result = sh("install_miniforge", prefix)
    assert result.returncode == 1
    assert "not a conda installation" in result.stderr
    assert stub.calls() == []


@pytest.mark.parametrize("case", ["fslversion", "fsldir", "fsldir_missing"])
def test_install_miniforge_refuses_fsl_prefix(sh, stub, case):
    """FSL's own root is never reused or installed over, whatever it contains."""
    stub.platform("Linux", "x86_64")
    _stub_curl(sh, stub)
    _stub_sha256sum(stub)
    prefix = sh.home / "miniforge3"
    env = {}
    if case == "fslversion":
        _fsl_with_conda(prefix)
    elif case == "fsldir":
        make_conda_root(prefix)
        env["FSLDIR"] = str(prefix) + "/"
    else:
        env["FSLDIR"] = prefix
    result = sh("install_miniforge", prefix, env=env)
    assert result.returncode == 1
    assert "is an FSL installation" in result.stderr
    assert result.stdout == ""
    assert stub.calls() == []
    if case == "fsldir_missing":
        assert not prefix.exists()


# ---------------------------------------------------------------------------
# Linux system packages and locale
# ---------------------------------------------------------------------------

#: The 3D Slicer package list (plus tcsh and unzip for FreeSurfer), written
#: out here on purpose (not read back from the script): the installer must
#: install exactly these, in this order.
APT_LIST = (
    "libegl1 libgl1 libopengl0 libgl1-mesa-dev libglu1-mesa libpulse0 "
    "libpulse-mainloop-glib0 libnss3 libx11-xcb1 libxdamage1 libxss1 "
    "libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 "
    "libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 "
    "libxcb-sync1 libxcb-xfixes0 libxcb-xinerama0 libxcb-xkb1 dc bc tcsh unzip"
)
#: apt-get waits for the dpkg lock instead of failing at once.
APT_LOCK = "-o DPkg::Lock::Timeout=300"
APT_INSTALL = "apt-get %s install -y --no-install-recommends" % APT_LOCK
APT_UPDATE = "apt-get %s update" % APT_LOCK
#: The one question of the Linux system step.
SYSTEM_QUESTION = "Run the Linux system setup steps above?"
#: What the installer says to do by hand about a missing locale.
LOCALE_HINT = "enable en_US.UTF-8 in your system's locale configuration"
#: Runs the step and prints the recorded warnings on stdout.
SYSTEM_STEP = 'linux_system_step; rc=$?; printf "%s" "$SUMMARY_WARNINGS"; exit $rc'


def _stub_linux_system(stub, apt_body=""):
    """Linux host with ``sudo`` (runs its arguments) and ``apt-get`` stubs."""
    stub.platform("Linux", "x86_64")
    stub("sudo", '"$@"')
    stub("apt-get", apt_body)


def _stub_locale(sh, stub, present=False, generated=True):
    """``locale -a`` lists en_US.utf8 when ``present``, or once ``locale-gen``
    ran successfully if ``generated``."""
    marker = sh.tmp / "locale-generated"
    stub(
        "locale",
        "echo C; echo POSIX\n"
        "%s"
        "[ -f %s ] && echo en_US.utf8\n"
        "exit 0" % ("echo en_US.utf8\n" if present else "", bash_quote(str(marker))),
    )
    stub("locale-gen", "touch %s" % bash_quote(str(marker)) if generated else "")


def _stub_dpkg(stub, missing=(), known=True, status="install ok installed"):
    """``dpkg-query -W -f=... PKG`` reports PKG with ``status`` (installed),
    except the ``missing`` ones (known, not installed); with ``known`` False
    it knows no package at all (exit 1). ``dpkg --print-architecture`` prints
    amd64."""
    stub("dpkg", "echo amd64")
    stub(
        "dpkg-query",
        "%s"
        'pkg="${3%%:amd64}"\n'
        'case " %s " in *" $pkg "*) echo "unknown ok not-installed"; exit 0 ;; esac\n'
        "echo %s"
        % ("" if known else "exit 1\n", " ".join(missing), bash_quote(status)),
    )


def _assert_shell_line(command):
    """``command`` is one valid shell line (``bash -n``): pasted as is, it
    cannot fail on a syntax error."""
    assert "\n" not in command
    check = subprocess.run(
        ["bash", "-n", "-c", command], capture_output=True, text=True, check=False
    )
    assert check.returncode == 0, (command, check.stderr)


def test_apt_installs_exact_package_list(sh, stub):
    _stub_linux_system(stub)
    result = sh("install_linux_packages")
    assert result.returncode == 0
    assert stub.calls("apt-get") == [
        APT_UPDATE,
        "%s %s" % (APT_INSTALL, APT_LIST),
        "%s libasound2t64" % APT_INSTALL,
    ]
    # Every apt-get call goes through sudo, and without "-n".
    assert stub.calls("sudo") == [
        "sudo %s" % APT_UPDATE,
        "sudo %s %s" % (APT_INSTALL, APT_LIST),
        "sudo %s libasound2t64" % APT_INSTALL,
    ]


def test_apt_falls_back_to_libasound2(sh, stub):
    _stub_linux_system(stub, 'case "$*" in *libasound2t64*) exit 100 ;; esac')
    result = sh.code(
        'install_linux_packages; rc=$?; printf "%s" "$SUMMARY_WARNINGS"; exit $rc'
    )
    assert result.returncode == 0
    assert stub.calls("apt-get")[-2:] == [
        "%s libasound2t64" % APT_INSTALL,
        "%s libasound2" % APT_INSTALL,
    ]
    # The fallback worked: nothing to report.
    assert result.stdout == ""


def test_apt_reports_when_both_alsa_packages_fail(sh, stub):
    _stub_linux_system(stub, 'case "$*" in *libasound2*) exit 100 ;; esac')
    result = sh.code(
        'install_linux_packages; rc=$?; printf "%s" "$SUMMARY_WARNINGS"; exit $rc'
    )
    assert result.returncode == 0
    assert "libasound2" in result.stdout


def test_apt_failure_warns_and_continues(sh, stub):
    _stub_linux_system(stub, '[ "$3" = install ] && exit 100 || exit 0')
    result = sh.code(
        'install_linux_packages; rc=$?; printf "%s" "$SUMMARY_WARNINGS"; exit $rc'
    )
    assert result.returncode == 0
    assert "WARNING:" in result.stderr
    assert "Installing the system packages failed" in result.stdout
    # The ALSA step still ran after the main list failed.
    assert stub.calls("apt-get")[-2:] == [
        "%s libasound2t64" % APT_INSTALL,
        "%s libasound2" % APT_INSTALL,
    ]


def test_apt_update_failure_warns_and_still_installs(sh, stub):
    _stub_linux_system(stub, '[ "$3" = update ] && exit 100 || exit 0')
    result = sh.code(
        'install_linux_packages; rc=$?; printf "%s" "$SUMMARY_WARNINGS"; exit $rc'
    )
    assert result.returncode == 0
    assert "apt-get update failed" in result.stdout
    assert "%s %s" % (APT_INSTALL, APT_LIST) in stub.calls("apt-get")


@pytest.mark.skipif(os.geteuid() == 0, reason="needs a non-root user")
@pytest.mark.parametrize("answer", ["y\n", "yes\n"])
def test_system_step_asks_once_and_runs_both_steps(sh, stub, answer):
    """One question, before the first sudo command, naming the steps."""
    _stub_linux_system(stub)
    _stub_locale(sh, stub)
    result = sh.code(SYSTEM_STEP, tty=answer)
    assert result.returncode == 0, result.stderr
    assert result.stderr.count(SYSTEM_QUESTION) == 1
    assert "may ask for your password" in result.stderr
    assert "apt-get install %s" % APT_LIST in result.stderr
    assert "locale-gen en_US.UTF-8" in result.stderr
    # The question comes before the first privileged step.
    assert result.stderr.index(SYSTEM_QUESTION) < result.stderr.index(
        "Installing system packages"
    )
    assert stub.calls("sudo") == [
        "sudo %s" % APT_UPDATE,
        "sudo %s %s" % (APT_INSTALL, APT_LIST),
        "sudo %s libasound2t64" % APT_INSTALL,
        "sudo locale-gen en_US.UTF-8",
    ]
    assert result.stdout == "", "nothing to warn about"


@pytest.mark.parametrize("answer", ["n\n", "\n", "no\n"])
def test_system_step_declined_runs_no_sudo_and_warns(sh, stub, answer):
    _stub_linux_system(stub)
    _stub_locale(sh, stub)
    result = sh.code(SYSTEM_STEP, tty=answer)
    assert result.returncode == 0, result.stderr
    assert result.stderr.count(SYSTEM_QUESTION) == 1
    assert stub.calls("sudo") == []
    assert stub.calls("apt-get") == []
    assert stub.calls("locale-gen") == []
    # One warning, for the summary, with the commands to run by hand.
    warnings = result.stdout.splitlines()
    assert len(warnings) == 1, warnings
    assert warnings[0].startswith("Linux system setup declined")
    # The libasound2 alternative is prose before the commands; everything
    # after "run: " is one shell line that can be pasted as is.
    prose, commands = warnings[0].split(", run: ")
    assert "on releases without libasound2t64, install libasound2 instead" in prose
    assert commands == (
        "sudo apt-get update && sudo apt-get install --no-install-recommends "
        "%s libasound2t64; sudo locale-gen en_US.UTF-8" % APT_LIST
    )
    _assert_shell_line(commands)


def test_system_step_declined_with_the_locale_present_names_only_apt(sh, stub):
    _stub_linux_system(stub)
    _stub_locale(sh, stub, present=True)
    result = sh.code(SYSTEM_STEP, tty="n\n")
    assert result.returncode == 0
    assert "locale-gen" not in result.stderr
    assert "locale-gen" not in result.stdout
    commands = result.stdout.splitlines()[0].split(", run: ")[1]
    assert commands == (
        "sudo apt-get update && sudo apt-get install --no-install-recommends "
        "%s libasound2t64" % APT_LIST
    )
    _assert_shell_line(commands)


def test_system_step_assume_yes_needs_no_terminal(sh, stub):
    _stub_linux_system(stub)
    _stub_locale(sh, stub)
    result = sh.code(SYSTEM_STEP, env={"ASSUME_YES": "1", "SWANE_TTY": "/nonexistent"})
    assert result.returncode == 0, result.stderr
    assert "%s yes (--yes)" % SYSTEM_QUESTION in result.stderr
    assert stub.calls("sudo")[0] == "sudo %s" % APT_UPDATE
    assert stub.calls("sudo")[-1] == "sudo locale-gen en_US.UTF-8"


def test_system_step_without_terminal_dies_like_every_prompt(sh, stub):
    _stub_linux_system(stub)
    _stub_locale(sh, stub)
    result = sh.code(SYSTEM_STEP, env={"SWANE_TTY": "/nonexistent"})
    assert result.returncode == 1
    assert "No terminal available: rerun with --yes" in result.stderr
    assert stub.calls("sudo") == []


@pytest.mark.parametrize(
    "status",
    [
        "install ok installed",
        # A package the user put on hold is still installed.
        "hold ok installed",
    ],
)
def test_system_step_with_nothing_missing_asks_nothing(sh, stub, status):
    """dpkg reports every package (libasound2 as the ALSA one) and the locale
    exists: no question, no sudo, also on a rerun without a terminal."""
    _stub_linux_system(stub)
    _stub_locale(sh, stub, present=True)
    _stub_dpkg(stub, missing=("libasound2t64",), status=status)
    result = sh.code(SYSTEM_STEP, env={"SWANE_TTY": "/nonexistent"})
    assert result.returncode == 0, result.stderr
    assert SYSTEM_QUESTION not in result.stderr
    # The exact line the installer-tests workflow requires on its rerun.
    assert (
        "==> The system packages for 3D Slicer and the en_US.UTF-8 locale are "
        "already installed\n"
    ) in result.stderr
    assert stub.calls("sudo") == []
    assert result.stdout == ""
    # The native architecture is asked first.
    assert "dpkg-query -W -f=${Status}\\n libegl1:amd64" in stub.calls("dpkg-query")


@pytest.mark.parametrize(
    "dpkg",
    [
        {"missing": ("tcsh",)},
        {"missing": ("libasound2t64", "libasound2")},
        # dpkg knows none of them (never installed on this host).
        {"known": False},
        # Removed, only the configuration files are left.
        {"status": "deinstall ok config-files"},
    ],
)
def test_system_step_asks_when_a_package_is_missing(sh, stub, dpkg):
    _stub_linux_system(stub)
    _stub_locale(sh, stub, present=True)
    _stub_dpkg(stub, **dpkg)
    result = sh.code(SYSTEM_STEP, tty="y\n")
    assert result.returncode == 0, result.stderr
    assert result.stderr.count(SYSTEM_QUESTION) == 1
    assert "locale-gen" not in result.stderr
    assert stub.calls("sudo")[1] == "sudo %s %s" % (APT_INSTALL, APT_LIST)
    assert stub.calls("locale-gen") == []


def test_system_step_plain_name_fallback_counts_as_installed(sh, stub):
    """dpkg-query fails for PKG:amd64 but knows PKG (Architecture: all)."""
    _stub_linux_system(stub)
    _stub_locale(sh, stub, present=True)
    stub("dpkg", "echo amd64")
    stub(
        "dpkg-query",
        'case "$3" in *:amd64) exit 1 ;; esac\necho "install ok installed"',
    )
    result = sh.code(SYSTEM_STEP, env={"SWANE_TTY": "/nonexistent"})
    assert result.returncode == 0, result.stderr
    assert SYSTEM_QUESTION not in result.stderr
    assert stub.calls("sudo") == []


@pytest.mark.skipif(os.geteuid() == 0, reason="needs a non-root user")
def test_system_step_packages_present_locale_missing_asks_for_locale_only(sh, stub):
    _stub_linux_system(stub)
    _stub_locale(sh, stub)
    _stub_dpkg(stub)
    result = sh.code(SYSTEM_STEP, tty="y\n")
    assert result.returncode == 0, result.stderr
    assert result.stderr.count(SYSTEM_QUESTION) == 1
    assert "apt-get install" not in result.stderr
    assert stub.calls("sudo") == ["sudo locale-gen en_US.UTF-8"]


def test_system_step_without_apt_never_asks_or_runs_sudo(sh, stub):
    stub.platform("Linux", "x86_64")
    stub("sudo", '"$@"')
    _stub_locale(sh, stub)
    result = sh.code(SYSTEM_STEP, env={"SWANE_TTY": "/nonexistent"})
    assert result.returncode == 0, result.stderr
    assert SYSTEM_QUESTION not in result.stderr
    assert stub.calls("sudo") == []
    assert stub.calls("locale-gen") == []
    warnings = result.stdout.splitlines()
    assert warnings[0].startswith("apt-get not found")
    assert "libxcb-cursor0" in warnings[0]
    assert warnings[1].startswith("The en_US.UTF-8 locale is missing: ")
    assert LOCALE_HINT in warnings[1]


@pytest.mark.skipif(os.geteuid() == 0, reason="needs a non-root user")
def test_system_step_without_sudo_for_non_root_warns(sh, stub):
    stub.platform("Linux", "x86_64")
    stub("apt-get")
    _stub_locale(sh, stub)
    result = sh.code(SYSTEM_STEP, env={"SWANE_TTY": "/nonexistent"})
    assert result.returncode == 0, result.stderr
    assert SYSTEM_QUESTION not in result.stderr
    assert stub.calls("apt-get") == []
    warnings = result.stdout.splitlines()
    assert len(warnings) == 2, warnings
    # The command ends the warning, with the libasound2 alternative as
    # prose before it.
    prose, command = warnings[0].split(": apt-get ")
    assert "on releases without libasound2t64, install libasound2 instead" in prose
    assert command == "install --no-install-recommends %s libasound2t64" % APT_LIST
    _assert_shell_line("apt-get " + command)
    assert LOCALE_HINT in warnings[1]


def test_locale_present_is_noop(sh, stub):
    stub.platform("Linux", "x86_64")
    stub("sudo", '"$@"')
    _stub_locale(sh, stub, present=True)
    result = sh("ensure_locale")
    assert result.returncode == 0
    assert stub.calls("locale-gen") == []
    assert stub.calls("sudo") == []


@pytest.mark.parametrize("listing", ["en_US.UTF-8", "EN_us.UTF8", "en_US.utf8"])
def test_has_en_us_locale_accepts_spellings(sh, stub, listing):
    stub("locale", "echo C; echo %s" % bash_quote(listing))
    assert sh("has_en_us_locale").returncode == 0


@pytest.mark.parametrize("listing", ["C\nPOSIX", "en_US.ISO-8859-1", "en_GB.utf8", ""])
def test_has_en_us_locale_rejects_others(sh, stub, listing):
    stub("locale", "printf '%s\\n' " + bash_quote(listing))
    assert sh("has_en_us_locale").returncode == 1


def test_locale_missing_runs_only_locale_gen(sh, stub):
    """The one privileged command is locale-gen; nothing under /etc is
    edited (a stand-in locale.gen with the entry commented stays as is)."""
    stub.platform("Linux", "x86_64")
    stub("sudo", '"$@"')
    _stub_locale(sh, stub)
    etc = sh.tmp / "etc"
    etc.mkdir()
    (etc / "locale.gen").write_text("# en_US.UTF-8 UTF-8\n")
    result = sh.code(
        'ensure_locale; rc=$?; printf "%s" "$SUMMARY_WARNINGS"; exit $rc',
        env={"SWANE_LOCALE_GEN_FILE": etc / "locale.gen"},
    )
    assert result.returncode == 0, result.stderr
    assert stub.calls("locale-gen") == ["locale-gen en_US.UTF-8"]
    assert stub.calls("sudo") == ["sudo locale-gen en_US.UTF-8"]
    assert (etc / "locale.gen").read_text() == "# en_US.UTF-8 UTF-8\n"
    assert os.listdir(etc) == ["locale.gen"]
    assert result.stdout == "", "the locale exists after locale-gen"


def test_script_never_names_a_file_under_etc():
    """No command of the installer reads or writes a system /etc path
    (only "<prefix>/etc/..." of conda environments appear in code lines)."""
    offending = []
    for number, line in enumerate(SCRIPT.read_text().splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        if re.search(r"(^|[\s\"'=:(])/etc(/|\b)", line):
            offending.append("%d: %s" % (number, line))
    assert offending == []
    assert "locale.gen" not in SCRIPT.read_text()


def test_locale_still_missing_after_locale_gen_warns(sh, stub):
    """Debian's locale-gen ignores its argument: the locale stays missing."""
    stub.platform("Linux", "x86_64")
    stub("sudo", '"$@"')
    _stub_locale(sh, stub, generated=False)
    result = sh.code('ensure_locale; rc=$?; printf "%s" "$SUMMARY_WARNINGS"; exit $rc')
    assert result.returncode == 0
    assert result.stdout.startswith(
        "The en_US.UTF-8 locale is still missing after locale-gen en_US.UTF-8: "
    )
    assert LOCALE_HINT in result.stdout
    assert "WARNING:" in result.stderr


def test_locale_gen_failure_warns_and_continues(sh, stub):
    stub.platform("Linux", "x86_64")
    stub("sudo", '"$@"')
    stub("locale", "echo C")
    stub("locale-gen", "exit 1")
    result = sh.code('ensure_locale; rc=$?; printf "%s" "$SUMMARY_WARNINGS"; exit $rc')
    assert result.returncode == 0
    assert result.stdout.startswith("locale-gen en_US.UTF-8 failed: ")
    assert LOCALE_HINT in result.stdout
    assert "WARNING:" in result.stderr


@pytest.mark.parametrize(
    "func", ["install_linux_packages", "ensure_locale", "linux_system_step"]
)
def test_linux_steps_noop_on_macos(sh, stub, func):
    stub.platform("Darwin", "arm64")
    stub("sudo", '"$@"')
    stub("apt-get")
    stub("locale", "echo C")
    stub("locale-gen")
    result = sh(func, env={"SWANE_TTY": "/nonexistent"})
    assert result.returncode == 0
    assert stub.calls("sudo") == []
    assert stub.calls("apt-get") == []
    assert stub.calls("locale-gen") == []
    assert result.stderr == ""


# ---------------------------------------------------------------------------
# swane-env
# ---------------------------------------------------------------------------

CHANNELS = "--override-channels --strict-channel-priority -c conda-forge"
VERSION_CODE = 'import sys; print("%d.%d" % sys.version_info[:2])'
#: The check, after pip, that the installed SWANe is recent enough.
SWANE_CHECK_CALL = "-I -c import swane.utils.fsl_conda"
SWANE_TOO_OLD = (
    "The installed SWANe (%s) is too old for this installer: "
    "it needs SWANe 0.2.5 or newer"
)


def _env_python(stub, path, label, version="3.12"):
    """Logging stub of an environment's ``bin/python``.

    ``-c`` (the version check) prints ``version``; ``-m pip`` prints some
    chatter on stdout and records ``PYTHONNOUSERSITE`` next to the stub; the
    ``-I -c`` SWANe check succeeds silently.
    """
    return stub.script(
        path,
        label,
        'case "$1" in\n'
        "    -c) echo %s ;;\n"
        '    -m) echo "pip output"\n'
        '        printf "%%s" "${PYTHONNOUSERSITE:-unset}" > "$0.nousersite" ;;\n'
        "esac" % bash_quote(version),
    )


class FakeConda:
    """A conda root whose ``bin/conda`` logs every call (as ``conda ...``).

    ``env list --json`` prints :attr:`envs_json`; ``create`` makes
    :attr:`new_prefix` (with a Python stub reporting 3.12) and lists it;
    ``--version`` prints ``version``. ``bin/python`` is the interpreter
    running the tests, so the installer's JSON parsing is the real one.
    """

    def __init__(
        self, sh, stub, version="conda 24.11.3", create_exit=0, install_dir=None
    ):
        self.stub = stub
        self.root = make_conda_root(sh.tmp / "conda root")
        self.envs_json = sh.tmp / "envs.json"
        # With ``install_dir`` (--install-dir) ``create -p`` makes the env there.
        self.new_prefix = (install_dir or self.root / "envs") / "swane-env"
        self.set_envs()
        make_executable(
            self.root / "bin" / "python", 'exec %s "$@"' % bash_quote(sys.executable)
        )
        template = _env_python(
            stub, sh.tmp / "python-template", str(self.new_prefix / "bin" / "python")
        )
        created = json.dumps({"envs": [str(self.root), str(self.new_prefix)]})
        stub.script(
            self.root / "bin" / "conda",
            "conda",
            'case "$1" in\n'
            "    --version) echo %s ;;\n"
            "    env) cat %s ;;\n"
            '    create) echo "conda create output"\n'
            "        [ %d = 0 ] || exit %d\n"
            "        mkdir -p %s %s\n"
            "        cp %s %s\n"
            "        printf '%%s' %s > %s ;;\n"
            '    install) echo "conda install output" ;;\n'
            "esac"
            % (
                bash_quote(version),
                bash_quote(str(self.envs_json)),
                create_exit,
                create_exit,
                bash_quote(str(self.new_prefix / "bin")),
                bash_quote(str(self.new_prefix / "conda-meta")),
                bash_quote(str(template)),
                bash_quote(str(self.new_prefix / "bin" / "python")),
                bash_quote(created),
                bash_quote(str(self.envs_json)),
            ),
        )

    def set_envs(self, *prefixes):
        """List the root plus ``prefixes`` in ``conda env list --json``."""
        envs = [str(self.root)] + [str(p) for p in prefixes]
        self.envs_json.write_text(json.dumps({"envs": envs}))

    def add_env(self, prefix, version="3.12", dot=False, tensorflow=False):
        """Make an existing environment at ``prefix``; return its python path."""
        python = prefix / "bin" / "python"
        _env_python(self.stub, python, str(python), version)
        if dot:
            make_executable(prefix / "bin" / "dot", "exit 0")
        if tensorflow:
            package = prefix / "lib" / "python3.12" / "site-packages" / "tensorflow"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text("")
        return python

    def conda_calls(self, subcommand):
        return [
            call
            for call in self.stub.calls("conda")
            if call.split()[1:2] == [subcommand]
        ]


def _ensure(sh, conda, spec="swane"):
    """Run ensure_swane_env and print SWANE_ENV_PREFIX on stdout."""
    return sh.code(
        'ensure_swane_env "$ROOT" "$SPEC"; printf "%s\\n" "$SWANE_ENV_PREFIX"',
        env={"ROOT": conda.root, "SPEC": spec},
    )


def test_conda_cmd_uses_bin_conda(sh, stub):
    root = sh.tmp / "root"
    stub.script(root / "bin" / "conda", "bin-conda")
    stub.script(root / "condabin" / "conda", "condabin-conda")
    assert sh("conda_cmd", root, "info", "--json").returncode == 0
    assert stub.calls() == ["bin-conda info --json"]


def test_conda_cmd_falls_back_to_condabin(sh, stub):
    root = sh.tmp / "root"
    stub.script(root / "condabin" / "conda", "condabin-conda", "exit 3")
    assert sh("conda_cmd", root, "--version").returncode == 3
    assert stub.calls() == ["condabin-conda --version"]


def test_conda_cmd_without_conda_dies(sh):
    result = sh("conda_cmd", sh.tmp / "empty", "--version")
    assert result.returncode == 1
    assert "No conda executable" in result.stderr


def test_find_env_prefix_matches_the_directory_name_exactly(sh, stub):
    conda = FakeConda(sh, stub)
    wanted = sh.tmp / "other envs" / "swane-env"
    conda.set_envs(
        conda.root / "envs" / "swane-env-dev",
        conda.root / "envs" / "my-swane-env",
        conda.root / "envs" / "swane-env" / "nested",
        str(wanted) + "/",
    )
    result = sh("find_env_prefix", conda.root, "swane-env")
    assert result.returncode == 0
    # The only exact match, as conda listed it.
    assert result.stdout == str(wanted) + "/\n"


def test_find_env_prefix_prefers_the_roots_own_env(sh, stub):
    conda = FakeConda(sh, stub)
    own = conda.root / "envs" / "swane-env"
    conda.set_envs(sh.tmp / "other conda" / "envs" / "swane-env", own)
    result = sh("find_env_prefix", conda.root, "swane-env")
    assert result.returncode == 0
    assert result.stdout == "%s\n" % own


def test_find_env_prefix_takes_the_first_match_outside_the_root(sh, stub):
    conda = FakeConda(sh, stub)
    first = sh.tmp / "conda a" / "envs" / "swane-env"
    conda.set_envs(first, sh.tmp / "conda b" / "envs" / "swane-env")
    result = sh("find_env_prefix", conda.root, "swane-env")
    assert result.returncode == 0
    assert result.stdout == "%s\n" % first


def _fsl_root(path):
    """A fake FSL install: a conda root with ``etc/fslversion``."""
    make_conda_root(path)
    (path / "etc" / "fslversion").write_text("6.0.7.8\n")
    return path


@pytest.mark.parametrize("how", ["fslversion", "fsldir", "under_fsldir"])
def test_find_env_prefix_skips_envs_inside_fsl(sh, stub, how):
    """An env registered by FSL's own conda is listed too: never reuse it."""
    conda = FakeConda(sh, stub)
    env = {}
    if how == "fslversion":
        fsl_env = _fsl_root(sh.tmp / "fsl") / "envs" / "swane-env"
    elif how == "fsldir":
        # $FSLDIR without etc/fslversion, given with a trailing slash.
        make_conda_root(sh.tmp / "fsl")
        fsl_env = sh.tmp / "fsl" / "envs" / "swane-env"
        env["FSLDIR"] = str(sh.tmp / "fsl") + "/"
    else:
        fsl_env = sh.tmp / "fsl" / "pkgs" / "envs" / "swane-env"
        env["FSLDIR"] = sh.tmp / "fsl"
    fsl_env.mkdir(parents=True)
    outside = sh.tmp / "other conda" / "envs" / "swane-env"
    conda.set_envs(fsl_env, outside)
    result = sh("find_env_prefix", conda.root, "swane-env", env=env)
    assert result.returncode == 0
    assert result.stdout == "%s\n" % outside
    assert "inside an FSL installation" in result.stderr
    # With only the FSL env listed, swane-env counts as absent.
    conda.set_envs(fsl_env)
    result = sh("find_env_prefix", conda.root, "swane-env", env=env)
    assert result.returncode == 1
    assert result.stdout == ""


def test_swane_env_inside_fsl_is_not_reused(sh, stub):
    """``conda create -n swane-env`` once run with FSL's conda: create a new one."""
    stub.platform("Linux", "x86_64")
    conda = FakeConda(sh, stub)
    fsl_env = _fsl_root(sh.tmp / "fsl") / "envs" / "swane-env"
    fsl_python = conda.add_env(fsl_env, dot=True)
    conda.set_envs(fsl_env)
    result = _ensure(sh, conda)
    assert result.returncode == 0, result.stderr
    assert conda.conda_calls("create") == [
        "conda create -y -n swane-env %s python=3.12 graphviz" % CHANNELS
    ]
    assert conda.conda_calls("install") == []
    assert stub.calls(str(fsl_python)) == []
    assert result.stdout == "%s\n" % conda.new_prefix


def test_find_env_prefix_absent_returns_1(sh, stub):
    conda = FakeConda(sh, stub)
    conda.set_envs(conda.root / "envs" / "swane-env-dev")
    result = sh("find_env_prefix", conda.root, "swane-env")
    assert result.returncode == 1
    assert result.stdout == ""


def test_find_env_prefix_unreadable_list_returns_2(sh, stub):
    conda = FakeConda(sh, stub)
    conda.envs_json.write_text("not json")
    assert sh("find_env_prefix", conda.root, "swane-env").returncode == 2


def test_find_env_prefix_with_install_dir_looks_only_there(sh, stub):
    """DIR/NAME with a conda-meta directory; conda's list is never read."""
    conda = FakeConda(sh, stub)
    install = sh.tmp / "install dir"
    listed = conda.root / "envs" / "swane-env"
    conda.set_envs(listed)
    env = {"SWANE_INSTALL_DIR": install}
    # Nothing there yet: absent, whatever conda lists.
    result = sh("find_env_prefix", conda.root, "swane-env", env=env)
    assert result.returncode == 1
    assert result.stdout == ""
    # A directory that is not an environment (no conda-meta) is absent too.
    (install / "swane-env").mkdir(parents=True)
    assert sh("find_env_prefix", conda.root, "swane-env", env=env).returncode == 1
    (install / "swane-env" / "conda-meta").mkdir()
    result = sh("find_env_prefix", conda.root, "swane-env", env=env)
    assert result.returncode == 0
    assert result.stdout == "%s\n" % (install / "swane-env")
    assert stub.calls("conda") == []


def test_conda_create_env_by_name_without_install_dir(sh, stub):
    conda = FakeConda(sh, stub)
    result = sh("conda_create_env", conda.root, "swane-env", "-c", "x", "python=3.12")
    assert result.returncode == 0, result.stderr
    assert conda.conda_calls("create") == [
        "conda create -y -n swane-env -c x python=3.12"
    ]


def test_conda_create_env_in_install_dir(sh, stub):
    conda = FakeConda(sh, stub)
    install = sh.tmp / "new" / "install dir"
    result = sh(
        "conda_create_env",
        conda.root,
        "swane-fsl",
        "-c",
        "x",
        env={"SWANE_INSTALL_DIR": install},
    )
    assert result.returncode == 0, result.stderr
    assert conda.conda_calls("create") == [
        "conda create -y -p %s -c x" % (install / "swane-fsl")
    ]
    # The parent directory is made; conda makes the environment itself.
    assert install.is_dir()


def test_conda_create_env_accepts_an_empty_target_directory(sh, stub):
    conda = FakeConda(sh, stub)
    install = sh.tmp / "install"
    (install / "swane-env").mkdir(parents=True)
    result = sh(
        "conda_create_env", conda.root, "swane-env", env={"SWANE_INSTALL_DIR": install}
    )
    assert result.returncode == 0, result.stderr
    assert len(conda.conda_calls("create")) == 1


@pytest.mark.parametrize("kind", ["files", "file"])
def test_conda_create_env_refuses_a_target_that_is_not_an_environment(sh, stub, kind):
    """``conda create -y -p DIR`` deletes an existing DIR: never let it."""
    conda = FakeConda(sh, stub)
    install = sh.tmp / "install"
    target = install / "swane-env"
    if kind == "files":
        target.mkdir(parents=True)
        (target / "precious.txt").write_text("data")
    else:
        install.mkdir()
        target.write_text("data")
    result = sh(
        "conda_create_env", conda.root, "swane-env", env={"SWANE_INSTALL_DIR": install}
    )
    assert result.returncode == 1
    assert "is not a conda environment" in result.stderr
    assert "--install-dir" in result.stderr
    assert conda.conda_calls("create") == []
    assert target.exists()


def test_ensure_swane_env_creates_in_install_dir(sh, stub):
    stub.platform("Linux", "x86_64")
    install = sh.tmp / "install dir"
    conda = FakeConda(sh, stub, install_dir=install)
    # An swane-env in conda's own directory is ignored with --install-dir.
    old = conda.root / "envs" / "swane-env"
    old_python = conda.add_env(old, dot=True)
    conda.set_envs(old)
    result = sh.code(
        'ensure_swane_env "$ROOT" swane; printf "%s\\n" "$SWANE_ENV_PREFIX"',
        env={"ROOT": conda.root, "SWANE_INSTALL_DIR": install},
    )
    assert result.returncode == 0, result.stderr
    assert conda.conda_calls("create") == [
        "conda create -y -p %s %s python=3.12 graphviz"
        % (install / "swane-env", CHANNELS)
    ]
    assert conda.conda_calls("install") == []
    assert stub.calls(str(old_python)) == []
    assert result.stdout == "%s\n" % (install / "swane-env")


def test_ensure_swane_env_updates_the_one_in_install_dir(sh, stub):
    stub.platform("Linux", "x86_64")
    install = sh.tmp / "install"
    conda = FakeConda(sh, stub, install_dir=install)
    existing = install / "swane-env"
    conda.add_env(existing)
    (existing / "conda-meta").mkdir()
    result = sh.code(
        'ensure_swane_env "$ROOT" swane; printf "%s\\n" "$SWANE_ENV_PREFIX"',
        env={"ROOT": conda.root, "SWANE_INSTALL_DIR": install},
    )
    assert result.returncode == 0, result.stderr
    assert conda.conda_calls("create") == []
    assert conda.conda_calls("install") == [
        "conda install -y -p %s %s graphviz" % (existing, CHANNELS)
    ]
    assert result.stdout == "%s\n" % existing


@pytest.mark.parametrize(
    "version", ["conda 23.7.4", "conda 23.9.0", "conda 4.14.0", "conda 22.11.1"]
)
def test_old_conda_warns(sh, stub, version):
    conda = FakeConda(sh, stub, version=version)
    result = sh.code(
        'warn_old_conda "$ROOT"; rc=$?; printf "%s" "$SUMMARY_WARNINGS"; exit $rc',
        env={"ROOT": conda.root},
    )
    assert result.returncode == 0
    assert "conda %s" % version.split()[1] in result.stdout
    assert "23.10" in result.stdout
    assert "WARNING:" in result.stderr


@pytest.mark.parametrize(
    "version", ["conda 24.11.3", "conda 23.10.0", "conda 23.11.0", "conda 25.1"]
)
def test_recent_conda_does_not_warn(sh, stub, version):
    conda = FakeConda(sh, stub, version=version)
    result = sh.code(
        'warn_old_conda "$ROOT"; rc=$?; printf "%s" "$SUMMARY_WARNINGS"; exit $rc',
        env={"ROOT": conda.root},
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert "WARNING:" not in result.stderr


def test_unreadable_conda_version_never_fails(sh, stub):
    conda = FakeConda(sh, stub, version="something else")
    result = sh.code(
        'warn_old_conda "$ROOT"; rc=$?; printf "%s" "$SUMMARY_WARNINGS"; exit $rc',
        env={"ROOT": conda.root},
    )
    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.parametrize(
    "a, b, lower",
    [
        ("23.7.4", "23.10", True),
        ("23.10", "23.10", False),
        ("23.10.0", "23.10", False),
        ("23.9.9", "23.10", True),
        ("24.1", "23.10", False),
        ("4.14.0", "23.10", True),
        ("23.10.0rc1", "23.10", False),
    ],
)
def test_version_lt(sh, a, b, lower):
    assert sh("version_lt", a, b).returncode == (0 if lower else 1)


def test_system_has_dot_checks_the_starting_path(sh, stub):
    assert sh("system_has_dot").returncode == 1
    stub("dot")
    assert sh("system_has_dot").returncode == 0


def test_system_has_dot_ignores_later_path_changes(sh):
    """A dot reachable only after sourcing (e.g. after an activation) is not the system's."""
    make_executable(sh.tmp / "later" / "dot", "exit 0")
    result = sh.code(
        'PATH="$LATER:$PATH"; system_has_dot', env={"LATER": sh.tmp / "later"}
    )
    assert result.returncode == 1


def test_create_env_linux_without_dot(sh, stub):
    stub.platform("Linux", "x86_64")
    conda = FakeConda(sh, stub)
    result = _ensure(sh, conda)
    assert result.returncode == 0, result.stderr
    assert conda.conda_calls("create") == [
        "conda create -y -n swane-env %s python=3.12 graphviz" % CHANNELS
    ]
    assert conda.conda_calls("install") == []
    assert all("defaults" not in call for call in stub.calls())
    assert all("tensorflow" not in call for call in stub.calls())
    # The prefix is published in the global; conda/pip chatter stays off stdout.
    assert result.stdout == "%s\n" % conda.new_prefix
    assert "conda create output" in result.stderr


def test_create_env_skips_graphviz_when_dot_present(sh, stub):
    stub.platform("Linux", "x86_64")
    stub("dot")
    conda = FakeConda(sh, stub)
    result = _ensure(sh, conda)
    assert result.returncode == 0, result.stderr
    assert conda.conda_calls("create") == [
        "conda create -y -n swane-env %s python=3.12" % CHANNELS
    ]


@pytest.mark.parametrize(
    "system, machine, tensorflow",
    [
        ("Darwin", "x86_64", True),
        ("Darwin", "arm64", False),
        ("Linux", "x86_64", False),
    ],
)
def test_create_env_macos_intel_adds_tensorflow(sh, stub, system, machine, tensorflow):
    stub.platform(system, machine)
    stub("dot")
    conda = FakeConda(sh, stub)
    result = _ensure(sh, conda)
    assert result.returncode == 0, result.stderr
    expected = "conda create -y -n swane-env %s python=3.12" % CHANNELS
    if tensorflow:
        expected += " tensorflow>=2.18"
    assert conda.conda_calls("create") == [expected]


def test_create_env_pip_installs_into_the_new_env(sh, stub):
    stub.platform("Linux", "x86_64")
    conda = FakeConda(sh, stub)
    result = _ensure(sh, conda)
    assert result.returncode == 0, result.stderr
    python = str(conda.new_prefix / "bin" / "python")
    assert stub.calls(python) == [
        "%s -m pip install -U swane" % python,
        "%s %s" % (python, SWANE_CHECK_CALL),
    ]
    # pip must not take ~/.local packages as already installed.
    assert (conda.new_prefix / "bin" / "python.nousersite").read_text() == "1"


def test_existing_env_is_updated_not_recreated(sh, stub):
    stub.platform("Linux", "x86_64")
    conda = FakeConda(sh, stub)
    prefix = conda.root / "envs" / "swane-env"
    python = conda.add_env(prefix, dot=True)
    conda.set_envs(conda.root / "envs" / "swane-env-dev", prefix)
    result = _ensure(sh, conda)
    assert result.returncode == 0, result.stderr
    assert conda.conda_calls("create") == []
    # graphviz is already there: nothing to install.
    assert conda.conda_calls("install") == []
    assert stub.calls(str(python)) == [
        "%s -c %s" % (python, VERSION_CODE),
        "%s -m pip install -U swane" % python,
        "%s %s" % (python, SWANE_CHECK_CALL),
    ]
    assert result.stdout == "%s\n" % prefix


@pytest.mark.parametrize(
    "system, machine, dot, tensorflow, missing",
    [
        ("Linux", "x86_64", False, False, "graphviz"),
        ("Darwin", "x86_64", True, False, "tensorflow>=2.18"),
        # The TensorFlow spec is passed even when TensorFlow is there.
        ("Darwin", "x86_64", False, True, "graphviz tensorflow>=2.18"),
        ("Darwin", "x86_64", True, True, "tensorflow>=2.18"),
        ("Darwin", "x86_64", False, False, "graphviz tensorflow>=2.18"),
    ],
)
def test_existing_env_installs_only_missing_packages(
    sh, stub, system, machine, dot, tensorflow, missing
):
    stub.platform(system, machine)
    conda = FakeConda(sh, stub)
    prefix = sh.tmp / "elsewhere" / "swane-env"
    conda.add_env(prefix, dot=dot, tensorflow=tensorflow)
    conda.set_envs(prefix)
    result = _ensure(sh, conda)
    assert result.returncode == 0, result.stderr
    assert conda.conda_calls("create") == []
    assert conda.conda_calls("install") == [
        "conda install -y -p %s %s %s" % (prefix, CHANNELS, missing)
    ]


def test_existing_env_on_macos_intel_always_requests_tensorflow(sh, stub):
    """Every update solve on macOS Intel carries the TensorFlow spec."""
    stub.platform("Darwin", "x86_64")
    stub("dot")
    conda = FakeConda(sh, stub)
    prefix = conda.root / "envs" / "swane-env"
    conda.add_env(prefix, tensorflow=True)
    conda.set_envs(prefix)
    assert _ensure(sh, conda).returncode == 0
    assert conda.conda_calls("install") == [
        "conda install -y -p %s %s tensorflow>=2.18" % (prefix, CHANNELS)
    ]


def test_existing_env_with_everything_on_macos_arm_installs_nothing(sh, stub):
    stub.platform("Darwin", "arm64")
    stub("dot")
    conda = FakeConda(sh, stub)
    prefix = conda.root / "envs" / "swane-env"
    conda.add_env(prefix)
    conda.set_envs(prefix)
    assert _ensure(sh, conda).returncode == 0
    assert conda.conda_calls("install") == []


def test_existing_env_wrong_python_dies(sh, stub):
    stub.platform("Linux", "x86_64")
    conda = FakeConda(sh, stub)
    prefix = conda.root / "envs" / "swane-env"
    python = conda.add_env(prefix, version="3.11")
    conda.set_envs(prefix)
    result = _ensure(sh, conda)
    assert result.returncode == 1
    assert "swane-env uses Python 3.11; remove it or rename it, then rerun" in (
        result.stderr
    )
    assert conda.conda_calls("create") == []
    assert conda.conda_calls("install") == []
    assert stub.calls(str(python)) == ["%s -c %s" % (python, VERSION_CODE)]


def test_existing_env_without_python_dies(sh, stub):
    stub.platform("Linux", "x86_64")
    conda = FakeConda(sh, stub)
    prefix = conda.root / "envs" / "swane-env"
    prefix.mkdir(parents=True)
    conda.set_envs(prefix)
    result = _ensure(sh, conda)
    assert result.returncode == 1
    assert "has no Python" in result.stderr


def test_swane_spec_is_passed_to_pip(sh, stub):
    stub.platform("Linux", "x86_64")
    conda = FakeConda(sh, stub)
    prefix = conda.root / "envs" / "swane-env"
    python = conda.add_env(prefix, dot=True)
    conda.set_envs(prefix)
    result = _ensure(sh, conda, spec="/path/to/checkout")
    assert result.returncode == 0, result.stderr
    assert stub.calls(str(python))[-2] == (
        "%s -m pip install -U /path/to/checkout" % python
    )


MISSING_FSL_CONDA = "ModuleNotFoundError: No module named 'swane.utils.fsl_conda'"


def _old_swane_python(stub, path, version="0.2.1.1", error=MISSING_FSL_CONDA):
    """An env ``bin/python`` whose ``import swane.utils.fsl_conda`` fails.

    The import prints a traceback ending with ``error`` and exits 1 (by
    default: a SWANe without swane.utils.fsl_conda); ``swane.__version__``
    prints ``version``. It records ``PYTHONNOUSERSITE`` of the SWANe checks
    (``-I``) next to it.
    """
    return stub.script(
        path,
        str(path),
        'case "$*" in\n'
        '    "-I "*) printf "%%s\\n" "${PYTHONNOUSERSITE:-unset}" >> "$0.checks" ;;\n'
        "esac\n"
        'case "$*" in\n'
        '    "-c "*) echo 3.12 ;;\n'
        '    "-m pip "*) echo "pip output" ;;\n'
        '    *"import swane.utils.fsl_conda"*)\n'
        "        echo 'Traceback (most recent call last):' >&2\n"
        "        echo %s >&2\n"
        "        exit 1 ;;\n"
        "    *swane.__version__*) echo %s ;;\n"
        "    *) exit 9 ;;\n"
        "esac" % (bash_quote(error), bash_quote(version)),
    )


@pytest.mark.parametrize("version, shown", [("0.2.1.1", "0.2.1.1"), ("", None)])
def test_swane_without_fsl_conda_is_too_old(sh, stub, version, shown):
    """PyPI's SWANe 0.2.1.1 has no swane.utils.fsl_conda: stop right after pip."""
    stub.platform("Linux", "x86_64")
    conda = FakeConda(sh, stub)
    prefix = conda.root / "envs" / "swane-env"
    python = _old_swane_python(stub, prefix / "bin" / "python", version)
    make_executable(prefix / "bin" / "dot", "exit 0")
    conda.set_envs(prefix)
    result = _ensure(sh, conda)
    assert result.returncode == 1
    assert SWANE_TOO_OLD % (shown or "unknown version") in result.stderr
    assert stub.calls(str(python))[-3:] == [
        "%s -m pip install -U swane" % python,
        "%s %s" % (python, SWANE_CHECK_CALL),
        "%s -I -c import swane; print(swane.__version__)" % python,
    ]
    # Both checks run isolated, without the user's site-packages.
    assert python.with_name("python.checks").read_text() == "1\n1\n"
    assert result.stdout == ""


LIBGL_ERROR = "ImportError: libGL.so.1: cannot open shared object file"


@pytest.mark.parametrize(
    "version, error, too_old",
    [
        # Below the minimum: too old, whatever the error.
        ("0.2.1.1", LIBGL_ERROR, True),
        # Recent enough, or no version: the Python error, never "too old".
        ("0.2.5", LIBGL_ERROR, False),
        ("0.3", "ModuleNotFoundError: No module named 'nibabel'", False),
        ("", LIBGL_ERROR, False),
    ],
)
def test_swane_import_failure_is_too_old_only_when_it_is(
    sh, stub, version, error, too_old
):
    stub.platform("Linux", "x86_64")
    conda = FakeConda(sh, stub)
    prefix = conda.root / "envs" / "swane-env"
    _old_swane_python(stub, prefix / "bin" / "python", version, error)
    make_executable(prefix / "bin" / "dot", "exit 0")
    conda.set_envs(prefix)
    result = _ensure(sh, conda)
    assert result.returncode == 1
    shown = version or "unknown version"
    if too_old:
        assert SWANE_TOO_OLD % shown in result.stderr
    else:
        assert "too old" not in result.stderr
        # The whole Python output, then the error line in the message.
        assert "Traceback (most recent call last):\n%s\n" % error in result.stderr
        assert (
            "ERROR: The installed SWANe (%s) cannot be imported in swane-env: %s\n"
            % (shown, error)
        ) in result.stderr
    assert result.stdout == ""


def test_create_failure_dies_before_pip(sh, stub):
    stub.platform("Linux", "x86_64")
    conda = FakeConda(sh, stub, create_exit=1)
    result = _ensure(sh, conda)
    assert result.returncode == 1
    assert "Could not create the swane-env environment" in result.stderr
    assert not (conda.new_prefix / "bin" / "python").exists()
    assert [call for call in stub.calls() if "pip" in call] == []


def test_pip_failure_dies(sh, stub):
    stub.platform("Linux", "x86_64")
    conda = FakeConda(sh, stub)
    prefix = conda.root / "envs" / "swane-env"
    stub.script(
        prefix / "bin" / "python",
        "python",
        '[ "$1" = -c ] && echo 3.12 || exit 1',
    )
    make_executable(prefix / "bin" / "dot", "exit 0")
    conda.set_envs(prefix)
    result = _ensure(sh, conda)
    assert result.returncode == 1
    assert "pip install -U swane failed" in result.stderr


def test_unreadable_env_list_dies_without_creating(sh, stub):
    stub.platform("Linux", "x86_64")
    conda = FakeConda(sh, stub)
    conda.envs_json.write_text("not json")
    result = _ensure(sh, conda)
    assert result.returncode == 1
    assert "Could not list the conda environments" in result.stderr
    assert conda.conda_calls("create") == []


# ---------------------------------------------------------------------------
# FSL
# ---------------------------------------------------------------------------

FSL_CHANNEL = "https://fsl.fmrib.ox.ac.uk/fsldownloads/fslconda/public/"
FSL_CHANNELS = (
    "--override-channels --strict-channel-priority -c %s -c conda-forge" % FSL_CHANNEL
)
FSL_SPECS = "fsl-bet2=2.1 fsl-installer=3.21.0 python=3.12.1"
FSL_LICENSE_URL = "https://fsl.fmrib.ox.ac.uk/fsl/docs/license.html"
#: The licence notice shown before every FSL licence acceptance.
FSL_LICENSE_NOTICE = (
    "==> FSL is free for non-commercial use only, under its own licence.\n"
    "==> Installing FSL means accepting the FSL licence: read it first at %s\n"
    % FSL_LICENSE_URL
)
#: The hint shown only when the licence is accepted at the terminal.
FSL_DECLINE_HINT = "If you do not accept it, answer anything but yes"
NEEDS_FSL = (
    "SWANe needs FSL; rerun the installer or install FSL from fsl.fmrib.ox.ac.uk"
)
#: The variables the hooks use, all of which must be gone after deactivation
#: (except ``_SWANE_FSL_LEFT``, kept on purpose for a following
#: reactivation), then those of the earlier drop/re-insert hooks, which must
#: never be set at all.
HOOK_VARIABLES = (
    "_SWANE_FSL_ACTIVE",
    "_SWANE_FSL_ADDED",
    "_SWANE_FSL_ENTRY",
    "_SWANE_OLD_FSLDIR",
    "_SWANE_OLD_FSLOUTPUTTYPE",
    "_SWANE_P",
    "_SWANE_FSL_BIN",
    "_SWANE_FSL_OWNED",
    "_SWANE_FSL_DROPPED",
    "_SWANE_FSL_KEPT",
    "_SWANE_FSL_LEFT_DROPPED",
    "_SWANE_FSL_LEFT_KEPT",
    "_SWANE_FSL_LEFT_FROM",
    "_SWANE_OLD_PATH",
    "_SWANE_NEW_PATH",
)


#: The wrappers an FSL must have (FSL_REQUIRED_WRAPPERS of the installer).
REQUIRED_WRAPPERS = ("bet", "flirt", "fsl-cluster")


def _make_fsl(path, version, marker=False, wrappers=True):
    """A fake FSL directory: ``etc/fslversion`` (and the installer's marker).

    With ``wrappers`` it also has FSL's command wrappers
    ``share/fsl/bin/{bet,flirt,fsl-cluster}``, without which the installer
    does not use an FSL.
    """
    (path / "etc").mkdir(parents=True, exist_ok=True)
    (path / "etc" / "fslversion").write_text(version)
    if marker:
        (path / "etc" / "swane_installer_fsl").write_text("")
    if wrappers:
        for tool in REQUIRED_WRAPPERS:
            make_executable(path / "share" / "fsl" / "bin" / tool, "exit 0")
    return path


#: The conda-meta records :func:`_fake_fsl_solver` writes: (record file,
#: channel, url, files). The FSL channel is written in each of its forms
#: (with and without the platform subdir, only in the url); the decoy's
#: channel merely starts with the same text.
FAKE_FSL_RECORDS = (
    (
        "fsl-bet2-2.1-0",
        FSL_CHANNEL + "linux-64",
        FSL_CHANNEL + "linux-64/fsl-bet2-2.1-0.conda",
        ["bin/bet", "share/fsl/doc/bet.txt"],
    ),
    (
        "fsl-flirt-2.0-0",
        FSL_CHANNEL.rstrip("/"),
        "",
        ["bin/flirt", "bin/.hidden", "bin/sub/inner", "lib/libflirt.so"],
    ),
    (
        "fsl-cluster-2.0-0",
        "",
        FSL_CHANNEL + "noarch/fsl-cluster-2.0-0.conda",
        ["bin/fsl-cluster", "bin/smoothest"],
    ),
    (
        "fsl-installer-3.21.0-0",
        FSL_CHANNEL + "noarch",
        "",
        ["bin/createFSLWrapper", "bin/removeFSLWrapper"],
    ),
    (
        "graphviz-12.0.0-0",
        "https://conda.anaconda.org/conda-forge/linux-64",
        "",
        ["bin/cluster", "bin/dot"],
    ),
    ("python-3.12.1-0", "https://conda.anaconda.org/conda-forge/linux-64", "", []),
    (
        "decoy-1-0",
        "https://fsl.fmrib.ox.ac.uk/fsldownloads/fslconda/publicity/linux-64",
        "",
        ["bin/decoy"],
    ),
)
#: The programs of the FSL-channel records above, in the order passed to
#: createFSLWrapper.
FSL_PROGRAMS = (
    "bet",
    "createFSLWrapper",
    "flirt",
    "fsl-cluster",
    "removeFSLWrapper",
    "smoothest",
)
#: Where the fake createFSLWrapper logs what it saw, one line per call.
WRAPPER_LOG = "calls.log.wrapper-env"


def _fake_fsl_solver(sh, stub):
    """A script ``fill-fsl PREFIX`` that fills PREFIX as an FSL solve would.

    Executables in ``bin`` (FSL's, graphviz's ``cluster`` and ``dot``,
    ``python``, a hidden and a nested one, the decoy), the
    :data:`FAKE_FSL_RECORDS` in ``conda-meta`` (plus a ``history`` file that
    is not JSON), and ``bin/createFSLWrapper`` (logged as
    ``createFSLWrapper``) unless ``FAKE_NO_CREATE_WRAPPER`` is set.

    The fake createFSLWrapper appends ``FSLDIR|PREFIX|FSL_CREATE_WRAPPER_SCRIPTS
    |PYTHONNOUSERSITE|<etc/fslversion>|<marker>`` to :data:`WRAPPER_LOG`, and
    prints a line on stdout. Like the real one (ledger probe) it does nothing
    unless FSL_CREATE_WRAPPER_SCRIPTS and PREFIX are set, wraps any name found
    in ``$FSLDIR/bin``, skips existing wrappers and always exits 0; names in
    ``FAKE_WRAPPER_SKIP`` (space-separated) are skipped.
    """
    wrapper = stub.script(
        sh.tmp / "createFSLWrapper-template",
        "createFSLWrapper",
        'version="$(cat "$FSLDIR/etc/fslversion" 2>/dev/null || echo none)"\n'
        'marker=none; [ -e "$FSLDIR/etc/swane_installer_fsl" ] && marker=marker\n'
        'printf "%s|%s|%s|%s|%s|%s\\n" "${FSLDIR-<unset>}" "${PREFIX-<unset>}" '
        '"${FSL_CREATE_WRAPPER_SCRIPTS-<unset>}" "${PYTHONNOUSERSITE-<unset>}" '
        '"$version" "$marker" >> "$CALLS_LOG.wrapper-env"\n'
        "echo createFSLWrapper output\n"
        '[ -n "${FSL_CREATE_WRAPPER_SCRIPTS:-}" ] && [ -n "${PREFIX:-}" ] || exit 0\n'
        'mkdir -p "$FSLDIR/share/fsl/bin"\n'
        'for name in "$@"; do\n'
        '    case " ${FAKE_WRAPPER_SKIP:-} " in *" $name "*) continue ;; esac\n'
        '    [ -e "$FSLDIR/bin/$name" ] || continue\n'
        '    [ -e "$FSLDIR/share/fsl/bin/$name" ] && continue\n'
        '    printf "#!/bin/sh\\nexec \'%s/bin/%s\' \\"\\$@\\"\\n" "$FSLDIR" "$name" '
        '> "$FSLDIR/share/fsl/bin/$name"\n'
        '    chmod 755 "$FSLDIR/share/fsl/bin/$name"\n'
        "done\n"
        "exit 0",
    )
    lines = [
        'prefix="$1"',
        'mkdir -p "$prefix/bin/sub" "$prefix/conda-meta"',
        "for name in bet flirt fsl-cluster smoothest removeFSLWrapper .hidden "
        "sub/inner cluster dot python decoy; do",
        '    printf "#!/bin/sh\\necho %s\\n" "$name" > "$prefix/bin/$name"',
        '    chmod 755 "$prefix/bin/$name"',
        "done",
        '[ -n "${FAKE_NO_CREATE_WRAPPER:-}" ] || '
        'cp %s "$prefix/bin/createFSLWrapper"' % bash_quote(str(wrapper)),
        'echo "not json" > "$prefix/conda-meta/history"',
    ]
    for name, channel, url, files in FAKE_FSL_RECORDS:
        record = {"name": name.rsplit("-", 2)[0], "files": files}
        if channel:
            record["channel"] = channel
        if url:
            record["url"] = url
        lines.append(
            "printf '%%s' %s > \"$prefix/conda-meta/%s.json\""
            % (bash_quote(json.dumps(record)), name)
        )
    return make_executable(sh.tmp / "fill-fsl", "\n".join(lines))


#: The env Python's case for the conda-meta reader (``python -I -``, the
#: program on stdin): run by the real interpreter.
ENV_PYTHON_STDIN_CASE = '    "-I - "*) exec %s "$@" ;;\n' % bash_quote(sys.executable)


class FslWorld:
    """A conda root with a ``swane-env`` for the FSL step.

    The env's ``bin/python`` (logged as ``env-python``) fakes the SWANe
    installed in it: ``-m swane.utils.fsl_conda --format github`` prints
    release 6.0.7.8 and ``specs`` (default :data:`FSL_SPECS`), the
    ``min_fsl_version`` code prints 6.0.7.8, ``-I -`` (the conda-meta reader)
    runs the real Python; anything else fails. Each call appends its
    ``PYTHONNOUSERSITE`` to ``<python>.nousersite``.

    The root's ``bin/conda`` (logged as ``conda``) prints :attr:`envs_json`
    for ``env list --json``; ``create`` makes :attr:`fsl_prefix` and lists it.
    ``create`` and ``install -p PREFIX`` fill the FSL prefix as an FSL solve
    would (:func:`_fake_fsl_solver`).
    """

    def __init__(self, sh, stub, resolver_exit=0, specs=FSL_SPECS, install_dir=None):
        self.sh = sh
        self.stub = stub
        self.root = make_conda_root(sh.tmp / "conda root")
        make_executable(
            self.root / "bin" / "python", 'exec %s "$@"' % bash_quote(sys.executable)
        )
        # With ``install_dir`` (--install-dir) both envs live there.
        base = install_dir or self.root / "envs"
        self.env = base / "swane-env"
        self.fsl_prefix = base / "swane-fsl"
        self.envs_json = sh.tmp / "envs.json"
        self.set_envs()
        self.python = self.env / "bin" / "python"
        stub.script(
            self.python,
            "env-python",
            'printf "%%s\\n" "${PYTHONNOUSERSITE:-unset}" >> "$0.nousersite"\n'
            'case "$*" in\n'
            "%s"
            '    *"-m swane.utils.fsl_conda --format github"*)\n'
            '        [ %d = 0 ] || { echo "no manifest" >&2; exit 1; }\n'
            "        printf 'release=6.0.7.8\\nplatform=linux-64\\nspecs=%s\\n' ;;\n"
            "    *min_fsl_version*) echo 6.0.7.8 ;;\n"
            "    *) exit 9 ;;\n"
            "esac" % (ENV_PYTHON_STDIN_CASE, resolver_exit, specs),
        )
        fill = _fake_fsl_solver(sh, stub)
        listed = json.dumps(
            {"envs": [str(self.root), str(self.env), str(self.fsl_prefix)]}
        )
        stub.script(
            self.root / "bin" / "conda",
            "conda",
            'case "$1" in\n'
            "    env) cat %s ;;\n"
            '    create) echo "conda create output"\n'
            "        mkdir -p %s\n"
            "        %s %s\n"
            "        printf '%%s' %s > %s ;;\n"
            '    install) echo "conda install output"\n'
            '        while [ "$#" -gt 0 ]; do\n'
            '            [ "$1" = -p ] && %s "$2"\n'
            "            shift\n"
            "        done ;;\n"
            "esac"
            % (
                bash_quote(str(self.envs_json)),
                bash_quote(str(self.fsl_prefix / "bin")),
                bash_quote(str(fill)),
                bash_quote(str(self.fsl_prefix)),
                bash_quote(listed),
                bash_quote(str(self.envs_json)),
                bash_quote(str(fill)),
            ),
        )

    @property
    def activate(self):
        return self.env / "etc" / "conda" / "activate.d" / "swane-fsl.sh"

    @property
    def deactivate(self):
        return self.env / "etc" / "conda" / "deactivate.d" / "swane-fsl.sh"

    def set_envs(self, *prefixes):
        """List the root, swane-env and ``prefixes`` in ``conda env list``."""
        envs = [str(self.root), str(self.env)] + [str(p) for p in prefixes]
        self.envs_json.write_text(json.dumps({"envs": envs}))

    def write_hook(self, fsldir):
        result = self.sh(
            "write_fsl_hook", self.env, fsldir, env={"FSLDIR": None}, tty=None
        )
        assert result.returncode == 0, result.stderr
        return result

    def hook_dir(self):
        """The FSLDIR the hook sets, or None without a hook."""
        result = self.sh("hook_written_fsldir", self.env)
        return result.stdout[:-1] if result.returncode == 0 else None

    def run(self, env=None, tty=None):
        """Run fsl_step; return the result and the published FSL_RESULT_*."""
        result = self.sh.code(
            'fsl_step "$ROOT" "$ENVP"\n'
            'printf "%s\\n" "$FSL_RESULT_STATE" "$FSL_RESULT_DIR" '
            '"$FSL_RESULT_VERSION"\n'
            'printf "%s" "$SUMMARY_WARNINGS"',
            env=dict({"ROOT": self.root, "ENVP": self.env}, **(env or {})),
            tty=tty,
        )
        info = {}
        if result.returncode == 0:
            lines = result.stdout.split("\n", 3)
            info = {
                "state": lines[0],
                "dir": lines[1],
                "version": lines[2],
                "warnings": lines[3],
            }
        return result, info

    def conda_calls(self):
        return self.stub.calls("conda")


def test_no_fsl_accept_installs_swane_fsl_in_install_dir(sh, stub):
    install = sh.tmp / "install dir"
    world = FslWorld(sh, stub, install_dir=install)
    result, info = world.run(env={"SWANE_INSTALL_DIR": install}, tty="y\nyes\n")
    assert result.returncode == 0, result.stderr
    # Looked up in the install dir only (conda's list is never read).
    assert world.conda_calls() == [
        "conda create -y -p %s %s %s"
        % (install / "swane-fsl", FSL_CHANNELS, FSL_SPECS),
    ]
    assert (world.fsl_prefix / "etc" / "swane_installer_fsl").is_file()
    assert world.hook_dir() == str(install / "swane-fsl")
    assert info["state"] == "installed"
    assert info["dir"] == str(install / "swane-fsl")


def test_swane_fsl_in_install_dir_is_updated_not_recreated(sh, stub):
    install = sh.tmp / "install"
    world = FslWorld(sh, stub, install_dir=install)
    first, _ = world.run(env={"SWANE_INSTALL_DIR": install}, tty="y\nyes\n")
    assert first.returncode == 0, first.stderr
    stub.calls_log.write_text("")
    second, info = world.run(env={"SWANE_INSTALL_DIR": install})
    assert second.returncode == 0, second.stderr
    assert not any(" create " in call for call in world.conda_calls())
    assert info["dir"] == str(install / "swane-fsl")


def test_no_fsl_accept_installs_swane_fsl(sh, stub):
    world = FslWorld(sh, stub)
    result, info = world.run(tty="y\nyes\n")
    assert result.returncode == 0, result.stderr
    # Looked up by name first (no swane-fsl yet), then found after create.
    assert world.conda_calls() == [
        "conda env list --json",
        "conda create -y -n swane-fsl %s %s" % (FSL_CHANNELS, FSL_SPECS),
        "conda env list --json",
    ]
    assert "defaults" not in stub.calls_log.read_text()
    assert (world.fsl_prefix / "etc" / "fslversion").read_text() == "6.0.7.8\n"
    assert (world.fsl_prefix / "etc" / "swane_installer_fsl").is_file()
    assert world.hook_dir() == str(world.fsl_prefix)
    assert info == {
        "state": "installed",
        "dir": str(world.fsl_prefix),
        "version": "6.0.7.8",
        "warnings": "",
    }
    # The licence notice came between the install question and the
    # acceptance prompt; no licence file is looked up or shown.
    question = result.stderr.index("Install a minimal FSL")
    notice = result.stderr.index(FSL_LICENSE_NOTICE)
    hint = result.stderr.index(FSL_DECLINE_HINT)
    prompt = result.stderr.index("Type yes to accept the FSL licence: ")
    assert question < notice < hint < prompt
    assert "licenses" not in stub.calls_log.read_text()
    assert "fsl.txt" not in result.stderr
    assert "conda create output" in result.stderr
    assert "conda create output" not in result.stdout


def test_swane_python_runs_isolated_without_user_site(sh, stub):
    world = FslWorld(sh, stub)
    result, _ = world.run(tty="y\nyes\n")
    assert result.returncode == 0, result.stderr
    calls = stub.calls("env-python")
    assert len(calls) == 3
    assert all(call.split()[1] == "-I" for call in calls)
    assert calls[1] == "env-python -I -m swane.utils.fsl_conda --format github"
    # The conda-meta reader of the wrapper step (its program on stdin).
    assert calls[2] == "env-python -I - %s %s" % (FSL_CHANNEL, world.fsl_prefix)
    nousersite = world.python.with_name("python.nousersite").read_text()
    assert nousersite == "1\n1\n1\n"


def _wrapper_log(stub):
    """The lines the fake createFSLWrapper logged (see _fake_fsl_solver)."""
    path = stub.dir / WRAPPER_LOG
    return path.read_text().splitlines() if path.exists() else []


def test_install_wraps_only_the_programs_of_fsl_packages(sh, stub):
    """createFSLWrapper gets the bin/ programs of FSL-channel records only."""
    world = FslWorld(sh, stub)
    result, info = world.run(tty="y\nyes\n")
    assert result.returncode == 0, result.stderr
    prefix = world.fsl_prefix
    assert stub.calls("createFSLWrapper") == [
        "createFSLWrapper " + " ".join(FSL_PROGRAMS)
    ]
    # The variables createFSLWrapper needs (it does nothing without
    # FSL_CREATE_WRAPPER_SCRIPTS and PREFIX), before etc/fslversion and the
    # marker exist.
    assert _wrapper_log(stub) == ["%s|%s|1|1|none|none" % (prefix, prefix)]
    wrappers = prefix / "share" / "fsl" / "bin"
    assert sorted(p.name for p in wrappers.iterdir()) == sorted(FSL_PROGRAMS)
    # graphviz's cluster is neither wrapped nor replaced (nipype runs
    # fsl-cluster); python, dot, the hidden, nested and decoy programs are
    # not wrapped either.
    assert (prefix / "bin" / "cluster").read_text().endswith("echo cluster\n")
    assert not (prefix / "bin" / "cluster").is_symlink()
    assert "createFSLWrapper output" in result.stderr
    assert "createFSLWrapper output" not in result.stdout
    assert info["state"] == "installed"
    assert (prefix / "etc" / "fslversion").read_text() == "6.0.7.8\n"


def test_update_runs_the_wrapper_step_too(sh, stub):
    world = FslWorld(sh, stub)
    _make_fsl(world.fsl_prefix, "6.0.7.1\n", marker=True)
    world.set_envs(world.fsl_prefix)
    world.write_hook(world.fsl_prefix)
    result, info = world.run()
    assert result.returncode == 0, result.stderr
    prefix = world.fsl_prefix
    assert stub.calls("createFSLWrapper") == [
        "createFSLWrapper " + " ".join(FSL_PROGRAMS)
    ]
    # After "conda install", before the new etc/fslversion is written.
    assert _wrapper_log(stub) == ["%s|%s|1|1|6.0.7.1|marker" % (prefix, prefix)]
    calls = stub.calls()
    assert calls.index(
        "conda install -y -p %s %s %s" % (prefix, FSL_CHANNELS, FSL_SPECS)
    ) < calls.index("createFSLWrapper " + " ".join(FSL_PROGRAMS))
    for tool in ("bet", "flirt", "fsl-cluster"):
        assert os.access(prefix / "share" / "fsl" / "bin" / tool, os.X_OK)
    assert info["state"] == "updated"
    assert (prefix / "etc" / "fslversion").read_text() == "6.0.7.8\n"


@pytest.mark.parametrize("tool", ["bet", "flirt", "fsl-cluster"])
def test_missing_wrapper_after_create_fsl_wrapper_dies(sh, stub, tool):
    """createFSLWrapper exits 0 whatever happened: the result is checked."""
    world = FslWorld(sh, stub)
    result, _ = world.run(env={"FAKE_WRAPPER_SKIP": tool}, tty="y\nyes\n")
    assert result.returncode == 1
    assert (
        "createFSLWrapper did not create %s/share/fsl/bin/%s" % (world.fsl_prefix, tool)
    ) in result.stderr
    # Not marked as done: no fslversion, no marker, no hook.
    assert not (world.fsl_prefix / "etc" / "fslversion").exists()
    assert not (world.fsl_prefix / "etc" / "swane_installer_fsl").exists()
    assert not world.activate.exists()


def test_missing_create_fsl_wrapper_dies(sh, stub):
    world = FslWorld(sh, stub)
    result, _ = world.run(env={"FAKE_NO_CREATE_WRAPPER": "1"}, tty="y\nyes\n")
    assert result.returncode == 1
    assert (
        "No createFSLWrapper in %s/bin (package fsl-installer)" % world.fsl_prefix
    ) in result.stderr
    assert not (world.fsl_prefix / "etc" / "swane_installer_fsl").exists()
    assert not world.activate.exists()


@pytest.mark.parametrize(
    "specs", [FSL_SPECS, "fsl-bet2=2.1 python=3.12.1"], ids=["listed", "unlisted"]
)
def test_resolver_specs_are_passed_unchanged(sh, stub, specs):
    """The resolver is the only source of the specs (fsl-installer included)."""
    world = FslWorld(sh, stub, specs=specs)
    result, _ = world.run(tty="y\nyes\n")
    assert result.returncode == 0, result.stderr
    (create,) = [c for c in world.conda_calls() if c.startswith("conda create")]
    assert create == "conda create -y -n swane-fsl %s %s" % (FSL_CHANNELS, specs)


@pytest.mark.parametrize("tool", REQUIRED_WRAPPERS)
@pytest.mark.parametrize("how", ["missing", "not_executable"])
def test_existing_fsl_without_wrappers_is_not_used(sh, stub, tool, how):
    """The hook never puts $FSLDIR/bin on PATH."""
    world = FslWorld(sh, stub)
    external = _make_fsl(sh.home / "fsl", "6.0.7.16\n")
    make_executable(external / "bin" / tool, "exit 0")
    wrapper = external / "share" / "fsl" / "bin" / tool
    wrapper.unlink()
    if how == "not_executable":
        wrapper.write_text("")
    result, info = world.run(env={"FSLDIR": None}, tty="y\nyes\n")
    assert result.returncode == 0, result.stderr
    assert "conda create -y -n swane-fsl %s %s" % (FSL_CHANNELS, FSL_SPECS) in (
        world.conda_calls()
    )
    assert world.hook_dir() == str(world.fsl_prefix)
    assert info["state"] == "installed"
    assert (
        "FSL 6.0.7.16 in %s lacks the FSL command wrappers bet flirt fsl-cluster "
        "(executables in %s/share/fsl/bin;" % (external, external)
    ) in info["warnings"]
    assert "left untouched" in info["warnings"]
    assert not (external / "etc" / "swane_installer_fsl").exists()


@pytest.mark.parametrize("missing", ["all", "flirt", "fsl-cluster"])
def test_installer_fsl_without_wrappers_is_updated(sh, stub, missing):
    """A swane-fsl made before the wrapper step, or that lost one, is repaired."""
    world = FslWorld(sh, stub)
    _make_fsl(world.fsl_prefix, "6.0.7.8\n", marker=True, wrappers=missing != "all")
    if missing != "all":
        (world.fsl_prefix / "share" / "fsl" / "bin" / missing).unlink()
    world.set_envs(world.fsl_prefix)
    world.write_hook(world.fsl_prefix)
    result, info = world.run()
    assert result.returncode == 0, result.stderr
    assert world.conda_calls() == [
        "conda install -y -p %s %s %s" % (world.fsl_prefix, FSL_CHANNELS, FSL_SPECS)
    ]
    assert "lacks the FSL command wrappers bet flirt fsl-cluster" in result.stderr
    for tool in REQUIRED_WRAPPERS:
        assert os.access(world.fsl_prefix / "share" / "fsl" / "bin" / tool, os.X_OK)
    assert info["state"] == "updated"
    assert info["warnings"] == ""


def test_fsldir_without_wrappers_keeps_the_installers_swane_fsl(sh, stub):
    world = FslWorld(sh, stub)
    external = _make_fsl(sh.tmp / "fsl no wrappers", "6.0.7.16\n", wrappers=False)
    _make_fsl(world.fsl_prefix, "6.0.7.8\n", marker=True)
    world.write_hook(world.fsl_prefix)
    result, info = world.run(env={"FSLDIR": external})
    assert result.returncode == 0, result.stderr
    assert world.conda_calls() == []
    assert "Leaving FSL 6.0.7.16 in %s aside" % external in result.stderr
    assert world.hook_dir() == str(world.fsl_prefix)
    assert info["state"] == "existing"
    assert info["warnings"] == ""


@pytest.mark.parametrize("answer", ["y", "Y", "Yes", "YES", "no", ""])
def test_licence_requires_literal_yes(sh, stub, answer):
    world = FslWorld(sh, stub)
    result, info = world.run(tty="y\n%s\n" % answer)
    assert result.returncode == 0, result.stderr
    assert world.conda_calls() == []
    assert FSL_LICENSE_NOTICE in result.stderr
    assert "licence not accepted" in result.stderr
    assert info["state"] == "skipped"
    assert info["dir"] == ""
    assert info["warnings"] == NEEDS_FSL
    assert not world.activate.exists()
    assert not world.deactivate.exists()


def test_declining_the_install_skips_before_the_licence(sh, stub):
    world = FslWorld(sh, stub)
    result, info = world.run(tty="n\n")
    assert result.returncode == 0, result.stderr
    assert world.conda_calls() == []
    assert FSL_LICENSE_URL not in result.stderr
    assert info["state"] == "skipped"
    assert info["warnings"] == NEEDS_FSL


def test_assume_yes_does_not_accept_the_licence(sh, stub):
    world = FslWorld(sh, stub)
    # --yes answers the install question only: the licence line is read.
    result, info = world.run(env={"ASSUME_YES": "1"}, tty="y\n")
    assert result.returncode == 0, result.stderr
    assert world.conda_calls() == []
    assert info["state"] == "skipped"
    # Without a terminal there is nobody to accept it.
    sh.tty_path.unlink()
    result, _ = world.run(env={"ASSUME_YES": "1"})
    assert result.returncode == 1
    assert "--accept-fsl-license" in result.stderr
    assert world.conda_calls() == []


def test_accept_fsl_license_flag_needs_no_terminal(sh, stub):
    world = FslWorld(sh, stub)
    result, info = world.run(env={"ASSUME_YES": "1", "ACCEPT_FSL_LICENSE": "1"})
    assert result.returncode == 0, result.stderr
    assert "conda create -y -n swane-fsl %s %s" % (FSL_CHANNELS, FSL_SPECS) in (
        world.conda_calls()
    )
    assert info["state"] == "installed"
    # The notice is printed even when the licence is accepted by flag; the
    # hint about answering at the terminal is not.
    assert FSL_LICENSE_NOTICE + "==> FSL licence accepted (--accept-fsl-license)\n" in (
        result.stderr
    )
    assert FSL_DECLINE_HINT not in result.stderr


def test_no_fsl_flag_skips(sh, stub):
    world = FslWorld(sh, stub)
    _make_fsl(sh.home / "fsl", "6.0.7.16\n")
    # No terminal file: any prompt would die.
    result, info = world.run(env={"NO_FSL": "1"})
    assert result.returncode == 0, result.stderr
    assert stub.calls() == []
    assert info["state"] == "skipped"
    assert info["warnings"] == NEEDS_FSL
    assert not world.activate.exists()


def test_no_fsl_flag_keeps_a_valid_hook_and_drops_a_stale_one(sh, stub):
    world = FslWorld(sh, stub)
    fsl = _make_fsl(sh.tmp / "fsl", "6.0.7.16\n")
    world.write_hook(fsl)
    result, info = world.run(env={"NO_FSL": "1"})
    assert result.returncode == 0, result.stderr
    assert world.hook_dir() == str(fsl)
    # swane-env still uses that FSL: reported as existing, not skipped.
    assert info == {
        "state": "existing",
        "dir": str(fsl),
        "version": "6.0.7.16",
        "warnings": "",
    }
    assert stub.calls() == []
    (fsl / "etc" / "fslversion").unlink()
    result, info = world.run(env={"NO_FSL": "1"})
    assert result.returncode == 0, result.stderr
    assert not world.activate.exists()
    assert not world.deactivate.exists()
    assert info["warnings"] == NEEDS_FSL


def test_existing_recent_fsl_is_wired_not_installed(sh, stub):
    world = FslWorld(sh, stub)
    fsl = _make_fsl(sh.home / "fsl", "6.0.7.16\n")
    result, info = world.run(env={"FSLDIR": None})
    assert result.returncode == 0, result.stderr
    assert world.conda_calls() == []
    assert world.hook_dir() == str(fsl)
    assert info == {
        "state": "existing",
        "dir": str(fsl),
        "version": "6.0.7.16",
        "warnings": "",
    }


def test_fslversion_with_hash_suffix(sh, stub):
    world = FslWorld(sh, stub)
    fsl = _make_fsl(sh.home / "fsl", "6.0.7.16:abcd1234\n")
    result, info = world.run()
    assert result.returncode == 0, result.stderr
    assert world.conda_calls() == []
    assert world.hook_dir() == str(fsl)
    assert info["state"] == "existing"
    # Reported as written.
    assert info["version"] == "6.0.7.16:abcd1234"


@pytest.mark.parametrize(
    "content, expected",
    [
        ("6.0.7.8\n", True),
        ("6.0.7.8", True),
        ("6.0.7.16:abcd1234\n", True),
        ("6.0.7.9\nsecond line 1.0\n", True),
        ("6.1\n", True),
        ("7.0.0\n", True),
        ("6.0.7.1\n", False),
        ("6.0.7\n", False),
        ("6.0.6.5:1234\n", False),
        # Only the part before ":" is a version (the 9 is not a fourth number).
        ("6.0.7:1234.9\n", False),
        ("\n", False),
        ("", False),
        ("not a version\n", False),
        (None, False),
    ],
)
def test_fsl_version_ge(sh, content, expected):
    fsl = sh.tmp / "fsl"
    fsl.mkdir()
    if content is not None:
        _make_fsl(fsl, content)
    result = sh("fsl_version_ge", fsl, "6.0.7.8")
    assert (result.returncode == 0) is expected
    assert result.stderr == ""


def test_find_existing_fsl_order(sh, stub):
    world = FslWorld(sh, stub)
    fsldir = _make_fsl(sh.tmp / "fsldir", "6.0.7.8\n")
    hooked = _make_fsl(sh.tmp / "hooked fsl", "6.0.7.8\n")
    home = _make_fsl(sh.home / "fsl", "6.0.7.8\n")
    system_a = sh.tmp / "system-a"
    system_b = _make_fsl(sh.tmp / "system-b", "6.0.7.8\n")
    world.write_hook(hooked)
    env = {
        "FSLDIR": fsldir,
        "SWANE_SYSTEM_FSL_DIRS": "%s %s" % (system_a, system_b),
    }

    def found():
        result = sh("find_existing_fsl", world.env, env=env)
        return result.stdout[:-1] if result.returncode == 0 else None

    assert found() == str(fsldir)
    # $FSLDIR without etc/fslversion is no FSL.
    (fsldir / "etc" / "fslversion").unlink()
    assert found() == str(hooked)
    (hooked / "etc" / "fslversion").unlink()
    assert found() == str(home)
    (home / "etc" / "fslversion").unlink()
    assert found() == str(system_b)
    (system_b / "etc" / "fslversion").unlink()
    assert found() is None


def test_old_installer_fsl_is_updated(sh, stub):
    world = FslWorld(sh, stub)
    _make_fsl(world.fsl_prefix, "6.0.7.1\n", marker=True)
    world.set_envs(world.fsl_prefix)
    world.write_hook(world.fsl_prefix)
    # No terminal: a prompt would die.
    result, info = world.run()
    assert result.returncode == 0, result.stderr
    assert world.conda_calls() == [
        "conda install -y -p %s %s %s" % (world.fsl_prefix, FSL_CHANNELS, FSL_SPECS)
    ]
    assert (world.fsl_prefix / "etc" / "fslversion").read_text() == "6.0.7.8\n"
    assert world.hook_dir() == str(world.fsl_prefix)
    assert info["state"] == "updated"
    assert info["version"] == "6.0.7.8"
    assert info["warnings"] == ""


def test_old_installer_fsl_in_fsldir_is_updated_by_prefix(sh, stub):
    world = FslWorld(sh, stub)
    fsl = _make_fsl(sh.tmp / "elsewhere" / "swane-fsl", "6.0.7.1\n", marker=True)
    result, info = world.run(env={"FSLDIR": fsl})
    assert result.returncode == 0, result.stderr
    assert world.conda_calls() == [
        "conda install -y -p %s %s %s" % (fsl, FSL_CHANNELS, FSL_SPECS)
    ]
    assert world.hook_dir() == str(fsl)
    assert info["state"] == "updated"


def test_old_external_fsl_untouched_and_swane_fsl_installed(sh, stub):
    world = FslWorld(sh, stub)
    external = _make_fsl(sh.home / "fsl", "6.0.6\n")
    result, info = world.run(tty="y\nyes\n")
    assert result.returncode == 0, result.stderr
    assert "conda create -y -n swane-fsl %s %s" % (FSL_CHANNELS, FSL_SPECS) in (
        world.conda_calls()
    )
    assert world.hook_dir() == str(world.fsl_prefix)
    assert (external / "etc" / "fslversion").read_text() == "6.0.6\n"
    assert sorted(p.name for p in (external / "etc").iterdir()) == ["fslversion"]
    assert info["state"] == "installed"
    assert "older than 6.0.7.8" in info["warnings"]
    assert str(external) in info["warnings"]


def test_old_external_fsldir_keeps_the_installers_swane_fsl(sh, stub):
    """A re-run with an old FSL sourced: the swane-fsl of the hook is kept."""
    world = FslWorld(sh, stub)
    external = _make_fsl(sh.tmp / "old fsl", "6.0.6\n")
    _make_fsl(world.fsl_prefix, "6.0.7.8\n", marker=True)
    world.write_hook(world.fsl_prefix)
    result, info = world.run(env={"FSLDIR": external})
    assert result.returncode == 0, result.stderr
    assert world.conda_calls() == []
    assert world.hook_dir() == str(world.fsl_prefix)
    assert info["state"] == "existing"
    assert info["dir"] == str(world.fsl_prefix)


@pytest.mark.parametrize("still_listed", [False, True])
def test_hook_to_deleted_fsl_counts_as_absent(sh, stub, still_listed):
    """Review Focus 4: swane-fsl removed by hand, the hook still points at it."""
    world = FslWorld(sh, stub)
    _make_fsl(world.fsl_prefix, "6.0.7.8\n", marker=True)
    world.write_hook(world.fsl_prefix)
    for path in sorted(world.fsl_prefix.rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    world.fsl_prefix.rmdir()
    if still_listed:
        world.set_envs(world.fsl_prefix)
    result = sh("find_existing_fsl", world.env)
    assert result.returncode == 1
    result, info = world.run(tty="y\nyes\n")
    assert result.returncode == 0, result.stderr
    assert "conda create -y -n swane-fsl %s %s" % (FSL_CHANNELS, FSL_SPECS) in (
        world.conda_calls()
    )
    assert world.hook_dir() == str(world.fsl_prefix)
    assert info["state"] == "installed"


def test_rerun_with_swane_env_active_after_swane_fsl_was_deleted(sh, stub):
    """The active hook exports FSLDIR=<deleted swane-fsl>: the new one is found."""
    world = FslWorld(sh, stub)
    world.write_hook(world.fsl_prefix)
    result, info = world.run(env={"FSLDIR": world.fsl_prefix}, tty="y\nyes\n")
    assert result.returncode == 0, result.stderr
    assert "conda create -y -n swane-fsl %s %s" % (FSL_CHANNELS, FSL_SPECS) in (
        world.conda_calls()
    )
    assert (world.fsl_prefix / "etc" / "swane_installer_fsl").is_file()
    assert world.hook_dir() == str(world.fsl_prefix)
    assert info["state"] == "installed"


def test_declined_install_removes_a_stale_hook(sh, stub):
    world = FslWorld(sh, stub)
    world.write_hook(sh.tmp / "deleted fsl")
    assert world.activate.exists()
    result, info = world.run(tty="n\n")
    assert result.returncode == 0, result.stderr
    assert not world.activate.exists()
    assert not world.deactivate.exists()
    assert info["state"] == "skipped"
    assert info["warnings"] == NEEDS_FSL


def test_foreign_swane_fsl_env_is_not_reused(sh, stub):
    world = FslWorld(sh, stub)
    (world.fsl_prefix / "bin").mkdir(parents=True)
    world.set_envs(world.fsl_prefix)
    result, _ = world.run(tty="y\nyes\n")
    assert result.returncode == 1
    assert (
        "swane-fsl exists in %s but is not marked as installed by this installer "
        "(a previous install may have failed): remove it with "
        '"%s" env remove -p "%s" and rerun'
        % (world.fsl_prefix, world.root / "bin" / "conda", world.fsl_prefix)
    ) in result.stderr
    assert [c for c in world.conda_calls() if "create" in c or "install" in c] == []


def test_resolver_failure_dies_before_conda(sh, stub):
    world = FslWorld(sh, stub, resolver_exit=1)
    result, _ = world.run(tty="y\nyes\n")
    assert result.returncode == 1
    assert "Could not resolve the FSL release" in result.stderr
    assert world.conda_calls() == []
    assert not world.activate.exists()


def test_hook_quotes_paths(sh, stub):
    """Review Focus 3: spaces, quotes and glob characters in FSLDIR survive."""
    world = FslWorld(sh, stub)
    fsl = _make_fsl(sh.tmp / "my fsl's dir $HOME `x` [a]*", "6.0.7.8\n")
    world.write_hook(fsl)
    assert world.hook_dir() == str(fsl)
    assert sh("hook_fsldir", world.env).stdout == "%s\n" % fsl
    for hook in (world.activate, world.deactivate):
        assert subprocess.run([BASH, "-n", str(hook)]).returncode == 0
    script = (
        '. "$A"; printf "%s|%s\\n" "$FSLDIR" "$PATH"; ' '. "$D"; printf "%s\\n" "$PATH"'
    )
    result = subprocess.run(
        [BASH, "-c", script],
        env={"A": str(world.activate), "D": str(world.deactivate), "PATH": "/a"},
        capture_output=True,
        text=True,
    )
    assert result.stdout.splitlines() == [
        "%s|%s/share/fsl/bin:/a" % (fsl, fsl),
        "/a",
    ]


def test_hook_never_names_fsldir_bin(sh, stub):
    """Only $FSLDIR/share/fsl/bin is ever put on PATH."""
    world = FslWorld(sh, stub)
    world.write_hook(sh.tmp / "fsl")
    lines = (world.activate.read_text() + world.deactivate.read_text()).splitlines()
    code = "\n".join(line for line in lines if not line.lstrip().startswith("#"))
    assert '_SWANE_FSL_ENTRY="$FSLDIR/share/fsl/bin"' in code
    allowed = ("$FSLDIR/share/fsl/bin", "$CONDA_PREFIX/bin")
    for text in allowed:
        code = code.replace(text, "")
    assert "/bin" not in code
    for name in ("_SWANE_FSL_BIN", "_SWANE_FSL_DROPPED", "_SWANE_OLD_PATH"):
        assert name not in code


def _hook_shells():
    shells = []
    for name in ("bash", "dash", "zsh"):
        path = shutil.which(name)
        shells.append(
            pytest.param(
                path,
                id=name,
                marks=pytest.mark.skipif(path is None, reason="%s not found" % name),
            )
        )
    return shells


#: Shell helpers of the round trip: ``drop ENTRY`` removes the first
#: occurrence of ENTRY from PATH, ``swap OLD NEW`` replaces the first OLD
#: with NEW in place (what conda does with an environment's bin).
PATH_HELPERS = (
    'drop() { _p=":$PATH:"; _p="${_p%%":$1:"*}:${_p#*":$1:"}"; '
    '_p="${_p#:}"; PATH="${_p%:}"; unset _p; }\n'
    'swap() { _p=":$PATH:"; _p="${_p%%":$1:"*}:$2:${_p#*":$1:"}"; '
    '_p="${_p#:}"; PATH="${_p%:}"; unset _p; }\n'
)
#: How conda reactivates an environment (``conda activate`` of the active
#: env, and after every ``conda install/update/remove`` in it): it computes
#: PATH first, runs the deactivate.d scripts, exports that PATH, then runs the
#: activate.d scripts (conda/activate.py ``build_reactivate``).
CONDA_REACTIVATE = '_saved="$PATH"; . "$D"; PATH="$_saved"; . "$A"; show'
#: How ``conda deactivate`` runs: it exports PATH without the env's own bin
#: first, then runs the deactivate.d scripts (``_yield_commands``).
CONDA_DROP_ENV_BIN = "drop /env/bin"

#: Scenarios of the hook round trip: shell code run before the activation,
#: code run between activation and deactivation (it may ``show``), and the
#: expected ``FSLDIR|FSLOUTPUTTYPE|PATH`` lines, one per ``show``: after the
#: activation, in between, after the deactivation. ``{dir}`` is the FSL dir,
#: ``{bin}`` its ``share/fsl/bin``.
HOOK_SCENARIOS = {
    "unset": (
        "unset FSLDIR FSLOUTPUTTYPE; PATH=/a:/b",
        "",
        ["{dir}|NIFTI_GZ|{bin}:/a:/b", "<unset>|<unset>|/a:/b"],
    ),
    "set": (
        "FSLDIR=/old; FSLOUTPUTTYPE=NIFTI; export FSLDIR FSLOUTPUTTYPE; PATH=/a",
        "",
        ["{dir}|NIFTI_GZ|{bin}:/a", "/old|NIFTI|/a"],
    ),
    "empty": (
        "FSLDIR=; export FSLDIR; unset FSLOUTPUTTYPE; PATH=/a",
        "",
        ["{dir}|NIFTI_GZ|{bin}:/a", "|<unset>|/a"],
    ),
    # The entry goes first, before swane-env's own bin (conda put it first).
    "before_env_bin": (
        "unset FSLDIR FSLOUTPUTTYPE; PATH=/env/bin:/a",
        "",
        ["{dir}|NIFTI_GZ|{bin}:/env/bin:/a", "<unset>|<unset>|/env/bin:/a"],
    ),
    # The user's own entry (FSL sourced in the shell) ahead of swane-env's
    # bin (here: swane-env's bin not on PATH) is neither duplicated, moved
    # nor removed.
    "already_on_path": (
        "unset FSLDIR FSLOUTPUTTYPE; PATH='/a:{bin}:/b'",
        "",
        ["{dir}|NIFTI_GZ|/a:{bin}:/b", "<unset>|<unset>|/a:{bin}:/b"],
    ),
    "already_ahead_of_env_bin": (
        "unset FSLDIR FSLOUTPUTTYPE; PATH='/a:{bin}:/env/bin:/b'",
        CONDA_DROP_ENV_BIN,
        ["{dir}|NIFTI_GZ|/a:{bin}:/env/bin:/b", "<unset>|<unset>|/a:{bin}:/b"],
    ),
    # The user's entry after swane-env's bin (conda put the env's bin in
    # front of it) stays, and a copy goes first; only the copy goes on
    # deactivation, also when conda rewrites PATH or reactivates.
    "already_after_env_bin": (
        "unset FSLDIR FSLOUTPUTTYPE; PATH='/env/bin:/base:{bin}:/b'",
        "",
        [
            "{dir}|NIFTI_GZ|{bin}:/env/bin:/base:{bin}:/b",
            "<unset>|<unset>|/env/bin:/base:{bin}:/b",
        ],
    ),
    "already_on_path_conda_deactivate": (
        "unset FSLDIR FSLOUTPUTTYPE; PATH='/env/bin:{bin}'",
        CONDA_DROP_ENV_BIN,
        ["{dir}|NIFTI_GZ|{bin}:/env/bin:{bin}", "<unset>|<unset>|{bin}"],
    ),
    "already_on_path_conda_reactivates": (
        "unset FSLDIR FSLOUTPUTTYPE; PATH='/env/bin:{bin}:/a'",
        "%s; %s; %s" % (CONDA_REACTIVATE, CONDA_REACTIVATE, CONDA_DROP_ENV_BIN),
        [
            "{dir}|NIFTI_GZ|{bin}:/env/bin:{bin}:/a",
            "{dir}|NIFTI_GZ|{bin}:/env/bin:{bin}:/a",
            "{dir}|NIFTI_GZ|{bin}:/env/bin:{bin}:/a",
            "<unset>|<unset>|{bin}:/a",
        ],
    ),
    # A stale _SWANE_FSL_LEFT never claims a user's entry after the env bin.
    "stale_left_entry_after_env_bin": (
        "unset FSLDIR FSLOUTPUTTYPE; _SWANE_FSL_LEFT='{bin}'; " "PATH='/env/bin:{bin}'",
        "",
        ["{dir}|NIFTI_GZ|{bin}:/env/bin:{bin}", "<unset>|<unset>|/env/bin:{bin}"],
    ),
    # conda sets PATH (dropping the env's own bin) before the deactivate.d
    # scripts run: only the entry the activation added goes.
    "conda_rewrites_path": (
        "unset FSLDIR FSLOUTPUTTYPE; PATH=/env/bin:/a",
        CONDA_DROP_ENV_BIN,
        ["{dir}|NIFTI_GZ|{bin}:/env/bin:/a", "<unset>|<unset>|/a"],
    ),
    # The added entry goes wherever it is by then; the rest stays as it is.
    "entry_moved_before_deactivate": (
        "unset FSLDIR FSLOUTPUTTYPE; PATH=/env/bin:/a",
        'drop "$FSLDIR/share/fsl/bin"; PATH="/x:$PATH:$FSLDIR/share/fsl/bin:/z"; show',
        [
            "{dir}|NIFTI_GZ|{bin}:/env/bin:/a",
            "{dir}|NIFTI_GZ|/x:/env/bin:/a:{bin}:/z",
            "<unset>|<unset>|/x:/env/bin:/a:/z",
        ],
    ),
    "entry_gone_before_deactivate": (
        "unset FSLDIR FSLOUTPUTTYPE; PATH=/env/bin:/a",
        'drop "$FSLDIR/share/fsl/bin"',
        ["{dir}|NIFTI_GZ|{bin}:/env/bin:/a", "<unset>|<unset>|/env/bin:/a"],
    ),
    "activated_twice": (
        "unset FSLDIR FSLOUTPUTTYPE; PATH=/a",
        '. "$A"',
        ["{dir}|NIFTI_GZ|{bin}:/a", "<unset>|<unset>|/a"],
    ),
    # Reactivation must not add a second entry, and the entry it keeps must
    # go on the final deactivation.
    "conda_reactivates": (
        "unset FSLDIR FSLOUTPUTTYPE; PATH=/env/bin:/a",
        "%s; %s; %s" % (CONDA_REACTIVATE, CONDA_REACTIVATE, CONDA_DROP_ENV_BIN),
        [
            "{dir}|NIFTI_GZ|{bin}:/env/bin:/a",
            "{dir}|NIFTI_GZ|{bin}:/env/bin:/a",
            "{dir}|NIFTI_GZ|{bin}:/env/bin:/a",
            "<unset>|<unset>|/a",
        ],
    ),
    "conda_reactivates_then_restores": (
        "unset FSLDIR FSLOUTPUTTYPE; PATH=/env/bin:/a",
        CONDA_REACTIVATE,
        [
            "{dir}|NIFTI_GZ|{bin}:/env/bin:/a",
            "{dir}|NIFTI_GZ|{bin}:/env/bin:/a",
            "<unset>|<unset>|/env/bin:/a",
        ],
    ),
    # Another FSL set up by the user's shell keeps every entry where it is:
    # the hook's entry simply comes first, and FSLDIR comes back.
    "old_fsl_on_path": (
        "FSLDIR=/old; export FSLDIR; unset FSLOUTPUTTYPE; "
        "PATH=/old/share/fsl/bin:/old/bin:/a",
        "",
        [
            "{dir}|NIFTI_GZ|{bin}:/old/share/fsl/bin:/old/bin:/a",
            "/old|<unset>|/old/share/fsl/bin:/old/bin:/a",
        ],
    ),
    "old_fsl_conda_deactivate": (
        "FSLDIR=/old; export FSLDIR; unset FSLOUTPUTTYPE; "
        "PATH=/env/bin:/old/share/fsl/bin:/a:/old/bin",
        CONDA_DROP_ENV_BIN,
        [
            "{dir}|NIFTI_GZ|{bin}:/env/bin:/old/share/fsl/bin:/a:/old/bin",
            "/old|<unset>|/old/share/fsl/bin:/a:/old/bin",
        ],
    ),
    # FSLDIR already names the hook's own FSL, its entry on PATH: untouched.
    "same_fsl_in_fsldir": (
        "FSLDIR='{dir}'; export FSLDIR; unset FSLOUTPUTTYPE; PATH='{bin}:/a'",
        "",
        ["{dir}|NIFTI_GZ|{bin}:/a", "{dir}|<unset>|{bin}:/a"],
    ),
    # "conda activate other" from swane-env, then back: the entry leaks into
    # "other" (a documented limitation: conda exports a PATH computed before
    # deactivate.d), is not added a second time, and goes on the final
    # deactivation.
    "conda_switches_env_and_back": (
        "unset FSLDIR FSLOUTPUTTYPE; PATH=/env/bin:/a",
        '_saved="$PATH"; . "$D"; PATH="$_saved"; swap /env/bin /other/bin; show\n'
        'swap /other/bin /env/bin; . "$A"; show\n' + CONDA_DROP_ENV_BIN,
        [
            "{dir}|NIFTI_GZ|{bin}:/env/bin:/a",
            "<unset>|<unset>|{bin}:/other/bin:/a",
            "{dir}|NIFTI_GZ|{bin}:/env/bin:/a",
            "<unset>|<unset>|/a",
        ],
    ),
}


@pytest.mark.parametrize("scenario", sorted(HOOK_SCENARIOS))
@pytest.mark.parametrize("shell", _hook_shells())
def test_hook_roundtrip_in_posix_shells(sh, stub, shell, scenario):
    """The hooks are sourced by conda in the user's shell, under ``set -u``.

    ``CONDA_PREFIX`` is ``/env``, as conda exports it before activate.d.
    """
    world = FslWorld(sh, stub)
    fsl = sh.tmp / "fsl dir"
    world.write_hook(fsl)
    before, between, expected = HOOK_SCENARIOS[scenario]

    def fill(text):
        return text.replace("{bin}", "%s/share/fsl/bin" % fsl).replace(
            "{dir}", str(fsl)
        )

    expected = [fill(line) for line in expected]
    leftovers = "".join("${%s+%s}" % (name, name) for name in HOOK_VARIABLES)
    script = (
        "set -u\n"
        "%s"
        'show() { printf "%%s|%%s|%%s\\n" "${FSLDIR-<unset>}" '
        '"${FSLOUTPUTTYPE-<unset>}" "$PATH"; }\n'
        "%s\n"
        '. "$A"\n'
        "show\n"
        "%s\n"
        '. "$D"\n'
        "show\n"
        'printf "left:%s\\n"\n' % (PATH_HELPERS, fill(before), between, leftovers)
    )
    result = subprocess.run(
        [shell, "-c", script],
        env={
            "A": str(world.activate),
            "D": str(world.deactivate),
            "PATH": "/a",
            "CONDA_PREFIX": "/env",
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines == expected + ["left:"]
    # $FSLDIR/bin (a whole conda env bin) is never put on PATH.
    for line in lines[:-1]:
        assert "%s/bin" % fsl not in line.split("|", 2)[2].split(":")


def _fsl_tool_dirs(sh, stub):
    """swane-env (python, graphviz's cluster), an old and the hook's FSL.

    The hook's FSL has ``bin/python``, ``bin/bet``, ``bin/cluster``
    (graphviz's) and the wrappers ``share/fsl/bin/bet`` and ``fsl-cluster``;
    the old FSL has bet in ``share/fsl/bin`` and ``bin``.
    """
    world = FslWorld(sh, stub)
    old = _make_fsl(sh.tmp / "old fsl", "6.0.5\n")
    new = _make_fsl(sh.tmp / "new fsl", "6.0.7.8\n")
    for path in (
        old / "bin" / "bet",
        new / "bin" / "bet",
        new / "bin" / "python",
        new / "bin" / "cluster",
        new / "share" / "fsl" / "bin" / "fsl-cluster",
        world.env / "bin" / "python",
        world.env / "bin" / "cluster",
    ):
        make_executable(path, "exit 0")
    world.write_hook(new)
    return world, old, new


@pytest.mark.parametrize("shell", _hook_shells())
def test_hook_wrappers_come_first_and_fsl_bin_stays_off_path(sh, stub, shell):
    """FSL set up by the profile, swane-env first: what each name runs."""
    world, old, new = _fsl_tool_dirs(sh, stub)
    start = "%s/bin:%s/share/fsl/bin:%s/bin:/usr/bin:/bin" % (world.env, old, old)
    script = (
        "set -u\n"
        '. "$A"\n'
        "for tool in bet fsl-cluster python cluster; do command -v $tool; done\n"
        'printf "%s\\n" "$FSLDIR"\n'
        '. "$D"\n'
        'printf "%s\\n%s\\n" "$FSLDIR" "$PATH"\n'
        "command -v bet\n"
    )
    result = subprocess.run(
        [shell, "-c", script],
        env={
            "A": str(world.activate),
            "D": str(world.deactivate),
            "PATH": start,
            "FSLDIR": str(old),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "%s/share/fsl/bin/bet" % new,
        "%s/share/fsl/bin/fsl-cluster" % new,
        # swane-env's python, never the FSL environment's; graphviz's
        # cluster of swane-env, not the FSL environment's bin/cluster.
        "%s/bin/python" % world.env,
        "%s/bin/cluster" % world.env,
        str(new),
        str(old),
        start,
        "%s/share/fsl/bin/bet" % old,
    ]


def _real_conda_sh():
    """``etc/profile.d/conda.sh`` of the conda running the tests, if any."""
    conda_exe = os.environ.get("CONDA_EXE")
    if not conda_exe:
        return None
    path = os.path.join(
        os.path.dirname(os.path.dirname(conda_exe)), "etc", "profile.d", "conda.sh"
    )
    return path if os.path.isfile(path) else None


def _fake_conda_prefix(prefix):
    """Make ``prefix`` look like a conda environment to ``conda activate``."""
    (prefix / "conda-meta").mkdir(parents=True, exist_ok=True)
    (prefix / "conda-meta" / "history").write_text("")
    (prefix / "bin").mkdir(exist_ok=True)


@pytest.mark.skipif(_real_conda_sh() is None, reason="no conda.sh (CONDA_EXE unset)")
def test_hook_with_the_real_conda_activation(sh, stub):
    """The hooks under the real ``conda activate``/``deactivate`` command order.

    Only fake prefixes are activated (nothing is installed); HOME is the
    test's own. Reactivation and a switch to another environment and back
    leave a single FSL entry, first and before swane-env's bin, removed on
    the last deactivation.
    """
    world = FslWorld(sh, stub)
    fsl = sh.tmp / "fsl dir"
    other = sh.tmp / "other-env"
    for prefix in (world.env, other):
        _fake_conda_prefix(prefix)
    world.write_hook(fsl)
    script = (
        '. "$CONDA_SH"\n'
        'show() { printf "%s|%s\\n" "${FSLDIR-<unset>}" "$PATH"; }\n'
        'conda activate "$P"; show\n'
        'conda activate "$P"; show\n'
        "conda deactivate; show\n"
        'conda activate "$P"; conda activate "$O"; show\n'
        "conda deactivate; show\n"
        "conda deactivate; show\n"
    )
    result = subprocess.run(
        [BASH, "-c", script],
        env={
            "HOME": str(sh.home),
            "PATH": str(sh.tools),
            "CONDA_SH": _real_conda_sh(),
            "P": str(world.env),
            "O": str(other),
        },
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert len(lines) == 6, result.stdout
    fsl_entry = "%s/share/fsl/bin" % fsl
    entries = [line.split("|", 1)[1].split(":") for line in lines]
    counts = [path.count(fsl_entry) for path in entries]
    # The switch to "other" keeps the entry (documented limitation).
    assert counts == [1, 1, 0, 1, 1, 0]
    assert [line.split("|", 1)[0] for line in lines] == [
        str(fsl),
        str(fsl),
        "<unset>",
        "<unset>",
        str(fsl),
        "<unset>",
    ]
    for index in (0, 1, 4):
        assert entries[index][:2] == [fsl_entry, "%s/bin" % world.env]
    assert all("%s/bin" % fsl not in path for path in entries)


@pytest.mark.skipif(_real_conda_sh() is None, reason="no conda.sh (CONDA_EXE unset)")
def test_hook_wrappers_win_with_the_real_conda_activation(sh, stub):
    """An older FSL set up by the profile, under the real ``conda activate``.

    bet is the hook's FSL's wrapper and python swane-env's while swane-env is
    active (also after a reactivation), and the final ``conda deactivate``
    gives back the PATH and FSLDIR the shell had.
    """
    world, old, new = _fsl_tool_dirs(sh, stub)
    _fake_conda_prefix(world.env)
    script = (
        '. "$CONDA_SH"\n'
        'start="$PATH"\n'
        'conda activate "$P"; command -v bet; command -v python\n'
        'conda activate "$P"; command -v bet; command -v python\n'
        "conda deactivate\n"
        '[ "$PATH" = "$start" ] && echo restored || printf "%s\\n%s\\n" "$start" "$PATH"\n'
        'printf "%s\\n" "$FSLDIR"\n'
        "command -v bet\n"
    )
    result = subprocess.run(
        [BASH, "-c", script],
        env={
            "HOME": str(sh.home),
            "PATH": "%s/share/fsl/bin:%s/bin:%s" % (old, old, sh.tools),
            "FSLDIR": str(old),
            "CONDA_SH": _real_conda_sh(),
            "P": str(world.env),
        },
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "%s/share/fsl/bin/bet" % new,
        "%s/bin/python" % world.env,
        "%s/share/fsl/bin/bet" % new,
        "%s/bin/python" % world.env,
        "restored",
        str(old),
        "%s/share/fsl/bin/bet" % old,
    ]


@pytest.mark.skipif(_real_conda_sh() is None, reason="no conda.sh (CONDA_EXE unset)")
@pytest.mark.parametrize("lead", ["", "/x:"])
def test_hook_restores_path_after_base_with_the_real_conda_activation(sh, stub, lead):
    """base active first, the profile's FSL entries right before its bin.

    conda puts swane-env's bin in place of base's and back on deactivation:
    PATH must still come back exactly.
    """
    world, old, new = _fsl_tool_dirs(sh, stub)
    _fake_conda_prefix(world.env)
    script = (
        '. "$CONDA_SH"\n'
        "conda activate base\n"
        'PATH="${LEAD}$OLD/share/fsl/bin:$OLD/bin:$PATH"\n'
        'start="$PATH"\n'
        'conda activate "$P"; command -v bet\n'
        'conda activate "$P"; command -v bet\n'
        "conda deactivate\n"
        '[ "$PATH" = "$start" ] && echo restored || printf "%s\\n%s\\n" "$start" "$PATH"\n'
        'printf "%s\\n" "$FSLDIR"\n'
    )
    result = subprocess.run(
        [BASH, "-c", script],
        env={
            "HOME": str(sh.home),
            "PATH": str(sh.tools),
            "FSLDIR": str(old),
            "OLD": str(old),
            "LEAD": lead,
            "CONDA_SH": _real_conda_sh(),
            "P": str(world.env),
        },
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "%s/share/fsl/bin/bet" % new,
        "%s/share/fsl/bin/bet" % new,
        "restored",
        str(old),
    ]


@pytest.mark.skipif(_real_conda_sh() is None, reason="no conda.sh (CONDA_EXE unset)")
def test_hook_entry_after_base_bin_with_the_real_conda_activation(sh, stub):
    """The default macOS zsh order with a reused fslinstaller FSL.

    ``~/.zprofile`` (FSL's installer) puts the FSL's share/fsl/bin on PATH,
    then ``~/.zshrc`` (conda init) activates base in front of it; conda puts
    swane-env's bin in place of base's, still in front. The activation puts
    a copy of the entry first (FSL's ``cluster`` wrapper wins over graphviz's
    in swane-env), also after a reactivation, and the deactivation removes
    only that copy: PATH and FSLDIR come back exactly.
    """
    world, _, new = _fsl_tool_dirs(sh, stub)
    make_executable(new / "share" / "fsl" / "bin" / "cluster", "exit 0")
    _fake_conda_prefix(world.env)
    entry = "%s/share/fsl/bin" % new
    script = (
        'PATH="$ENTRY:$PATH"\n'
        '. "$CONDA_SH"\n'
        "conda activate base\n"
        'start="$PATH"\n'
        'conda activate "$P"; command -v cluster; printf "%s\\n" "$PATH"\n'
        'conda activate "$P"; command -v cluster; printf "%s\\n" "$PATH"\n'
        "conda deactivate\n"
        '[ "$PATH" = "$start" ] && echo restored || printf "%s\\n%s\\n" "$start" "$PATH"\n'
        'printf "%s\\n" "$FSLDIR"\n'
        "command -v cluster\n"
    )
    result = subprocess.run(
        [BASH, "-c", script],
        env={
            "HOME": str(sh.home),
            "PATH": str(sh.tools),
            "FSLDIR": str(new),
            "ENTRY": entry,
            "CONDA_SH": _real_conda_sh(),
            "P": str(world.env),
        },
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert len(lines) == 7, result.stdout
    for index in (0, 2):
        assert lines[index] == "%s/cluster" % entry
        path = lines[index + 1].split(":")
        assert path[:2] == [entry, "%s/bin" % world.env]
        assert path.count(entry) == 2
    assert lines[4:] == ["restored", str(new), "%s/cluster" % entry]


def test_hook_activate_deactivate_roundtrip(sh, stub):
    world = FslWorld(sh, stub)
    fsl = _make_fsl(sh.tmp / "fsl", "6.0.7.8\n")
    result = sh.code(
        'write_fsl_hook "$ENVP" "$DIR"\n'
        'A="$(fsl_hook_activate "$ENVP")"\n'
        'D="$(fsl_hook_deactivate "$ENVP")"\n'
        "unset FSLDIR\n"
        "PATH=/a:/b\n"
        '. "$A"\n'
        'printf "%s|%s\\n" "${FSLDIR-<unset>}" "$PATH"\n'
        '. "$D"\n'
        'printf "%s|%s\\n" "${FSLDIR-<unset>}" "$PATH"',
        env={"ENVP": world.env, "DIR": fsl},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "%s|%s/share/fsl/bin:/a:/b" % (fsl, fsl),
        "<unset>|/a:/b",
    ]


# ---------------------------------------------------------------------------
# Launcher (~/.local/bin/swane)
# ---------------------------------------------------------------------------

MARKER_BEGIN = "# >>> SWANe installer >>>"
MARKER_END = "# <<< SWANe installer <<<"
#: The block the installer appends to the one startup file of the shell.
PATH_BLOCK = (
    "%s\n"
    'case ":$PATH:" in\n'
    '    *":$HOME/.local/bin:"*) ;;\n'
    '    *) export PATH="$HOME/.local/bin:$PATH" ;;\n'
    "esac\n"
    "%s\n" % (MARKER_BEGIN, MARKER_END)
)


class LauncherWorld:
    """A fake conda root and swane-env, and the launcher written for them.

    ``conda.sh`` defines a ``conda`` function that logs its arguments; the
    fake ``<prefix>/bin/swane`` prints what the real SWANe would see. The
    launcher is written on ``system`` (``uname -s``, Linux by default).
    """

    def __init__(self, sh, prefix_name="swane-env", system="Linux"):
        self.sh = sh
        sh.stubs.platform(system, "x86_64")
        self.root = make_conda_root(sh.tmp / "conda root")
        self.prefix = sh.tmp / prefix_name
        self.log = sh.tmp / "conda.log"
        # The unset-variable expansion fails the launcher if it ever ran
        # conda.sh under "set -u".
        (self.root / "etc" / "profile.d" / "conda.sh").write_text(
            'conda() { printf "%%s\\n" "$*" >> %s; }\n'
            ': "$SWANE_TEST_UNSET_VARIABLE"\n' % bash_quote(str(self.log))
        )
        make_executable(
            self.prefix / "bin" / "swane",
            'echo "launcher=$SWANE_LAUNCHER"\n'
            'echo "nousersite=${PYTHONNOUSERSITE-unset}"\n'
            'echo "qpa=${QT_QPA_PLATFORM-unset}"\n'
            'echo "args=$*"',
        )
        self.launcher = sh.home / ".local" / "bin" / "swane"
        data = sh.home / ".local" / "share"
        self.desktop = data / "applications" / "swane.desktop"
        self.menu_script = data / "swane" / "swane-launcher.sh"

    def write(self):
        result = self.sh("write_launcher", self.root, self.prefix)
        assert result.returncode == 0, result.stderr
        return result

    def run(self, *args, env=None):
        return subprocess.run(
            [str(self.launcher), *args],
            env=self.sh.environment(env),
            capture_output=True,
            text=True,
            timeout=30,
        )


def test_launcher_activates_and_execs(sh):
    world = LauncherWorld(sh)
    world.write()
    assert world.launcher.stat().st_mode & 0o777 == 0o755
    assert world.launcher.read_text().startswith("#!/usr/bin/env bash\n")
    result = world.run("a", "b", env={"PYTHONNOUSERSITE": None})
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "launcher=%s" % world.launcher,
        # ~/.local packages never shadow swane-env.
        "nousersite=1",
        # Qt through xcb on Linux.
        "qpa=xcb",
        "args=a b",
    ]
    assert world.log.read_text() == "activate %s\n" % world.prefix


@pytest.mark.parametrize(
    "system, given, seen",
    [
        ("Linux", None, "xcb"),
        ("Linux", "", "xcb"),
        ("Linux", "wayland", "wayland"),
        ("Linux", "offscreen", "offscreen"),
        ("Darwin", None, "unset"),
        ("Darwin", "cocoa", "cocoa"),
    ],
)
def test_launcher_qt_platform_only_on_linux_and_only_when_unset(
    sh, system, given, seen
):
    """A QT_QPA_PLATFORM of the user's always wins; macOS is untouched."""
    world = LauncherWorld(sh, system=system)
    world.write()
    text = world.launcher.read_text()
    assert ("QT_QPA_PLATFORM" in text) is (system == "Linux")
    assert subprocess.run([BASH, "-n", str(world.launcher)]).returncode == 0
    result = world.run(env={"QT_QPA_PLATFORM": given})
    assert result.returncode == 0, result.stderr
    assert "qpa=%s" % seen in result.stdout.splitlines()


def test_launcher_pins_root_and_prefix_on_single_lines(sh):
    """Task 10 reads the pinned values back with grep/source."""
    world = LauncherWorld(sh)
    world.write()
    lines = world.launcher.read_text().splitlines()
    assert "SWANE_CONDA_ROOT=%s" % bash_quote(str(world.root)) in lines
    assert "SWANE_ENV_PREFIX=%s" % bash_quote(str(world.prefix)) in lines
    assert "SWANE_LAUNCHER=%s" % bash_quote(str(world.launcher)) in lines
    pins = subprocess.run(
        [
            BASH,
            "-c",
            'eval "$(grep -E \'^SWANE_(CONDA_ROOT|ENV_PREFIX)=\' "$0")"; '
            'printf "%s\\n%s" "$SWANE_CONDA_ROOT" "$SWANE_ENV_PREFIX"',
            str(world.launcher),
        ],
        capture_output=True,
        text=True,
    )
    assert pins.stdout == "%s\n%s" % (world.root, world.prefix)


def test_launcher_is_atomic_and_replaces_the_old_one(sh):
    world = LauncherWorld(sh)
    world.write()
    first = world.launcher.read_text()
    other = LauncherWorld(sh, prefix_name="other-env")
    other.write()
    assert world.launcher.read_text() != first
    assert "other-env" in world.launcher.read_text()
    assert os.listdir(world.launcher.parent) == ["swane"]


def _write_launcher_warnings(sh, world):
    """Run write_launcher; return (result, SUMMARY_WARNINGS afterwards)."""
    result = sh.code(
        'write_launcher "$R" "$P"; printf "%s" "$SUMMARY_WARNINGS"',
        env={"R": world.root, "P": world.prefix},
    )
    assert result.returncode == 0, result.stderr
    return result, result.stdout


def _foreign_warning(launcher, backup):
    return (
        "%s was not written by the SWANe installer: it was moved to %s and "
        "replaced by the SWANe launcher" % (launcher, backup)
    )


def test_launcher_replaces_its_own_launcher_silently(sh):
    """A launcher of an earlier run (marker line) is no foreign file."""
    world = LauncherWorld(sh)
    world.write()
    result, warnings = _write_launcher_warnings(sh, world)
    assert warnings == ""
    assert "WARNING" not in result.stderr
    assert os.listdir(world.launcher.parent) == ["swane"]


def test_launcher_backs_up_a_foreign_file(sh):
    """E.g. the entry point of an old ``pip install --user swane``."""
    world = LauncherWorld(sh)
    world.launcher.parent.mkdir(parents=True)
    world.launcher.write_text("#!/usr/bin/python3\nfrom swane import main\n")
    result, warnings = _write_launcher_warnings(sh, world)
    backup = world.launcher.parent / "swane.bk"
    assert warnings == _foreign_warning(world.launcher, backup)
    assert "WARNING: %s" % warnings in result.stderr
    assert backup.read_text() == "#!/usr/bin/python3\nfrom swane import main\n"
    assert "SWANE_ENV_PREFIX=" in world.launcher.read_text()
    assert sorted(os.listdir(world.launcher.parent)) == ["swane", "swane.bk"]


def test_launcher_backs_up_a_symlink_not_its_target(sh):
    world = LauncherWorld(sh)
    target = sh.tmp / "elsewhere" / "swane"
    make_executable(target, "echo other")
    world.launcher.parent.mkdir(parents=True)
    world.launcher.symlink_to(target)
    _, warnings = _write_launcher_warnings(sh, world)
    backup = world.launcher.parent / "swane.bk"
    assert warnings == _foreign_warning(world.launcher, backup)
    assert backup.is_symlink()
    assert os.readlink(backup) == str(target)
    assert target.read_text() == "#!%s\necho other\n" % BASH
    assert not world.launcher.is_symlink()
    assert "SWANE_ENV_PREFIX=" in world.launcher.read_text()


def test_launcher_backup_takes_the_first_free_name(sh):
    world = LauncherWorld(sh)
    bin_dir = world.launcher.parent
    bin_dir.mkdir(parents=True)
    (bin_dir / "swane.bk").write_text("first")
    (bin_dir / "swane.bk.1").write_text("second")
    # A dangling symlink takes its name too.
    (bin_dir / "swane.bk.2").symlink_to(sh.tmp / "missing")
    world.launcher.write_text("foreign")
    _, warnings = _write_launcher_warnings(sh, world)
    backup = bin_dir / "swane.bk.3"
    assert warnings == _foreign_warning(world.launcher, backup)
    assert backup.read_text() == "foreign"
    assert (bin_dir / "swane.bk").read_text() == "first"
    assert (bin_dir / "swane.bk.1").read_text() == "second"


def test_launcher_backup_warning_reaches_the_summary(sh, stub):
    world = InstallWorld(sh, stub)
    world.launcher.parent.mkdir(parents=True)
    world.launcher.write_text("foreign")
    result = world.run(*E2E_ARGS)
    assert result.returncode == 0, result.stderr
    backup = world.launcher.parent / "swane.bk"
    assert "WARNING: %s" % _foreign_warning(world.launcher, backup) in (
        result.stdout.splitlines()
    )
    assert backup.read_text() == "foreign"


def test_launcher_ignores_its_own_name_when_called_through_a_symlink(sh):
    """SWANE_LAUNCHER is the pinned install path, not $0."""
    world = LauncherWorld(sh)
    world.write()
    link = sh.tmp / "link-to-swane"
    link.symlink_to(world.launcher)
    result = subprocess.run(
        [str(link), "x"],
        env=sh.environment(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert "launcher=%s" % world.launcher in result.stdout.splitlines()


def test_launcher_self_heals(sh):
    world = LauncherWorld(sh)
    world.write()
    for path in (world.desktop, world.menu_script):
        path.parent.mkdir(parents=True)
        path.write_text("x")
    (world.prefix / "bin" / "swane").unlink()
    result = world.run()
    assert result.returncode == 1
    assert "SWANe is no longer installed: rerun install_swane.sh" in result.stderr
    assert not world.launcher.exists()
    assert not world.desktop.exists()
    assert not world.menu_script.exists()
    assert not world.log.exists()


def test_launcher_self_heal_honours_xdg_data_home(sh):
    world = LauncherWorld(sh)
    world.write()
    data = sh.tmp / "xdg data"
    desktop = data / "applications" / "swane.desktop"
    script = data / "swane" / "swane-launcher.sh"
    for path in (desktop, script):
        path.parent.mkdir(parents=True)
        path.write_text("x")
    (world.prefix / "bin" / "swane").unlink()
    assert world.run(env={"XDG_DATA_HOME": data}).returncode == 1
    assert not desktop.exists()
    assert not script.exists()
    assert not world.launcher.exists()


def test_launcher_with_space_in_prefix(sh):
    """Review Focus 3: spaces and quotes in the paths survive."""
    world = LauncherWorld(sh, prefix_name="home/my env's $HOME")
    world.write()
    assert subprocess.run([BASH, "-n", str(world.launcher)]).returncode == 0
    result = world.run("a b")
    assert result.returncode == 0, result.stderr
    assert "args=a b" in result.stdout.splitlines()
    assert world.log.read_text() == "activate %s\n" % world.prefix
    (world.prefix / "bin" / "swane").unlink()
    assert world.run().returncode == 1
    assert not world.launcher.exists()


def test_launcher_fails_cleanly_without_conda_sh(sh):
    world = LauncherWorld(sh)
    world.write()
    (world.root / "etc" / "profile.d" / "conda.sh").unlink()
    result = world.run()
    assert result.returncode != 0
    assert "launcher=" not in result.stdout


# ---------------------------------------------------------------------------
# ~/.local/bin on PATH
# ---------------------------------------------------------------------------

#: Every startup file a shell may read: the installer writes exactly one.
STARTUP_FILES = (
    ".zshrc",
    ".zprofile",
    ".zshenv",
    ".zlogin",
    ".bashrc",
    ".bash_profile",
    ".bash_login",
    ".profile",
)

#: (SHELL, uname -s, the one file that gets the block).
PATH_FILE_CASES = [
    ("/bin/zsh", "Linux", ".zshrc"),
    ("/bin/zsh", "Darwin", ".zshrc"),
    ("/bin/ZSH", "Darwin", ".zshrc"),
    ("/bin/bash", "Linux", ".bashrc"),
    ("/usr/bin/bash", "Linux", ".bashrc"),
    ("/bin/bash", "Darwin", ".bash_profile"),
    ("/opt/homebrew/bin/bash", "Darwin", ".bash_profile"),
    ("/bin/sh", "Linux", ".profile"),
    ("/usr/bin/dash", "Linux", ".profile"),
    ("/bin/sh", "Darwin", ".profile"),
]


def _blocks(sh):
    """{file name: number of PATH blocks} for every existing startup file."""
    found = {}
    for name in STARTUP_FILES:
        path = sh.home / name
        if path.exists():
            found[name] = path.read_text().count(MARKER_BEGIN)
    return found


@pytest.mark.parametrize("shell, system, expected", PATH_FILE_CASES)
def test_path_block_goes_into_one_file_per_shell(sh, stub, shell, system, expected):
    stub.platform(system, "x86_64")
    result = sh("path_startup_file", env={"SHELL": shell})
    assert result.returncode == 0, result.stderr
    assert result.stdout == "%s/%s\n" % (sh.home, expected)
    for _ in range(2):
        result = sh("ensure_local_bin_on_path", env={"SHELL": shell})
        assert result.returncode == 0, result.stderr
    assert (sh.home / expected).read_text() == PATH_BLOCK
    assert sorted(os.listdir(sh.home)) == [expected], "no other file is written"


@pytest.mark.parametrize("shell, system, expected", PATH_FILE_CASES)
def test_path_block_leaves_the_other_startup_files_alone(
    sh, stub, shell, system, expected
):
    """Existing startup files of every kind: only the chosen one changes."""
    stub.platform(system, "x86_64")
    for name in STARTUP_FILES:
        (sh.home / name).write_text("# %s\n" % name)
    assert sh("ensure_local_bin_on_path", env={"SHELL": shell}).returncode == 0
    for name in STARTUP_FILES:
        text = (sh.home / name).read_text()
        if name == expected:
            assert text == "# %s\n%s" % (name, PATH_BLOCK)
        else:
            assert text == "# %s\n" % name, name


def test_path_block_keeps_content_without_final_newline(sh, stub):
    """Review Focus 5: a file without a final newline, run twice."""
    stub.platform("Linux", "x86_64")
    rc_file = sh.home / ".bashrc"
    rc_file.write_text("alias ll='ls -l'")
    for _ in range(2):
        result = sh("ensure_local_bin_on_path", env={"SHELL": "/bin/bash"})
        assert result.returncode == 0, result.stderr
    assert rc_file.read_text() == "alias ll='ls -l'\n" + PATH_BLOCK
    assert _blocks(sh) == {".bashrc": 1}


@pytest.mark.parametrize(
    "existing, expected",
    [
        ((), ".bash_profile"),
        ((".profile",), ".profile"),
        ((".bash_login", ".profile"), ".bash_login"),
        ((".bash_profile", ".bash_login", ".profile"), ".bash_profile"),
        ((".bashrc",), ".bash_profile"),
    ],
)
def test_macos_bash_never_hides_the_login_file_bash_reads(sh, stub, existing, expected):
    """bash login reads only the first of .bash_profile, .bash_login and
    .profile: creating .bash_profile next to the user's .profile would hide it."""
    stub.platform("Darwin", "arm64")
    for name in existing:
        (sh.home / name).write_text("")
    result = sh("path_startup_file", env={"SHELL": "/bin/bash"})
    assert result.stdout == "%s/%s\n" % (sh.home, expected)
    assert sh("ensure_local_bin_on_path", env={"SHELL": "/bin/bash"}).returncode == 0
    assert _blocks(sh) == dict(
        {name: 0 for name in existing}, **{expected: 1}
    ), "the block goes into one file"


def test_linux_bash_uses_bashrc_even_with_a_bash_profile(sh, stub):
    stub.platform("Linux", "x86_64")
    (sh.home / ".bash_profile").write_text("keep\n")
    assert sh("ensure_local_bin_on_path", env={"SHELL": "/bin/bash"}).returncode == 0
    assert (sh.home / ".bash_profile").read_text() == "keep\n"
    assert _blocks(sh) == {".bash_profile": 0, ".bashrc": 1}


def test_rerun_over_an_older_install_adds_no_second_file(sh, stub):
    """An earlier installer wrote .zprofile and .zshrc: nothing changes."""
    stub.platform("Darwin", "arm64")
    for name in (".zprofile", ".zshrc"):
        (sh.home / name).write_text(PATH_BLOCK)
    assert sh("ensure_local_bin_on_path", env={"SHELL": "/bin/zsh"}).returncode == 0
    assert _blocks(sh) == {".zprofile": 1, ".zshrc": 1}


@pytest.mark.parametrize("shell", ["bash", "dash", "zsh"])
def test_path_block_never_duplicates_the_entry(sh, shell):
    """A profile that sources the rc file runs the block twice."""
    path = shutil.which(shell)
    if path is None:
        pytest.skip("%s not found" % shell)
    block = sh.tmp / "block.sh"
    block.write_text(PATH_BLOCK)
    result = subprocess.run(
        [path, "-c", '. "$B"; . "$B"; printf "%s" "$PATH"'],
        env={"B": str(block), "HOME": str(sh.home), "PATH": "/a:/b"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "%s/.local/bin:/a:/b" % sh.home
    result = subprocess.run(
        [path, "-c", '. "$B"; printf "%s" "$PATH"'],
        env={
            "B": str(block),
            "HOME": str(sh.home),
            "PATH": "/a:%s/.local/bin" % sh.home,
        },
        capture_output=True,
        text=True,
    )
    assert result.stdout == "/a:%s/.local/bin" % sh.home


@pytest.mark.skipif(os.geteuid() == 0, reason="root can write a read-only file")
def test_unwritable_startup_file_warns(sh, stub):
    stub.platform("Linux", "x86_64")
    rc_file = sh.home / ".bashrc"
    rc_file.write_text("x\n")
    rc_file.chmod(0o444)
    result = sh.code(
        'ensure_local_bin_on_path; rc=$?; printf "%s" "$SUMMARY_WARNINGS"; exit $rc',
        env={"SHELL": "/bin/bash"},
    )
    assert result.returncode == 0
    assert result.stdout == (
        "Could not update %s: add ~/.local/bin to PATH to run swane" % rc_file
    )
    assert rc_file.read_text() == "x\n"
    assert sorted(os.listdir(sh.home)) == [".bashrc"]


@pytest.mark.parametrize("suffix", ["", "/"])
def test_startup_file_untouched_when_local_bin_on_path(sh, suffix):
    rc_file = sh.home / ".zshrc"
    rc_file.write_text("keep\n")
    path = "%s:%s/.local/bin%s" % (sh.path, sh.home, suffix)
    result = sh("ensure_local_bin_on_path", env={"SHELL": "/bin/zsh", "PATH": path})
    assert result.returncode == 0
    assert rc_file.read_text() == "keep\n"
    assert os.listdir(sh.home) == [".zshrc"]


def test_path_check_uses_the_starting_path(sh):
    """A conda activation after sourcing must not hide a missing entry."""
    result = sh.code(
        'PATH="$HOME/.local/bin:$PATH"; ensure_local_bin_on_path',
        env={"SHELL": "/bin/zsh"},
    )
    assert result.returncode == 0
    assert MARKER_BEGIN in (sh.home / ".zshrc").read_text()


@pytest.mark.parametrize("shell", ["/usr/bin/fish", "/bin/tcsh", ""])
def test_unknown_shell_warns_with_a_manual_hint(sh, stub, shell):
    stub.platform("Linux", "x86_64")
    assert sh("path_startup_file", env={"SHELL": shell}).returncode == 1
    result = sh.code(
        'ensure_local_bin_on_path; printf "%s" "$SUMMARY_WARNINGS"',
        env={"SHELL": shell},
    )
    assert result.returncode == 0
    assert "WARNING: Unknown shell" in result.stderr
    assert 'export PATH="$HOME/.local/bin:$PATH"' in result.stdout
    assert os.listdir(sh.home) == []


# ---------------------------------------------------------------------------
# main: the whole flow and the summary
# ---------------------------------------------------------------------------


class InstallWorld:
    """Every external tool of a whole installer run, stubbed.

    A conda root (found through ``CONDA_EXE``) without ``swane-env``. Its
    ``bin/conda`` (logged as ``conda``) prints :attr:`envs_json` for ``env
    list --json``; ``create -n swane-env`` makes :attr:`env` (with
    ``bin/dot`` when graphviz is requested) and ``create -n swane-fsl``
    makes :attr:`fsl_prefix` (filled as an FSL solve would, see
    :func:`_fake_fsl_solver`, as is the prefix of ``install -p``), each then
    listed. The env's ``bin/python``
    (logged as ``env-python``) fakes the SWANe installed in it, as in
    :class:`FslWorld`. ``mktemp`` and ``basename`` wrap the real tools, so
    the launcher step (its ``mktemp``) and the PATH step (``basename`` of
    ``$SHELL``) show up in the call log too.

    Parameters
    ----------
    root : Path, optional
        The conda root (default ``<tmp>/conda root``).
    system, machine : str
        What ``uname -s`` / ``uname -m`` print.
    """

    def __init__(self, sh, stub, root=None, system="Linux", machine="x86_64"):
        self.sh = sh
        self.stub = stub
        self.root = make_conda_root(root or sh.tmp / "conda root")
        make_executable(
            self.root / "bin" / "python", 'exec %s "$@"' % bash_quote(sys.executable)
        )
        self.env = self.root / "envs" / "swane-env"
        self.fsl_prefix = self.root / "envs" / "swane-fsl"
        self.envs_json = sh.tmp / "envs.json"
        self.envs_json.write_text(json.dumps({"envs": [str(self.root)]}))
        template = stub.script(
            sh.tmp / "env-python-template",
            "env-python",
            'case "$*" in\n'
            "%s"
            '    *"-m swane.utils.fsl_conda --format github"*)\n'
            "        printf 'release=6.0.7.8\\nplatform=linux-64\\nspecs=%s\\n' ;;\n"
            "    *min_fsl_version*) echo 6.0.7.8 ;;\n"
            '    "%s") ;;\n'
            '    "-c "*) echo 3.12 ;;\n'
            '    "-m pip install -U "*) echo "pip output" ;;\n'
            "    *) exit 9 ;;\n"
            "esac" % (ENV_PYTHON_STDIN_CASE, FSL_SPECS, SWANE_CHECK_CALL),
        )
        fill = _fake_fsl_solver(sh, stub)
        with_env = json.dumps({"envs": [str(self.root), str(self.env)]})
        with_fsl = json.dumps(
            {"envs": [str(self.root), str(self.env), str(self.fsl_prefix)]}
        )
        stub.script(
            self.root / "bin" / "conda",
            "conda",
            'case "$1" in\n'
            '    --version) echo "conda 24.11.3" ;;\n'
            "    env) cat %(json)s ;;\n"
            '    create) echo "conda create output"\n'
            '        case " $* " in\n'
            '            *" -n swane-env "*)\n'
            "                mkdir -p %(env_bin)s\n"
            "                cp %(template)s %(env_bin)s/python\n"
            '                case " $* " in\n'
            '                    *" graphviz "*) printf "#!/bin/sh\\n" > %(env_bin)s/dot\n'
            "                        chmod 755 %(env_bin)s/dot ;;\n"
            "                esac\n"
            "                printf '%%s' %(with_env)s > %(json)s ;;\n"
            '            *" -n swane-fsl "*)\n'
            "                mkdir -p %(fsl_bin)s\n"
            "                %(fill)s %(fsl)s\n"
            "                printf '%%s' %(with_fsl)s > %(json)s ;;\n"
            "        esac ;;\n"
            '    install) echo "conda install output"\n'
            '        while [ "$#" -gt 0 ]; do\n'
            '            [ "$1" = -p ] && [ "$2" != %(env)s ] && %(fill)s "$2"\n'
            "            shift\n"
            "        done ;;\n"
            "esac"
            % {
                "json": bash_quote(str(self.envs_json)),
                "env_bin": bash_quote(str(self.env / "bin")),
                "template": bash_quote(str(template)),
                "with_env": bash_quote(with_env),
                "fsl_bin": bash_quote(str(self.fsl_prefix / "bin")),
                "fsl": bash_quote(str(self.fsl_prefix)),
                "env": bash_quote(str(self.env)),
                "fill": bash_quote(str(fill)),
                "with_fsl": bash_quote(with_fsl),
            },
        )
        stub.platform(system, machine)
        stub("sudo", '"$@"')
        stub("apt-get")
        _stub_locale(sh, stub)
        for tool in ("mktemp", "basename"):
            stub(tool, 'exec %s "$@"' % bash_quote(str(sh.tools / tool)))
        self.launcher = sh.home / ".local" / "bin" / "swane"
        self.profile = sh.home / ".profile"

    def run(self, *args, env=None):
        """Execute the installer file with ``args`` (no terminal, empty stdin)."""
        base = {"CONDA_EXE": self.root / "bin" / "conda", "SHELL": "/bin/sh"}
        return subprocess.run(
            [BASH, str(SCRIPT), *args],
            env=self.sh.environment(dict(base, **(env or {}))),
            cwd=str(self.sh.tmp),
            input="",
            capture_output=True,
            text=True,
            timeout=60,
        )

    def conda_calls(self):
        return self.stub.calls("conda")


E2E_ARGS = ("--yes", "--accept-fsl-license", "--swane-spec", "/x")


def _first_index(calls, prefix):
    """Index of the first logged call starting with ``prefix``."""
    for index, call in enumerate(calls):
        if call.startswith(prefix):
            return index
    raise AssertionError("no call starting with %r in %r" % (prefix, calls))


def test_main_end_to_end_with_stubs(sh, stub):
    world = InstallWorld(sh, stub)
    result = world.run(*E2E_ARGS)
    assert result.returncode == 0, result.stderr
    calls = stub.calls()
    # One marker call per step, in the order of main.
    steps = [
        "uname",  # detect_platform
        "conda --version",  # the conda found (warn_old_conda)
        "sudo %s" % APT_UPDATE,  # install_linux_packages
        "sudo locale-gen en_US.UTF-8",  # ensure_locale
        "conda create -y -n swane-env",  # ensure_swane_env
        "env-python -m pip install -U /x",
        "env-python %s" % SWANE_CHECK_CALL,
        "env-python -I -c from swane.utils.fsl_conda import min_fsl_version",
        "conda create -y -n swane-fsl",  # fsl_step
        "createFSLWrapper " + " ".join(FSL_PROGRAMS),
        "mktemp",  # write_launcher
        "basename",  # ensure_local_bin_on_path
    ]
    indexes = [_first_index(calls, step) for step in steps]
    assert indexes == sorted(indexes), calls
    assert world.conda_calls() == [
        "conda --version",
        "conda env list --json",
        "conda create -y -n swane-env %s python=3.12 graphviz" % CHANNELS,
        "conda env list --json",
        "conda env list --json",
        "conda create -y -n swane-fsl %s %s" % (FSL_CHANNELS, FSL_SPECS),
        "conda env list --json",
    ]
    assert "defaults" not in stub.calls_log.read_text()
    # The summary is the only output on stdout.
    assert result.stdout.splitlines() == [
        "SWANe installer: conda %s" % world.root,
        "SWANe installer: env %s" % world.env,
        "SWANe installer: FSL %s (6.0.7.8) installed" % world.fsl_prefix,
        "Open a new terminal and run: swane",
        "Or run now: %s" % world.launcher,
    ]
    # The one sudo question, answered by --yes, before any sudo call.
    assert result.stderr.count("%s yes (--yes)" % SYSTEM_QUESTION) == 1
    assert "with sudo, which may ask for your password" in result.stderr
    assert result.stderr.count("password") == 1
    assert str(world.env) in world.launcher.read_text()
    assert MARKER_BEGIN in world.profile.read_text()
    activate = world.env / "etc" / "conda" / "activate.d" / "swane-fsl.sh"
    assert str(world.fsl_prefix) in activate.read_text()


def test_main_rerun_reports_existing_fsl(sh, stub):
    world = InstallWorld(sh, stub)
    assert world.run(*E2E_ARGS).returncode == 0
    stub.calls_log.unlink()
    profile = world.profile.read_text()
    result = world.run(*E2E_ARGS)
    assert result.returncode == 0, result.stderr
    # swane-env is found (graphviz already in it), the hook's FSL is reused.
    assert world.conda_calls() == ["conda --version", "conda env list --json"]
    assert not any(" create " in call for call in stub.calls())
    assert "env-python -m pip install -U /x" in stub.calls()
    assert result.stdout.splitlines() == [
        "SWANe installer: conda %s" % world.root,
        "SWANe installer: env %s" % world.env,
        "SWANe installer: FSL %s (6.0.7.8) existing" % world.fsl_prefix,
        "Open a new terminal and run: swane",
        "Or run now: %s" % world.launcher,
    ]
    assert world.profile.read_text() == profile


def test_main_rerun_with_no_fsl_reports_the_kept_fsl(sh, stub):
    world = InstallWorld(sh, stub)
    assert world.run(*E2E_ARGS).returncode == 0
    result = world.run("--yes", "--no-fsl", "--swane-spec", "/x")
    assert result.returncode == 0, result.stderr
    assert "SWANe installer: FSL skipped" not in result.stdout
    assert (
        "SWANe installer: FSL %s (6.0.7.8) existing" % world.fsl_prefix
    ) in result.stdout.splitlines()
    assert "WARNING:" not in result.stdout


def test_main_summary_lists_skipped_fsl_and_warnings(sh, stub):
    world = InstallWorld(sh, stub)
    result = world.run(
        "--yes", "--no-fsl", "--swane-spec", "/x", env={"SHELL": "/usr/bin/fish"}
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[:3] == [
        "SWANe installer: conda %s" % world.root,
        "SWANe installer: env %s" % world.env,
        "SWANe installer: FSL skipped",
    ]
    assert lines[3] == "WARNING: %s" % NEEDS_FSL
    assert lines[4].startswith("WARNING: Unknown shell: ")
    assert lines[5:] == [
        "Open a new terminal and run: swane",
        "Or run now: %s" % world.launcher,
    ]
    assert not any("swane-fsl" in call for call in stub.calls())
    assert not world.profile.exists()


def test_main_on_macos_skips_the_linux_steps(sh, stub):
    world = InstallWorld(sh, stub, system="Darwin", machine="arm64")
    result = world.run(*E2E_ARGS)
    assert result.returncode == 0, result.stderr
    assert stub.calls("sudo") == []
    assert stub.calls("apt-get") == []
    assert stub.calls("locale-gen") == []
    assert "password" not in result.stderr
    assert result.stdout.splitlines()[-2:] == [
        "Open a new terminal and run: swane",
        "Or run now: %s" % world.launcher,
    ]


def test_main_installs_miniforge_when_no_conda_is_found(sh, stub):
    """No conda anywhere: Miniforge goes into --miniforge-prefix and is used."""
    prefix = sh.home / "forge"
    world = InstallWorld(sh, stub, root=prefix)
    staged = sh.tmp / "staged-miniforge"
    prefix.rename(staged)
    installer = sh.tmp / "fake-miniforge.sh"
    installer.write_text(
        'printf "miniforge-installer %%s\\n" "$*" >> %s\n'
        'mkdir -p "$3" && cp -R %s/. "$3"\n'
        % (bash_quote(str(stub.calls_log)), bash_quote(str(staged)))
    )
    _stub_curl(sh, stub, installer=installer)
    _stub_sha256sum(stub)
    result = world.run(*E2E_ARGS, "--miniforge-prefix", prefix, env={"CONDA_EXE": None})
    assert result.returncode == 0, result.stderr
    assert stub.calls("miniforge-installer") == [
        "miniforge-installer -b -p %s" % prefix
    ]
    assert stub.calls("conda")[0] == "conda --version"
    assert result.stdout.splitlines()[0] == "SWANe installer: conda %s" % prefix


def test_unknown_flag_exit_2(sh, stub):
    world = InstallWorld(sh, stub)
    result = world.run("--bogus")
    assert result.returncode == 2
    assert "Unknown option: --bogus" in result.stderr
    assert result.stdout == ""
    assert stub.calls() == []


def test_main_refuses_to_run_inside_a_swane_env(sh, stub):
    """Dies before any prompt, external call or file change."""
    world = InstallWorld(sh, stub)
    sh.tty_path.write_text("y\n")
    result = world.run(
        "--swane-spec",
        "/x",
        env={
            "CONDA_PREFIX": "/c/envs/other",
            "CONDA_PREFIX_1": world.env,
            "CONDA_SHLVL": "2",
        },
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert "cannot run inside a SWANe conda environment (active: %s)" % world.env in (
        result.stderr
    )
    assert "[y/N]" not in result.stderr
    assert stub.calls() == []
    assert not world.launcher.exists()
    assert list(sh.home.iterdir()) == []


def test_main_help_works_inside_a_swane_env(sh, stub):
    world = InstallWorld(sh, stub)
    result = world.run("--help", env={"CONDA_PREFIX": world.env})
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("Usage: install_swane.sh")


def test_main_under_rosetta_dies_before_downloading(sh, stub):
    """No conda found, so Miniforge would be next: never reached."""
    world = InstallWorld(sh, stub, system="Darwin", machine="x86_64")
    _stub_curl(sh, stub)
    stub("sysctl", "echo 1")
    result = world.run(*E2E_ARGS, env={"CONDA_EXE": None})
    assert result.returncode == 1
    assert ROSETTA_ERROR in result.stderr
    assert [call.split()[0] for call in stub.calls()] == ["uname", "uname", "sysctl"]
    assert stub.calls("curl") == []
    assert result.stdout == ""


def test_main_declined_system_setup_warns_in_the_summary(sh, stub):
    """Answering "n" at the one sudo question, the install goes on."""
    world = InstallWorld(sh, stub)
    sh.tty_path.write_text("n\n")
    result = world.run("--no-fsl", "--swane-spec", "/x")
    assert result.returncode == 0, result.stderr
    assert result.stderr.count(SYSTEM_QUESTION) == 1
    assert stub.calls("sudo") == []
    assert stub.calls("apt-get") == []
    warnings = [
        line for line in result.stdout.splitlines() if line.startswith("WARNING: ")
    ]
    assert warnings[0].startswith("WARNING: Linux system setup declined")
    assert "sudo locale-gen en_US.UTF-8" in warnings[0]
    assert "env-python -m pip install -U /x" in stub.calls()
    assert result.stdout.splitlines()[-2:] == [
        "Open a new terminal and run: swane",
        "Or run now: %s" % world.launcher,
    ]
