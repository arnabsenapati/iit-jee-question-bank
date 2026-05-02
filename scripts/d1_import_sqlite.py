#!/usr/bin/env python3
import argparse
import json
import os
import sqlite3
from pathlib import Path

QUESTION_COLUMNS = [
    "id", "subject_id", "source", "magazine", "normalized_magazine", "edition",
    "issue_year", "issue_month", "page_range", "question_set", "question_set_name",
    "chapter", "high_level_chapter", "question_number", "question_text", "answer_text",
    "explanation", "metadata_json", "created_at", "updated_at"
]

SUBJECT_COLUMNS = ["id", "name", "created_at"]
LIST_COLUMNS = ["id", "name", "metadata_json", "archived", "created_at", "updated_at"]
TAG_COLUMNS = ["id", "name", "color", "created_at"]
CONFIG_COLUMNS = ["key", "value_json", "updated_at"]
EXAM_COLUMNS = ["id", "name", "list_name", "imported_at", "evaluated", "evaluated_at", "total_questions", "answered", "correct", "wrong", "score", "percent", "source_path", "payload_json"]
EXAM_QUESTION_COLUMNS = ["id", "exam_id", "q_index", "question_json", "response_json", "correct", "answered", "score", "eval_status", "eval_comment"]


def q(value):
    if value is None:
        return "NULL"
    if isinstance(value, bytes):
        return "X'" + value.hex() + "'"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def has_table(conn, table):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def table_cols(conn, table):
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def write_file(path, statements):
    with open(path, "w", encoding="utf-8") as f:
        f.write("PRAGMA foreign_keys = OFF;\nBEGIN TRANSACTION;\n")
        for s in statements:
            f.write(s)
            if not s.endswith("\n"):
                f.write("\n")
        f.write("COMMIT;\nPRAGMA foreign_keys = ON;\n")


def insert_stmt(table, columns, values):
    return f"INSERT OR REPLACE INTO {table} ({', '.join(columns)}) VALUES ({', '.join(q(v) for v in values)});"


def select_mapped(conn, table, target_cols, transforms=None):
    transforms = transforms or {}
    src_cols = table_cols(conn, table)
    rows = conn.execute(f"SELECT * FROM {table}")
    for row in rows:
        d = dict(zip(src_cols, row))
        vals = []
        for col in target_cols:
            if col in transforms:
                vals.append(transforms[col](d))
            else:
                vals.append(d.get(col))
        yield vals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", default="migration_out")
    ap.add_argument("--chunk-size", type=int, default=2000)
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--extras", action="store_true", help="Also export configs, tags, lists, and exams. Images/embeddings are skipped.")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db)

    manifest = {"chunks": [], "counts": {}}

    reset = []
    if args.reset:
        reset += [
            "DELETE FROM question_images;",
            "DELETE FROM question_embeddings;",
            "DELETE FROM exam_questions;",
            "DELETE FROM exams;",
            "DELETE FROM question_list_items;",
            "DELETE FROM question_lists;",
            "DELETE FROM question_tags;",
            "DELETE FROM tags;",
            "DELETE FROM questions;",
            "DELETE FROM subjects;",
        ]

    stmts = list(reset)

    if has_table(conn, "subjects"):
        for vals in select_mapped(conn, "subjects", SUBJECT_COLUMNS, {"created_at": lambda d: d.get("created_at") or "2025-01-01 00:00:00"}):
            stmts.append(insert_stmt("subjects", SUBJECT_COLUMNS, vals))
        manifest["counts"]["subjects"] = conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]

    f0 = out / "00_reset_and_subjects.sql"
    write_file(f0, stmts)
    manifest["chunks"].append(str(f0.name))

    # Questions preserve original IDs so images/lists/exams can still reference them later.
    if has_table(conn, "questions"):
        src_cols = table_cols(conn, "questions")
        cur = conn.execute("SELECT * FROM questions ORDER BY id")
        batch, part, first_id, last_id, total = [], 1, None, None, 0
        for row in cur:
            d = dict(zip(src_cols, row))
            vals = []
            for col in QUESTION_COLUMNS:
                if col == "page_range":
                    vals.append(d.get("page_range") if d.get("page_range") is not None else d.get("page_num"))
                else:
                    vals.append(d.get(col))
            first_id = first_id or d.get("id")
            last_id = d.get("id")
            batch.append(insert_stmt("questions", QUESTION_COLUMNS, vals))
            total += 1
            if len(batch) >= args.chunk_size:
                fname = out / f"{part:02d}_questions_{first_id}_{last_id}.sql"
                write_file(fname, batch)
                manifest["chunks"].append(fname.name)
                batch, part, first_id = [], part + 1, None
        if batch:
            fname = out / f"{part:02d}_questions_{first_id}_{last_id}.sql"
            write_file(fname, batch)
            manifest["chunks"].append(fname.name)
        manifest["counts"]["questions"] = total

    if args.extras:
        extra_stmts = []
        if has_table(conn, "configs"):
            for vals in select_mapped(conn, "configs", CONFIG_COLUMNS):
                extra_stmts.append(insert_stmt("configs", CONFIG_COLUMNS, vals))
            manifest["counts"]["configs"] = conn.execute("SELECT COUNT(*) FROM configs").fetchone()[0]
        if has_table(conn, "tags"):
            for vals in select_mapped(conn, "tags", TAG_COLUMNS):
                extra_stmts.append(insert_stmt("tags", TAG_COLUMNS, vals))
            manifest["counts"]["tags"] = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
        if has_table(conn, "question_lists"):
            transforms = {
                "archived": lambda d: int(bool(json.loads(d.get("metadata_json") or "{}").get("archived", 0))) if d.get("metadata_json") else 0,
                "updated_at": lambda d: d.get("updated_at") or d.get("created_at"),
            }
            for vals in select_mapped(conn, "question_lists", LIST_COLUMNS, transforms):
                extra_stmts.append(insert_stmt("question_lists", LIST_COLUMNS, vals))
            manifest["counts"]["question_lists"] = conn.execute("SELECT COUNT(*) FROM question_lists").fetchone()[0]
        if has_table(conn, "question_list_items"):
            cols = ["list_id", "question_id", "position", "created_at"]
            for vals in select_mapped(conn, "question_list_items", cols, {"created_at": lambda d: d.get("created_at") or "2025-01-01 00:00:00"}):
                extra_stmts.append(insert_stmt("question_list_items", cols, vals))
            manifest["counts"]["question_list_items"] = conn.execute("SELECT COUNT(*) FROM question_list_items").fetchone()[0]
        if has_table(conn, "exams"):
            for vals in select_mapped(conn, "exams", EXAM_COLUMNS):
                extra_stmts.append(insert_stmt("exams", EXAM_COLUMNS, vals))
            manifest["counts"]["exams"] = conn.execute("SELECT COUNT(*) FROM exams").fetchone()[0]
        if has_table(conn, "exam_questions"):
            for vals in select_mapped(conn, "exam_questions", EXAM_QUESTION_COLUMNS):
                extra_stmts.append(insert_stmt("exam_questions", EXAM_QUESTION_COLUMNS, vals))
            manifest["counts"]["exam_questions"] = conn.execute("SELECT COUNT(*) FROM exam_questions").fetchone()[0]
        if extra_stmts:
            fname = out / "99_extras.sql"
            write_file(fname, extra_stmts)
            manifest["chunks"].append(fname.name)

    with open(out / "MANIFEST.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    main()
