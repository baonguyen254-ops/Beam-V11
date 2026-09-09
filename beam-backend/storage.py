"""Durable state and signed energy integrals. No backfilled or invented history."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


def encode(value):
    return json.dumps(
        value, default=lambda x: x.isoformat(), allow_nan=False, ensure_ascii=False
    )


class Store:
    def __init__(self, path=None):
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(
            str(path) if path else ":memory:", check_same_thread=False
        )
        self.db.row_factory = sqlite3.Row
        if self.db.execute("PRAGMA user_version").fetchone()[0] > 2:
            raise ValueError("Database was created by a newer BEAM version")
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;
        PRAGMA busy_timeout=5000;
        CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS records(kind TEXT, id TEXT, value TEXT NOT NULL, PRIMARY KEY(kind,id));
        CREATE TABLE IF NOT EXISTS commands(actor TEXT,id TEXT,fingerprint TEXT,result TEXT,PRIMARY KEY(actor,id));
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,at TEXT,actor TEXT,action TEXT,ok INTEGER,detail TEXT);
        CREATE TABLE IF NOT EXISTS energy(tier INTEGER,scope TEXT,bucket INTEGER,actual REAL,baseline REAL,cost REAL,carbon REAL,seconds REAL,measured REAL,PRIMARY KEY(tier,scope,bucket));
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,username TEXT UNIQUE,password TEXT,role TEXT,active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),expires REAL);
        PRAGMA optimize;
        """)
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version > 2:
            raise ValueError("Database was created by a newer BEAM version")
        if version < 2:
            # Additive migration. Legacy mixed samples cannot be un-mixed honestly.
            self.db.executescript("""
            BEGIN IMMEDIATE;
            CREATE TABLE IF NOT EXISTS energy_by_source(
                tier INTEGER,scope TEXT,source TEXT,bucket INTEGER,
                actual REAL,baseline REAL,cost REAL,carbon REAL,seconds REAL,measured REAL,
                PRIMARY KEY(tier,scope,source,bucket));
            INSERT OR IGNORE INTO energy_by_source
                SELECT tier,scope,CASE WHEN measured=0 THEN 'SIMULATION'
                    WHEN ABS(measured-seconds)<0.000001 THEN 'CONNECTED'
                    ELSE 'LEGACY_MIXED' END,bucket,actual,baseline,cost,carbon,seconds,measured FROM energy;
            PRAGMA user_version=2;
            COMMIT;
            """)
        self.db.commit()
        self.last_prune = 0

    def get(self, key, default=None):
        row = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, key, value):
        self.db.execute(
            "INSERT INTO kv VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, encode(value)),
        )

    def records(self, kind):
        return {
            r["id"]: json.loads(r["value"])
            for r in self.db.execute(
                "SELECT id,value FROM records WHERE kind=?", (kind,)
            )
        }

    def save_records(self, kind, records):
        self.db.executemany(
            "INSERT INTO records VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET value=excluded.value WHERE value<>excluded.value",
            [(kind, k, encode(v)) for k, v in records.items()],
        )

    def audit(self, actor, action, ok, detail):
        self.db.execute(
            "INSERT INTO audit(at,actor,action,ok,detail) VALUES(?,?,?,?,?)",
            (
                datetime.now(timezone.utc).isoformat(),
                actor,
                action,
                int(ok),
                str(detail)[:1500],
            ),
        )

    def record_energy(self, now, dt, samples, tariff, emission):
        end = now.timestamp()
        rows = []
        for tier in (1, 60, 3600):
            cursor = end - dt
            while cursor < end - 1e-8:
                bucket = int(cursor // tier) * tier
                span = min(end, bucket + tier) - cursor
                for scope, actual, baseline, measured in samples:
                    hours = span / 3600
                    delta = (baseline - actual) * hours
                    rows.append(
                        (
                            tier,
                            scope,
                            bucket,
                            actual * hours,
                            baseline * hours,
                            delta * tariff,
                            delta * emission,
                            span,
                            span if measured else 0,
                        )
                    )
                cursor += span
        self.db.executemany(
            """INSERT INTO energy VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(tier,scope,bucket) DO UPDATE SET actual=actual+excluded.actual,baseline=baseline+excluded.baseline,cost=cost+excluded.cost,carbon=carbon+excluded.carbon,seconds=seconds+excluded.seconds,measured=measured+excluded.measured""",
            rows,
        )
        self.db.executemany(
            """INSERT INTO energy_by_source VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(tier,scope,source,bucket) DO UPDATE SET
            actual=actual+excluded.actual,baseline=baseline+excluded.baseline,
            cost=cost+excluded.cost,carbon=carbon+excluded.carbon,
            seconds=seconds+excluded.seconds,measured=measured+excluded.measured""",
            [(r[0], r[1], "CONNECTED" if r[8] else "SIMULATION", *r[2:]) for r in rows],
        )
        if end - self.last_prune >= 60:
            self.db.execute(
                "DELETE FROM energy WHERE tier=1 AND bucket<?", (int(end) - 3600,)
            )
            self.db.execute(
                "DELETE FROM energy WHERE tier=60 AND bucket<?", (int(end) - 3 * 86400,)
            )
            self.db.execute("DELETE FROM sessions WHERE expires<?", (end,))
            self.db.execute(
                "DELETE FROM energy_by_source WHERE tier=1 AND bucket<?",
                (int(end) - 3600,),
            )
            self.db.execute(
                "DELETE FROM energy_by_source WHERE tier=60 AND bucket<?",
                (int(end) - 3 * 86400,),
            )
            self.last_prune = end

    def history(
        self,
        scope="facility",
        resolution="hour",
        start=None,
        end=None,
        tz="Asia/Ho_Chi_Minh",
        source="ALL",
    ):
        formats = {
            "second": "%Y-%m-%dT%H:%M:%S%z",
            "minute": "%Y-%m-%dT%H:%M%z",
            "hour": "%Y-%m-%dT%H:00%z",
            "day": "%Y-%m-%d",
            "month": "%Y-%m",
            "year": "%Y",
        }
        if resolution not in formats:
            raise ValueError("Invalid energy resolution")
        if source not in {"ALL", "SIMULATION", "CONNECTED", "LEGACY_MIXED"}:
            raise ValueError("Unknown energy source")
        end = float(end or datetime.now(timezone.utc).timestamp())
        span = {
            "second": 3600,
            "minute": 3 * 86400,
            "hour": 7 * 86400,
            "day": 90 * 86400,
            "month": 3 * 366 * 86400,
            "year": 10 * 366 * 86400,
        }[resolution]
        start = float(start if start is not None else end - span)
        if not 0 < end - start <= 11 * 366 * 86400:
            raise ValueError("Invalid report interval; maximum 11 years")
        zone = ZoneInfo(tz)
        tier = {"second": 1, "minute": 60}.get(resolution, 3600)
        groups = {}
        query = "SELECT * FROM energy WHERE tier=? AND scope=? AND bucket>=? AND bucket<? ORDER BY bucket"
        args = (tier, scope, int(start // tier) * tier, end)
        if source != "ALL":
            query = "SELECT * FROM energy_by_source WHERE tier=? AND scope=? AND bucket>=? AND bucket<? AND source=? ORDER BY bucket"
            args = (*args, source)
        for row in self.db.execute(query, args):
            period = (
                datetime.fromtimestamp(row["bucket"], timezone.utc)
                .astimezone(zone)
                .strftime(formats[resolution])
            )
            p = groups.setdefault(
                period,
                {
                    "period": period,
                    "actual_kwh": 0.0,
                    "baseline_kwh": 0.0,
                    "savings_vnd": 0.0,
                    "carbon_kg": 0.0,
                    "observed_seconds": 0.0,
                    "measured_seconds": 0.0,
                },
            )
            for dest, src in (
                ("actual_kwh", "actual"),
                ("baseline_kwh", "baseline"),
                ("savings_vnd", "cost"),
                ("carbon_kg", "carbon"),
                ("observed_seconds", "seconds"),
                ("measured_seconds", "measured"),
            ):
                p[dest] += row[src]
        points = list(groups.values())
        for p in points:
            p["saved_kwh"] = p["baseline_kwh"] - p["actual_kwh"]
            p["average_kw"] = p["actual_kwh"] * 3600 / max(p["observed_seconds"], 1e-9)
            p["baseline_kw"] = (
                p["baseline_kwh"] * 3600 / max(p["observed_seconds"], 1e-9)
            )
        totals = {
            k: sum(p[k] for p in points)
            for k in (
                "actual_kwh",
                "baseline_kwh",
                "saved_kwh",
                "savings_vnd",
                "carbon_kg",
                "observed_seconds",
                "measured_seconds",
            )
        }
        return {
            "scope": scope,
            "source": source,
            "query_start": start,
            "query_end": end,
            "resolution": resolution,
            "timezone": tz,
            "points": points[-5000:],
            "totals": totals,
            "coverage_percent": min(
                100, 100 * totals["observed_seconds"] / (end - start)
            ),
            "truncated": len(points) > 5000,
            "bucket_alignment_seconds": tier,
            "retention": {"second": "1 hour", "minute": "3 days", "hour": "retained"},
            "method": "Signed integral; missing intervals remain missing. Complete intersecting buckets are included.",
        }
