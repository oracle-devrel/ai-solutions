@echo off
REM Oracle MCP AI Agents Setup Script for Windows
REM This script sets up the environment for Oracle MCP AI Agents

echo Setting up Oracle MCP AI Agents...

REM Create virtual environment
echo Creating Python virtual environment...
python -m venv mcp_env
call mcp_env\Scripts\activate.bat

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install requirements
echo Installing Python requirements...
pip install -r requirements.txt

REM Install Langflow
echo Installing Langflow...
pip install langflow --no-cache-dir

REM Create necessary directories
echo Creating directories...
if not exist logs mkdir logs
if not exist data mkdir data
if not exist flows mkdir flows

echo Setup complete! To start:
echo 1. Activate environment: mcp_env\Scripts\activate.bat
echo 2. Configure config\config.ini with your database details
echo 3. Start Langflow: langflow run --host 0.0.0.0 --port 7860
echo 4. Open browser to http://localhost:7860

pause
