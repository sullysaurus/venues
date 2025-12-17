"""
Temporal Cloud client configuration.

Connects to Temporal Cloud using API key authentication.
"""

import os
from typing import Optional
from temporalio.client import Client, TLSConfig

# Default task queue for venue pipeline
TASK_QUEUE = "venue-pipeline-queue"


async def get_temporal_client() -> Client:
    """
    Create a Temporal Cloud client.

    Requires environment variables:
    - TEMPORAL_NAMESPACE: Your Temporal Cloud namespace
    - TEMPORAL_ADDRESS: Temporal Cloud address (e.g., namespace.tmprl.cloud:7233)
    - TEMPORAL_API_KEY: Your Temporal Cloud API key

    For local development with Temporal dev server:
    - Set TEMPORAL_LOCAL=true to connect to localhost:7233 without TLS

    Returns:
        Connected Temporal client
    """
    # Check for local development mode
    if os.environ.get("TEMPORAL_LOCAL", "").lower() == "true":
        return await Client.connect(
            "localhost:7233",
            namespace="default",
        )

    # Temporal Cloud configuration
    namespace = os.environ.get("TEMPORAL_NAMESPACE")
    address = os.environ.get("TEMPORAL_ADDRESS")
    api_key = os.environ.get("TEMPORAL_API_KEY")

    if not all([namespace, address, api_key]):
        missing = []
        if not namespace:
            missing.append("TEMPORAL_NAMESPACE")
        if not address:
            missing.append("TEMPORAL_ADDRESS")
        if not api_key:
            missing.append("TEMPORAL_API_KEY")
        raise ValueError(
            f"Missing required environment variables for Temporal Cloud: {', '.join(missing)}\n"
            "Set TEMPORAL_LOCAL=true to use local dev server instead."
        )

    client = await Client.connect(
        address,
        namespace=namespace,
        api_key=api_key,
        tls=True,
    )

    return client


# Singleton pattern for reuse
_client: Optional[Client] = None


async def get_client() -> Client:
    """Get or create a Temporal client (singleton)."""
    global _client
    if _client is None:
        _client = await get_temporal_client()
    return _client


def reset_client():
    """Reset the singleton client (for testing)."""
    global _client
    _client = None
