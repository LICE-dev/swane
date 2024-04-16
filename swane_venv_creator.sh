#!/bin/bash

# Deactivating running virtual env, if any
deactivate

cd $HOME
venv_name="swane_venv"
python_version="python3"

# Checking the FSL/FREESURFER user profile configuration
echo "Checking User Profile configuration..."
python_path=$(which $python_version)
if [[ $python_path = *^fsl^* ]]; then
    echo "Wrong FSL and FREESURFER configuration in your profile"
    echo "Please fix it before installing SWANe"
    echo "More info on https://github.com/LICE-dev/swane/wiki/04-Dependencies-Guides#freesurferfsl-conflict-with-python"
    exit 1
fi

# Creating a swane_env virtual environment dedicated to SWANe using the python3 interpreter
"${python_version}" -m venv "$venv_name"

# Activating the swane_venv
source "$HOME/$venv_name/bin/activate"

# Installing SWANe package using pip
"${python_version}" -m pip install swane

# Deactivating swane_venv
deactivate

# Creating a script to activate the virtual env and execute the command python -m swane
echo "#!/bin/bash" > run_swane.sh
echo "source $HOME/$venv_name/bin/activate" >> run_swane.sh
echo "${python_version} -m swane" >> run_swane.sh
chmod +x run_swane.sh

echo "SWANe Virtual Environment created and configurated"
echo "To activate swane_venv and start SWANe please run the following command: $HOME/run_swane.sh"