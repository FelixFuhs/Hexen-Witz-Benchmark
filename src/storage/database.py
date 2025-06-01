import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone 

from src.models import BenchmarkRecord, GenerationResult, Summary, JudgeScore 

logger = logging.getLogger(__name__)

RECORDS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS records (
  id TEXT PRIMARY KEY,
  run_id TEXT,
  model TEXT,
  run INTEGER,
  gewuenscht TEXT,
  bekommen TEXT,
  phonetische_aehnlichkeit INTEGER,
  anzueglichkeit INTEGER,
  logik INTEGER,
  kreativitaet INTEGER,
  gesamt INTEGER,
  prompt_tokens INTEGER,
  completion_tokens INTEGER,
  cost_usd REAL,
  ts TIMESTAMP
);"""

RECORDS_INDEX_DDL = """CREATE INDEX IF NOT EXISTS idx_model_run_id ON records(model, run_id);"""

def create_connection(db_file_str: str) -> Optional[sqlite3.Connection]:
    """Creates a connection to the SQLite database specified by db_file."""
    db_file = Path(db_file_str)
    try:
        db_file.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_file)) 
        logger.info(f"SQLite connection established to {db_file}")
        return conn
    except sqlite3.Error as e:
        logger.error(f"Error connecting to SQLite database {db_file}: {e}", exc_info=True)
        return None
    except OSError as e: 
        logger.error(f"Error creating directory for SQLite database {db_file.parent}: {e}", exc_info=True)
        return None


def execute_ddl(conn: sqlite3.Connection) -> bool:
    """Executes the DDL statements to create tables and indexes."""
    try:
        cursor = conn.cursor()
        cursor.execute(RECORDS_TABLE_DDL)
        cursor.execute(RECORDS_INDEX_DDL)
        conn.commit()
        logger.info("Successfully executed DDL (table and index creation).")
        return True
    except sqlite3.Error as e:
        logger.error(f"Error executing DDL: {e}", exc_info=True)
        return False


def insert_benchmark_record(conn: sqlite3.Connection, record: BenchmarkRecord, run_id: str) -> bool:
    """Inserts a BenchmarkRecord into the database."""
    record_unique_id = "" 

    try:
        cursor = conn.cursor()
        gen = record.generation
        judge = record.judge

        gewuenscht_val = gen.summary.gewuenscht if gen.summary else None
        bekommen_val = gen.summary.bekommen if gen.summary else None

        safe_model_name = gen.model.replace('/', '_')
        record_unique_id = f"{run_id}_{safe_model_name}_{gen.run}"

        timestamp_iso = gen.timestamp.isoformat() if gen.timestamp else datetime.now(timezone.utc).isoformat()

        cursor.execute("""
            INSERT INTO records (
                id, run_id, model, run, gewuenscht, bekommen,
                phonetische_aehnlichkeit, anzueglichkeit, logik, kreativitaet, gesamt,
                prompt_tokens, completion_tokens, cost_usd, ts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                run_id=excluded.run_id, model=excluded.model, run=excluded.run, gewuenscht=excluded.gewuenscht,
                bekommen=excluded.bekommen, phonetische_aehnlichkeit=excluded.phonetische_aehnlichkeit,
                anzueglichkeit=excluded.anzueglichkeit, logik=excluded.logik, kreativitaet=excluded.kreativitaet,
                gesamt=excluded.gesamt, prompt_tokens=excluded.prompt_tokens, completion_tokens=excluded.completion_tokens,
                cost_usd=excluded.cost_usd, ts=excluded.ts;
            """, (
            record_unique_id, run_id, gen.model, gen.run, gewuenscht_val, bekommen_val,
            judge.phonetische_aehnlichkeit, judge.anzueglichkeit, judge.logik, judge.kreativitaet, judge.gesamt,
            gen.prompt_tokens, gen.completion_tokens, gen.cost_usd, timestamp_iso
        ))
        conn.commit()
        logger.debug(f"Inserted/Updated BenchmarkRecord with id {record_unique_id} into SQLite.")
        return True
    except sqlite3.Error as e:
        logger.error(f"Error inserting/updating BenchmarkRecord with id {record_unique_id}: {e}", exc_info=True)
        return False
    except AttributeError as e: 
        logger.error(
            f"AttributeError inserting/updating BenchmarkRecord (likely missing summary parts or timestamp) for id {record_unique_id}: {e}",
            exc_info=True
        )
        return False

def get_records_by_model(conn: sqlite3.Connection, model_name: str) -> List[Dict[str, Any]]:
    """Fetches all records for a given model name. Returns a list of dicts."""
    try:
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM records WHERE model = ?", (model_name,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        logger.error(f"Error fetching records for model {model_name}: {e}", exc_info=True)
        return []
    finally:
        conn.row_factory = None 


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    db_dir = Path("benchmarks_output/test_run_sqlite_main_dir") 
    db_dir.mkdir(parents=True, exist_ok=True)
    DB_FILE = str(db_dir / "benchmark_data.sqlite") 
    TEST_RUN_ID_SQLITE = "test_run_sqlite_main_v1"

    logger.info(f"Using SQLite DB file: {DB_FILE}")

    sample_summary = Summary(gewuenscht="Ein schnelles Auto", bekommen="Ein Schaf das niest (Hatschi!)")
    sample_gen_ts_1 = datetime.now(timezone.utc)
    sample_gen = GenerationResult(
        model="test/model-sqlite-main", run=1, summary=sample_summary, full_response="Ein Schaf macht Hatschi!",
        prompt_tokens=12, completion_tokens=22, cost_usd=0.0012, timestamp=sample_gen_ts_1
    )
    sample_judge = JudgeScore(
        phonetische_aehnlichkeit=33, anzueglichkeit=5, logik=10, kreativitaet=18, gesamt=66,
        begruendung={"phonetisch": "gut", "anzueglich": "kaum", "logik": "naja", "kreativ": "sehr"},
        flags=[]
    )
    sample_record = BenchmarkRecord(generation=sample_gen, judge=sample_judge)

    conn = create_connection(DB_FILE)
    if conn:
        logger.info("SQLite Connection created successfully for __main__ test.")
        try:
            if execute_ddl(conn):
                logger.info("DDL executed successfully for __main__ test.")
                if insert_benchmark_record(conn, sample_record, TEST_RUN_ID_SQLITE):
                    safe_model_name = sample_gen.model.replace('/', '_')
                    logger.info(f"Record {TEST_RUN_ID_SQLITE}_{safe_model_name}_{sample_gen.run} inserted successfully.")

                sample_gen_no_summary_ts = datetime.now(timezone.utc)
                sample_gen_no_summary = GenerationResult(
                    model="test/model-sqlite-main", run=2, summary=None, full_response="Kein Witz, keine Pointe.",
                    prompt_tokens=6, completion_tokens=6, cost_usd=0.0006, timestamp=sample_gen_no_summary_ts
                )
                sample_judge_for_no_summary = JudgeScore(
                    phonetische_aehnlichkeit=0, anzueglichkeit=0, logik=0, kreativitaet=0, gesamt=0,
                    begruendung={"system": "Summary missing, auto-scored to 0"}, flags=["summary_missing"]
                )
                sample_record_no_summary = BenchmarkRecord(generation=sample_gen_no_summary, judge=sample_judge_for_no_summary)

                if insert_benchmark_record(conn, sample_record_no_summary, TEST_RUN_ID_SQLITE):
                    safe_model_name_no_summary = sample_gen_no_summary.model.replace('/', '_')
                    logger.info(f"Record (no summary) {TEST_RUN_ID_SQLITE}_{safe_model_name_no_summary}_{sample_gen_no_summary.run} inserted successfully.")

                retrieved_records = get_records_by_model(conn, "test/model-sqlite-main")
                logger.info(f"Retrieved {len(retrieved_records)} records for model 'test/model-sqlite-main':")
                for r_idx, r_dict in enumerate(retrieved_records):
                    print(f"  Record {r_idx + 1}: {r_dict}")

                sample_gen_updated_ts = datetime.now(timezone.utc)
                sample_gen_updated = GenerationResult(
                    model="test/model-sqlite-main", run=1, summary=sample_summary, full_response="Ein Schaf macht Hatschi! (aktualisiert)",
                    prompt_tokens=13, completion_tokens=23, cost_usd=0.0013, timestamp=sample_gen_updated_ts
                )
                sample_judge_updated = JudgeScore(
                    phonetische_aehnlichkeit=34, anzueglichkeit=6, logik=11, kreativitaet=19, gesamt=70,
                    begruendung={"phonetisch": "besser", "anzueglich": "immer noch kaum", "logik": "etwas besser", "kreativ": "top"},
                    flags=["updated_record"]
                )
                sample_record_updated = BenchmarkRecord(generation=sample_gen_updated, judge=sample_judge_updated)
                if insert_benchmark_record(conn, sample_record_updated, TEST_RUN_ID_SQLITE):
                     logger.info(f"Record {TEST_RUN_ID_SQLITE}_{sample_gen_updated.model.replace('/', '_')}_{sample_gen_updated.run} (updated) inserted successfully.")

                retrieved_records_after_update = get_records_by_model(conn, "test/model-sqlite-main")
                logger.info(f"Retrieved {len(retrieved_records_after_update)} records for model 'test/model-sqlite-main' after update:")
                for r_idx, r_dict_upd in enumerate(retrieved_records_after_update):
                    print(f"  Record {r_idx + 1} (after update): {r_dict_upd}")
            else:
                logger.error("Failed to execute DDL for __main__ test.")
        except Exception as e:
            logger.error(f"An error occurred during __main__ test operations: {e}", exc_info=True)
        finally:
            logger.info("Closing SQLite connection for __main__ test.")
            conn.close()
    else:
        logger.error(f"Failed to create SQLite connection to {DB_FILE} for __main__ test.")