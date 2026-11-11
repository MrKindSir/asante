"""Administrative setup/negative tests. Never exposed as an MCP tool."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import traceback
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from minio import Minio
from minio.credentials import StaticProvider
from minio.error import S3Error
from minio.minioadmin import MinioAdmin
from urllib3 import PoolManager, Timeout

from scripts.codex.project_mcp import database_connection, storage_client
from scripts.codex.settings import INSPECTION_SCHEMA, READER_ROLE, reader_values

POLICY = "codex-asante-readonly"
MARKER = "Codex Asante read-only permission probe; no application data"


def policy_document(bucket: str) -> dict:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
             "Resource": ["arn:aws:s3:::" + bucket]},
            {"Effect": "Allow", "Action": ["s3:GetObject"],
             "Resource": ["arn:aws:s3:::" + bucket + "/*"]},
            {"Effect": "Deny", "Action": [
                "s3:PutObject", "s3:DeleteObject", "s3:DeleteObjectVersion",
                "s3:CreateBucket", "s3:DeleteBucket", "s3:PutBucketPolicy",
            ], "Resource": ["arn:aws:s3:::" + bucket, "arn:aws:s3:::" + bucket + "/*"]},
        ],
    }


def admin_storage(app: dict[str, str]) -> Minio:
    return Minio(
        "minio:9000", secure=False, access_key=app["ASANTE_MINIO_ROOT_USER"],
        secret_key=app["ASANTE_MINIO_ROOT_PASSWORD"],
        http_client=PoolManager(timeout=Timeout(connect=3, read=10), retries=False),
    )


def provision(payload: dict) -> None:
    app = payload["app"]
    reader = reader_values()
    with psycopg.connect(
        host="postgres", dbname=reader["CODEX_ASANTE_POSTGRES_DB"],
        user=app["ASANTE_POSTGRES_USER"], password=app["ASANTE_POSTGRES_PASSWORD"],
        connect_timeout=5,
    ) as connection:
        existing = connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (READER_ROLE,)).fetchone()
        if existing and not payload["existingCredentials"]:
            raise RuntimeError("Reserved Codex role exists without its credential file")
        if not existing:
            connection.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(READER_ROLE)))
        connection.execute(sql.SQL(
            "ALTER ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 4 PASSWORD {}"
        ).format(sql.Identifier(READER_ROLE), sql.Literal(reader["CODEX_ASANTE_POSTGRES_PASSWORD"])))
        for setting, value in [
            ("default_transaction_read_only", "on"), ("statement_timeout", "3000"),
            ("lock_timeout", "1000"), ("idle_in_transaction_session_timeout", "5000"),
        ]:
            connection.execute(sql.SQL("ALTER ROLE {} SET {} = {}").format(
                sql.Identifier(READER_ROLE), sql.Identifier(setting), sql.Literal(value),
            ))
        connection.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
            sql.Identifier(reader["CODEX_ASANTE_POSTGRES_DB"]), sql.Identifier(READER_ROLE),
        ))
        connection.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(INSPECTION_SCHEMA)))
        connection.execute(sql.SQL(
            "CREATE TABLE IF NOT EXISTS {}.permission_probe (id integer PRIMARY KEY, marker text NOT NULL)"
        ).format(sql.Identifier(INSPECTION_SCHEMA)))
        connection.execute(sql.SQL(
            "INSERT INTO {}.permission_probe VALUES (1,%s) ON CONFLICT (id) DO NOTHING"
        ).format(sql.Identifier(INSPECTION_SCHEMA)), (MARKER,))
        connection.execute(sql.SQL("GRANT USAGE ON SCHEMA public, {} TO {}").format(
            sql.Identifier(INSPECTION_SCHEMA), sql.Identifier(READER_ROLE),
        ))
        connection.execute(sql.SQL(
            "GRANT SELECT ON public.spatial_ref_sys, {}.permission_probe TO {}"
        ).format(sql.Identifier(INSPECTION_SCHEMA), sql.Identifier(READER_ROLE)))
        memberships = connection.execute(
            "SELECT 1 FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=%s)",
            (READER_ROLE,),
        ).fetchall()
        if memberships:
            raise RuntimeError("Codex reader must not be a member of another database role")

    manager = MinioAdmin(
        endpoint="minio:9000", secure=False,
        credentials=StaticProvider(app["ASANTE_MINIO_ROOT_USER"], app["ASANTE_MINIO_ROOT_PASSWORD"]),
    )
    access = reader["CODEX_ASANTE_MINIO_ACCESS_KEY"]
    if not payload["existingCredentials"]:
        users = json.loads(manager.user_list())
        if access in users:
            raise RuntimeError("Reserved Codex MinIO identity already exists")
    manager.user_add(access, reader["CODEX_ASANTE_MINIO_SECRET_KEY"])
    with tempfile.TemporaryDirectory(prefix="codex-asante-policy-") as directory:
        path = Path(directory) / "readonly.json"
        path.write_text(json.dumps(policy_document(reader["CODEX_ASANTE_MINIO_BUCKET"])))
        manager.policy_add(POLICY, str(path))
    manager.policy_set(POLICY, user=access)


def verify(payload: dict) -> dict:
    checks: list[str] = []
    with database_connection() as connection:
        identity = connection.execute(
            "SELECT current_setting('transaction_read_only') AS readonly, rolsuper, "
            "rolcreatedb, rolcreaterole, rolreplication, rolbypassrls FROM pg_roles WHERE rolname=current_user"
        ).fetchone()
        assert identity["readonly"] == "on"
        assert not any(identity[key] for key in identity if key != "readonly")
        assert connection.execute("SELECT srid FROM public.spatial_ref_sys WHERE srid=4326").fetchone()["srid"] == 4326
        checks.extend(["postgres_read_only_default", "postgres_no_admin_flags", "postgis_read_allowed"])

    # Explicit READ WRITE proves ACLs deny changes even if a client disables its read-only default.
    attempts = {
        "postgres_insert_denied": "INSERT INTO codex_asante_inspection.permission_probe VALUES (2,'denied')",
        "postgres_update_denied": "UPDATE codex_asante_inspection.permission_probe SET marker='denied' WHERE id=1",
        "postgres_delete_denied": "DELETE FROM codex_asante_inspection.permission_probe WHERE id=1",
        "postgres_ddl_denied": "CREATE TABLE codex_asante_inspection.must_not_exist (id integer)",
        "postgres_role_creation_denied": "CREATE ROLE codex_asante_must_not_exist",
    }
    for name, statement in attempts.items():
        connection = database_connection()
        try:
            connection.execute("SET TRANSACTION READ WRITE")
            try:
                connection.execute(statement)
            except psycopg.errors.InsufficientPrivilege:
                checks.append(name)
            else:
                raise AssertionError("A PostgreSQL write was unexpectedly permitted")
        finally:
            connection.rollback()
            connection.close()

    reader = reader_values()
    bucket = reader["CODEX_ASANTE_MINIO_BUCKET"]
    administrator = admin_storage(payload["app"])
    if not administrator.bucket_exists(bucket):
        raise RuntimeError("Configured Asante media bucket does not exist")
    token = uuid4().hex
    probe = "codex-verification/" + token + "/read-probe.txt"
    denied_key = "codex-verification/" + token + "/must-not-write.txt"
    administrator.put_object(bucket, probe, io.BytesIO(MARKER.encode()), len(MARKER.encode()), content_type="text/plain")
    client = storage_client()
    try:
        assert client.stat_object(bucket, probe).size == len(MARKER.encode())
        response = client.get_object(bucket, probe)
        try:
            assert response.read(256).decode() == MARKER
        finally:
            response.close()
            response.release_conn()
        checks.extend(["minio_head_allowed", "minio_get_allowed"])
        assert any(item.object_name == probe for item in client.list_objects(bucket, prefix=probe))
        checks.append("minio_scoped_list_allowed")
        for name, operation in [
            ("minio_put_denied", lambda: client.put_object(bucket, denied_key, io.BytesIO(b"x"), 1)),
            ("minio_delete_denied", lambda: client.remove_object(bucket, probe)),
        ]:
            try:
                operation()
            except S3Error as error:
                if error.code not in {"AccessDenied", "AllAccessDisabled"}:
                    raise
                checks.append(name)
            else:
                raise AssertionError(name + " was unexpectedly permitted")
        try:
            visible = client.list_buckets()
        except S3Error as error:
            if error.code != "AccessDenied":
                raise
            checks.append("minio_global_bucket_list_denied")
        else:
            # MinIO may return only the buckets authorized by the account policy.
            assert all(item.name == bucket for item in visible), "Unapproved bucket visibility"
            checks.append("minio_bucket_visibility_scoped")
    finally:
        # Only remove the exact two randomly named objects owned by this verification.
        administrator.remove_object(bucket, probe)
        administrator.remove_object(bucket, denied_key)
    return {"role": READER_ROLE, "bucket": bucket, "checks": checks, "passed": True}


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if payload.get("action") == "setup":
            provision(payload)
        elif payload.get("action") != "verify":
            raise ValueError("Unknown Codex setup action")
        print(json.dumps(verify(payload)))
    except Exception as error:
        admin_code = None
        admin_detail = None
        try:
            body = json.loads(getattr(error, "_body", "{}"))
            admin_code = body.get("Code") or body.get("code")
            admin_detail = str(body.get("Message", ""))[:300]
        except (ValueError, TypeError, AttributeError):
            pass
        print(json.dumps({
            "passed": False, "errorType": type(error).__name__,
            "code": getattr(error, "code", None) or getattr(error, "sqlstate", None) or admin_code,
            "detail": admin_detail,
            "assertion": str(error)[:200] if isinstance(error, AssertionError) else None,
            "source": traceback.extract_tb(error.__traceback__)[-1].lineno,
            "message": "Codex read-only provisioning or verification failed; credentials were not printed.",
        }))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
