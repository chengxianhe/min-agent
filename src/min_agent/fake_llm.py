from __future__ import annotations

import re

from min_agent.types import AgentAction, AgentContext, Observation, TaskArtifactDraft, TaskDefinition, TaskSnapshot


FILE_PATTERN = re.compile(r"[\w./-]+\.md")
MAX_FAKE_READS = 3
PATH_KEYWORDS = {
    "architecture": ("architecture", "架构", "结构", "模块", "流程"),
    "notes": ("notes", "笔记", "示例"),
    "project": ("project", "项目", "demo", "目标", "概览"),
    "usage": ("usage", "使用", "方式", "用法", "运行", "命令"),
}
WRITE_VERBS = ("生成", "写入", "保存", "create", "write", "save")
TIME_KEYWORDS = ("现在几点", "当前时间", "current time", "what time")

# V0.8: 复合目标检测需要三个信号
PROJECT_READING_SIGNALS = ("workspace", "项目资料", "工作区", "项目文件", "workspace 中的")
COMPOSITE_TIME_SIGNALS = ("获取当前时间", "获取时间", "当前时间", "get current time")
COMPOSITE_WRITE_TARGETS = ("summary.md", "总结.md", "report.md")


class FakeLLM:
    def decide(self, context: AgentContext) -> AgentAction:
        # --- V0.8: 如果已有计划，按计划执行 ---
        if context.task_plan:
            return self._decide_planned_goal(context)

        # --- V0.8: 检测复合目标 ---
        if self._is_composite_goal(context.user_goal):
            return self._create_composite_plan(context.user_goal)

        # --- V0.7: goal-first command routing for current-time queries ---
        if self._is_time_query(context.user_goal):
            return self._decide_time(context)

        mentioned_paths = self._extract_target_paths(context.user_goal)
        write_target = self._extract_write_target(context.user_goal)
        target_paths = self._source_target_paths(mentioned_paths, write_target)[:MAX_FAKE_READS]
        if not target_paths:
            listing_observation = self._find_latest_observation(
                context.observations,
                "list_dir",
                {"path": "."},
            )
            if listing_observation is None:
                observed_read_paths = self._read_paths_from_observations(context.observations)
                if write_target and observed_read_paths:
                    target_paths = observed_read_paths[:MAX_FAKE_READS]
                elif self._tool_available(context, "list_dir"):
                    return AgentAction.tool_call(
                        tool_name="list_dir",
                        args={"path": "."},
                        reason="用户目标没有指定 Markdown 文件，需要先查看 workspace 根目录中有哪些文件",
                    )
                else:
                    return self._cannot_decide_without_file_path()
            elif not listing_observation.result.success:
                return AgentAction.final_answer(
                    message=f"列出 workspace 文件失败：{listing_observation.result.error}",
                    reason="目录列表工具没有返回可用于选择文件的结果",
                    success=False,
                )
            else:
                listed_paths = self._markdown_paths_from_listing(listing_observation)
                if write_target:
                    listed_paths = [path for path in listed_paths if path != write_target]

                target_paths = self._select_markdown_paths(
                    context.user_goal,
                    listed_paths,
                )[:MAX_FAKE_READS]
                if not target_paths:
                    return AgentAction.final_answer(
                        message="没有在 workspace 根目录中发现可总结的 Markdown 文件。",
                        reason="目录列表结果中没有 type=file 且 path 以 .md 结尾的条目",
                        success=False,
                    )

        for target_path in target_paths:
            observation = self._find_latest_read_observation(context.observations, target_path)
            if observation is None:
                if target_path == write_target and self._tool_available(context, "write_file"):
                    continue
                if not self._tool_available(context, "read_file"):
                    return AgentAction.final_answer(
                        message=f"无法读取 {target_path}：当前上下文没有可用的 read_file 工具。",
                        reason="计划读取 Markdown 文件，但 read_file 工具不可用",
                        success=False,
                    )
                return AgentAction.tool_call(
                    tool_name="read_file",
                    args={"path": target_path},
                    reason=f"还没有 {target_path} 的内容，需要先读取文件后才能总结",
                )

            if not observation.result.success:
                return AgentAction.final_answer(
                    message=f"读取文件失败：{observation.result.error}",
                    reason="工具没有返回可用于总结的文件内容",
                    success=False,
                )

        if write_target:
            if not self._tool_available(context, "write_file"):
                return AgentAction.final_answer(
                    message=f"无法写入 {write_target}：当前上下文没有可用的 write_file 工具。",
                    reason="用户目标需要写文件，但 write_file 工具不可用",
                    success=False,
                )

            write_obs = self._find_write_observation(context.observations, write_target)
            if write_obs is None:
                read_paths = self._read_paths_from_observations(context.observations) or target_paths
                write_content = self._build_write_content(read_paths, context.observations)
                return AgentAction.tool_call(
                    tool_name="write_file",
                    args={
                        "path": write_target,
                        "content": write_content,
                        "mode": "create",
                    },
                    reason=f"已读取所需文件，需要把综合总结写入 {write_target}",
                )

            if write_obs.result.success:
                return AgentAction.final_answer(
                    message=f"已生成 {write_target}。\n{write_obs.result.content}",
                    reason=f"write_file 已成功创建 {write_target}",
                )

            if write_obs.result.metadata.get("permission") == "rejected":
                return AgentAction.final_answer(
                    message=f"没有生成 {write_target}，因为用户拒绝了写文件权限。",
                    reason="用户拒绝了写文件权限，Agent 不再重试",
                    success=False,
                )

            return AgentAction.final_answer(
                message=f"写入文件失败：{write_obs.result.error}",
                reason="write_file 工具返回了错误",
                success=False,
            )

        return AgentAction.final_answer(
            message=self._preview_multiple_files(target_paths, context.observations),
            reason="已经获得计划内 Markdown 文件内容，可以基于 observation 生成总结",
        )

    def _cannot_decide_without_file_path(self) -> AgentAction:
        return AgentAction.final_answer(
            message="无法判断需要读取哪个文件。请在任务中提供明确的 .md 文件名。",
            reason="用户目标中没有可识别的 Markdown 文件路径，且无法列出 workspace 文件",
            success=False,
        )

    def _extract_target_paths(self, user_goal: str) -> list[str]:
        target_paths: list[str] = []
        for match in FILE_PATTERN.findall(user_goal):
            if match not in target_paths:
                target_paths.append(match)
        return target_paths

    def _tool_available(self, context: AgentContext, tool_name: str) -> bool:
        return any(tool.name == tool_name for tool in context.available_tools)

    def _source_target_paths(self, target_paths: list[str], write_target: str | None) -> list[str]:
        if write_target is None:
            return target_paths
        return [target_path for target_path in target_paths if target_path != write_target]

    def _find_latest_observation(
        self,
        observations: list[Observation],
        tool_name: str,
        args: dict[str, object],
    ) -> Observation | None:
        for observation in reversed(observations):
            if observation.tool_name == tool_name and observation.args == args:
                return observation
        return None

    def _markdown_paths_from_listing(self, observation: Observation) -> list[str]:
        entries = observation.result.metadata.get("entries")
        if not isinstance(entries, list):
            return []

        target_paths: list[str] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            path = entry.get("path")
            if entry.get("type") != "file" or not isinstance(path, str) or not path.endswith(".md"):
                continue
            if path not in target_paths:
                target_paths.append(path)
        return target_paths

    def _select_markdown_paths(self, user_goal: str, paths: list[str]) -> list[str]:
        scored_paths = [
            (self._path_relevance_score(user_goal, path), index, path)
            for index, path in enumerate(paths)
        ]
        scored_paths.sort(key=lambda item: (-item[0], item[1]))
        return [path for _score, _index, path in scored_paths]

    def _path_relevance_score(self, user_goal: str, path: str) -> int:
        normalized_goal = user_goal.lower()
        normalized_path = path.lower()
        score = 0
        for path_keyword, goal_keywords in PATH_KEYWORDS.items():
            if path_keyword not in normalized_path:
                continue
            for keyword in goal_keywords:
                if keyword.lower() in normalized_goal:
                    score += 1
        return score

    def _find_latest_read_observation(
        self,
        observations: list[Observation],
        target_path: str,
    ) -> Observation | None:
        observation = self._find_latest_observation(
            observations,
            "read_file",
            {"path": target_path},
        )
        return observation

    def _preview_multiple_files(self, target_paths: list[str], observations: list[Observation]) -> str:
        previews: list[str] = []
        for target_path in target_paths:
            observation = self._find_latest_read_observation(observations, target_path)
            content = observation.result.content if observation else ""
            previews.append(self._preview_content(target_path, content))
        return "\n".join(previews)

    def _preview_content(self, target_path: str, content: str) -> str:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if not lines:
            return f"{target_path} 是一个空文件，没有可总结的内容。"
        preview = "；".join(lines[:3])
        return f"{target_path} 的主要内容：{preview}"

    def _has_write_intent(self, user_goal: str) -> bool:
        normalized = user_goal.lower()
        return any(verb in normalized for verb in WRITE_VERBS)

    def _extract_write_target(self, user_goal: str) -> str | None:
        if not self._has_write_intent(user_goal):
            return None
        target_paths = self._extract_target_paths(user_goal)
        for target_path in target_paths:
            write_verb_positions = [
                user_goal.lower().find(verb) for verb in WRITE_VERBS
            ]
            path_pos = user_goal.lower().find(target_path.lower())
            if any(
                pos >= 0 and path_pos > pos
                for pos in write_verb_positions
            ):
                return target_path
        if target_paths:
            return target_paths[0]
        return None

    def _read_paths_from_observations(self, observations: list[Observation]) -> list[str]:
        paths: list[str] = []
        for obs in observations:
            if obs.tool_name == "read_file" and obs.result.success:
                path = obs.args.get("path")
                if isinstance(path, str) and path not in paths:
                    paths.append(path)
        return paths

    def _find_write_observation(
        self,
        observations: list[Observation],
        target_path: str,
    ) -> Observation | None:
        for obs in reversed(observations):
            if obs.tool_name == "write_file" and obs.args.get("path") == target_path:
                return obs
        return None

    def _build_write_content(
        self,
        target_paths: list[str],
        observations: list[Observation],
    ) -> str:
        sections: list[str] = ["# Summary\n"]
        for target_path in target_paths:
            obs = self._find_latest_read_observation(observations, target_path)
            if obs and obs.result.success:
                lines = [line.strip() for line in obs.result.content.splitlines() if line.strip()]
                preview = " ".join(lines[:3])
                sections.append(f"## {target_path}\n{preview}\n")
        return "\n".join(sections)

    # ---- V0.7: current-time command routing ----

    @staticmethod
    def _is_time_query(user_goal: str) -> bool:
        normalized = user_goal.lower()
        return any(keyword in normalized for keyword in TIME_KEYWORDS)

    def _decide_time(self, context: AgentContext) -> AgentAction:
        """Route current-time queries based on the latest run_command Observation."""
        time_obs = self._find_latest_time_observation(context.observations)

        if time_obs is None:
            if self._tool_available(context, "run_command"):
                return AgentAction.tool_call(
                    tool_name="run_command",
                    args={"command_id": "get_current_time"},
                    reason="当前时间是实时信息，需要通过允许的本地命令获取",
                )
            return AgentAction.final_answer(
                message="当前 Agent 没有获取实时本地时间的工具（run_command 不可用），无法回答时间问题。",
                reason="run_command 工具不可用",
                success=False,
            )

        if time_obs.result.success:
            return AgentAction.final_answer(
                message=f"当前本地时间是 {time_obs.result.content}。",
                reason="已通过 run_command 获得当前时间",
            )

        if time_obs.result.metadata.get("permission") == "rejected":
            return AgentAction.final_answer(
                message="未获授权执行获取时间的命令，无法获取当前本地时间。",
                reason="用户拒绝了 run_command 权限",
                success=False,
            )

        error = time_obs.result.error or "unknown error"
        return AgentAction.final_answer(
            message=f"获取当前时间失败：{error}",
            reason=f"run_command 返回了错误：{error}",
            success=False,
        )

    def _find_latest_time_observation(
        self,
        observations: list[Observation],
    ) -> Observation | None:
        for obs in reversed(observations):
            if obs.tool_name == "run_command" and obs.args.get("command_id") == "get_current_time":
                return obs
        return None

    # ---- V0.8: composite goal routing ----

    @staticmethod
    def _is_composite_goal(user_goal: str) -> bool:
        """需要同时满足三个信号：项目/workspace 阅读意图 + 获取当前时间意图 + 显式 Markdown 写入目标。"""
        normalized = user_goal.lower()

        # 项目阅读意图：排除明确否定
        has_project_reading = any(
            signal.lower() in normalized for signal in PROJECT_READING_SIGNALS
        )
        # 如果包含"不需要阅读项目资料"等否定，排除
        if "不需要" in normalized and "项目资料" in normalized:
            has_project_reading = False

        # 时间意图：必须是"获取时间"的动作，而非内容匹配
        has_time_intent = any(
            signal.lower() in normalized for signal in COMPOSITE_TIME_SIGNALS
        )
        # 排除引号内的"当前时间"（内容匹配而非系统时间意图）
        if has_time_intent and '"当前时间"' in user_goal:
            has_time_intent = False
        if has_time_intent and '“当前时间”' in user_goal:
            has_time_intent = False

        has_write_target = any(
            target.lower() in normalized for target in COMPOSITE_WRITE_TARGETS
        ) or ("生成" in normalized and ".md" in normalized)

        return has_project_reading and has_time_intent and has_write_target

    def _create_composite_plan(self, user_goal: str) -> AgentAction:
        """为复合目标生成固定的 4 任务计划。"""
        _ = user_goal  # 参数保留用于未来扩展
        tasks = [
            TaskDefinition(
                task_id="task-1",
                title="查看项目文件",
                completion_criteria="成功获得 workspace 中可用 Markdown 文件列表",
            ),
            TaskDefinition(
                task_id="task-2",
                title="读取并整理资料",
                completion_criteria="成功读取相关 Markdown 文件并形成摘要所需内容",
            ),
            TaskDefinition(
                task_id="task-3",
                title="获取当前时间",
                completion_criteria="成功获得 run_command/get_current_time 的真实结果",
            ),
            TaskDefinition(
                task_id="task-4",
                title="生成并写入摘要",
                completion_criteria="成功创建包含项目摘要和真实时间的 summary.md",
            ),
        ]
        return AgentAction.create_plan(tasks, reason="用户目标包含项目阅读、时间获取和文件写入三个可验收子目标")

    def _decide_planned_goal(self, context: AgentContext) -> AgentAction:
        """在已有计划中按当前任务执行。"""
        current_id = context.current_task_id
        observations = context.observations

        if current_id == "task-1":
            return self._decide_task1(observations)
        elif current_id == "task-2":
            return self._decide_task2(observations, context)
        elif current_id == "task-3":
            return self._decide_task3(observations)
        elif current_id == "task-4":
            return self._decide_task4(observations, context)
        else:
            # 全部完成
            return AgentAction.final_answer(
                message="已完成 summary.md 的生成，包含项目资料摘要和当前时间。",
                reason="所有四个任务都已完成",
            )

    def _decide_task1(self, observations: list[Observation]) -> AgentAction:
        """任务 1：查看项目文件。"""
        list_obs = self._find_latest_observation(observations, "list_dir", {"path": "."})
        if list_obs is None:
            return AgentAction.tool_call(
                tool_name="list_dir",
                args={"path": "."},
                reason="需要查看 workspace 中有哪些项目文件",
            )
        if list_obs.result.success:
            return AgentAction.complete_task(
                task_id="task-1",
                completion_evidence="list_dir Observation succeeded",
                evidence_observation_indexes=[1],
                reason="已成功获得 workspace 文件列表",
                task_artifact=TaskArtifactDraft("Workspace Markdown 文件清单", list_obs.result.content),
            )
        return AgentAction.final_answer(
            message=f"查看项目文件失败：{list_obs.result.error}",
            reason="list_dir 失败",
            success=False,
        )

    def _decide_task2(self, observations: list[Observation], context: AgentContext) -> AgentAction:
        """任务 2：读取并整理项目资料。"""
        read_obs_count = sum(1 for o in observations if o.tool_name == "read_file" and o.result.success)
        if read_obs_count < MAX_FAKE_READS:
            listing = self._inherited_artifact(context, "task-1")
            paths_to_read = self._artifact_markdown_paths(listing.content) if listing else []
            paths_to_read = [path for path in paths_to_read if path not in {"summary.md", "minagent.md"}]
            if not paths_to_read:
                return AgentAction.final_answer(
                    message="缺少 task-1 的 Workspace Markdown 文件清单，无法读取项目资料。",
                    reason="任务 2 只能从继承的 task-1 产物选择文件",
                    success=False,
                )
            for path in paths_to_read:
                obs = self._find_latest_read_observation(observations, path)
                if obs is None:
                    return AgentAction.tool_call(
                        tool_name="read_file",
                        args={"path": path},
                        reason=f"需要读取 {path} 以获取项目资料内容",
                    )
            pass

        if read_obs_count > 0:
            indexes = [i + 1 for i, o in enumerate(observations)
                       if o.tool_name == "read_file" and o.result.success]
            return AgentAction.complete_task(
                task_id="task-2",
                completion_evidence="read_file Observations succeeded",
                evidence_observation_indexes=indexes,
                reason="已成功读取相关 Markdown 文件",
                task_artifact=TaskArtifactDraft("项目资料摘要", self._summary_from_reads(observations)),
            )

        return AgentAction.tool_call(
            tool_name="read_file",
            args={"path": "project.md"},
            reason="需要读取项目资料",
        )

    def _decide_task3(self, observations: list[Observation]) -> AgentAction:
        """任务 3：获取当前时间。"""
        time_obs = self._find_latest_time_observation(observations)
        if time_obs is None:
            return AgentAction.tool_call(
                tool_name="run_command",
                args={"command_id": "get_current_time"},
                reason="需要获取当前系统时间",
            )
        if time_obs.result.success:
            return AgentAction.complete_task(
                task_id="task-3",
                completion_evidence="run_command/get_current_time Observation succeeded",
                evidence_observation_indexes=[1],
                reason="已成功获取当前时间",
                task_artifact=TaskArtifactDraft("当前本地时间", time_obs.result.content),
            )
        error = time_obs.result.error or "unknown"
        return AgentAction.final_answer(
            message=f"获取当前时间失败：{error}",
            reason=f"run_command 失败：{error}",
            success=False,
        )

    def _decide_task4(self, observations: list[Observation], context: AgentContext) -> AgentAction:
        """任务 4：生成并写入 summary.md。"""
        write_obs = self._find_write_observation(observations, "summary.md")
        if write_obs is None:
            summary = self._inherited_artifact(context, "task-2")
            current_time = self._inherited_artifact(context, "task-3")
            if summary is None or current_time is None:
                return AgentAction.final_answer(
                    message="缺少项目资料摘要或当前时间产物，无法生成 summary.md。",
                    reason="任务 4 必须使用 task-2 和 task-3 的已存储产物",
                    success=False,
                )
            write_content = f"# Summary\n\n{summary.content}\n\nGenerated at: {current_time.content}\n"

            return AgentAction.tool_call(
                tool_name="write_file",
                args={
                    "path": "summary.md",
                    "content": write_content,
                    "mode": "create",
                },
                reason="需要将包含项目摘要和时间的总结写入 summary.md",
            )

        if write_obs.result.success:
            return AgentAction.complete_task(
                task_id="task-4",
                completion_evidence="write_file Observation succeeded",
                evidence_observation_indexes=[len(observations)],
                reason="已成功创建 summary.md",
                task_artifact=TaskArtifactDraft("摘要文件写入结果", write_obs.result.content),
            )

        if write_obs.result.metadata.get("permission") == "rejected":
            return AgentAction.final_answer(
                message="没有生成 summary.md，因为用户拒绝了写文件权限。",
                reason="用户拒绝了写文件权限",
                success=False,
            )

        return AgentAction.final_answer(
            message=f"写入文件失败：{write_obs.result.error}",
            reason="write_file 失败",
            success=False,
        )

    @staticmethod
    def _inherited_artifact(context: AgentContext, task_id: str):
        return next(
            (artifact for artifact in context.inherited_task_artifacts
             if artifact.task_id == task_id and artifact.status == "available"),
            None,
        )

    def _artifact_markdown_paths(self, content: str) -> list[str]:
        paths: list[str] = []
        for path in FILE_PATTERN.findall(content):
            if path not in paths:
                paths.append(path)
        return paths[:MAX_FAKE_READS]

    def _summary_from_reads(self, observations: list[Observation]) -> str:
        sections: list[str] = []
        for observation in observations:
            if observation.tool_name != "read_file" or not observation.result.success:
                continue
            path = observation.args.get("path")
            if not isinstance(path, str):
                continue
            lines = [line.strip() for line in observation.result.content.splitlines() if line.strip()]
            sections.append(f"## {path}\n{' '.join(lines[:3])}")
        return "\n\n".join(sections)
