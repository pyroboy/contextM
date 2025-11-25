#!/bin/bash
# Get the directory where the script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Change to the script's directory so the app can find its files
cd "$DIR"

# Run the python script
/usr/local/bin/python3 main.py
