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
