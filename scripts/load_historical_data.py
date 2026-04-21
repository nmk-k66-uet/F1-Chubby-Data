#!/usr/bin/env python3
"""
Historical Data Loader — One-time ETL from FastF1 → Cloud SQL PostgreSQL.

Populates:
  race_calendar, session_results, driver_standings, constructor_standings

Usage:
  python scripts/load_historical_data.py --years 2024 2025 2026
  python scripts/load_historical_data.py --years 2024 2025 2026 --host <CLOUD_SQL_IP>

Requires: psycopg2-binary, fastf1, pandas
"""

import argparse
import os
import sys

import fastf1
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# FastF1 cache
CACHE_DIR = "f1_cache"
os.makedirs(CACHE_DIR, exist_ok=True)
fastf1.Cache.enable_cache(CACHE_DIR)
fastf1.set_log_level("WARNING")


def _connect(args):
    return psycopg2.connect(
        host=args.host,
        port=args.port,
        dbname=args.db,
        user=args.user,
        password=args.password,
    )


def _td_to_ms(td):
    """Convert pandas Timedelta to milliseconds, return None if NaT."""
    if pd.isna(td):
        return None
    return td.total_seconds() * 1000


def load_calendar(conn, year):
    print(f"  [calendar] {year}...")
    schedule = fastf1.get_event_schedule(year)
    schedule = schedule[schedule["RoundNumber"] > 0]

    rows = []
    for _, ev in schedule.iterrows():
        event_date = ev.get("EventDate")
        if pd.notna(event_date):
            event_date = pd.Timestamp(event_date)
            if event_date.tzinfo is not None:
                event_date = event_date.tz_localize(None)
            event_date = event_date.date()
        else:
            event_date = None

        rows.append((
            int(year),
            int(ev["RoundNumber"]),
            str(ev.get("EventName", "")),
            str(ev.get("Country", "")),
            event_date,
            str(ev.get("Location", "")),
            str(ev.get("EventFormat", "conventional")),
        ))

    with conn.cursor() as cur:
        execute_values(
            cur,
            """INSERT INTO race_calendar (year, round, event_name, country, event_date, circuit, event_format)
               VALUES %s
               ON CONFLICT (year, round) DO UPDATE SET
                 event_name = EXCLUDED.event_name,
                 country = EXCLUDED.country,
                 event_date = EXCLUDED.event_date,
                 circuit = EXCLUDED.circuit,
                 event_format = EXCLUDED.event_format""",
            rows,
        )
    conn.commit()
    print(f"    → {len(rows)} rounds")


def load_session_results(conn, year, round_num, session_type):
    """Load results for one session into session_results."""
    try:
        session = fastf1.get_session(year, round_num, session_type)
        session.load(telemetry=False, weather=False, messages=False)
    except Exception as e:
        print(f"    [skip] {year} R{round_num} {session_type}: {e}")
        return 0

    results = session.results
    if results is None or results.empty:
        return 0

    # For Race/Sprint, get each driver's best lap from session.laps
    # (session.results doesn't include BestLapTime for race sessions)
    driver_best_lap = {}
    if session_type in ("R", "S"):
        try:
            laps = session.laps
            if laps is not None and not laps.empty:
                for drv, grp in laps.groupby("Driver"):
                    valid = grp.dropna(subset=["LapTime"])
                    if not valid.empty:
                        driver_best_lap[drv] = valid["LapTime"].min()
        except Exception:
            pass

    rows = []
    for _, r in results.iterrows():
        pos = pd.to_numeric(r.get("Position"), errors="coerce")
        pos = int(pos) if pd.notna(pos) else None
        grid = pd.to_numeric(r.get("GridPosition"), errors="coerce")
        grid = int(grid) if pd.notna(grid) else None
        points = pd.to_numeric(r.get("Points"), errors="coerce")
        points = float(points) if pd.notna(points) else 0.0

        time_ms = None
        time_val = r.get("Time")
        if pd.notna(time_val) and hasattr(time_val, "total_seconds"):
            time_ms = time_val.total_seconds() * 1000

        # BestLapTime: from results (Q sessions) or from laps (R/S sessions)
        abbr = str(r.get("Abbreviation", ""))
        if "BestLapTime" in r.index and pd.notna(r.get("BestLapTime")):
            best_lap = _td_to_ms(r["BestLapTime"])
        elif abbr in driver_best_lap:
            best_lap = _td_to_ms(driver_best_lap[abbr])
        else:
            best_lap = None

        rows.append((
            int(year),
            int(round_num),
            session_type,
            abbr,
            str(r.get("FullName", "")),
            str(r.get("TeamName", "")),
            pos,
            grid,
            time_ms,
            str(r.get("Status", "")),
            points,
            _td_to_ms(r.get("Q1")),
            _td_to_ms(r.get("Q2")),
            _td_to_ms(r.get("Q3")),
            best_lap,
        ))

    with conn.cursor() as cur:
        execute_values(
            cur,
            """INSERT INTO session_results
                 (year, round, session_type, driver_abbr, full_name, team_name,
                  position, grid_position, time_ms, status, points,
                  q1_ms, q2_ms, q3_ms, best_lap_ms)
               VALUES %s
               ON CONFLICT (year, round, session_type, driver_abbr) DO UPDATE SET
                 full_name = EXCLUDED.full_name,
                 team_name = EXCLUDED.team_name,
                 position = EXCLUDED.position,
                 grid_position = EXCLUDED.grid_position,
                 time_ms = EXCLUDED.time_ms,
                 status = EXCLUDED.status,
                 points = EXCLUDED.points,
                 q1_ms = EXCLUDED.q1_ms,
                 q2_ms = EXCLUDED.q2_ms,
                 q3_ms = EXCLUDED.q3_ms,
                 best_lap_ms = EXCLUDED.best_lap_ms""",
            rows,
        )
    conn.commit()
    return len(rows)


def load_all_sessions(conn, year):
    schedule = fastf1.get_event_schedule(year)
    schedule = schedule[schedule["RoundNumber"] > 0]

    total = 0
    for _, ev in schedule.iterrows():
        rnd = int(ev["RoundNumber"])
        fmt = str(ev.get("EventFormat", "conventional")).lower()

        sessions_to_load = ["Q", "R"]
        if fmt in ("sprint", "sprint_qualifying", "sprint_shootout"):
            sessions_to_load.append("S")

        for st_code in sessions_to_load:
            n = load_session_results(conn, year, rnd, st_code)
            if n > 0:
                print(f"    R{rnd} {st_code}: {n} drivers")
            total += n

    print(f"  [results] {year}: {total} total rows")


def load_standings(conn, year):
    """Compute cumulative standings after each round from session_results."""
    with conn.cursor() as cur:
        # Get all rounds for this year that have race results
        cur.execute(
            "SELECT DISTINCT round FROM session_results WHERE year=%s AND session_type='R' ORDER BY round",
            (year,),
        )
        rounds = [r[0] for r in cur.fetchall()]

    if not rounds:
        print(f"  [standings] {year}: no race results found, skipping")
        return

    for rnd in rounds:
        # Driver standings: cumulative points + wins up to this round
        # Use MAX(round) subquery to get the latest team for each driver
        with conn.cursor() as cur:
            cur.execute("""
                WITH driver_pts AS (
                    SELECT driver_abbr,
                           MIN(full_name) as full_name,
                           SUM(points) as total_points,
                           COUNT(*) FILTER (WHERE position = 1) as wins
                    FROM session_results
                    WHERE year=%s AND round<=%s AND session_type IN ('R', 'S')
                    GROUP BY driver_abbr
                ),
                latest_team AS (
                    SELECT DISTINCT ON (driver_abbr) driver_abbr, team_name
                    FROM session_results
                    WHERE year=%s AND round<=%s AND session_type='R'
                    ORDER BY driver_abbr, round DESC
                )
                SELECT dp.driver_abbr, dp.full_name, COALESCE(lt.team_name, '') as team_name,
                       dp.total_points, dp.wins
                FROM driver_pts dp
                LEFT JOIN latest_team lt USING (driver_abbr)
                ORDER BY dp.total_points DESC, dp.wins DESC
            """, (year, rnd, year, rnd))
            driver_rows = cur.fetchall()

        d_vals = []
        for pos, (abbr, fname, team, pts, wins) in enumerate(driver_rows, 1):
            driver_id = fname.lower().replace(" ", "_")
            d_vals.append((year, rnd, driver_id, abbr, fname, team, pos, float(pts), int(wins)))

        if d_vals:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO driver_standings
                         (year, round, driver_id, driver_abbr, full_name, team_name, position, points, wins)
                       VALUES %s
                       ON CONFLICT (year, round, driver_id) DO UPDATE SET
                         driver_abbr = EXCLUDED.driver_abbr,
                         full_name = EXCLUDED.full_name,
                         team_name = EXCLUDED.team_name,
                         position = EXCLUDED.position,
                         points = EXCLUDED.points,
                         wins = EXCLUDED.wins""",
                    d_vals,
                )

        # Constructor standings: cumulative points + wins up to this round
        with conn.cursor() as cur:
            cur.execute("""
                SELECT team_name,
                       SUM(points) as total_points,
                       COUNT(*) FILTER (WHERE position = 1) as wins
                FROM session_results
                WHERE year=%s AND round<=%s AND session_type IN ('R', 'S')
                GROUP BY team_name
                ORDER BY total_points DESC, wins DESC
            """, (year, rnd))
            cons_rows = cur.fetchall()

        c_vals = []
        for pos, (team, pts, wins) in enumerate(cons_rows, 1):
            cid = team.lower().replace(" ", "_")
            c_vals.append((year, rnd, cid, team, pos, float(pts), int(wins)))

        if c_vals:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO constructor_standings
                         (year, round, constructor_id, constructor_name, position, points, wins)
                       VALUES %s
                       ON CONFLICT (year, round, constructor_id) DO UPDATE SET
                         constructor_name = EXCLUDED.constructor_name,
                         position = EXCLUDED.position,
                         points = EXCLUDED.points,
                         wins = EXCLUDED.wins""",
                    c_vals,
                )

        conn.commit()

    print(f"  [standings] {year}: computed for {len(rounds)} rounds")


def main():
    parser = argparse.ArgumentParser(description="Load F1 historical data into PostgreSQL")
    parser.add_argument("--years", nargs="+", type=int, default=[2024, 2025, 2026])
    parser.add_argument("--host", default=os.environ.get("POSTGRES_HOST", "localhost"))
    parser.add_argument("--port", default=os.environ.get("POSTGRES_PORT", "5432"))
    parser.add_argument("--db", default=os.environ.get("POSTGRES_DB", "f1chubby"))
    parser.add_argument("--user", default=os.environ.get("POSTGRES_USER", "postgres"))
    parser.add_argument("--password", default=os.environ.get("POSTGRES_PASSWORD", ""))
    parser.add_argument("--init-schema", action="store_true", help="Run sql/init.sql before loading")
    parser.add_argument("--skip-if-seeded", action="store_true", help="Exit early if session_results already has data")
    parser.add_argument("--offline", action="store_true", help="Use only FastF1 cache, block all API calls")
    args = parser.parse_args()

    if args.offline:
        # Block HTTP requests at the adapter level.
        # requests_cache serves cached responses at the Session level (before
        # reaching the adapter), so cache hits still work. Cache misses hit
        # the adapter where we raise, and the existing try/except skips them.
        import requests
        def _blocked_send(self, request, **kwargs):
            raise requests.exceptions.ConnectionError(
                f"Blocked by --offline: {request.method} {request.url}"
            )
        requests.adapters.HTTPAdapter.send = _blocked_send
        print("Offline mode: using FastF1 cache only, no API calls")

    if not args.password:
        print("ERROR: --password or POSTGRES_PASSWORD env required")
        sys.exit(1)

    conn = _connect(args)
    print(f"Connected to {args.host}:{args.port}/{args.db}")

    if args.skip_if_seeded:
        with conn.cursor() as cur:
            cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='session_results')")
            if cur.fetchone()[0]:
                cur.execute("SELECT count(*) FROM session_results")
                count = cur.fetchone()[0]
                if count > 0:
                    print(f"Database already seeded ({count} rows in session_results). Skipping.")
                    conn.close()
                    return

    if args.init_schema:
        schema_path = os.path.join(os.path.dirname(__file__), "..", "sql", "init.sql")
        if os.path.exists(schema_path):
            with open(schema_path) as f:
                conn.cursor().execute(f.read())
            conn.commit()
            print("Schema initialized from sql/init.sql")

    for year in args.years:
        print(f"\n=== Loading {year} ===")
        load_calendar(conn, year)
        load_all_sessions(conn, year)
        load_standings(conn, year)

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
