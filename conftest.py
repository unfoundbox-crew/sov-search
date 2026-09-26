import sys
from pathlib import Path

# Add firehose, stealth, offline, index to sys.path so tests can import modules directly
root = Path(__file__).parent
for sub in ["firehose", "stealth", "offline", "index"]:
    p = str(root / sub)
    if p not in sys.path:
        sys.path.insert(0, p)
