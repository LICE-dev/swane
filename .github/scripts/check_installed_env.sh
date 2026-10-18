#!/usr/bin/env bash
# CI check of an environment built by installer/install_swane.sh (used by
# .github/workflows/installer-tests.yml after each installer run).
#
# Usage: bash -l check_installed_env.sh SUMMARY_FILE
#
# Reads the conda root and swane-env prefix pinned in ~/.local/bin/swane
# (never sourcing the launcher: it would exec SWANe), checks them against the
# installer summary, activates swane-env the way the launcher does and checks
# FSL, graphviz, a headless SWANe import and, when EXPECT_CONDA_TENSORFLOW is
# "true" (macOS Intel), TensorFlow; then deactivates it and checks that the
# FSL hook undid its changes.
#
# FSL is reached only through its command wrappers: the hook puts
# $FSLDIR/share/fsl/bin first on PATH (before swane-env's bin), never
# $FSLDIR/bin (Ruling R19).
#
# Bash 3.2 compatible (macOS).
# No "set -u": conda.sh is not safe under it.
set -eo pipefail

fail() {
    echo "::error::$*"
    exit 1
}

summary="${1:-}"
[ -f "$summary" ] || fail "No installer summary file: '$summary'"
launcher="$HOME/.local/bin/swane"
[ -x "$launcher" ] || fail "No executable launcher at $launcher"
cat "$launcher"

# pin NAME: the single-quoted value of the NAME='...' line of the launcher.
pin() {
    sed -n "s/^$1='\\(.*\\)'\$/\\1/p" "$launcher" | head -n 1 | sed "s/'\\\\''/'/g"
}

SWANE_CONDA_ROOT="$(pin SWANE_CONDA_ROOT)"
SWANE_ENV_PREFIX="$(pin SWANE_ENV_PREFIX)"
echo "SWANE_CONDA_ROOT=$SWANE_CONDA_ROOT"
echo "SWANE_ENV_PREFIX=$SWANE_ENV_PREFIX"
[ -n "$SWANE_CONDA_ROOT" ] || fail "No SWANE_CONDA_ROOT line in $launcher"
[ -n "$SWANE_ENV_PREFIX" ] || fail "No SWANE_ENV_PREFIX line in $launcher"
grep -qxF "SWANe installer: conda $SWANE_CONDA_ROOT" "$summary" ||
    fail "The launcher's conda root $SWANE_CONDA_ROOT is not the one in the summary"
grep -qxF "SWANe installer: env $SWANE_ENV_PREFIX" "$summary" ||
    fail "The launcher's env $SWANE_ENV_PREFIX is not the one in the summary"

# shellcheck disable=SC1091 # exists only on the runner
. "$SWANE_CONDA_ROOT/etc/profile.d/conda.sh" ||
    fail "Could not source $SWANE_CONDA_ROOT/etc/profile.d/conda.sh"
# What the deactivation must give back.
path_before="$PATH"
fsldir_before="${FSLDIR-<unset>}"
fsloutputtype_before="${FSLOUTPUTTYPE-<unset>}"
conda activate "$SWANE_ENV_PREFIX" || fail "conda activate $SWANE_ENV_PREFIX failed"
export PYTHONNOUSERSITE=1
python_path="$(command -v python)" || fail "No python after activating swane-env"
[ "$python_path" = "$SWANE_ENV_PREFIX/bin/python" ] ||
    fail "python is $python_path, not $SWANE_ENV_PREFIX/bin/python"

hook="$SWANE_ENV_PREFIX/etc/conda/activate.d/swane-fsl.sh"
[ -f "$hook" ] || fail "No FSL activation hook at $hook"
cat "$hook"
echo "FSLDIR=${FSLDIR:-} FSLOUTPUTTYPE=${FSLOUTPUTTYPE:-}"
[ -n "${FSLDIR:-}" ] || fail "FSLDIR is not set after activating swane-env"
[ "${FSLOUTPUTTYPE:-}" = NIFTI_GZ ] || fail "FSLOUTPUTTYPE is '${FSLOUTPUTTYPE:-}', not NIFTI_GZ"
[ -f "$FSLDIR/etc/fslversion" ] || fail "No $FSLDIR/etc/fslversion"
cat "$FSLDIR/etc/fslversion"
[ -f "$FSLDIR/etc/swane_installer_fsl" ] || fail "No installer marker in $FSLDIR"

# path_index ENTRY: print the 1-based position of the first PATH entry equal
# to ENTRY, or nothing.
path_index() {
    local rest="$PATH:" entry i=0
    while [ -n "$rest" ]; do
        entry="${rest%%:*}"
        rest="${rest#*:}"
        i=$((i + 1))
        if [ "$entry" = "$1" ]; then
            echo "$i"
            return 0
        fi
    done
}

wrappers="$FSLDIR/share/fsl/bin"
echo "PATH=$PATH"
[ -z "$(path_index "$FSLDIR/bin")" ] || fail "$FSLDIR/bin is on PATH: only $wrappers may be"
wrappers_at="$(path_index "$wrappers")"
env_bin_at="$(path_index "$CONDA_PREFIX/bin")"
[ -n "$wrappers_at" ] || fail "$wrappers is not on PATH"
[ -n "$env_bin_at" ] || fail "$CONDA_PREFIX/bin is not on PATH"
[ "$wrappers_at" -lt "$env_bin_at" ] ||
    fail "$wrappers (entry $wrappers_at) does not come before $CONDA_PREFIX/bin (entry $env_bin_at)"
fsldir_physical="$(cd -P -- "$FSLDIR" && pwd -P)" || fail "Cannot resolve $FSLDIR"
# The FSL commands SWANe runs (swane/utils/fsl_conda.py FSL_PACKAGES). Each
# one installed in $FSLDIR/bin must have an executable wrapper that runs it
# and is what the name resolves to; bet, flirt and fsl-cluster must exist.
checked=0
for tool in bet flirt convert_xfm fnirt invwarp mcflirt susan slicetimer \
    feat_model film_gls fsl-cluster smoothest eddy_cpu dtifit bedpostx probtrackx2; do
    if [ ! -x "$FSLDIR/bin/$tool" ]; then
        case "$tool" in
            bet | flirt | fsl-cluster) fail "No executable $FSLDIR/bin/$tool" ;;
        esac
        echo "($tool is not installed in $FSLDIR/bin: not checked)"
        continue
    fi
    [ -f "$wrappers/$tool" ] && [ -x "$wrappers/$tool" ] ||
        fail "No executable FSL wrapper $wrappers/$tool"
    grep -qF -- "$FSLDIR/bin/$tool" "$wrappers/$tool" ||
        grep -qF -- "$fsldir_physical/bin/$tool" "$wrappers/$tool" ||
        fail "$wrappers/$tool does not run $FSLDIR/bin/$tool: $(cat "$wrappers/$tool")"
    resolved="$(command -v "$tool")" || fail "$tool is not on PATH"
    [ "$resolved" = "$wrappers/$tool" ] || fail "$tool resolves to $resolved, not $wrappers/$tool"
    checked=$((checked + 1))
done
echo "$checked FSL wrappers checked in $wrappers"

# run_usage TOOL: the output of TOOL without arguments (FSL's tools print
# their usage and exit non-zero then, so only the text tells they ran).
run_usage() {
    "$1" </dev/null 2>&1 || true
}

output="$(run_usage bet)"
case "$output" in
    *"Usage:"*"bet <input> <output>"*) echo "bet runs" ;;
    *) fail "Unexpected output of bet: $output" ;;
esac
output="$(run_usage flirt)"
case "$output" in
    *"Usage:"*"-in <inputvol> -ref <refvol>"*) echo "flirt runs" ;;
    *) fail "Unexpected output of flirt: $output" ;;
esac
flirt_version="$(flirt -version 2>&1)" || fail "flirt -version failed: $flirt_version"
echo "$flirt_version"
case "$flirt_version" in
    *[Ff][Ll][Ii][Rr][Tt]" version "[0-9]*) ;;
    *) fail "Unexpected flirt -version output: $flirt_version" ;;
esac
# FSL's cluster tool is fsl-cluster (nipype runs that name): bin/cluster
# belongs to graphviz. A share/fsl/bin/cluster wrapper, if any, must run
# FSL's tool, not graphviz's ("Usage: .../cluster <options> graphfile").
fsl_cluster_text="The following COMPULSORY options have not been set"
output="$(run_usage fsl-cluster)"
case "$output" in
    *"$fsl_cluster_text"*) echo "fsl-cluster runs FSL's cluster" ;;
    *) fail "Unexpected output of fsl-cluster: $output" ;;
esac
if [ -e "$wrappers/cluster" ]; then
    output="$(run_usage "$wrappers/cluster")"
    case "$output" in
        *"$fsl_cluster_text"*) echo "$wrappers/cluster runs FSL's cluster" ;;
        *) fail "$wrappers/cluster does not run FSL's cluster: $output" ;;
    esac
fi
python -c "from swane.utils.DependencyManager import DependencyManager as D; d = D.check_fsl(); print(d.state, d.label); assert d.state.name == 'DETECTED'" ||
    fail "DependencyManager.check_fsl() is not DETECTED"

command -v dot || fail "dot (graphviz) is not on PATH"
dot -V || fail "dot -V failed"

# Headless: importing the entry module does not start the GUI (main() runs
# only under __name__ == "__main__").
python -c "import swane.__main__" || fail "import swane.__main__ failed"

if [ "${EXPECT_CONDA_TENSORFLOW:-}" = true ]; then
    platform="$(uname -s)-$(uname -m)"
    [ "$platform" = Darwin-x86_64 ] || fail "Expected a macOS Intel runner, got $platform"
    conda list -p "$SWANE_ENV_PREFIX" tensorflow
    python -c "import tensorflow as tf; print('tensorflow', tf.__version__)" ||
        fail "import tensorflow failed"
fi

# Deactivation: on a clean runner the wrapper entry was not on PATH before
# the activation, the hook added it, and conda deactivate must give back
# exactly the PATH, FSLDIR and FSLOUTPUTTYPE of before.
case ":$path_before:" in
    *":$wrappers:"*) fail "$wrappers was already on PATH before the activation (not a clean runner): $path_before" ;;
esac
conda deactivate || fail "conda deactivate failed"
echo "PATH=$PATH"
[ "$PATH" = "$path_before" ] ||
    fail "PATH after conda deactivate is $PATH, not the PATH before the activation: $path_before"
[ "${FSLDIR-<unset>}" = "$fsldir_before" ] ||
    fail "FSLDIR is '${FSLDIR-<unset>}' after conda deactivate, not '$fsldir_before'"
[ "${FSLOUTPUTTYPE-<unset>}" = "$fsloutputtype_before" ] ||
    fail "FSLOUTPUTTYPE is '${FSLOUTPUTTYPE-<unset>}' after conda deactivate, not '$fsloutputtype_before'"
echo "swane-env check passed"
