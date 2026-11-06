"""Source-checkout launcher; all paths remain relative to this installation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from min_agent_chat.__main__ import main

if __name__ == "__main__":
    main()
