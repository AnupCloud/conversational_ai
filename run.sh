#!/bin/bash
# ===========================================
# Conversation AI - Run Script
# ===========================================
# This script starts the agent and generates a test token

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
ROOM_NAME="${ROOM_NAME:-test-room}"
PARTICIPANT_NAME="${PARTICIPANT_NAME:-user-test}"
PLAYGROUND_URL="https://agents-playground.livekit.io/"

echo -e "${BLUE}"
echo "=========================================="
echo "   Conversation AI - Voice Agent"
echo "=========================================="
echo -e "${NC}"

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${RED}Error: .env file not found!${NC}"
    echo "Please copy .env.example to .env and configure your credentials:"
    echo "  cp .env.example .env"
    exit 1
fi

# Source environment variables
source .env

# Check required environment variables
if [ -z "$LIVEKIT_URL" ] || [ -z "$LIVEKIT_API_KEY" ] || [ -z "$LIVEKIT_API_SECRET" ]; then
    echo -e "${RED}Error: LiveKit credentials not configured in .env${NC}"
    exit 1
fi

if [ -z "$SARVAM_API_KEY" ]; then
    echo -e "${RED}Error: SARVAM_API_KEY not configured in .env${NC}"
    exit 1
fi

if [ -z "$GEMINI_API_KEY" ]; then
    echo -e "${RED}Error: GEMINI_API_KEY not configured in .env${NC}"
    exit 1
fi

# Check if uv is installed
if command -v uv &> /dev/null; then
    PYTHON_CMD="uv run python"
    echo -e "${GREEN}Using uv package manager${NC}"
else
    # Check for virtual environment
    if [ -d ".venv" ]; then
        source .venv/bin/activate
        PYTHON_CMD="python"
        echo -e "${GREEN}Using virtual environment${NC}"
    else
        echo -e "${YELLOW}Warning: No virtual environment found. Using system Python.${NC}"
        PYTHON_CMD="python"
    fi
fi

# Generate token
echo -e "\n${YELLOW}Generating access token...${NC}"
TOKEN=$($PYTHON_CMD generate_token.py "$ROOM_NAME" "$PARTICIPANT_NAME")

if [ -z "$TOKEN" ]; then
    echo -e "${RED}Error: Failed to generate token${NC}"
    exit 1
fi

# Note: Agent uses auto-dispatch mode - no explicit dispatch needed
# The agent will automatically join when a participant connects to the room

# Display connection information
echo -e "\n${GREEN}=========================================="
echo -e "   AGENT READY - Connect Now!"
echo -e "==========================================${NC}"
echo ""
echo -e "${BLUE}1. Open LiveKit Playground:${NC}"
echo "   $PLAYGROUND_URL"
echo ""
echo -e "${BLUE}2. LiveKit URL:${NC}"
echo "   $LIVEKIT_URL"
echo ""
echo -e "${BLUE}3. Access Token:${NC}"
echo "   $TOKEN"
echo ""
echo -e "${BLUE}4. Room:${NC} $ROOM_NAME"
echo ""
echo -e "${YELLOW}Starting agent... (Press Ctrl+C to stop)${NC}"
echo "=========================================="
echo ""

# Start the agent
$PYTHON_CMD main.py dev
