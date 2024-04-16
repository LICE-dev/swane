#!/bin/bash

# Checking the FSL/FREESURFER user profile configuration
python_check=$(which python3)
if [[ python_check = *^fsl^* ]]; then
    echo "Wrong FSL and FREESURFER configuration in your profile"
    echo "Please fix it before installing SWANe"
    echo "More info on https://github.com/LICE-dev/swane/wiki/04-Dependencies-Guides#freesurferfsl-conflict-with-python"
    exit 1
fi

# Create a swane_env virtual environment dedicated to SWANe using the python3 interpreter
cd $HOME
venv_name="swane_venv"
python_version="python3"

"${python_version}" -m venv "$venv_name"

# Activate the swane_venv
source "$HOME/$venv_name/bin/activate"

# Installing the SWANe package using pip
"${python_version}" -m pip install swane

# Deactivate the swane_venv
deactivate

# Create a script to activate the virtual env and execute the command python -m swane
echo "#!/bin/bash" > run_swane.sh
echo "source $HOME/$venv_name/bin/activate" >> run_swane.sh
echo "${python_version} -m swane" >> run_swane.sh
chmod +x run_swane.sh

echo "SWANe Virtual Environment created and configurated"
echo "Execute './run_swane.sh' to activate the swane_venv and start SWANe"
echo "Checking User Profile configuration..."

