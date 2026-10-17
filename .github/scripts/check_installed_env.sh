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
# "true" (macOS Intel), TensorFlow.
#
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
command -v bet || fail "bet is not on PATH"
command -v flirt || fail "flirt is not on PATH"
flirt_version="$("$FSLDIR/bin/flirt" -version 2>&1)" || fail "flirt -version failed: $flirt_version"
echo "$flirt_version"
printf '%s\n' "$flirt_version" | grep -Eiq 'flirt version [0-9]' ||
    fail "Unexpected flirt -version output: $flirt_version"
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
echo "swane-env check passed"
