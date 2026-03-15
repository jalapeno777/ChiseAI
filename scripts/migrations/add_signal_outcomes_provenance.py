#!/usr/bin/env python3
"""Migration: Add provenance columns to signal_outcomes table.

PAPER-FORENSIC-001: Add missing provenance fields for audit trail.

This migration adds:
- execution_venue (VARCHAR): Where trade executed (e.g., "bybit_demo", "local_sim")
- execution_mode (VARCHAR): Mode of execution (e.g., "demo", "testnet", "production")
- execution_source (VARCHAR): Source component (e.g., "bybit_demo_connector", "paper_trading")
- venue_metadata (JSONB): Additional venue-specific metadata

Usage:
    python scripts/migrations/add_signal_outcomes_provenance.py [--rollback]
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import UTC, datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# SQL statements
MIGRATION_SQL = """
-- Add provenance columns to signal_outcomes table
-- PAPER-FORENSIC-001

-- Add execution_venue column
ALTER TABLE signal_outcomes 
ADD COLUMN IF NOT EXISTS execution_venue VARCHAR(100);

-- Add execution_mode column
ALTER TABLE signal_outcomes 
ADD COLUMN IF NOT EXISTS execution_mode VARCHAR(50);

-- Add execution_source column
ALTER TABLE signal_outcomes 
ADD COLUMN IF NOT EXISTS execution_source VARCHAR(100);

-- Add venue_metadata column
ALTER TABLE signal_outcomes 
ADD COLUMN IF NOT EXISTS venue_metadata JSONB;

-- Add comment for documentation
COMMENT ON COLUMN signal_outcomes.execution_venue IS 'Where trade executed (e.g., bybit_demo, local_sim)';
COMMENT ON COLUMN signal_outcomes.execution_mode IS 'Mode of execution (e.g., demo, testnet, production)';
COMMENT ON COLUMN signal_outcomes.execution_source IS 'Source component (e.g., bybit_demo_connector, paper_trading)';
COMMENT ON COLUMN signal_outcomes.venue_metadata IS 'Additional venue-specific metadata';
"""

ROLLBACK_SQL = """
-- Rollback: Remove provenance columns from signal_outcomes table

ALTER TABLE signal_outcomes 
DROP COLUMN IF EXISTS execution_venue;

ALTER TABLE signal_outcomes 
DROP COLUMN IF EXISTS execution_mode;

ALTER TABLE signal_outcomes 
DROP COLUMN IF EXISTS execution_source;

ALTER TABLE signal_outcomes 
DROP COLUMN IF EXISTS venue_metadata;
"""

VERIFICATION_SQL = """
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'signal_outcomes'
AND column_name IN ('execution_venue', 'execution_mode', 'execution_source', 'venue_metadata')
ORDER BY ordinal_position;
"""


async def get_db_pool():
    """Get PostgreSQL connection pool."""
    try:
        import asyncpg

        db_host = os.getenv("DB_HOST", "host.docker.internal")
        db_port = int(os.getenv("DB_PORT", "5434"))
        db_name = os.getenv("DB_NAME", "chiseai")
        db_user = os.getenv("DB_USER", "chiseai")
        db_pass = os.getenv("DB_PASSWORD", "chiseai")

        pool = await asyncpg.create_pool(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user,
            password=db_pass,
            min_size=1,
            max_size=2,
        )
        logger.info(f"Connected to PostgreSQL at {db_host}:{db_port}")
        return pool
    except ImportError:
        logger.error("asyncpg not installed. Install with: pip install asyncpg")
        raise
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        raise


async def run_migration(pool, rollback: bool = False) -> dict:
    """Run the migration or rollback.

    Args:
        pool: PostgreSQL connection pool
        rollback: If True, run rollback instead of migration

    Returns:
        Dictionary with migration results
    """
    result = {
        "success": False,
        "action": "rollback" if rollback else "migration",
        "timestamp": datetime.now(UTC).isoformat(),
        "changes": [],
        "errors": [],
    }

    async with pool.acquire() as conn:
        try:
            # Start transaction
            async with conn.transaction():
                sql = ROLLBACK_SQL if rollback else MIGRATION_SQL

                logger.info(f"Running {result['action']}...")
                await conn.execute(sql)

                # Verify changes
                rows = await conn.fetch(VERIFICATION_SQL)

                if rollback:
                    # After rollback, columns should not exist
                    if len(rows) == 0:
                        result["success"] = True
                        result["changes"].append(
                            "All provenance columns removed successfully"
                        )
                    else:
                        remaining = [r["column_name"] for r in rows]
                        result["errors"].append(
                            f"Columns still exist after rollback: {remaining}"
                        )
                else:
                    # After migration, columns should exist
                    expected_columns = {
                        "execution_venue": "character varying",
                        "execution_mode": "character varying",
                        "execution_source": "character varying",
                        "venue_metadata": "jsonb",
                    }

                    found_columns = {r["column_name"]: r["data_type"] for r in rows}

                    for col, expected_type in expected_columns.items():
                        if col in found_columns:
                            result["changes"].append(
                                f"Added column: {col} ({found_columns[col]})"
                            )
                        else:
                            result["errors"].append(f"Missing column: {col}")

                    if len(result["errors"]) == 0:
                        result["success"] = True

                if result["success"]:
                    logger.info(
                        f"✅ {result['action'].capitalize()} completed successfully"
                    )
                    for change in result["changes"]:
                        logger.info(f"  - {change}")
                else:
                    logger.error(f"❌ {result['action'].capitalize()} failed")
                    for error in result["errors"]:
                        logger.error(f"  - {error}")

                    # Raise exception to trigger rollback
                    raise Exception("Migration verification failed")

        except Exception as e:
            logger.error(f"Error during {result['action']}: {e}")
            result["errors"].append(str(e))
            raise

    return result


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Add provenance columns to signal_outcomes table"
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Rollback the migration (remove columns)",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify current schema, don't run migration",
    )
    args = parser.parse_args()

    pool = None
    try:
        pool = await get_db_pool()

        if args.verify_only:
            logger.info("Running verification only...")
            async with pool.acquire() as conn:
                rows = await conn.fetch(VERIFICATION_SQL)
                if rows:
                    logger.info("Found provenance columns:")
                    for row in rows:
                        logger.info(
                            f"  - {row['column_name']}: {row['data_type']} (nullable: {row['is_nullable']})"
                        )
                else:
                    logger.info("No provenance columns found")
            return 0

        # Run migration or rollback
        result = await run_migration(pool, rollback=args.rollback)

        if result["success"]:
            return 0
        else:
            return 1

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return 1
    finally:
        if pool:
            await pool.close()
            logger.info("Database connection closed")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
