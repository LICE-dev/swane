#!/bin/bash

# Validate the user profile configuration
user_profile_validate() {
    fsl="FSL"
    freesurfer="FREESURFER_HOME"

    # Array dei file di profilo da controllare
    profile_files=("$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.zshrc" "$HOME/.profile")

    # Variabile per tenere traccia se un file è stato trovato
    files_found=false

    # Itera su ciascun file di profilo
    for profile_file in "${profile_files[@]}"; do
        if [ -f "$profile_file" ]; then
            # Un file di profilo è stato trovato
            files_found=true
            echo "Checking $profile_file..."

            # Check the profile file for the FSL and FreeSurfer configuration
            fsl_row=$(grep -n "^export $fsl=" "$profile_file" | cut -d: -f1)
            freesurfer_row=$(grep -n "^export $freesurfer=" "$profile_file" | cut -d: -f1)

            # Check the configuration order
            if [ -n "$fsl_row" ] && [ -n "$freesurfer_row" ]; then
                if [ "$fsl_row" -lt "$freesurfer_row" ]; then
                    echo "$fsl configuration must be placed AFTER $freesurfer configuration in $profile_file"
                else
                    echo "$freesurfer and $fsl are configured correctly in $profile_file"
                fi
            elif [ -n "$fsl_row" ]; then
                echo "$fsl has been found in $profile_file, but $freesurfer is missing."
            elif [ -n "$freesurfer_row" ]; then
                echo "$freesurfer has been found in $profile_file, but $fsl is missing."
            else
                echo "$freesurfer and $fsl are missing in $profile_file."
            fi
            echo ""
        fi
    done

    if [ "$files_found" = false ]; then
        echo "User Profile files not found. Cannot check the FSL/FREESURFER configuration"
    fi
}


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
user_profile_validate