"""Quick test of Temporal connection."""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def test():
    print("Environment variables:")
    print(f"  TEMPORAL_NAMESPACE: {os.environ.get('TEMPORAL_NAMESPACE', 'NOT SET')}")
    print(f"  TEMPORAL_ADDRESS: {os.environ.get('TEMPORAL_ADDRESS', 'NOT SET')}")
    api_key = os.environ.get('TEMPORAL_API_KEY', '')
    print(f"  TEMPORAL_API_KEY: {'SET (' + str(len(api_key)) + ' chars)' if api_key else 'NOT SET'}")
    
    if not all([os.environ.get('TEMPORAL_NAMESPACE'), os.environ.get('TEMPORAL_ADDRESS'), os.environ.get('TEMPORAL_API_KEY')]):
        print("\nMissing environment variables!")
        return
    
    print("\nTesting connection...")
    try:
        from temporalio.client import Client
        client = await Client.connect(
            os.environ['TEMPORAL_ADDRESS'],
            namespace=os.environ['TEMPORAL_NAMESPACE'],
            api_key=os.environ['TEMPORAL_API_KEY'],
            tls=True,
        )
        print("✅ Connected successfully!")
        
        # Try to list workflows to verify permissions
        workflows = [w async for w in client.list_workflows(query="WorkflowType='test'", page_size=1)]
        print("✅ Can query workflows - permissions OK!")
        
    except Exception as e:
        print(f"❌ Connection failed: {type(e).__name__}: {e}")

asyncio.run(test())
