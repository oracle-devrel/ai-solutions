#!/bin/bash

# Oracle MCP AI Agents Setup Script
# This script sets up the environment for Oracle MCP AI Agents

echo "Setting up Oracle MCP AI Agents..."

# Create virtual environment
echo "Creating Python virtual environment..."
python3 -m venv mcp_env
source mcp_env/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo "Installing Python requirements..."
pip install -r requirements.txt

# Install Langflow
echo "Installing Langflow..."
pip install langflow --no-cache-dir

# Create necessary directories
echo "Creating directories..."
mkdir -p logs
mkdir -p data
mkdir -p flows

# Set permissions
chmod +x scripts/*.sh

echo "Setup complete! To start:"
echo "1. Activate environment: source mcp_env/bin/activate"
echo "2. Configure config/config.ini with your database details"
echo "3. Start Langflow: langflow run --host 0.0.0.0 --port 7860"
echo "4. Open browser to http://localhost:7860"
