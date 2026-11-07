"""Durable inbox/task/outbox transactions. One worker, no automatic task replay."""
import os
import sqlite3
import threading
import time
import uuid

from min_agent_desktop.sanitize import clean_text
from .files import private_directory

HELP = ("已连接小看板。直接发送文字即可创建只读任务。\n"
        "进度：查看最近任务\n结果：重发最近结果\n帮助：查看说明\n"
        "每条任务使用独立 Codex 会话，不继承桌面聊天上下文。暂不支持图片、语音或写文件。")


class Database:
    def __init__(self, directory, owner, bound_at):
        path = private_directory(directory) / "bridge.sqlite3"
        if path.is_symlink():
            raise ValueError("数据库不能是符号链接")
        self.db = sqlite3.connect(path, check_same_thread=False)
        os.chmod(path, 0o600)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.owner, self.bound_at = owner, bound_at
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS inbox (id TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, prompt TEXT, context TEXT, status TEXT,
                detail TEXT, result TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS outbox (
                id TEXT PRIMARY KEY, context TEXT, text TEXT, attempts INTEGER DEFAULT 0,
                due REAL DEFAULT 0, delivered INTEGER DEFAULT 0);
        """)
        previous = self.db.execute("SELECT value FROM meta WHERE key='owner'").fetchone()
        if previous and previous[0] != owner:
            self.db.close()
            raise ValueError("此状态目录属于其他绑定账号，请使用新目录")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO meta VALUES ('owner', ?)", (owner,))

    def cursor(self):
        with self.lock:
            row = self.db.execute("SELECT value FROM meta WHERE key='cursor'").fetchone()
            return row[0] if row else ""

    def _reply(self, context, text, key=None):
        self.db.execute("INSERT OR IGNORE INTO outbox(id,context,text) VALUES (?,?,?)",
                        (key or str(uuid.uuid4()), context, clean_text(text, 3500)))

    def ingest(self, batch):
        """Commit message deduplication, tasks, replies and cursor together."""
        with self.lock, self.db:
            for msg in batch.get("msgs", []):
                if not isinstance(msg, dict) or msg.get("from_user_id") != self.owner:
                    continue
                if msg.get("group_id") or msg.get("message_type") != 1:
                    continue
                identity = msg.get("message_id")
                context = msg.get("context_token")
                stamp = msg.get("create_time_ms", 0)
                if (not isinstance(identity, (str, int)) or isinstance(identity, bool)
                        or not identity or not isinstance(context, str) or not context
                        or not isinstance(stamp, (int, float)) or stamp / 1000 < self.bound_at - 30):
                    continue
                inserted = self.db.execute("INSERT OR IGNORE INTO inbox VALUES (?)", (str(identity),))
                if not inserted.rowcount:
                    continue
                items = msg.get("item_list", [])
                if not isinstance(items, list):
                    items = []
                texts = [i.get("text_item", {}).get("text", "") for i in items
                         if isinstance(i, dict) and i.get("type") == 1
                         and isinstance(i.get("text_item"), dict)]
                text = "\n".join(x for x in texts if isinstance(x, str)).strip()
                if not text:
                    self._reply(context, "目前仅支持文字任务，请输入文字。")
                elif text in ("帮助", "/help"):
                    self._reply(context, HELP)
                elif text in ("进度", "/status", "结果", "/result"):
                    row = self.db.execute("SELECT * FROM tasks ORDER BY created DESC LIMIT 1").fetchone()
                    if not row:
                        self._reply(context, "还没有任务。直接发送文字即可开始。")
                    else:
                        labels = {"queued": "排队中", "running": "执行中", "succeeded": "已完成",
                                  "failed": "失败", "interrupted": "已中断"}
                        body = row["result"] if text in ("结果", "/result") else row["detail"]
                        self._reply(context, f"任务 {row['id']} · {labels[row['status']]}\n{body or '尚无结果'}")
                elif len(text) > 4000:
                    self._reply(context, "任务超过 4000 字，请缩短后发送。")
                elif self.db.execute("SELECT count(*) FROM tasks WHERE status IN ('queued','running')").fetchone()[0] >= 10:
                    self._reply(context, "待处理任务已达 10 条，请稍后再试。")
                else:
                    task_id = uuid.uuid4().hex[:12]
                    self.db.execute("INSERT INTO tasks VALUES (?,?,?,'queued','等待执行','',?)",
                                    (task_id, text, context, time.time()))
                    self._reply(context, f"已收到任务 {task_id}，正在排队。", task_id + ":received")
            if isinstance(batch.get("get_updates_buf"), str):
                self.db.execute("INSERT OR REPLACE INTO meta VALUES ('cursor',?)", (batch["get_updates_buf"],))

    def recover(self):
        with self.lock, self.db:
            rows = self.db.execute("SELECT * FROM tasks WHERE status='running'").fetchall()
            for row in rows:
                self.finish(row["id"], "interrupted", "服务重启，原任务已中断；如需重做请重新发送。")
            return [row["id"] for row in rows]

    def claim(self):
        with self.lock, self.db:
            row = self.db.execute("SELECT * FROM tasks WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if row:
                self.db.execute("UPDATE tasks SET status='running',detail='正在执行只读任务' WHERE id=?", (row["id"],))
                self._reply(row["context"], f"开始任务 {row['id']}：正在执行只读任务。", row["id"] + ":started")
                return dict(row)

    def progress(self, task_id, detail):
        with self.lock, self.db:
            self.db.execute("UPDATE tasks SET detail=? WHERE id=?", (clean_text(detail, 800), task_id))

    def finish(self, task_id, status, result):
        if status not in ("succeeded", "failed", "interrupted"):
            raise ValueError("无效终态")
        result = clean_text(result, 12000)
        with self.lock, self.db:
            row = self.db.execute("SELECT context FROM tasks WHERE id=?", (task_id,)).fetchone()
            self.db.execute("UPDATE tasks SET status=?,detail=?,result=? WHERE id=?", (status, result[:800], result, task_id))
            label = {"succeeded": "完成", "failed": "失败", "interrupted": "中断"}[status]
            # Bounded multi-part result. Stable IDs survive send retries.
            chunks = [result[i:i + 2800] for i in range(0, len(result), 2800)] or ["无结果"]
            for index, chunk in enumerate(chunks):
                self._reply(row[0], f"任务 {task_id} · {label} ({index + 1}/{len(chunks)})\n{chunk}",
                            f"{task_id}:final:{index}")

    def pending(self):
        with self.lock:
            row = self.db.execute("SELECT * FROM outbox WHERE delivered=0 AND attempts<5 ORDER BY rowid LIMIT 1").fetchone()
            return dict(row) if row and row["due"] <= time.time() else None

    def sent(self, identity, success):
        with self.lock, self.db:
            if success:
                self.db.execute("UPDATE outbox SET delivered=1 WHERE id=?", (identity,))
            else:
                self.db.execute("UPDATE outbox SET attempts=attempts+1,due=? WHERE id=?",
                                (time.time() + 30, identity))

    def summary(self):
        with self.lock:
            return {"tasks": dict(self.db.execute("SELECT status,count(*) FROM tasks GROUP BY status")),
                    "unsent": self.db.execute("SELECT count(*) FROM outbox WHERE delivered=0").fetchone()[0]}
