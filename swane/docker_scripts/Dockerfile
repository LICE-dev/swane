# Use the official Ubuntu image as a base
FROM --platform=linux/amd64 ubuntu:20.04


# Set environment variables to non-interactive
ENV DEBIAN_FRONTEND=noninteractive

# Install basic dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    curl \
    wget \
    unzip \
    graphviz \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install dcm2niix
RUN apt-get update && apt-get install -y \
    dcm2niix \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy and install FSL using the provided Python script
COPY fslinstaller.py /tmp/fslinstaller.py
RUN python3 /tmp/fslinstaller.py --noninteractive --dest=/usr/local/fsl \
&& echo ". /usr/local/fsl/etc/fslconf/fsl.sh" >> ~/.bashrc

# Install FreeSurfer
RUN wget -qO- ftp://surfer.nmr.mgh.harvard.edu/pub/dist/freesurfer/7.1.1/freesurfer-Linux-centos6_x86_64-stable-pub-v7.1.1.tar.gz | tar -xz -C /opt \
    && ln -s /opt/freesurfer/7.1.1/ /opt/freesurfer \
    && echo "source /opt/freesurfer/SetUpFreeSurfer.sh" >> ~/.bashrc

# Install Matlab Runtime
RUN wget https://ssd.mathworks.com/supportfiles/downloads/R2020b/Release/5/deployment_files/installer/complete/glnxa64/MATLAB_Runtime_R2020b_glnxa64.zip \
    && unzip MATLAB_Runtime_R2020b_glnxa64.zip -d /opt/MATLAB_Runtime_R2020b \
    && rm MATLAB_Runtime_R2020b_glnxa64.zip

# Install 3D Slicer
RUN wget https://download.slicer.org/bitstream/63f71ecf38d7e30c56706bd9 \
    && mv 63f71ecf38d7e30c56706bd9 /usr/local/bin/Slicer \
    && chmod +x /usr/local/bin/Slicer

# Install Graphviz
RUN apt-get update && apt-get install -y \
    graphviz \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables for FSL and FreeSurfer
ENV FSLDIR=/usr/local/fsl \
    FREESURFER_HOME=/opt/freesurfer \
    FS_LICENSE=/opt/freesurfer/license.txt \
    PATH=$FSLDIR/bin:$FREESURFER_HOME/bin:$PATH \
    MATLAB_RUNTIME=/opt/MATLAB_Runtime_R2020b/v910

# Copy FreeSurfer license
COPY license.txt /opt/freesurfer/license.txt

RUN pip3 install swane
# Set entrypoint to bash to allow interactive sessions
ENTRYPOINT ["/bin/bash"]
