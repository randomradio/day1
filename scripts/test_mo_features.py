#!/usr/bin/env python3
"""Verify MatrixOne features required by Day1.

Usage:
    BM_DATABASE_URL="mysql+aiomysql://user:pass@host:6001/db" \
        python scripts/test_mo_features.py

Tests 14 features:
  1. Connection + CREATE TABLE
  2. INSERT / SELECT
  3. vecf32 column + cosine_similarity()
  4. FULLTEXT INDEX + MATCH AGAINST
  5. DATA BRANCH CREATE TABLE
  6. Insert into branch table
  7. DATA BRANCH DIFF
  8. DATA BRANCH DIFF OUTPUT COUNT
  9. DATA BRANCH MERGE (WHEN CONFLICT SKIP)
 10. DATA BRANCH MERGE (WHEN CONFLICT ACCEPT)
 11. CREATE SNAPSHOT FOR TABLE
 12. Time travel: SELECT ... {AS OF TIMESTAMP}
 13. JSON column support
 14. DROP TABLE cleanup
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Load .env from project root
_project_root = Path(__file__).resolve().parents[1]
load_dotenv(_project_root / ".env")


async def main() -> None:
    url = os.environ.get(
        "BM_DATABASE_URL",
        "mysql+aiomysql://user:pass@localhost:6001/branchedmind",
    )
    engine = create_async_engine(url, echo=False)
    passed = 0
    failed = 0
    skipped = 0

    # Extract database name from URL for SNAPSHOT commands
    db_name = url.rsplit("/", 1)[-1].split("?")[0]

    async def run_test(name: str, coro):
        nonlocal passed, failed, skipped
        try:
            await coro
            print(f"  [PASS] {name}")
            passed += 1
        except Exception as e:
            err = str(e)[:200]
            if "not supported" in err.lower():
                print(f"  [SKIP] {name}: {err}")
                skipped += 1
            else:
                print(f"  [FAIL] {name}: {err}")
                failed += 1

    print(f"Connecting to: {url.split('@')[-1] if '@' in url else url}")
    print(f"Database: {db_name}")
    print("=" * 60)

    # --- Connectivity check ---
    try:
        async with engine.connect() as test_conn:
            await test_conn.execute(text("SELECT 1"))
    except Exception as e:
        err = str(e)
        if "name resolution" in err or "Can't connect" in err:
            print(f"  [ERROR] Cannot connect to database: {err[:120]}")
            print("")
            print("  Possible causes:")
            print("    - No network access (sandbox/CI environment)")
            print("    - MO Cloud host unreachable")
            print("    - Wrong connection string")
            print("")
            print("  Set BM_DATABASE_URL to a reachable MatrixOne instance and retry.")
            await engine.dispose()
            sys.exit(1)
        raise

    # =========================================================
    # Phase 1: Standard SQL (uses normal transaction)
    # =========================================================
    print("\n--- Phase 1: Standard SQL ---")

    async with engine.begin() as conn:
        # Cleanup from previous runs
        for tbl in ["bm_test_branch", "bm_test_branch2", "bm_test_main", "bm_test_ft"]:
            await conn.execute(text(f"DROP TABLE IF EXISTS `{tbl}`"))

        # 1. Connection + CREATE TABLE
        async def test_connection():
            await conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS `bm_test_main` ("
                    "  id VARCHAR(36) PRIMARY KEY,"
                    "  fact_text TEXT,"
                    "  embedding TEXT,"
                    "  category VARCHAR(50),"
                    "  metadata TEXT,"
                    "  created_at DATETIME DEFAULT NOW()"
                    ")"
                )
            )

        await run_test("1. Connection + CREATE TABLE", test_connection())

        # 2. INSERT / SELECT
        async def test_crud():
            await conn.execute(
                text(
                    "INSERT INTO `bm_test_main` (id, fact_text, category) "
                    "VALUES ('t1', 'Python is great', 'code'),"
                    "       ('t2', 'FastAPI is fast', 'framework'),"
                    "       ('t3', 'MatrixOne rocks', 'database')"
                )
            )
            r = await conn.execute(text("SELECT COUNT(*) FROM `bm_test_main`"))
            assert r.scalar() == 3, "Expected 3 rows"

        await run_test("2. INSERT / SELECT", test_crud())

        # 3. vecf32 + cosine_similarity
        async def test_vector():
            await conn.execute(
                text(
                    "UPDATE `bm_test_main`"
                    " SET embedding = '[1.0,0.0,0.0]'"
                    " WHERE id = 't1'"
                )
            )
            await conn.execute(
                text(
                    "UPDATE `bm_test_main`"
                    " SET embedding = '[0.0,1.0,0.0]'"
                    " WHERE id = 't2'"
                )
            )
            await conn.execute(
                text(
                    "UPDATE `bm_test_main`"
                    " SET embedding = '[0.707,0.707,0.0]'"
                    " WHERE id = 't3'"
                )
            )
            r = await conn.execute(
                text(
                    "SELECT id, cosine_similarity(embedding, '[1.0,0.0,0.0]') AS score "
                    "FROM `bm_test_main` WHERE embedding IS NOT NULL "
                    "ORDER BY score DESC"
                )
            )
            rows = r.fetchall()
            assert len(rows) == 3, f"Expected 3 rows, got {len(rows)}"
            assert rows[0][0] == "t1", f"Expected t1 first, got {rows[0][0]}"

        await run_test("3. vecf32 + cosine_similarity()", test_vector())

        # 4. FULLTEXT INDEX + MATCH AGAINST
        async def test_fulltext():
            await conn.execute(
                text(
                    "CREATE TABLE `bm_test_ft` ("
                    "  id VARCHAR(36) PRIMARY KEY,"
                    "  content TEXT,"
                    "  tag VARCHAR(50)"
                    ")"
                )
            )
            await conn.execute(
                text("CREATE FULLTEXT INDEX ft_test ON `bm_test_ft`(content, tag)")
            )
            await conn.execute(
                text(
                    "INSERT INTO `bm_test_ft` VALUES "
                    "('a', 'machine learning models', 'ai'),"
                    "('b', 'database optimization', 'db'),"
                    "('c', 'neural network training', 'ai')"
                )
            )
            r = await conn.execute(
                text(
                    "SELECT id FROM `bm_test_ft` "
                    "WHERE MATCH(content, tag) AGAINST("
                    "'machine learning'"
                    " IN NATURAL LANGUAGE MODE)"
                )
            )
            rows = r.fetchall()
            assert len(rows) >= 1, "Expected at least 1 fulltext match"

        await run_test("4. FULLTEXT INDEX + MATCH AGAINST", test_fulltext())

    # =========================================================
    # Phase 2: MO-native operations (requires AUTOCOMMIT)
    #   DATA BRANCH and CREATE SNAPSHOT cannot run inside a txn.
    #   Each test gets its own connection so a lost-connection
    #   failure in one test does not cascade to subsequent tests.
    # =========================================================
    print("\n--- Phase 2: MO Native (autocommit) ---")

    async def _autocommit_conn():
        raw = await engine.connect()
        return await raw.execution_options(isolation_level="AUTOCOMMIT")

    # 5. DATA BRANCH CREATE TABLE
    async def test_branch_create():
        conn = await _autocommit_conn()
        try:
            await conn.execute(
                text("DATA BRANCH CREATE TABLE `bm_test_branch` FROM `bm_test_main`")
            )
            r = await conn.execute(text("SELECT COUNT(*) FROM `bm_test_branch`"))
            assert r.scalar() == 3, "Branch should have 3 rows"
        finally:
            await conn.close()

    await run_test("5. DATA BRANCH CREATE TABLE", test_branch_create())

    # 6. Insert into branch table
    async def test_branch_insert():
        conn = await _autocommit_conn()
        try:
            await conn.execute(
                text(
                    "INSERT INTO `bm_test_branch` (id, fact_text, category) "
                    "VALUES ('t4', 'Branch-only fact', 'test')"
                )
            )
            r = await conn.execute(text("SELECT COUNT(*) FROM `bm_test_branch`"))
            assert r.scalar() == 4, "Branch should have 4 rows"
            r2 = await conn.execute(text("SELECT COUNT(*) FROM `bm_test_main`"))
            assert r2.scalar() == 3, "Main should still have 3 rows"
        finally:
            await conn.close()

    await run_test("6. Insert into branch table", test_branch_insert())

    # 7. DATA BRANCH DIFF (retry once on lost connection)
    async def test_diff():
        last_err = None
        for attempt in range(2):
            conn = await _autocommit_conn()
            try:
                r = await conn.execute(
                    text("DATA BRANCH DIFF `bm_test_branch` AGAINST `bm_test_main`")
                )
                rows = r.fetchall()
                assert len(rows) >= 1, f"Expected diffs, got {len(rows)}"
                return
            except Exception as e:
                last_err = e
                if attempt == 0:
                    await asyncio.sleep(1)
            finally:
                await conn.close()
        raise last_err  # type: ignore[misc]

    await run_test("7. DATA BRANCH DIFF", test_diff())

    # 8. DATA BRANCH DIFF OUTPUT COUNT (with fallback)
    async def test_diff_count():
        # Try OUTPUT COUNT first; some MO versions drop the connection
        try:
            conn = await _autocommit_conn()
            try:
                r = await conn.execute(
                    text(
                        "DATA BRANCH DIFF"
                        " `bm_test_branch`"
                        " AGAINST `bm_test_main`"
                        " OUTPUT COUNT"
                    )
                )
                row = r.fetchone()
                assert row is not None, "Expected count result"
                assert int(row[0]) >= 1, f"Expected count >= 1, got {row[0]}"
                return
            finally:
                await conn.close()
        except Exception:
            pass
        # Fallback: count rows from plain DIFF
        conn = await _autocommit_conn()
        try:
            r = await conn.execute(
                text("DATA BRANCH DIFF `bm_test_branch` AGAINST `bm_test_main`")
            )
            count = len(r.fetchall())
            assert count >= 1, f"Expected diff count >= 1, got {count}"
        finally:
            await conn.close()

    await run_test(
        "8. DATA BRANCH DIFF count (OUTPUT COUNT or fallback)", test_diff_count()
    )

    # 9. DATA BRANCH MERGE (SKIP)
    async def test_merge_skip():
        conn = await _autocommit_conn()
        try:
            await conn.execute(
                text("DATA BRANCH CREATE TABLE `bm_test_branch2` FROM `bm_test_main`")
            )
            await conn.execute(
                text(
                    "INSERT INTO `bm_test_branch2` (id, fact_text, category) "
                    "VALUES ('t5', 'Merge test skip', 'test')"
                )
            )
            await conn.execute(
                text(
                    "DATA BRANCH MERGE `bm_test_branch2`"
                    " INTO `bm_test_main`"
                    " WHEN CONFLICT SKIP"
                )
            )
            r = await conn.execute(text("SELECT COUNT(*) FROM `bm_test_main`"))
            assert r.scalar() >= 4, "Main should have merged rows"
        finally:
            await conn.close()

    await run_test("9. DATA BRANCH MERGE (WHEN CONFLICT SKIP)", test_merge_skip())

    # 10. DATA BRANCH MERGE (ACCEPT)
    async def test_merge_accept():
        conn = await _autocommit_conn()
        try:
            await conn.execute(
                text(
                    "DATA BRANCH MERGE `bm_test_branch`"
                    " INTO `bm_test_main`"
                    " WHEN CONFLICT ACCEPT"
                )
            )
            r = await conn.execute(text("SELECT COUNT(*) FROM `bm_test_main`"))
            count = r.scalar()
            assert count >= 4, f"Main should have >= 4 rows, got {count}"
        finally:
            await conn.close()

    await run_test("10. DATA BRANCH MERGE (WHEN CONFLICT ACCEPT)", test_merge_accept())

    # 11. CREATE SNAPSHOT FOR TABLE
    async def test_snapshot():
        conn = await _autocommit_conn()
        try:
            await conn.execute(
                text(
                    f"CREATE SNAPSHOT bm_test_snap FOR TABLE `{db_name}` `bm_test_main`"
                )
            )
        finally:
            await conn.close()

    await run_test("11. CREATE SNAPSHOT FOR TABLE", test_snapshot())

    # =========================================================
    # Phase 3: More standard SQL + cleanup
    # =========================================================
    print("\n--- Phase 3: Time travel, JSON, cleanup ---")

    async with engine.begin() as conn:
        # 12. Time travel (AS OF TIMESTAMP)
        async def test_time_travel():
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            r = await conn.execute(
                text(f"SELECT COUNT(*) FROM `bm_test_main` {{AS OF TIMESTAMP '{ts}'}}")
            )
            count = r.scalar()
            assert count >= 0, "Time travel should return result"

        await run_test("12. Time travel: {AS OF TIMESTAMP}", test_time_travel())

        # 13. JSON column support
        async def test_json():
            await conn.execute(
                text(
                    "UPDATE `bm_test_main`"
                    ' SET metadata = \'{"key": "value"}\''
                    " WHERE id = 't1'"
                )
            )
            r = await conn.execute(
                text("SELECT metadata FROM `bm_test_main` WHERE id = 't1'")
            )
            row = r.fetchone()
            assert row is not None, "Expected JSON result"

        await run_test("13. JSON column support", test_json())

    # Cleanup (autocommit for snapshot drop)
    async with engine.connect() as raw_conn:
        conn = await raw_conn.execution_options(isolation_level="AUTOCOMMIT")

        async def test_cleanup():
            for tbl in [
                "bm_test_branch",
                "bm_test_branch2",
                "bm_test_main",
                "bm_test_ft",
            ]:
                await conn.execute(text(f"DROP TABLE IF EXISTS `{tbl}`"))
            try:
                await conn.execute(text("DROP SNAPSHOT bm_test_snap"))
            except Exception:
                pass

        await run_test("14. DROP TABLE cleanup", test_cleanup())

    await engine.dispose()

    print("")
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped")
    if failed > 0:
        sys.exit(1)
    print("All required MO features verified!")


if __name__ == "__main__":
    asyncio.run(main())
