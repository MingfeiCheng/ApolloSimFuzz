#!/bin/bash

set -e  # Exit on error

apollo_version=$(cat VERSION)
echo "Current project version is: $apollo_version"

git clone -b "v${apollo_version}.0" https://github.com/ApolloAuto/apollo.git

env_name="drivora-apollo-${apollo_version}"

# Check if conda env exists
if conda info --envs | awk '{print $1}' | grep -q "^${env_name}$"; then
    echo "Conda environment '${env_name}' already exists. Skipping creation."
else
    echo "Creating conda environment '${env_name}'..."
    conda create -n "${env_name}" python=3.7 -y
fi

# Activate environment (note: must be run via 'source')
eval "$(conda shell.bash hook)"
conda activate "${env_name}"

# Install Python dependencies
pip install -r requirements.txt

cd TrafficSandbox

docker build -t drivora/sandbox .
