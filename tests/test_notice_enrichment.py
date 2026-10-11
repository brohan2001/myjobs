import uuid

from src.processing import notice


class FakeConn:
    def __init__(self, rows):
        self.rows, self.executed = rows, []

    async def fetch(self, sql, limit):
        return self.rows[:limit]

    async def execute(self, sql, *args):
        self.executed.append(args)


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self):
                return pool.conn

            async def __aexit__(self, *exc):
                return False

        return _Ctx()


async def test_batch_writes_extracted_days_and_hash(monkeypatch):
    monkeypatch.setattr(notice, "extract_notice_period", lambda html: 30 if "30" in html else None)
    a, b = uuid.uuid4(), uuid.uuid4()
    conn = FakeConn([{"id": a, "html": "Notice period: 30 days", "hash": 11}, {"id": b, "html": "Hi", "hash": 22}])

    assert await notice.enrich_notice_batch(FakePool(conn)) == 2
    assert conn.executed == [([a, b], [30, None], [11, 22])]


async def test_empty_batch_writes_nothing():
    conn = FakeConn([])
    assert await notice.enrich_notice_batch(FakePool(conn)) == 0
    assert conn.executed == []
