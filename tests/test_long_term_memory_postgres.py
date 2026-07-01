from context.long_term_memory import PostgresLongTermMemory


class RecordingCursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))


class RecordingConnection:
    def __init__(self):
        self.cursor_obj = RecordingCursor()

    def cursor(self):
        return self.cursor_obj


def _memory_with_fake_connection():
    memory = object.__new__(PostgresLongTermMemory)
    memory.user_id = "test-user"
    memory.conn = RecordingConnection()
    return memory


def test_postgres_trip_stats_skip_destination_frequency_when_destination_missing():
    memory = _memory_with_fake_connection()

    memory.save_trip_history({"origin": "北京", "destination": None})

    _, stats_params = memory.conn.cursor_obj.calls[1]
    stats_sql = memory.conn.cursor_obj.calls[1][0]
    assert "jsonb_set" not in stats_sql
    assert stats_params == ("test-user",)


def test_postgres_trip_stats_update_destination_frequency_when_destination_present():
    memory = _memory_with_fake_connection()

    memory.save_trip_history({"origin": "北京", "destination": "南京"})

    stats_sql, stats_params = memory.conn.cursor_obj.calls[1]
    assert "jsonb_set" in stats_sql
    assert stats_params == ("南京", "南京", "test-user")
