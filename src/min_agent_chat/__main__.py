from pathlib import Path

from min_agent_chat.runtime import ChatRuntime
from min_agent_chat.server import build_server


def main() -> None:
    # No caller-controlled workspace, command, model, or API-key parameters.
    root = Path(__file__).resolve().parents[2]
    runtime = ChatRuntime(root / "examples/workspace", root / "runs/chat")
    build_server(runtime).run(transport="stdio")


if __name__ == "__main__":
    main()
