from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class SessionKeyStoreTest(unittest.TestCase):
    def test_lifecycle_and_invalid_input_preserves_existing_value(self) -> None:
        from min_agent.session_key_store import (
            InvalidSessionKey,
            SessionKeyNotConfigured,
            SessionKeyStore,
        )

        store = SessionKeyStore()
        self.assertFalse(store.is_configured())
        with self.assertRaises(SessionKeyNotConfigured):
            store.require()
        store.configure("  test-secret-never-log  ")
        self.assertEqual(store.require(), "test-secret-never-log")
        with self.assertRaises(InvalidSessionKey):
            store.configure("   ")
        self.assertEqual(store.require(), "test-secret-never-log")
        with self.assertRaises(InvalidSessionKey):
            store.configure(123)
        self.assertEqual(store.require(), "test-secret-never-log")
        store.clear()
        with self.assertRaises(SessionKeyNotConfigured):
            store.require()
