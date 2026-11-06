from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    from mcp import Client, StdioServerParameters
    from mcp.types import ElicitResult

    from min_agent_chat.runtime import ChatRuntime
    from min_agent_chat.server import CARD_URI, build_server

    HAS_MCP = True
except ImportError:
    HAS_MCP = False


@unittest.skipUnless(HAS_MCP, "Optional chat extra is not installed")
class ChatAdapterTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        shutil.copytree(
            ROOT / "examples/workspace",
            self.workspace,
            ignore=shutil.ignore_patterns("summary*.md"),
        )
        self.runtime = ChatRuntime(self.workspace, self.root / "runs", delay=0)

    async def asyncTearDown(self):
        self.runtime.close()
        self.temp.cleanup()

    async def wait_for(self, client, run_id, states):
        for _ in range(200):
            result = await client.call_tool("get_demo", {"run_id": run_id})
            self.assertFalse(result.is_error, result.content)
            row = result.structured_content
            if row["status"] in states and (
                row["status"] != "waiting_permission" or row["permission"]
            ):
                return row
            await asyncio.sleep(0.01)
        self.fail("Demo did not reach expected state")

    async def start_write(self, client):
        result = await client.call_tool(
            "start_demo", {"goal": "请阅读 project.md 并生成 summary.md"}
        )
        self.assertFalse(result.is_error, result.content)
        return await self.wait_for(
            client, result.structured_content["run_id"], {"waiting_permission"}
        )

    async def test_read_only_goal_and_paginated_trace(self):
        async with Client(build_server(self.runtime), mode="legacy") as client:
            result = await client.call_tool(
                "start_demo",
                {"goal": "请阅读这个工作区里的资料，并总结这个 demo 是怎么工作的"},
            )
            self.assertFalse(result.is_error, result.content)
            row = await self.wait_for(
                client, result.structured_content["run_id"], {"completed"}
            )
            self.assertTrue(row["final_answer"])
            self.assertEqual("fake", row["decision_model"])
            first = (
                await client.call_tool(
                    "get_demo_trace", {"run_id": row["run_id"], "limit": 2}
                )
            ).structured_content
            self.assertEqual(2, len(first["events"]))
            self.assertTrue(first["has_more"])
            second = (
                await client.call_tool(
                    "get_demo_trace",
                    {
                        "run_id": row["run_id"],
                        "after_step": first["next_after_step"],
                        "limit": 2,
                    },
                )
            ).structured_content
            self.assertGreater(second["events"][0]["step"], first["next_after_step"])
            self.assertFalse((self.workspace / "summary.md").exists())

    async def test_tools_cannot_supply_approval_model_or_workspace(self):
        async with Client(build_server(self.runtime), mode="legacy") as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            self.assertNotIn(
                "approved", tools["confirm_demo_permission"].input_schema["properties"]
            )
            self.assertEqual(
                {"goal"}, set(tools["start_demo"].input_schema["properties"])
            )
            self.assertFalse(tools["start_demo"].annotations.read_only_hint)
            self.assertTrue(tools["get_demo"].annotations.read_only_hint)
            self.assertEqual(CARD_URI, tools["show_demo"].meta["ui"]["resourceUri"])
            for name, args in [
                ("start_demo", {"goal": ""}),
                ("get_demo", {"run_id": "../../outside"}),
                ("list_demos", {"limit": 1000}),
            ]:
                result = await client.call_tool(name, args)
                self.assertTrue(result.is_error)

    async def test_pending_write_and_missing_client_confirmation_never_write(self):
        async with Client(build_server(self.runtime), mode="legacy") as client:
            row = await self.start_write(client)
            result = await client.call_tool(
                "confirm_demo_permission",
                {
                    "run_id": row["run_id"],
                    "permission_id": row["permission"]["permission_id"],
                },
            )
            self.assertTrue(result.is_error)
            self.assertFalse((self.workspace / "summary.md").exists())
            self.assertEqual(
                "waiting_permission", self.runtime.get(row["run_id"])["status"]
            )
            conflict = await client.call_tool("start_demo", {"goal": "读取资料"})
            self.assertTrue(conflict.is_error)

    async def test_declined_write_stops_without_file(self):
        async def decline(_ctx, _params):
            return ElicitResult(action="decline")

        async with Client(
            build_server(self.runtime), mode="legacy", elicitation_callback=decline
        ) as client:
            row = await self.start_write(client)
            result = await client.call_tool(
                "confirm_demo_permission",
                {
                    "run_id": row["run_id"],
                    "permission_id": row["permission"]["permission_id"],
                },
            )
            self.assertFalse(result.is_error, result.content)
            self.assertFalse(result.structured_content["approved"])
            await self.wait_for(client, row["run_id"], {"failed"})
            self.assertFalse((self.workspace / "summary.md").exists())

    async def test_cancel_keeps_waiting_and_explicit_confirmation_writes_once(self):
        responses = [
            ElicitResult(action="cancel"),
            ElicitResult(action="accept", content={"approve": True}),
        ]

        async def decide(_ctx, params):
            self.assertIn("summary.md", params.message)
            return responses.pop(0)

        async with Client(
            build_server(self.runtime), mode="legacy", elicitation_callback=decide
        ) as client:
            row = await self.start_write(client)
            args = {
                "run_id": row["run_id"],
                "permission_id": row["permission"]["permission_id"],
            }
            first = await client.call_tool("confirm_demo_permission", args)
            self.assertFalse(first.is_error, first.content)
            self.assertEqual("waiting_permission", first.structured_content["status"])
            self.assertFalse((self.workspace / "summary.md").exists())
            second = await client.call_tool("confirm_demo_permission", args)
            self.assertFalse(second.is_error, second.content)
            self.assertTrue(second.structured_content["approved"])
            finished = await self.wait_for(client, row["run_id"], {"completed"})
            self.assertTrue((self.workspace / "summary.md").exists())
            self.assertEqual("summary.md", finished["files"][0]["path"])
            self.assertIn("# Summary", finished["files"][0]["content"])
            repeat = await client.call_tool("confirm_demo_permission", args)
            self.assertTrue(repeat.is_error)

    async def test_wrong_run_and_changed_permission_rejected(self):
        async def stale(_ctx, _params):
            request = self.runtime.permissions.current()
            self.runtime.permissions.resolve(request.permission_id, False)
            return ElicitResult(action="accept", content={"approve": True})

        async with Client(
            build_server(self.runtime), mode="legacy", elicitation_callback=stale
        ) as client:
            row = await self.start_write(client)
            wrong = await client.call_tool(
                "confirm_demo_permission",
                {
                    "run_id": "other-run",
                    "permission_id": row["permission"]["permission_id"],
                },
            )
            self.assertTrue(wrong.is_error)
            late = await client.call_tool(
                "confirm_demo_permission",
                {
                    "run_id": row["run_id"],
                    "permission_id": row["permission"]["permission_id"],
                },
            )
            self.assertTrue(late.is_error)
            self.assertFalse((self.workspace / "summary.md").exists())

    async def test_saved_history_is_read_only(self):
        async with Client(build_server(self.runtime), mode="legacy") as client:
            started = await client.call_tool(
                "start_demo", {"goal": "请阅读 project.md"}
            )
            run_id = started.structured_content["run_id"]
            await self.wait_for(client, run_id, {"completed"})
        before = {
            p.name: p.read_bytes() for p in self.workspace.iterdir() if p.is_file()
        }
        other = ChatRuntime(self.workspace, self.root / "runs", delay=0)
        async with Client(build_server(other), mode="legacy") as client:
            result = await client.call_tool("get_demo", {"run_id": run_id})
            self.assertEqual("completed", result.structured_content["status"])
            self.assertTrue(result.structured_content["final_answer"])
            self.assertIsNone(other.manager.current_snapshot())
        self.assertEqual(
            before,
            {p.name: p.read_bytes() for p in self.workspace.iterdir() if p.is_file()},
        )

    async def test_ui_resource_is_self_contained(self):
        async with Client(build_server(self.runtime), mode="legacy") as client:
            result = await client.read_resource(CARD_URI)
            html = result.contents[0].text
            self.assertIn("ui/initialize", html)
            self.assertIn("ui/notifications/tool-result", html)
            self.assertNotIn("innerHTML", html)
            self.assertNotIn("https://", html)

    async def test_real_stdio_protocol_roundtrip(self):
        code = (
            "from pathlib import Path; from min_agent_chat.runtime import ChatRuntime; "
            "from min_agent_chat.server import build_server; "
            "import sys; build_server(ChatRuntime(Path(sys.argv[1]),Path(sys.argv[2]),0)).run()"
        )
        transport = StdioServerParameters(
            command=sys.executable,
            args=["-c", code, str(self.workspace), str(self.root / "stdio-runs")],
            env={"PYTHONPATH": str(ROOT / "src")},
        )
        async with Client(transport) as client:
            result = await client.call_tool("start_demo", {"goal": "请阅读 project.md"})
            self.assertFalse(result.is_error, result.content)
            row = await self.wait_for(
                client, result.structured_content["run_id"], {"completed"}
            )
            self.assertTrue(row["final_answer"])
            shown = await client.call_tool("show_demo", {"run_id": row["run_id"]})
            self.assertEqual(row["run_id"], shown.structured_content["run_id"])


if __name__ == "__main__":
    unittest.main()
