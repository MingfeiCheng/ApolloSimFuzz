#!/bin/bash

# List of folders and files you want to include
INCLUDE_LIST=(
  apollo_bridge
  fuzzer
  registry
  scenario_corpus
  scenario_elements
  scenario_runner
  seed_generator
  tools
  TrafficSandbox
  config.yaml
  git_add.sh
  install.sh
  start_fuzzer.py
  README.md
  requirements.txt
  VERSION
)

find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type f -name ".DS_Store" -exec rm -f {} +

# Max file size in bytes (5MB = 5 * 1024 * 1024)
MAX_SIZE=$((5 * 1024 * 1024))

git add -u

# Loop through items and find files < 5MB
for item in "${INCLUDE_LIST[@]}"; do
  if [ -f "$item" ]; then
    # Item is a file
    if [ $(stat -c%s "$item") -lt $MAX_SIZE ]; then
      git add "$item"
    fi
  elif [ -d "$item" ]; then
    # Item is a directory
    find "$item" -type f -size -5M -exec git add {} \;
  fi
done
