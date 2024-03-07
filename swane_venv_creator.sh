#!/bin/bash

# Create a swane_env virtual environment dedicated to SWANe using the python3 interpreter
cd $HOME
venv_name = swane_venv
python_version = python3
python"${python_version}" -m venv "$venv_name"

# Activate the swane_venv
source "$HOME/$venv_name/bin/activate"

# Installing the SWANe package using pip
"${python_version}" -m pip install swane

# Deactivate the swane_venv
source "$HOME/$venv_name/bin/deactivate"

# Crea uno script per attivare l'ambiente virtuale e eseguire il comando python -m swane
echo "#!/bin/bash" > run_swane.sh
echo "source $HOME/$venv_name/bin/activate" >> run_swane.sh
echo "${python_version} -m swane" >> run_swane.sh
chmod +x run_swane.sh

echo "SWANe Virtual Environment created and configurated"
echo "Execute './run_swane.sh' to activate the swane_venv and start SWANe"
