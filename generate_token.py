#!/usr/bin/env python
"""
Generate a LiveKit access token for testing.
Uses environment variables for credentials.
"""

import sys
import os
import datetime
from dotenv import load_dotenv
from livekit import api

# Load environment variables
load_dotenv()

# Get credentials from environment
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")
LIVEKIT_URL = os.getenv("LIVEKIT_URL")


def generate_token(room_name="test-room", participant_name="user-test", ttl_seconds=3600):
    """
    Generate a LiveKit access token.

    Args:
        room_name: Name of the room to join
        participant_name: Name for the participant
        ttl_seconds: Token validity duration in seconds (default 1 hour)

    Returns:
        JWT token string
    """
    if not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        raise ValueError("LIVEKIT_API_KEY and LIVEKIT_API_SECRET must be set in environment")

    # Create token
    token = api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)

    # Set identity and room
    token.with_identity(participant_name).with_name(participant_name)

    # Grant permissions
    token.with_grants(
        api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
        )
    )

    # Set TTL
    token.with_ttl(datetime.timedelta(seconds=ttl_seconds))

    return token.to_jwt()


if __name__ == "__main__":
    # Get room name from command line or use default
    room = sys.argv[1] if len(sys.argv) > 1 else "test-room"
    participant = sys.argv[2] if len(sys.argv) > 2 else "user-test"

    try:
        token = generate_token(room, participant)
        print(token)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
