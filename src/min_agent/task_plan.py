"""V0.8: 不可变任务计划状态机。

TaskPlan 拥有所有合法的任务状态转换。它接收 TaskDefinition 列表，
内部维护可变运行时记录，仅通过 TaskSnapshot 副本对外暴露状态。
"""

from __future__ import annotations

from min_agent.types import (
    Observation,
    TaskArtifact,
    TaskArtifactDraft,
    TaskDefinition,
    TaskSnapshot,
    TaskStatus,
)


class TaskPlanError(ValueError):
    """任务计划状态转换非法。"""


class CompletionResult(tuple):
    """兼容 V0.8 快照属性访问的 (TaskSnapshot, TaskArtifact) 返回值。"""

    def __new__(cls, snapshot: TaskSnapshot, artifact: TaskArtifact):
        return super().__new__(cls, (snapshot, artifact))

    @property
    def snapshot(self) -> TaskSnapshot:
        return self[0]

    @property
    def artifact(self) -> TaskArtifact:
        return self[1]

    @property
    def status(self) -> TaskStatus:
        return self.snapshot.status

    @property
    def task_id(self) -> str:
        return self.snapshot.task_id


class TaskPlan:
    """不可变计划的运行时状态机。"""

    def __init__(self, definitions: list[TaskDefinition]) -> None:
        self._definitions: list[TaskDefinition] = list(definitions)
        self._statuses: dict[str, TaskStatus] = {}
        self._failure_reasons: dict[str, str] = {}
        self._artifacts: dict[str, TaskArtifact] = {}
        for d in self._definitions:
            self._statuses[d.task_id] = "pending"

    # ---- 工厂方法 ----

    @classmethod
    def create(cls, definitions: list[TaskDefinition]) -> TaskPlan:
        """从 TaskDefinition 列表创建并校验计划。"""
        cls._validate_definitions(definitions)
        return cls(definitions)

    @staticmethod
    def _validate_definitions(definitions: list[TaskDefinition]) -> None:
        n = len(definitions)
        if n < 2 or n > 5:
            raise TaskPlanError(f"计划必须包含 2–5 个任务，当前为 {n} 个")

        seen_ids: set[str] = set()
        for i, d in enumerate(definitions):
            expected_id = f"task-{i + 1}"
            if d.task_id != expected_id:
                raise TaskPlanError(
                    f"任务 ID 必须为 'task-{i + 1}'，实际为 '{d.task_id}'"
                )
            if d.task_id in seen_ids:
                raise TaskPlanError(f"任务 ID 重复：{d.task_id}")
            seen_ids.add(d.task_id)
            if not d.title.strip():
                raise TaskPlanError(f"任务 {d.task_id} 标题为空")
            if not d.completion_criteria.strip():
                raise TaskPlanError(f"任务 {d.task_id} 完成标准为空")

    # ---- 查询 ----

    def snapshot(self) -> list[TaskSnapshot]:
        """返回所有任务的当前状态副本。"""
        return [
            TaskSnapshot(
                task_id=d.task_id,
                title=d.title,
                completion_criteria=d.completion_criteria,
                status=self._statuses[d.task_id],
                failure_reason=self._failure_reasons.get(d.task_id, ""),
                artifact=self._artifacts.get(d.task_id),
            )
            for d in self._definitions
        ]

    def current_task(self) -> TaskSnapshot | None:
        """返回当前运行中的任务，没有则返回 None。"""
        for d in self._definitions:
            if self._statuses[d.task_id] == "running":
                return TaskSnapshot(
                    task_id=d.task_id,
                    title=d.title,
                    completion_criteria=d.completion_criteria,
                    status="running",
                )
        return None

    def all_completed(self) -> bool:
        """所有任务是否都已完成。"""
        return all(self._statuses[d.task_id] == "completed" for d in self._definitions)

    def artifacts(self) -> list[TaskArtifact]:
        return [self._artifacts[d.task_id] for d in self._definitions if d.task_id in self._artifacts]

    def artifact_for(self, task_id: str) -> TaskArtifact | None:
        return self._artifacts.get(task_id)

    def later_task_ids(self, task_id: str) -> list[str]:
        found = False
        later: list[str] = []
        for definition in self._definitions:
            if found:
                later.append(definition.task_id)
            elif definition.task_id == task_id:
                found = True
        return later

    # ---- 状态转换 ----

    def start_next(self) -> TaskSnapshot | None:
        """启动下一个 pending 任务，返回已启动的快照；无 pending 任务则返回 None。"""
        # 先检查是否已有 running 任务
        current = self.current_task()
        if current is not None:
            raise TaskPlanError(
                f"无法启动新任务：任务 {current.task_id} 仍在运行中"
            )

        for d in self._definitions:
            if self._statuses[d.task_id] == "pending":
                self._statuses[d.task_id] = "running"
                return TaskSnapshot(
                    task_id=d.task_id,
                    title=d.title,
                    completion_criteria=d.completion_criteria,
                    status="running",
                )
        return None

    def complete_current(
        self,
        task_id: str,
        completion_evidence: str,
        evidence_observation_indexes: list[int],
        observations: list[Observation],
        task_artifact: TaskArtifactDraft | None,
        created_at_step: int,
    ) -> CompletionResult:
        """将当前任务标记为完成，需提供有效证据。"""
        current = self.current_task()
        if current is None:
            raise TaskPlanError("没有正在运行的任务")
        if current.task_id != task_id:
            raise TaskPlanError(
                f"当前运行的任务是 {current.task_id}，不能完成 {task_id}"
            )

        self._validate_completion_evidence(
            task_id, completion_evidence, evidence_observation_indexes, observations
        )
        self._validate_artifact(task_artifact, created_at_step)

        assert task_artifact is not None
        artifact = TaskArtifact(
            task_id=task_id,
            title=task_artifact.title.strip(),
            content=task_artifact.content.strip(),
            evidence_observation_indexes=list(evidence_observation_indexes),
            created_at_step=created_at_step,
            status="available",
        )
        self._artifacts[task_id] = artifact
        self._statuses[task_id] = "completed"
        d = self._get_definition(task_id)
        completed = TaskSnapshot(
            task_id=d.task_id,
            title=d.title,
            completion_criteria=d.completion_criteria,
            status="completed",
            artifact=artifact,
        )
        return CompletionResult(completed, artifact)

    def fail_current(self, reason: str) -> tuple[TaskSnapshot, list[TaskSnapshot]]:
        """失败当前任务，跳过所有 pending 任务。返回 (failed_snapshot, skipped_snapshots)。"""
        current = self.current_task()
        if current is None:
            raise TaskPlanError("没有正在运行的任务可以失败")

        task_id = current.task_id
        self._statuses[task_id] = "failed"
        self._failure_reasons[task_id] = reason
        d = self._get_definition(task_id)
        failed = TaskSnapshot(
            task_id=d.task_id,
            title=d.title,
            completion_criteria=d.completion_criteria,
            status="failed",
            failure_reason=reason,
        )

        skipped: list[TaskSnapshot] = []
        for d2 in self._definitions:
            if self._statuses[d2.task_id] == "pending":
                self._statuses[d2.task_id] = "skipped"
                skip_reason = f"前序任务 {task_id} 失败，未执行：{reason}"
                self._failure_reasons[d2.task_id] = skip_reason
                skipped.append(
                    TaskSnapshot(
                        task_id=d2.task_id,
                        title=d2.title,
                        completion_criteria=d2.completion_criteria,
                        status="skipped",
                        failure_reason=skip_reason,
                    )
                )

        return failed, skipped

    # ---- 内部方法 ----

    def _get_definition(self, task_id: str) -> TaskDefinition:
        for d in self._definitions:
            if d.task_id == task_id:
                return d
        raise TaskPlanError(f"任务 ID 不存在：{task_id}")

    @staticmethod
    def _validate_completion_evidence(
        task_id: str,
        completion_evidence: str,
        evidence_observation_indexes: list[int],
        observations: list[Observation],
    ) -> None:
        if not completion_evidence.strip():
            raise TaskPlanError("完成证据不能为空")

        if not evidence_observation_indexes:
            raise TaskPlanError("必须至少引用一个当前任务的 Observation 索引")

        if len(evidence_observation_indexes) != len(set(evidence_observation_indexes)):
            raise TaskPlanError("Observation 索引不能重复")

        for idx in evidence_observation_indexes:
            if not isinstance(idx, int) or isinstance(idx, bool):
                raise TaskPlanError(f"Observation 索引必须是整数，实际为 {type(idx).__name__}: {idx}")
            if idx < 1:
                raise TaskPlanError(f"Observation 索引必须 >= 1（1-based），实际为 {idx}")
            if idx > len(observations):
                raise TaskPlanError(
                    f"Observation 索引 {idx} 超出范围（当前任务共 {len(observations)} 条 Observation）"
                )
            obs = observations[idx - 1]
            if not obs.result.success:
                raise TaskPlanError(
                    f"Observation {idx}（{obs.tool_name}）执行失败，不能作为完成证据"
                )

    @staticmethod
    def _validate_artifact(
        task_artifact: TaskArtifactDraft | None, created_at_step: int
    ) -> None:
        if task_artifact is None:
            raise TaskPlanError("完成任务必须提供任务产物")
        if not task_artifact.title.strip():
            raise TaskPlanError("任务产物标题不能为空")
        if not task_artifact.content.strip():
            raise TaskPlanError("任务产物内容不能为空")
        if not isinstance(created_at_step, int) or isinstance(created_at_step, bool) or created_at_step < 1:
            raise TaskPlanError("任务产物创建 step 必须是正整数")
