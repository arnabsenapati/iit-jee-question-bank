#!/usr/bin/env python3
import argparse
import base64
import hashlib
import json
import mimetypes
import os
import sqlite3
from pathlib import Path

LARGE_TEXT_THRESHOLD = 20_000


def q(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def has_table(conn, table):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def table_cols(conn, table):
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def pick_col(cols, candidates):
    lower = {c.lower(): c for c in cols}
    for name in candidates:
        if name.lower() in lower:
            return lower[name.lower()]
    for c in cols:
        cl = c.lower()
        if any(token in cl for token in candidates):
            return c
    return None


def write_object(objects_dir, key, data):
    path = objects_dir / key
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    path.write_bytes(data)
    return path, len(data)


def pointer_json(key, original_field, original_bytes, content_type="application/octet-stream"):
    return json.dumps({
        "storage": "r2",
        "r2_key": key,
        "content_type": content_type,
        "original_field": original_field,
        "original_bytes": original_bytes,
        "migration": "moved_large_payload_to_r2"
    }, separators=(",", ":"))


def safe_key_part(value):
    text = str(value if value is not None else "unknown")
    return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in text)[:80] or "unknown"


def maybe_decode_image(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("data:image") and "," in text:
            return base64.b64decode(text.split(",", 1)[1])
        # Try base64 only if it looks reasonably like base64.
        compact = text.replace("\n", "").replace("\r", "")
        if len(compact) > 100 and all(ch.isalnum() or ch in "+/=" for ch in compact[:200]):
            try:
                return base64.b64decode(compact, validate=True)
            except Exception:
                return None
    return None


def infer_mime(row, mime_col, filename_col, data):
    if mime_col and row.get(mime_col):
        return str(row[mime_col])
    if filename_col and row.get(filename_col):
        guessed, _ = mimetypes.guess_type(str(row[filename_col]))
        if guessed:
            return guessed
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith(b"GIF8"):
        return "image/gif"
    if data.startswith(b"RIFF") and b"WEBP" in data[:20]:
        return "image/webp"
    return "application/octet-stream"


def extension_for_mime(mime):
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "application/json": ".json",
        "text/plain": ".txt",
    }.get(mime, mimetypes.guess_extension(mime) or ".bin")


def export_large_payloads(conn, objects_dir, sql, manifest):
    tasks = [
        ("configs", "key", {"value_json": "application/json"}),
        ("question_lists", "id", {"metadata_json": "application/json"}),
        ("exams", "id", {"payload_json": "application/json", "source_path": "text/plain"}),
        ("exam_questions", "id", {"question_json": "application/json", "response_json": "application/json", "eval_comment": "text/plain"}),
    ]
    moved = 0
    for table, pk_col, fields in tasks:
        if not has_table(conn, table):
            continue
        cols = table_cols(conn, table)
        if pk_col not in cols:
            continue
        select_cols = [pk_col] + [f for f in fields if f in cols]
        if len(select_cols) <= 1:
            continue
        for row_tuple in conn.execute(f"SELECT {', '.join(select_cols)} FROM {table}"):
            row = dict(zip(select_cols, row_tuple))
            pk = row[pk_col]
            for field, content_type in fields.items():
                if field not in row or row[field] is None:
                    continue
                text = str(row[field])
                size = len(text.encode("utf-8"))
                if size <= LARGE_TEXT_THRESHOLD:
                    continue
                ext = ".json" if content_type == "application/json" else ".txt"
                key = f"large-payloads/{table}/{safe_key_part(pk)}/{field}{ext}"
                file_path, bytes_written = write_object(objects_dir, key, text)
                pointer = pointer_json(key, f"{table}.{field}", bytes_written, content_type)
                sql.append(f"UPDATE {table} SET {field} = {q(pointer)} WHERE {pk_col} = {q(pk)};")
                manifest["r2_objects"].append({"key": key, "file": str(file_path), "bytes": bytes_written, "kind": "large_payload"})
                moved += 1
    manifest["counts"]["large_payloads_moved"] = moved


def export_images(conn, db_path, objects_dir, sql, manifest, reset_images=True):
    if not has_table(conn, "images"):
        manifest["notes"].append("No old images table found.")
        return

    cols = table_cols(conn, "images")
    id_col = pick_col(cols, ["id", "image_id"])
    question_id_col = pick_col(cols, ["question_id", "qid", "question"])
    blob_col = pick_col(cols, ["data", "image_data", "blob", "content", "bytes", "file_blob", "image_blob"])
    path_col = pick_col(cols, ["path", "file_path", "image_path", "local_path", "storage_path"])
    filename_col = pick_col(cols, ["filename", "file_name", "name", "original_name"])
    mime_col = pick_col(cols, ["mime_type", "mimetype", "content_type", "type"])
    kind_col = pick_col(cols, ["kind", "role", "image_kind"])

    if not question_id_col:
        manifest["warnings"].append(f"Images table columns found, but no question_id-like column found: {cols}")
        return
    if not blob_col and not path_col:
        manifest["warnings"].append(f"Images table columns found, but no blob/path-like column found: {cols}")
        return

    if reset_images:
        sql.append("DELETE FROM question_images;")

    db_dir = Path(db_path).resolve().parent
    exported = 0
    skipped = 0
    cur = conn.execute(f"SELECT * FROM images")
    for row_tuple in cur:
        row = dict(zip(cols, row_tuple))
        question_id = row.get(question_id_col)
        if question_id is None:
            skipped += 1
            continue

        data = None
        if blob_col:
            data = maybe_decode_image(row.get(blob_col))
        if data is None and path_col and row.get(path_col):
            p = Path(str(row[path_col]))
            if not p.is_absolute():
                p = db_dir / p
            if p.exists() and p.is_file():
                data = p.read_bytes()
        if not data:
            skipped += 1
            continue

        mime = infer_mime(row, mime_col, filename_col, data)
        ext = extension_for_mime(mime)
        image_id = row.get(id_col) if id_col else exported + 1
        digest = hashlib.sha1(data).hexdigest()[:12]
        key = f"question-images/{safe_key_part(question_id)}/{safe_key_part(image_id)}-{digest}{ext}"
        file_path, size_bytes = write_object(objects_dir, key, data)
        kind = str(row.get(kind_col) or "question")
        sql.append(
            "INSERT INTO question_images (question_id, kind, mime_type, r2_key, size_bytes) "
            f"VALUES ({q(question_id)}, {q(kind)}, {q(mime)}, {q(key)}, {q(size_bytes)});"
        )
        manifest["r2_objects"].append({"key": key, "file": str(file_path), "bytes": size_bytes, "kind": "question_image", "question_id": question_id})
        exported += 1

    manifest["counts"]["images_exported"] = exported
    manifest["counts"]["images_skipped"] = skipped
    manifest["notes"].append(f"Detected old images columns: question_id={question_id_col}, blob={blob_col}, path={path_col}, mime={mime_col}, kind={kind_col}")


def write_sql(path, statements):
    with open(path, "w", encoding="utf-8") as f:
        f.write("PRAGMA foreign_keys = OFF;\n")
        for s in statements:
            f.write(s)
            if not s.endswith("\n"):
                f.write("\n")
        f.write("PRAGMA foreign_keys = ON;\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", default="r2_migration_out")
    ap.add_argument("--skip-large-payloads", action="store_true")
    ap.add_argument("--skip-images", action="store_true")
    ap.add_argument("--keep-existing-images", action="store_true")
    args = ap.parse_args()

    out = Path(args.out)
    objects_dir = out / "r2_objects"
    out.mkdir(parents=True, exist_ok=True)
    objects_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(args.db)
    sql = []
    manifest = {"r2_objects": [], "counts": {}, "notes": [], "warnings": []}

    if not args.skip_large_payloads:
        export_large_payloads(conn, objects_dir, sql, manifest)
    if not args.skip_images:
        export_images(conn, args.db, objects_dir, sql, manifest, reset_images=not args.keep_existing_images)

    sql_path = out / "r2_d1_updates.sql"
    write_sql(sql_path, sql)
    manifest["d1_sql"] = str(sql_path)
    manifest["counts"]["d1_statements"] = len(sql)

    with open(out / "R2_MANIFEST.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
