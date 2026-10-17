#!/usr/bin/env bash
# SWANe installer for Linux and macOS.
#
# Builds a working SWANe environment: conda (Miniforge when no conda is
# found), a Python 3.12 "swane-env", graphviz, TensorFlow on macOS Intel,
# "pip install swane", an optional minimal FSL, the Linux system packages
# 3D Slicer needs and a "swane" launcher in ~/.local/bin.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/LICE-dev/swane/main/installer/install_swane.sh | bash
#   bash install_swane.sh [options]        (see --help)
#
# The file is a library of functions plus a main that runs only when the file
# is executed (directly or from a pipe), never when it is sourced: the test
# suite sources it and drives each function against stub executables.
#
# Requires bash >= 3.2 (macOS /bin/bash): no associative arrays, no ${var,,},
# no mapfile.

set -euo pipefail

INSTALLER_URL="https://raw.githubusercontent.com/LICE-dev/swane/main/installer/install_swane.sh"
MINIFORGE_RELEASES_URL="https://github.com/conda-forge/miniforge/releases"

# The PATH the installer started with, before any conda activation: later
# steps check it for a system "dot" and for ~/.local/bin.
# shellcheck disable=SC2034 # read by the later steps and by the test suite
ORIGINAL_PATH="${PATH:-}"

# Newline-separated list of warnings, repeated in the final summary
# (a string, not an array, for bash 3.2 and "set -u").
SUMMARY_WARNINGS=""

# Options. Defaults keep values from the environment so the test suite can set
# them; main resets them before parsing the command line.
ASSUME_YES="${ASSUME_YES:-0}"
ACCEPT_FSL_LICENSE="${ACCEPT_FSL_LICENSE:-0}"
NO_FSL="${NO_FSL:-0}"
SWANE_SPEC="${SWANE_SPEC:-swane}"
MINIFORGE_PREFIX="${MINIFORGE_PREFIX:-$HOME/miniforge3}"

# System-wide conda roots probed after the user's own (space-separated;
# overridable so tests never see the machine's real conda).
SWANE_SYSTEM_CONDA_ROOTS="${SWANE_SYSTEM_CONDA_ROOTS-/opt/conda}"

# Locale definitions file edited (through sudo) when en_US.UTF-8 is missing.
# Overridable so tests never point at the real /etc/locale.gen.
SWANE_LOCALE_GEN_FILE="${SWANE_LOCALE_GEN_FILE:-/etc/locale.gen}"

# Terminal the prompts read from. Under "curl ... | bash" stdin is the script
# itself, so prompts must never read stdin. Overridable for tests.
SWANE_TTY="${SWANE_TTY:-/dev/tty}"
# Set once file descriptor 7 is open on SWANE_TTY: it stays open so
# consecutive prompts read consecutive lines.
TTY_OPEN=0

# ---------------------------------------------------------------------------
# Logging (stderr only: stdout carries function results)
# ---------------------------------------------------------------------------

log_info() {
    printf '==> %s\n' "$*" >&2
}

log_warn() {
    printf 'WARNING: %s\n' "$*" >&2
    if [ -n "$SUMMARY_WARNINGS" ]; then
        SUMMARY_WARNINGS="$SUMMARY_WARNINGS
$*"
    else
        SUMMARY_WARNINGS="$*"
    fi
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

have_command() {
    command -v "$1" >/dev/null 2>&1
}

# ---------------------------------------------------------------------------
# Prompts (always from the terminal, never from stdin)
# ---------------------------------------------------------------------------

# open_tty: open SWANE_TTY on descriptor 7 once; return 1 if it cannot be opened
# (no controlling terminal, e.g. CI or a detached session).
open_tty() {
    if [ "$TTY_OPEN" = "1" ]; then
        return 0
    fi
    # Probe in a subshell first: a failed "exec" redirection must not be
    # able to end the installer.
    if ! (exec 7<"$SWANE_TTY") 2>/dev/null; then
        return 1
    fi
    exec 7<"$SWANE_TTY"
    TTY_OPEN=1
}

# read_tty VAR PROMPT: show PROMPT on stderr and read one line from the
# terminal into VAR (leading/trailing blanks stripped; empty on end of input).
# Return 1 if no terminal is available. Do not call it inside $(...): the
# terminal descriptor must stay open in the installer's own shell.
read_tty() {
    local __read_tty_var="$1" __read_tty_prompt="$2" __read_tty_line=""
    open_tty || return 1
    printf '%s' "$__read_tty_prompt" >&2
    if ! read -r __read_tty_line <&7; then
        # End of input: keep a partial last line, otherwise answer empty.
        printf '\n' >&2
    fi
    printf -v "$__read_tty_var" '%s' "$__read_tty_line"
}

# prompt_yes_no QUESTION: return 0 for yes. --yes (ASSUME_YES=1) answers yes
# without reading the terminal.
prompt_yes_no() {
    local question="$1" answer=""
    if [ "$ASSUME_YES" = "1" ]; then
        log_info "$question yes (--yes)"
        return 0
    fi
    if ! read_tty answer "$question [y/N] "; then
        die "No terminal available: rerun with --yes"
    fi
    case "$answer" in
        y | Y | yes | Yes | YES) return 0 ;;
    esac
    return 1
}

# ---------------------------------------------------------------------------
# Platform
# ---------------------------------------------------------------------------

# detect_platform: print the FSL platform name of this machine (the names of
# swane.utils.fsl_conda.host_platform); die on anything but Linux or macOS.
detect_platform() {
    local os arch
    os="$(uname -s)"
    arch="$(uname -m)"
    case "$os" in
        Linux)
            case "$arch" in
                x86_64 | amd64) printf 'linux-64\n' ;;
                aarch64 | arm64) printf 'linux-aarch64\n' ;;
                *) die "Unsupported Linux architecture: $arch (SWANe supports x86_64 and aarch64)" ;;
            esac
            ;;
        Darwin)
            case "$arch" in
                x86_64) printf 'macos-64\n' ;;
                arm64 | aarch64) printf 'macos-M1\n' ;;
                *) die "Unsupported macOS architecture: $arch" ;;
            esac
            ;;
        *)
            die "Unsupported operating system: $os (the SWANe installer supports Linux and macOS only)"
            ;;
    esac
}

is_macos_intel() {
    [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "x86_64" ]
}

# ---------------------------------------------------------------------------
# Conda discovery
# ---------------------------------------------------------------------------

# physical_dir DIR: print DIR with symlinks resolved, or DIR without trailing
# slashes when it does not exist.
physical_dir() {
    local dir="$1"
    if [ -d "$dir" ]; then
        (cd -P -- "$dir" 2>/dev/null && pwd) && return 0
    fi
    while [ "${#dir}" -gt 1 ] && [ "${dir%/}" != "$dir" ]; do
        dir="${dir%/}"
    done
    printf '%s\n' "$dir"
}

# is_fsl_root DIR: return 0 if DIR is an FSL install (has etc/fslversion or
# is $FSLDIR). FSL ships its own conda, which must never host swane-env.
is_fsl_root() {
    local dir="$1"
    if [ -f "$dir/etc/fslversion" ]; then
        return 0
    fi
    if [ -n "${FSLDIR:-}" ] && [ "$(physical_dir "$dir")" = "$(physical_dir "$FSLDIR")" ]; then
        return 0
    fi
    return 1
}

# is_conda_root DIR: a usable conda root has etc/profile.d/conda.sh and is
# not an FSL install.
is_conda_root() {
    local dir="$1"
    [ -n "$dir" ] || return 1
    [ -f "$dir/etc/profile.d/conda.sh" ] || return 1
    if is_fsl_root "$dir"; then
        log_info "Skipping the conda inside FSL: $dir"
        return 1
    fi
    return 0
}

# find_conda: print the first usable conda root among $CONDA_EXE, "conda" on
# PATH, the usual per-user roots, MINIFORGE_PREFIX and
# SWANE_SYSTEM_CONDA_ROOTS; return 1 if there is none. A shell started by
# "curl | bash" has not read the user's rc files, so PATH alone is not enough.
find_conda() {
    local candidate conda_path root
    if [ -n "${CONDA_EXE:-}" ]; then
        candidate="$(dirname -- "$(dirname -- "$CONDA_EXE")")"
        if is_conda_root "$candidate"; then
            printf '%s\n' "$candidate"
            return 0
        fi
    fi
    conda_path="$(command -v conda 2>/dev/null || true)"
    case "$conda_path" in
        */condabin/conda) candidate="${conda_path%/condabin/conda}" ;;
        */bin/conda) candidate="${conda_path%/bin/conda}" ;;
        *) candidate="" ;;
    esac
    if [ -n "$candidate" ] && is_conda_root "$candidate"; then
        printf '%s\n' "$candidate"
        return 0
    fi
    for candidate in "$HOME/miniforge3" "$HOME/miniconda3" "$HOME/anaconda3" "$MINIFORGE_PREFIX"; do
        if is_conda_root "$candidate"; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    # Word splitting is intended: the variable is a space-separated list.
    for root in $SWANE_SYSTEM_CONDA_ROOTS; do
        if is_conda_root "$root"; then
            printf '%s\n' "$root"
            return 0
        fi
    done
    return 1
}

# ---------------------------------------------------------------------------
# Miniforge
# ---------------------------------------------------------------------------

# download URL OUT: fetch URL into the file OUT with curl, or wget if curl is
# missing.
download() {
    local url="$1" out="$2"
    if have_command curl; then
        curl -fsSL -o "$out" "$url"
    elif have_command wget; then
        wget -qO "$out" "$url"
    else
        die "Neither curl nor wget is available: install one of them and rerun"
    fi
}

# miniforge_latest_tag: print the tag of Miniforge's latest release, read
# from the redirect of releases/latest. Only the versioned installers have a
# published .sha256 file.
miniforge_latest_tag() {
    local url="" tag
    if have_command curl; then
        url="$(curl -fsSLI -o /dev/null -w '%{url_effective}' "$MINIFORGE_RELEASES_URL/latest")" || return 1
    elif have_command wget; then
        url="$(wget -S --spider "$MINIFORGE_RELEASES_URL/latest" 2>&1 |
            sed -n 's/^ *[Ll]ocation: *\([^ ]*\).*/\1/p' | tail -n 1)" || return 1
    else
        die "Neither curl nor wget is available: install one of them and rerun"
    fi
    case "$url" in
        */releases/tag/*) tag="${url##*/releases/tag/}" ;;
        *) return 1 ;;
    esac
    tag="$(printf '%s' "$tag" | tr -d '\r')"
    case "$tag" in
        "" | *[!A-Za-z0-9._-]*) return 1 ;;
    esac
    printf '%s\n' "$tag"
}

# sha256_of FILE: print the SHA-256 of FILE (sha256sum on Linux, shasum on
# macOS).
sha256_of() {
    local file="$1" line
    if have_command sha256sum; then
        line="$(sha256sum "$file")"
    elif have_command shasum; then
        line="$(shasum -a 256 "$file")"
    else
        die "Neither sha256sum nor shasum is available to verify the Miniforge download"
    fi
    printf '%s\n' "${line%% *}"
}

# install_miniforge PREFIX: download the latest Miniforge installer for this
# platform, verify its published SHA-256 and install it in batch mode into
# PREFIX; print PREFIX. Never runs "conda init": the user's shell startup
# files are not touched.
install_miniforge() {
    local prefix="$1" os arch tag name url workdir expected actual
    if is_fsl_root "$prefix"; then
        die "$prefix is an FSL installation: choose another --miniforge-prefix"
    fi
    if [ -f "$prefix/etc/profile.d/conda.sh" ]; then
        log_info "Miniforge already installed in $prefix"
        printf '%s\n' "$prefix"
        return 0
    fi
    if [ -e "$prefix" ]; then
        die "$prefix exists but is not a conda installation: remove it or choose another --miniforge-prefix"
    fi
    os="$(uname -s)"
    arch="$(uname -m)"
    case "$os" in
        Linux) ;;
        Darwin) os="MacOSX" ;;
        *) die "Unsupported operating system for Miniforge: $os" ;;
    esac
    tag="$(miniforge_latest_tag)" || die "Could not find the latest Miniforge release at $MINIFORGE_RELEASES_URL"
    name="Miniforge3-$tag-$os-$arch.sh"
    url="$MINIFORGE_RELEASES_URL/download/$tag/$name"
    workdir="$(mktemp -d "${TMPDIR:-/tmp}/swane-miniforge.XXXXXX")" || die "Could not create a temporary directory"
    log_info "Downloading $url"
    if ! download "$url" "$workdir/$name" || ! download "$url.sha256" "$workdir/$name.sha256"; then
        rm -rf "$workdir"
        die "Could not download Miniforge from $url"
    fi
    expected="$(sed -n '1s/^\([0-9A-Fa-f]*\).*/\1/p' "$workdir/$name.sha256" | tr 'A-F' 'a-f')"
    actual="$(sha256_of "$workdir/$name" | tr 'A-F' 'a-f')"
    if [ "${#expected}" -ne 64 ] || [ "$expected" != "$actual" ]; then
        rm -rf "$workdir"
        die "Miniforge checksum mismatch for $name (expected '$expected', got '$actual'): download not used"
    fi
    log_info "Installing Miniforge into $prefix"
    # The Miniforge installer prints to stdout: keep stdout for the result.
    if ! bash "$workdir/$name" -b -p "$prefix" >&2; then
        rm -rf "$workdir"
        die "The Miniforge installer failed"
    fi
    rm -rf "$workdir"
    [ -f "$prefix/etc/profile.d/conda.sh" ] || die "Miniforge installed into $prefix without etc/profile.d/conda.sh"
    printf '%s\n' "$prefix"
}

# ---------------------------------------------------------------------------
# Linux system packages and locale (sudo steps: warn and continue)
# ---------------------------------------------------------------------------

# Packages the 3D Slicer binaries need (the list of the Windows/Linux test
# workflow, without the virtual display server), then libasound2t64 or
# libasound2 depending on the release.
APT_PACKAGES="libegl1 libgl1 libopengl0 libgl1-mesa-dev libglu1-mesa libpulse0 libpulse-mainloop-glib0 libnss3 libx11-xcb1 libxdamage1 libxss1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-sync1 libxcb-xfixes0 libxcb-xinerama0 libxcb-xkb1 dc bc"

is_linux() {
    [ "$(uname -s)" = "Linux" ]
}

# can_run_privileged: return 0 if sudo exists or we already are root.
can_run_privileged() {
    have_command sudo || [ "${EUID:-1}" = "0" ]
}

# run_privileged CMD ARGS...: run a command through sudo (directly as root
# when there is no sudo). "--yes" never implies "sudo -n": the password
# prompt, if any, is the user's.
run_privileged() {
    if have_command sudo; then
        sudo "$@"
    else
        "$@"
    fi
}

# install_linux_packages: install APT_PACKAGES and libasound2t64 (or
# libasound2) with apt-get. No-op off Linux. Every failure is a warning, never
# an error: SWANe itself works without them, only 3D Slicer needs them.
# Call it directly (not inside $(...)) so the warnings reach SUMMARY_WARNINGS.
install_linux_packages() {
    is_linux || return 0
    if ! have_command apt-get; then
        log_warn "apt-get not found: install these packages with your system package manager (3D Slicer needs them): $APT_PACKAGES, and libasound2t64 or libasound2"
        return 0
    fi
    if ! can_run_privileged; then
        log_warn "sudo not found and not running as root: install these packages as root (3D Slicer needs them): $APT_PACKAGES, and libasound2t64 or libasound2"
        return 0
    fi
    log_info "Installing system packages for 3D Slicer (sudo may ask for your password)"
    if ! run_privileged apt-get update; then
        log_warn "apt-get update failed: the package lists may be stale"
    fi
    # Word splitting is intended: the variable is a space-separated list.
    # shellcheck disable=SC2086
    if ! run_privileged apt-get install -y --no-install-recommends $APT_PACKAGES; then
        log_warn "Installing the system packages failed: 3D Slicer may not start. Install manually: $APT_PACKAGES"
    fi
    if ! run_privileged apt-get install -y --no-install-recommends libasound2t64 &&
        ! run_privileged apt-get install -y --no-install-recommends libasound2; then
        log_warn "Installing libasound2t64 / libasound2 failed: 3D Slicer may not start"
    fi
    return 0
}

# has_en_us_locale: return 0 if "locale -a" lists en_US.utf8 / en_US.UTF-8
# (any case, with or without the dash).
has_en_us_locale() {
    local listing
    listing="$(locale -a 2>/dev/null || true)"
    printf '%s\n' "$listing" | grep -Eiq '^en_US\.utf-?8$'
}

# ensure_locale: make the en_US.UTF-8 locale available (the FSL check needs
# it). No-op off Linux or when it already exists. Failures are warnings.
ensure_locale() {
    is_linux || return 0
    if has_en_us_locale; then
        return 0
    fi
    if ! can_run_privileged; then
        log_warn "The en_US.UTF-8 locale is missing and sudo is not available: generate it as root (locale-gen en_US.UTF-8)"
        return 0
    fi
    log_info "Generating the en_US.UTF-8 locale (sudo may ask for your password)"
    if [ -f "$SWANE_LOCALE_GEN_FILE" ]; then
        if ! run_privileged sed -i 's/^# *\(en_US.UTF-8 UTF-8\)/\1/' "$SWANE_LOCALE_GEN_FILE"; then
            log_warn "Could not enable en_US.UTF-8 in $SWANE_LOCALE_GEN_FILE"
        fi
    fi
    if ! run_privileged locale-gen en_US.UTF-8; then
        log_warn "locale-gen en_US.UTF-8 failed: FSL may report a missing locale"
    fi
    return 0
}

# ---------------------------------------------------------------------------
# swane-env (the conda environment SWANe runs in)
# ---------------------------------------------------------------------------

SWANE_ENV_NAME="swane-env"
SWANE_ENV_PYTHON="3.12"
# PyPI has no recent TensorFlow wheels for macOS Intel (setup.py leaves it out
# of the pip requirements there): it comes from conda-forge on that platform.
SWANE_TENSORFLOW_SPEC="tensorflow>=2.18"
# First conda release whose default solver is libmamba.
SWANE_MIN_FAST_CONDA="23.10"
# Prefix of swane-env, set by ensure_swane_env. A global rather than stdout:
# ensure_swane_env warns and dies, which would be lost inside $(...).
SWANE_ENV_PREFIX=""

# conda_cmd ROOT ARGS...: run the conda of the root ROOT (bin/conda, else
# condabin/conda) without activating it.
conda_cmd() {
    local root="$1"
    shift
    if [ -x "$root/bin/conda" ]; then
        "$root/bin/conda" ${1+"$@"}
    elif [ -x "$root/condabin/conda" ]; then
        "$root/condabin/conda" ${1+"$@"}
    else
        die "No conda executable in $root (bin/conda or condabin/conda)"
    fi
}

# env_in_fsl PREFIX: return 0 if the environment PREFIX belongs to an FSL
# install: its conda root (PREFIX/../..) is an FSL root, or PREFIX lies under
# $FSLDIR. swane-env must never live inside FSL.
env_in_fsl() {
    local dir env_root fsl_dir
    dir="$(physical_dir "$1")"
    env_root="$(dirname -- "$(dirname -- "$dir")")"
    if is_fsl_root "$env_root"; then
        return 0
    fi
    if [ -n "${FSLDIR:-}" ]; then
        fsl_dir="$(physical_dir "$FSLDIR")"
        case "$dir/" in
            "$fsl_dir/"*) return 0 ;;
        esac
    fi
    return 1
}

# find_env_prefix ROOT NAME: print the prefix, as conda lists it, of an
# environment from "conda env list --json" whose directory name is exactly
# NAME. The list also holds the environments of other conda installs (all
# share ~/.conda/environments.txt), so matches inside an FSL install are
# skipped, a match in ROOT/envs is preferred, and otherwise the first
# remaining match is taken. Return 1 if there is none, 2 if the list cannot
# be read. The JSON is parsed by the root's own Python, in isolated mode (-I)
# so nothing in the current directory or the user's site-packages can be
# imported.
find_env_prefix() {
    local root="$1" name="$2" listing matches candidate dir own_envs first=""
    listing="$(conda_cmd "$root" env list --json </dev/null)" || return 2
    matches="$(printf '%s\n' "$listing" | "$root/bin/python" -I -c '
import json
import os
import sys

for env in json.load(sys.stdin).get("envs", []):
    if os.path.basename(os.path.normpath(env)) == sys.argv[1]:
        print(env)
' "$name")" || return 2
    own_envs="$(physical_dir "$root")/envs"
    while IFS= read -r candidate; do
        [ -n "$candidate" ] || continue
        if env_in_fsl "$candidate"; then
            log_info "Skipping $candidate: it is inside an FSL installation"
            continue
        fi
        dir="$(physical_dir "$candidate")"
        if [ "$(dirname -- "$dir")" = "$own_envs" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
        [ -n "$first" ] || first="$candidate"
    done <<EOF
$matches
EOF
    [ -n "$first" ] || return 1
    printf '%s\n' "$first"
}

# version_lt A B: return 0 if the dotted version A is lower than B. Compared
# number by number; a missing number counts as 0 and anything after the
# leading digits of a number ("4rc1") is ignored.
version_lt() {
    local a="$1." b="$2." x y
    while [ -n "$a" ] || [ -n "$b" ]; do
        x="${a%%.*}"
        a="${a#*.}"
        y="${b%%.*}"
        b="${b#*.}"
        x="${x%%[!0-9]*}"
        y="${y%%[!0-9]*}"
        x="${x:-0}"
        y="${y:-0}"
        if [ "$x" -lt "$y" ]; then
            return 0
        fi
        if [ "$x" -gt "$y" ]; then
            return 1
        fi
    done
    return 1
}

# warn_old_conda ROOT: warn (recorded for the summary) when the conda of ROOT
# is older than SWANE_MIN_FAST_CONDA, whose classic solver can take very long
# on swane-env. Never fails. Call it directly, not inside $(...).
warn_old_conda() {
    local root="$1" output version
    output="$(conda_cmd "$root" --version 2>&1 </dev/null)" || output=""
    version="$(printf '%s\n' "$output" | sed -n 's/^conda \([0-9][0-9.]*\).*/\1/p' | head -n 1)" || version=""
    if [ -z "$version" ]; then
        log_info "Could not read the conda version in $root"
        return 0
    fi
    if version_lt "$version" "$SWANE_MIN_FAST_CONDA"; then
        log_warn "conda $version in $root is older than $SWANE_MIN_FAST_CONDA (no libmamba solver by default): creating $SWANE_ENV_NAME may be very slow; consider updating conda"
    fi
    return 0
}

# system_has_dot: return 0 if a "dot" executable (graphviz) is on the PATH the
# installer started with, before any conda activation. The PATH is walked by
# hand: "command -v" would also see the shell's hash table.
system_has_dot() {
    local rest="$ORIGINAL_PATH:" dir
    while [ -n "$rest" ]; do
        dir="${rest%%:*}"
        rest="${rest#*:}"
        # An empty entry means the current directory: never trusted here.
        if [ -n "$dir" ] && [ -f "$dir/dot" ] && [ -x "$dir/dot" ]; then
            return 0
        fi
    done
    return 1
}

# swane_env_packages [PREFIX]: print the conda-forge packages swane-env needs
# besides Python, space-separated (possibly nothing): graphviz unless
# system_has_dot, TensorFlow on macOS Intel. With PREFIX (an existing
# swane-env) the packages already there are left out: graphviz when
# PREFIX/bin/dot exists, TensorFlow when PREFIX's site-packages holds the
# tensorflow package (installed by conda or pip alike).
swane_env_packages() {
    local prefix="${1:-}" packages=""
    if ! system_has_dot; then
        if [ -z "$prefix" ] || [ ! -x "$prefix/bin/dot" ]; then
            packages="graphviz"
        fi
    fi
    if is_macos_intel; then
        if [ -z "$prefix" ] || [ ! -f "$prefix/lib/python$SWANE_ENV_PYTHON/site-packages/tensorflow/__init__.py" ]; then
            packages="${packages:+$packages }$SWANE_TENSORFLOW_SPEC"
        fi
    fi
    printf '%s\n' "$packages"
}

# ensure_swane_env ROOT SWANE_SPEC: create swane-env in the conda ROOT (Python
# SWANE_ENV_PYTHON plus swane_env_packages), or update an existing one (same
# Python required, missing packages added), then "pip install -U SWANE_SPEC"
# into it. Sets SWANE_ENV_PREFIX and prints nothing on stdout (conda and pip
# output goes to stderr). Call it directly, not inside $(...).
#
# Every solve uses conda-forge only (never the "defaults" channel), whatever
# the user's .condarc says. pip runs with PYTHONNOUSERSITE=1 so packages in
# ~/.local are not taken as already installed.
ensure_swane_env() {
    local root="$1" spec="$2" prefix="" version packages rc=0
    SWANE_ENV_PREFIX=""
    prefix="$(find_env_prefix "$root" "$SWANE_ENV_NAME")" || rc=$?
    case "$rc" in
        0)
            log_info "Updating the existing $SWANE_ENV_NAME environment in $prefix"
            if [ ! -x "$prefix/bin/python" ]; then
                die "$SWANE_ENV_NAME in $prefix has no Python; remove it or rename it, then rerun"
            fi
            version="$("$prefix/bin/python" -c 'import sys; print("%d.%d" % sys.version_info[:2])' </dev/null)" || version="unknown"
            if [ "$version" != "$SWANE_ENV_PYTHON" ]; then
                die "$SWANE_ENV_NAME uses Python $version; remove it or rename it, then rerun"
            fi
            packages="$(swane_env_packages "$prefix")"
            if [ -n "$packages" ]; then
                log_info "Installing into $SWANE_ENV_NAME: $packages"
                # Word splitting is intended: a space-separated list. "-p"
                # targets the very environment checked above.
                # shellcheck disable=SC2086
                conda_cmd "$root" install -y -p "$prefix" --override-channels --strict-channel-priority -c conda-forge $packages </dev/null >&2 ||
                    die "Could not install $packages into $SWANE_ENV_NAME"
            fi
            ;;
        1)
            packages="$(swane_env_packages)"
            log_info "Creating the $SWANE_ENV_NAME environment (Python $SWANE_ENV_PYTHON${packages:+ $packages})"
            # shellcheck disable=SC2086 # word splitting intended, as above
            conda_cmd "$root" create -y -n "$SWANE_ENV_NAME" --override-channels --strict-channel-priority -c conda-forge "python=$SWANE_ENV_PYTHON" $packages </dev/null >&2 ||
                die "Could not create the $SWANE_ENV_NAME environment"
            prefix="$(find_env_prefix "$root" "$SWANE_ENV_NAME")" ||
                die "conda does not list $SWANE_ENV_NAME after creating it"
            ;;
        *)
            die "Could not list the conda environments of $root"
            ;;
    esac
    log_info "Installing $spec into $SWANE_ENV_NAME"
    PYTHONNOUSERSITE=1 "$prefix/bin/python" -m pip install -U "$spec" </dev/null >&2 ||
        die "pip install -U $spec failed in $SWANE_ENV_NAME"
    # shellcheck disable=SC2034 # read by main and by the test suite
    SWANE_ENV_PREFIX="$prefix"
}

# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

usage() {
    cat <<EOF
Usage: install_swane.sh [options]
   or: curl -fsSL $INSTALLER_URL | bash -s -- [options]

Install SWANe into a conda environment named swane-env (Linux and macOS).
An existing conda is reused; otherwise Miniforge is installed. SWANe is then
started with the "swane" command from a new terminal.

Options:
  --yes                    Answer yes to every prompt except the FSL licence.
  --accept-fsl-license     Accept the FSL licence without prompting.
  --no-fsl                 Do not install or configure FSL.
  --swane-spec SPEC        pip requirement or local path to install
                           (default: swane).
  --miniforge-prefix DIR   Where to install Miniforge when no conda is found
                           (default: ~/miniforge3).
  -h, --help               Show this help and exit.
EOF
}

usage_error() {
    printf 'ERROR: %s\n\n' "$*" >&2
    usage >&2
    exit 2
}

# parse_args ARGS...: set the option globals; exit 2 on a bad command line.
parse_args() {
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --yes) ASSUME_YES=1 ;;
            --accept-fsl-license) ACCEPT_FSL_LICENSE=1 ;;
            --no-fsl) NO_FSL=1 ;;
            --swane-spec)
                if [ "$#" -lt 2 ] || [ -z "$2" ]; then
                    usage_error "--swane-spec needs a value"
                fi
                SWANE_SPEC="$2"
                shift
                ;;
            --miniforge-prefix)
                if [ "$#" -lt 2 ] || [ -z "$2" ]; then
                    usage_error "--miniforge-prefix needs a value"
                fi
                MINIFORGE_PREFIX="$2"
                shift
                ;;
            -h | --help)
                usage
                exit 0
                ;;
            *) usage_error "Unknown option: $1" ;;
        esac
        shift
    done
}

main() {
    ASSUME_YES=0
    ACCEPT_FSL_LICENSE=0
    NO_FSL=0
    SWANE_SPEC="swane"
    MINIFORGE_PREFIX="$HOME/miniforge3"
    # ${1+"$@"}: an empty "$@" is an unbound-variable error under "set -u"
    # in old bash releases (macOS /bin/bash 3.2).
    parse_args ${1+"$@"}
}

# Run main only when executed (directly or as "curl ... | bash"), never when
# sourced. "return" succeeds only in a sourced file.
if ! (return 0 2>/dev/null); then
    main ${1+"$@"}
fi
