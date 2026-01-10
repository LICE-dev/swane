FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV FSLOUTPUTTYPE=NIFTI_GZ

# ----------------------------
# System dependencies
# ----------------------------
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-lxml \
    wget \
    git \
    graphviz \
    dcm2niix \
    libgl1-mesa-glx \
    libx11-6 \
    libxcb-xinerama0 \
    libxcb-cursor0 \
    libxrender1 \
    libxext6 \
    libxrandr2 \
    libxi6 \
    libpulse-dev \
    libnss3 \
    libglu1-mesa \
    libxkbcommon-x11-0 \
    libxkbcommon0 \
    && apt install --reinstall libxcb-xinerama0 \
    && rm -rf /var/lib/apt/lists/*

# ----------------------------
# Miniforge + FSL
# ----------------------------
ENV CONDA_DIR=/opt/conda
RUN wget -q https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh \
    && bash Miniforge3-Linux-x86_64.sh -b -p $CONDA_DIR \
    && rm Miniforge3-Linux-x86_64.sh
ENV PATH=$CONDA_DIR/bin:$PATH

RUN conda config --system --set channel_priority strict \
 && conda config --system --add channels https://fsl.fmrib.ox.ac.uk/fsldownloads/fslconda/public/ \
 && conda config --system --add channels conda-forge \
 && conda config --system --add channels defaults

# Installazione FSL
RUN conda create -y -n fsl fsl-base=2511.0 \
 && conda clean -afy

ENV FSLDIR=$CONDA_DIR/envs/fsl
ENV PATH=$FSLDIR/bin:$PATH
ENV FSLOUTPUTTYPE=NIFTI_GZ


# ----------------------------
# FreeSurfer
# ----------------------------
ENV FREESURFER_HOME=/opt/freesurfer
# esempio semplificato: usare installer ufficiale
# RUN wget ... && bash installer.sh
# USER deve montare la licenza

# ----------------------------
# Slicer CLI
# ----------------------------
#RUN wget https://download.slicer.org/bitstream/xyz/Slicer.tar.gz \
#    && tar -xzf Slicer.tar.gz -C /opt \
#    && rm Slicer.tar.gz
#ENV PATH=/opt/Slicer:$PATH

# ----------------------------
# Python deps
# ----------------------------
RUN pip install --no-cache-dir swane

# DEBUG: missing EGL
RUN apt-get update && apt-get install -y \
    libegl1 \
    && rm -rf /var/lib/apt/lists/*

# Qt6 XCB runtime (required for PySide6)
RUN apt-get update && apt-get install -y \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcb-cursor0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render0 \
    libxcb-render-util0 \
    libxcb-shape0 \
    libxcb-sync1 \
    libxcb-xfixes0 \
    libxcb-xinerama0 \
    libxcb-xkb1 \
    libxcb-util1 \
    libxkbcommon0 \
    libxkbcommon-x11-0 \
    libxrender1 \
    libxi6 \
    libxrandr2 \
    libegl1 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y \
    libxkbcommon0 \
    libxcb-cursor0 \
    libxcb-xinerama0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-render-util0 \
    libxrender1 \
    libxi6 \
    libegl1 \
    libgl1 \
    libsm6 \
    libice6 \
    libxext6 \
    libx11-6 \
    libx11-xcb1 \
    libxcb-cursor-dev \
    && rm -rf /var/lib/apt/lists/*


# Entrypoint che crea l'utente a runtime
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
