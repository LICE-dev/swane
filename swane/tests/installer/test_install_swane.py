"""Tests of the bash installer skeleton: options, prompts, platform, conda.

Every call runs in the isolated harness of ``harness.py``: no real conda,
network tool or terminal is ever reached.
"""

import json
import os
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

MINIFORGE_TAG = "26.7.2-0"
RELEASES = "https://github.com/conda-forge/miniforge/releases"
GOOD_HASH = "a" * 64
BAD_HASH = "b" * 64


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


@pytest.mark.parametrize(
    "args, message",
    [
        (["--bogus"], "Unknown option: --bogus"),
        (["--swane-spec"], "--swane-spec needs a value"),
        (["--miniforge-prefix"], "--miniforge-prefix needs a value"),
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
        '--miniforge-prefix "/p q"; '
        'printf "%s|" "$ASSUME_YES" "$ACCEPT_FSL_LICENSE" "$NO_FSL" '
        '"$SWANE_SPEC" "$MINIFORGE_PREFIX"'
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "1|1|1|/x/y|/p q|"


def test_main_defaults_ignore_the_environment(sh):
    """Options come from the command line only, not from inherited variables."""
    result = sh.code(
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


def _serve(sh):
    """Bash that writes the fake download for $url into $out."""
    installer = _fake_miniforge_installer(sh)
    return (
        'case "$url" in\n'
        "    *.sha256)\n"
        '        name="${url##*/}"\n'
        '        printf "%%s  ./%%s\\n" %s "${name%%.sha256}" > "$out" ;;\n'
        '    *) cp %s "$out" ;;\n'
        "esac" % (GOOD_HASH, bash_quote(str(installer)))
    )


def _stub_curl(sh, stub, tag_url="%s/tag/%s" % (RELEASES, MINIFORGE_TAG)):
    stub(
        "curl",
        'out=""; url=""; write_out=0\n'
        'while [ "$#" -gt 0 ]; do\n'
        '    case "$1" in\n'
        '        -o) out="$2"; shift ;;\n'
        "        -w) write_out=1; shift ;;\n"
        "        -*) ;;\n"
        '        *) url="$1" ;;\n'
        "    esac\n"
        "    shift\n"
        "done\n"
        'if [ "$write_out" = 1 ]; then printf "%%s" %s; exit 0; fi\n'
        "%s" % (bash_quote(tag_url), _serve(sh)),
    )


def _stub_wget(sh, stub):
    stub(
        "wget",
        'if [ "$1" = "-S" ]; then\n'
        '    echo "  HTTP/1.1 302 Found" >&2\n'
        '    echo "  Location: %s/tag/%s [following]" >&2\n'
        "    exit 0\n"
        "fi\n"
        'out="$2"; url="$3"\n'
        "%s" % (RELEASES, MINIFORGE_TAG, _serve(sh)),
    )


def _stub_sha256sum(stub, digest=GOOD_HASH):
    stub("sha256sum", 'printf "%%s  %%s\\n" %s "$1"' % digest)


def _installer_name(system, machine):
    return "Miniforge3-%s-%s-%s.sh" % (MINIFORGE_TAG, system, machine)


def test_install_miniforge_downloads_verifies_and_installs(sh, stub):
    stub.platform("Linux", "x86_64")
    _stub_curl(sh, stub)
    _stub_sha256sum(stub)
    prefix = sh.home / "miniforge3"
    result = sh("install_miniforge", prefix)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "%s\n" % prefix, "installer output must not reach stdout"
    assert (prefix / "etc" / "profile.d" / "conda.sh").is_file()
    name = _installer_name("Linux", "x86_64")
    url = "%s/download/%s/%s" % (RELEASES, MINIFORGE_TAG, name)
    curl = stub.calls("curl")
    assert (
        curl[0] == "curl -fsSLI -o /dev/null -w %%{url_effective} %s/latest" % RELEASES
    )
    assert curl[1].startswith("curl -fsSL -o ") and curl[1].endswith(" " + url)
    assert curl[2].endswith(" " + url + ".sha256")
    assert stub.calls("miniforge-installer") == [
        "miniforge-installer -b -p %s" % prefix
    ]
    assert not any("init" in call for call in stub.calls())
    assert list(sh.tmpdir.iterdir()) == [], "the download directory is removed"


def test_install_miniforge_macos_uses_shasum(sh, stub):
    stub.platform("Darwin", "arm64")
    _stub_curl(sh, stub)
    stub("shasum", 'printf "%%s  %%s\\n" %s "$3"' % GOOD_HASH)
    prefix = sh.tmp / "forge"
    result = sh("install_miniforge", prefix)
    assert result.returncode == 0, result.stderr
    assert stub.calls("curl")[1].endswith("/" + _installer_name("MacOSX", "arm64"))
    assert stub.calls("shasum")[0].startswith("shasum -a 256 ")


def test_install_miniforge_refuses_checksum_mismatch(sh, stub):
    stub.platform("Linux", "x86_64")
    _stub_curl(sh, stub)
    _stub_sha256sum(stub, BAD_HASH)
    prefix = sh.home / "miniforge3"
    result = sh("install_miniforge", prefix)
    assert result.returncode == 1
    assert "checksum mismatch" in result.stderr
    assert result.stdout == ""
    assert not prefix.exists()
    assert stub.calls("miniforge-installer") == []
    assert list(sh.tmpdir.iterdir()) == []


def test_install_miniforge_falls_back_to_wget(sh, stub):
    stub.platform("Linux", "aarch64")
    _stub_wget(sh, stub)
    _stub_sha256sum(stub)
    prefix = sh.home / "miniforge3"
    result = sh("install_miniforge", prefix)
    assert result.returncode == 0, result.stderr
    wget = stub.calls("wget")
    assert wget[0] == "wget -S --spider %s/latest" % RELEASES
    assert wget[1].startswith("wget -qO ")
    assert wget[1].endswith("/" + _installer_name("Linux", "aarch64"))
    assert (prefix / "etc" / "profile.d" / "conda.sh").is_file()


def test_install_miniforge_without_latest_tag_dies(sh, stub):
    stub.platform("Linux", "x86_64")
    _stub_curl(sh, stub, tag_url="https://github.com/login")
    _stub_sha256sum(stub)
    result = sh("install_miniforge", sh.home / "miniforge3")
    assert result.returncode == 1
    assert "latest Miniforge release" in result.stderr
    assert len(stub.calls("curl")) == 1


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

#: The 3D Slicer package list, written out here on purpose (not read back from
#: the script): the installer must install exactly these, in this order.
APT_LIST = (
    "libegl1 libgl1 libopengl0 libgl1-mesa-dev libglu1-mesa libpulse0 "
    "libpulse-mainloop-glib0 libnss3 libx11-xcb1 libxdamage1 libxss1 "
    "libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 "
    "libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 "
    "libxcb-sync1 libxcb-xfixes0 libxcb-xinerama0 libxcb-xkb1 dc bc"
)
APT_INSTALL = "apt-get install -y --no-install-recommends"


def _stub_linux_system(stub, apt_body=""):
    """Linux host with ``sudo`` (runs its arguments) and ``apt-get`` stubs."""
    stub.platform("Linux", "x86_64")
    stub("sudo", '"$@"')
    stub("apt-get", apt_body)


def test_apt_installs_exact_package_list(sh, stub):
    _stub_linux_system(stub)
    result = sh("install_linux_packages")
    assert result.returncode == 0
    assert stub.calls("apt-get") == [
        "apt-get update",
        "%s %s" % (APT_INSTALL, APT_LIST),
        "%s libasound2t64" % APT_INSTALL,
    ]
    # Every apt-get call goes through sudo, and without "-n".
    assert stub.calls("sudo") == [
        "sudo apt-get update",
        "sudo %s %s" % (APT_INSTALL, APT_LIST),
        "sudo %s libasound2t64" % APT_INSTALL,
    ]


def test_apt_yes_does_not_make_sudo_non_interactive(sh, stub):
    _stub_linux_system(stub)
    result = sh("install_linux_packages", env={"ASSUME_YES": "1"})
    assert result.returncode == 0
    assert all(call.startswith("sudo apt-get") for call in stub.calls("sudo"))


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


def test_no_apt_prints_list_and_continues(sh, stub):
    stub.platform("Linux", "x86_64")
    stub("sudo", '"$@"')
    result = sh.code(
        'install_linux_packages; rc=$?; printf "%s" "$SUMMARY_WARNINGS"; exit $rc'
    )
    assert result.returncode == 0
    assert "libxcb-cursor0" in result.stderr
    assert "libxcb-cursor0" in result.stdout  # recorded for the summary
    assert stub.calls("sudo") == []


@pytest.mark.skipif(os.geteuid() == 0, reason="needs a non-root user")
def test_no_sudo_for_non_root_warns_and_continues(sh, stub):
    stub.platform("Linux", "x86_64")
    stub("apt-get")
    result = sh.code(
        'install_linux_packages; rc=$?; printf "%s" "$SUMMARY_WARNINGS"; exit $rc'
    )
    assert result.returncode == 0
    assert "libxcb-cursor0" in result.stdout
    assert stub.calls("apt-get") == []


def test_apt_failure_warns_and_continues(sh, stub):
    _stub_linux_system(stub, '[ "$1" = install ] && exit 100 || exit 0')
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
    _stub_linux_system(stub, '[ "$1" = update ] && exit 100 || exit 0')
    result = sh.code(
        'install_linux_packages; rc=$?; printf "%s" "$SUMMARY_WARNINGS"; exit $rc'
    )
    assert result.returncode == 0
    assert "apt-get update failed" in result.stdout
    assert "%s %s" % (APT_INSTALL, APT_LIST) in stub.calls("apt-get")


def test_locale_present_is_noop(sh, stub):
    stub.platform("Linux", "x86_64")
    stub("sudo", '"$@"')
    stub("locale", "echo C; echo en_US.utf8; echo POSIX")
    stub("locale-gen")
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


def test_locale_missing_runs_locale_gen(sh, stub):
    stub.platform("Linux", "x86_64")
    stub("sudo", '"$@"')
    stub("locale", "echo C; echo POSIX")
    stub("locale-gen")
    result = sh("ensure_locale")
    assert result.returncode == 0
    assert stub.calls("locale-gen") == ["locale-gen en_US.UTF-8"]
    assert stub.calls("sudo") == ["sudo locale-gen en_US.UTF-8"]


def test_locale_missing_enables_entry_in_locale_gen_file(sh, stub):
    """The commented en_US line is uncommented through sudo, before locale-gen."""
    stub.platform("Linux", "x86_64")
    stub("sudo", '"$@"')
    stub("locale", "echo C")
    stub("locale-gen")
    locale_gen = sh.tmp / "locale.gen"
    locale_gen.write_text(
        "# de_DE.UTF-8 UTF-8\n#  en_US.UTF-8 UTF-8\n# fr_FR.UTF-8 UTF-8\n"
    )
    result = sh("ensure_locale", env={"SWANE_LOCALE_GEN_FILE": locale_gen})
    assert result.returncode == 0
    assert locale_gen.read_text() == (
        "# de_DE.UTF-8 UTF-8\nen_US.UTF-8 UTF-8\n# fr_FR.UTF-8 UTF-8\n"
    )
    assert stub.calls("sudo") == [
        "sudo sed -i s/^# *\\(en_US.UTF-8 UTF-8\\)/\\1/ %s" % locale_gen,
        "sudo locale-gen en_US.UTF-8",
    ]


def test_locale_without_locale_gen_file_skips_the_edit(sh, stub):
    stub.platform("Linux", "x86_64")
    stub("sudo", '"$@"')
    stub("locale", "echo C")
    stub("locale-gen")
    assert not (sh.tmp / "locale.gen").exists()
    result = sh("ensure_locale")
    assert result.returncode == 0
    assert stub.calls("sudo") == ["sudo locale-gen en_US.UTF-8"]


def test_locale_gen_failure_warns_and_continues(sh, stub):
    stub.platform("Linux", "x86_64")
    stub("sudo", '"$@"')
    stub("locale", "echo C")
    stub("locale-gen", "exit 1")
    result = sh.code('ensure_locale; rc=$?; printf "%s" "$SUMMARY_WARNINGS"; exit $rc')
    assert result.returncode == 0
    assert "locale-gen en_US.UTF-8 failed" in result.stdout
    assert "WARNING:" in result.stderr


def test_locale_sudo_failure_warns_and_continues(sh, stub):
    stub.platform("Linux", "x86_64")
    stub("sudo", "exit 1")
    stub("locale", "echo C")
    locale_gen = sh.tmp / "locale.gen"
    locale_gen.write_text("# en_US.UTF-8 UTF-8\n")
    result = sh.code(
        'ensure_locale; rc=$?; printf "%s" "$SUMMARY_WARNINGS"; exit $rc',
        env={"SWANE_LOCALE_GEN_FILE": locale_gen},
    )
    assert result.returncode == 0
    assert "locale-gen en_US.UTF-8 failed" in result.stdout
    assert "Could not enable en_US.UTF-8" in result.stdout
    # sudo failed before the edit: the real file is untouched.
    assert locale_gen.read_text() == "# en_US.UTF-8 UTF-8\n"


@pytest.mark.parametrize("func", ["install_linux_packages", "ensure_locale"])
def test_linux_steps_noop_on_macos(sh, stub, func):
    stub.platform("Darwin", "arm64")
    stub("sudo", '"$@"')
    stub("apt-get")
    stub("locale", "echo C")
    stub("locale-gen")
    result = sh(func)
    assert result.returncode == 0
    assert stub.calls("sudo") == []
    assert stub.calls("apt-get") == []
    assert stub.calls("locale-gen") == []


# ---------------------------------------------------------------------------
# swane-env
# ---------------------------------------------------------------------------

CHANNELS = "--override-channels --strict-channel-priority -c conda-forge"
VERSION_CODE = 'import sys; print("%d.%d" % sys.version_info[:2])'


def _env_python(stub, path, label, version="3.12"):
    """Logging stub of an environment's ``bin/python``.

    ``-c`` (the version check) prints ``version``; ``-m pip`` prints some
    chatter on stdout and records ``PYTHONNOUSERSITE`` next to the stub.
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

    def __init__(self, sh, stub, version="conda 24.11.3", create_exit=0):
        self.stub = stub
        self.root = make_conda_root(sh.tmp / "conda root")
        self.envs_json = sh.tmp / "envs.json"
        self.new_prefix = self.root / "envs" / "swane-env"
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
            "        mkdir -p %s\n"
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
    assert stub.calls(python) == ["%s -m pip install -U swane" % python]
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
    ]
    assert result.stdout == "%s\n" % prefix


@pytest.mark.parametrize(
    "system, machine, dot, tensorflow, missing",
    [
        ("Linux", "x86_64", False, False, "graphviz"),
        ("Darwin", "x86_64", True, False, "tensorflow>=2.18"),
        ("Darwin", "x86_64", False, True, "graphviz"),
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


def test_existing_env_with_everything_on_macos_intel_installs_nothing(sh, stub):
    stub.platform("Darwin", "x86_64")
    stub("dot")
    conda = FakeConda(sh, stub)
    prefix = conda.root / "envs" / "swane-env"
    conda.add_env(prefix, tensorflow=True)
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
    assert stub.calls(str(python))[-1] == (
        "%s -m pip install -U /path/to/checkout" % python
    )


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
