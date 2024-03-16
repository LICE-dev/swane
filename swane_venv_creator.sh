#!/bin/bash

# Check the user profile configuration
user_profile_check() {
    if [[ -f $1 ]]; then
    	echo 0
    else
    	echo 1
    fi
}

# Common user configuration paths
file_bash="$HOME/.bashrc"
file_bash_profile="$HOME/.bash_profile"
file_zsh="$HOME/.zshrc"
file_profile="$HOME/.profile"

# Get the user profile configuration
user_profile_get() {
    if user_profile_check "$file_bash"; then
    	echo "$file_bash"
    elif user_profile_check "$file_bash_profile"; then
    	echo "$file_bash_profile"
    elif user_profile_check "$file_zsh"; then
    	echo "$file_zsh"
	elif user_profile_check "$file_profile"; then
		echo "$file_profile"
	else:
		echo ""
	fi
}

user_profile_validate() {
	fsl="FSL"
	freesurfer="FREESURFER_HOME"

	# Get user profile path
	profile_file=$(user_profile_get)

	if profile_file == ""; then
		echo "User Profile not found. Cannot check the FSL/FREESURFER configuration"
	else:
		# Check the profile file for the FSL and FreeSurfer configuration
		fsl_row=$(grep -n "^export $fsl=" "$profile_file" | cut -d: -f1)
		freesurfer_row=$(grep -n "^export $freesurfer=" "$profile_file" | cut -d: -f1)

		# Check thhe configuration order
		if [ -n "$fsl_row" ] && [ -n "$freesurfer_row" ]; then
		    if [ "$fsl_row" -lt "$freesurfer_row" ]; then
		        echo "$fsl configuration must be placed AFTER $freesurfer configuration"
		    else
		        echo "$freesurfer and $fsl are configured correctly"
		    fi
		elif [ -n "$fsl_row" ]; then
		    echo "$fsl has been found, but $freesurfer is missing."
		elif [ -n "$freesurfer_row" ]; then
		    echo "$freesurfer has been found, but $fsl is missing."
		else
		    echo "$freesurfer and $fsl are missing."
	fi
}


# Create a swane_env virtual environment dedicated to SWANe using the python3 interpreter
cd $HOME
venv_name = "swane_venv"
python_version = "python3"
${python_version} -m venv "$venv_name"

# Activate the swane_venv
source "$HOME/$venv_name/bin/activate"

# Installing the SWANe package using pip
"${python_version}" -m pip install swane

# Deactivate the swane_venv
source "$HOME/$venv_name/bin/deactivate"

# Create a script to activate the virtual env and execute the command python -m swane
echo "#!/bin/bash" > run_swane.sh
echo "source $HOME/$venv_name/bin/activate" >> run_swane.sh
echo "${python_version} -m swane" >> run_swane.sh
chmod +x run_swane.sh

echo "SWANe Virtual Environment created and configurated"
echo "Execute './run_swane.sh' to activate the swane_venv and start SWANe"
echo "Checking User Profile configuration..."
user_profile_validate