"""Durable delivery receipts. An ambiguous Codex send is never blindly replayed."""
import os
import sqlite3
import threading
import time

from min_agent_desktop.sanitize import clean_text
from .files import private_directory


class RelayStore:
    def __init__(self, directory, owner, thread_id, since=None):
        directory = private_directory(directory)
        path = directory / "relay.sqlite3"
        if path.is_symlink():
            raise ValueError("转发数据库不能是符号链接")
        self.db = sqlite3.connect(path, check_same_thread=False)
        os.chmod(path, 0o600)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.owner = owner
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS inbox (
              id TEXT PRIMARY KEY, text TEXT, status TEXT, turn_id TEXT DEFAULT '', created REAL);
            CREATE TABLE IF NOT EXISTS outbox (
              id TEXT PRIMARY KEY, text TEXT, delivered INTEGER DEFAULT 0,
              attempts INTEGER DEFAULT 0, due REAL DEFAULT 0);
        """)
        for key, value in (("owner", owner), ("thread", thread_id)):
            old = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            if old and old[0] != value:
                self.db.close()
                raise ValueError("此转发目录已经绑定其他账号或会话")
        with self.db:
            for key, value in (("owner", owner), ("thread", thread_id)):
                self.db.execute("INSERT OR IGNORE INTO meta VALUES (?,?)", (key, value))
            self.db.execute("INSERT OR IGNORE INTO meta VALUES ('since',?)", (str(since or time.time()),))
            interrupted = self.db.execute("SELECT id FROM inbox WHERE status='sending'").fetchall()
            self.db.execute("UPDATE inbox SET status='uncertain' WHERE status='sending'")
            for row in interrupted:
                self.enqueue("uncertain:" + row[0], "服务恢复：有一条消息的投递回执未保存，可能已进入当前会话；不会自动重发，请先在桌面核对。")

    def get(self, key, default=""):
        with self.lock:
            row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            return row[0] if row else default

    def put(self, key, value):
        with self.lock, self.db:
            self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, str(value)))

    def enqueue(self, identity, text):
        """Caller may include this in the same transaction as consuming an inbox message."""
        self.db.execute("INSERT OR IGNORE INTO outbox(id,text) VALUES (?,?)", (identity, clean_text(text, 3200)))

    def ingest(self, batch):
        if not isinstance(batch.get("msgs", []), list):
            raise ValueError("微信收件格式无效")
        with self.lock, self.db:
            for msg in batch.get("msgs", []):
                if (not isinstance(msg, dict) or msg.get("from_user_id") != self.owner
                        or msg.get("message_type") != 1 or msg.get("group_id")):
                    continue
                identity, context, stamp = msg.get("message_id"), msg.get("context_token"), msg.get("create_time_ms")
                if (not isinstance(identity, (str, int)) or isinstance(identity, bool) or not identity
                        or not isinstance(context, str) or not context or len(context) > 16384
                        or not isinstance(stamp, (int, float)) or stamp / 1000 < float(self.get("since"))):
                    continue
                items = msg.get("item_list", [])
                if not isinstance(items, list):
                    items = []
                texts = [x.get("text_item", {}).get("text", "") for x in items if isinstance(x, dict)
                         and x.get("type") == 1 and isinstance(x.get("text_item"), dict)]
                text = "\n".join(x for x in texts if isinstance(x, str)).strip()
                identity = str(identity)
                if self.db.execute("SELECT 1 FROM inbox WHERE id=?", (identity,)).fetchone():
                    continue
                self.db.execute("INSERT OR REPLACE INTO meta VALUES ('context',?)", (context,))
                status = "queued"
                error = ""
                if not text:
                    error = "目前只接收文字消息。"
                elif len(text) > 8000:
                    error = "消息超过 8000 字，请缩短后再发。"
                elif self.db.execute("SELECT count(*) FROM inbox WHERE status IN ('queued','sending')").fetchone()[0] >= 20:
                    error = "待转发消息已达 20 条，请稍后再试。"
                if error:
                    status = "rejected"
                self.db.execute("INSERT INTO inbox(id,text,status,created) VALUES (?,?,?,?)",
                                (identity, text[:8000], status, time.time()))
                if error:
                    self.enqueue("reject:" + identity, error)
            if isinstance(batch.get("get_updates_buf"), str):
                self.db.execute("INSERT OR REPLACE INTO meta VALUES ('cursor',?)", (batch["get_updates_buf"],))

    def next_message(self):
        with self.lock:
            row = self.db.execute("SELECT * FROM inbox WHERE status='queued' ORDER BY rowid LIMIT 1").fetchone()
            return dict(row) if row else None

    def mark(self, identity, status, turn_id="", reply=""):
        with self.lock, self.db:
            self.db.execute("UPDATE inbox SET status=?,turn_id=? WHERE id=?", (status, turn_id, identity))
            if reply:
                self.enqueue(status + ":" + identity, reply)

    def outgoing(self):
        with self.lock:
            if not self.get("context"):
                return None
            row = self.db.execute("SELECT * FROM outbox WHERE delivered=0 AND attempts<5 ORDER BY rowid LIMIT 1").fetchone()
            return dict(row) if row and row["due"] <= time.time() else None

    def sent(self, identity, success):
        with self.lock, self.db:
            if success:
                self.db.execute("UPDATE outbox SET delivered=1 WHERE id=?", (identity,))
            else:
                self.db.execute("UPDATE outbox SET attempts=attempts+1,due=? WHERE id=?", (time.time() + 30, identity))

    def summary(self):
        with self.lock:
            return {"tasks": dict(self.db.execute("SELECT status,count(*) FROM inbox GROUP BY status")),
                    "unsent": self.db.execute("SELECT count(*) FROM outbox WHERE delivered=0").fetchone()[0]}
