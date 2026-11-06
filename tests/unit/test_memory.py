from src.memory.store import MemoryStore


def test_conversation_and_preference_persistence(tmp_path):
    memory = MemoryStore(tmp_path / "memory.db")
    memory.add_message("u1", "t1", "user", "Summarize revenue")
    memory.add_message("u1", "t1", "assistant", "Revenue evidence [1]")
    assert len(memory.history("u1", "t1")) == 2
    memory.save_preference("u1", "style", "concise")
    assert memory.preferences("u1")["style"] == "concise"
    assert memory.relevant_memories("u1", "concise report")
    memory.clear_user("u1")
    assert memory.preferences("u1") == {}
    assert memory.history("u1", "t1") == []


def test_clear_checkpoint_thread_removes_only_target(tmp_path):
    import sqlite3
    from src.memory.store import clear_checkpoint_thread
    path = tmp_path / "checkpoints.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE checkpoints (thread_id TEXT, checkpoint_id TEXT)")
        conn.execute("CREATE TABLE writes (thread_id TEXT, task_id TEXT)")
        conn.executemany("INSERT INTO checkpoints VALUES (?, ?)", [("t1", "a"), ("t2", "b")])
        conn.executemany("INSERT INTO writes VALUES (?, ?)", [("t1", "x"), ("t2", "y")])
    assert clear_checkpoint_thread("t1", path) == 2
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id='t2'").fetchone()[0] == 1
