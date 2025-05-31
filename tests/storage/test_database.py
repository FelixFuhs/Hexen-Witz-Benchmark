import pytest
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from src.storage.database import (
    create_connection,
    execute_ddl,
    insert_benchmark_record,
    get_records_by_model
)
from src.models import BenchmarkRecord, GenerationResult, Summary, JudgeScore

# Tests for storage/database.py will be implemented here.

@pytest.fixture
def temp_db_path(tmp_path: Path) -> str:
    """Provides a path to a temporary SQLite database file."""
    db_file = tmp_path / "test_benchmark.sqlite"
    return str(db_file)

@pytest.fixture
def db_conn(temp_db_path: str) -> sqlite3.Connection:
    """Creates a connection to a temporary SQLite DB and executes DDL."""
    conn = create_connection(temp_db_path)
    assert conn is not None, "Failed to create database connection for test."
    assert execute_ddl(conn), "Failed to execute DDL for test."
    yield conn
    conn.close()

@pytest.fixture
def sample_benchmark_record_for_db() -> BenchmarkRecord:
    gen_result = GenerationResult(
        model="db_test/model_v1",
        run=1,
        summary=Summary(gewuenscht="DB Wunsch", bekommen="DB Bekommen"),
        full_response="DB full response.",
        prompt_tokens=60,
        completion_tokens=160,
        cost_usd=0.00030,
        timestamp=datetime.now(timezone.utc)
    )
    judge_score = JudgeScore(
        phonetische_aehnlichkeit=25,
        anzueglichkeit=5,
        logik=12,
        kreativitaet=18,
        gesamt=60,
        begruendung={"db_test": "Looks good in DB"},
        flags=[]
    )
    return BenchmarkRecord(generation=gen_result, judge=judge_score)

# Example test ideas for storage/database.py:
# - test_create_connection_success_and_failure: Check connection object or None.
# - test_execute_ddl_creates_table_and_index: Check schema using sqlite_master.
# - test_insert_benchmark_record_success: Insert a record and verify using SELECT.
# - test_insert_benchmark_record_with_optional_fields_none (e.g. summary):
#   Verify it handles None for gewuenscht/bekommen.
# - test_insert_benchmark_record_upsert_behavior: Insert same record ID twice, check update.
# - test_get_records_by_model_retrieves_correctly: Insert multiple records, retrieve by model.
# - test_get_records_by_model_empty_result: Query for a non-existent model.
# - test_error_handling_sqlite_error_on_insert: Mock cursor.execute to raise sqlite3.Error.

# Example test structure
def test_db_connection_and_ddl(db_conn: sqlite3.Connection):
    # Check if table 'records' exists
    cursor = db_conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='records';")
    table = cursor.fetchone()
    assert table is not None, "'records' table not created by DDL."

    # Check if index 'idx_model_run_id' exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_model_run_id';")
    index = cursor.fetchone()
    assert index is not None, "'idx_model_run_id' index not created by DDL."

def test_insert_and_get_benchmark_record(db_conn: sqlite3.Connection, sample_benchmark_record_for_db: BenchmarkRecord):
    run_id = "db_test_run_001"
    success = insert_benchmark_record(db_conn, sample_benchmark_record_for_db, run_id)
    assert success, "Failed to insert sample benchmark record."

    retrieved_records = get_records_by_model(db_conn, sample_benchmark_record_for_db.generation.model)
    assert len(retrieved_records) == 1

    record_dict = retrieved_records[0]
    gen = sample_benchmark_record_for_db.generation
    judge = sample_benchmark_record_for_db.judge

    assert record_dict["run_id"] == run_id
    assert record_dict["model"] == gen.model
    assert record_dict["run"] == gen.run
    assert record_dict["gewuenscht"] == gen.summary.gewuenscht
    assert record_dict["bekommen"] == gen.summary.bekommen
    assert record_dict["phonetische_aehnlichkeit"] == judge.phonetische_aehnlichkeit
    assert record_dict["cost_usd"] == gen.cost_usd
    assert datetime.fromisoformat(record_dict["ts"]) == gen.timestamp

def test_insert_record_no_summary(db_conn: sqlite3.Connection):
    run_id = "db_test_no_summary_run"
    gen_no_summary = GenerationResult(
        model="db_test/no_summary_model", run=1, summary=None, full_response="No summary here.",
        prompt_tokens=5, completion_tokens=5, cost_usd=0.0001, timestamp=datetime.now(timezone.utc)
    )
    judge_score = JudgeScore(
        phonetische_aehnlichkeit=0, anzueglichkeit=0, logik=0, kreativitaet=0, gesamt=0,
        begruendung={"system": "No summary"}, flags=["no_summary"]
    )
    record_no_summary = BenchmarkRecord(generation=gen_no_summary, judge=judge_score)

    success = insert_benchmark_record(db_conn, record_no_summary, run_id)
    assert success, "Failed to insert record with no summary."

    retrieved = get_records_by_model(db_conn, "db_test/no_summary_model")
    assert len(retrieved) == 1
    assert retrieved[0]["gewuenscht"] is None
    assert retrieved[0]["bekommen"] is None
