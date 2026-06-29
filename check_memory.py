import sqlite3
import json

conn = sqlite3.connect("data/app.db")
conn.row_factory = sqlite3.Row

def count_table(table):
    try:
        count = conn.execute(f"select count(*) from {table}").fetchone()[0]
        print(f"{table}: {count}")
    except Exception as e:
        print(f"{table}: ERROR {e}")

print("=== table counts ===")
for table in [
    "raw_events",
    "nightly_reviews",
    "daily_memory_graphs",
    "memories",
    "problem_board",
    "memory_operations",
    "problem_operations",
    "skill_memories",
    "skill_operations",
    "global_memory_nodes",
    "global_memory_edges",
]:
    count_table(table)

print("\n=== latest nightly_reviews ===")
rows = conn.execute("""
select id, review_date, parse_status, error_message
from nightly_reviews
order by id desc
limit 3
""").fetchall()
for r in rows:
    print(dict(r))

print("\n=== latest memories ===")
rows = conn.execute("""
select *
from memories
order by id desc
limit 5
""").fetchall()
for r in rows:
    d = dict(r)
    print({
        k: d.get(k)
        for k in ["id", "memory_type", "content", "status", "merge_key", "confidence", "effectiveness_score"]
        if k in d
    })

print("\n=== latest problems ===")
rows = conn.execute("""
select *
from problem_board
order by id desc
limit 5
""").fetchall()
for r in rows:
    d = dict(r)
    print({
        k: d.get(k)
        for k in ["id", "problem_type", "subject", "description", "status", "merge_key", "severity", "confidence"]
        if k in d
    })

print("\n=== latest skills ===")
rows = conn.execute("""
select *
from skill_memories
order by id desc
limit 5
""").fetchall()
for r in rows:
    d = dict(r)
    print({
        k: d.get(k)
        for k in ["id", "skill_name", "title", "status", "merge_key", "confidence", "effectiveness_score"]
        if k in d
    })

print("\n=== latest gate result ===")
row = conn.execute("""
select id, parse_status, gate_results_json
from nightly_reviews
order by id desc
limit 1
""").fetchone()

if row is None:
    print("No nightly review found.")
else:
    print("review_id:", row["id"])
    print("parse_status:", row["parse_status"])
    raw = row["gate_results_json"]
    print("has_gate_results:", bool(raw))

    if raw:
        data = json.loads(raw)
        text = json.dumps(data, ensure_ascii=False, indent=2)
        print(text[:4000])

        print("\n=== embedding diagnostics ===")
        for keyword in ["embedding_status", "embedding_provider", "embedding_model", "embedding_error"]:
            idx = text.find(keyword)
            if idx != -1:
                print(text[max(0, idx - 100): idx + 300])
                print("-" * 60)

conn.close()
