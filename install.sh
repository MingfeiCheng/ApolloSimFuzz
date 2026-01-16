#!/usr/bin/env bash

set -Eeuo pipefail

#######################################
# Utilities
#######################################

log() {
    echo -e "[ApolloSimFuzz] $*"
}

error() {
    echo -e "[ApolloSimFuzz][ERROR] $*" >&2
    exit 1
}

trap 'error "Command failed at line $LINENO"' ERR

#######################################
# Load Apollo version
#######################################

if [[ ! -f VERSION ]]; then
    error "VERSION file not found"
fi

apollo_version="$(cat VERSION)"
log "Current Apollo version: ${apollo_version}"

apollo_tag="v${apollo_version}.0"
apollo_repo="https://github.com/ApolloAuto/apollo.git"

#######################################
# Clone Apollo (if not exists)
#######################################

if [[ -d apollo ]]; then
    log "Apollo repository already exists. Skipping clone."
else
    log "Cloning Apollo (${apollo_tag})..."
    git clone -b "${apollo_tag}" "${apollo_repo}" apollo
fi

#######################################
# Conda environment setup
#######################################

env_name="apollosimfuzz-${apollo_version}"

# Initialize conda
if ! command -v conda &> /dev/null; then
    error "Conda not found. Please install Anaconda/Miniconda first."
fi

eval "$(conda shell.bash hook)"

if conda info --envs | awk '{print $1}' | grep -qx "${env_name}"; then
    log "Conda environment '${env_name}' already exists. Skipping creation."
else
    log "Creating conda environment '${env_name}'..."
    conda create -n "${env_name}" python=3.7 -y
fi

log "Activating conda environment '${env_name}'..."
conda activate "${env_name}"

#######################################
# Python dependencies
#######################################

if [[ ! -f requirements.txt ]]; then
    error "requirements.txt not found"
fi

log "Installing Python dependencies..."
python -m pip install -r requirements.txt

#######################################
# TrafficSandbox setup
#######################################

if [[ ! -d TrafficSandbox ]]; then
    error "TrafficSandbox directory not found"
fi

if [[ ! -f TrafficSandbox/install.sh ]]; then
    error "TrafficSandbox/install.sh not found"
fi

log "Installing TrafficSandbox..."
bash TrafficSandbox/install.sh

#######################################
# Done
#######################################

log "Installation completed successfully."
log "Activated environment: ${env_name}"
