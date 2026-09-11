import psycopg2
from psycopg2.extras import RealDictCursor, Json
from datetime import datetime
import transformations
import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "options": "-c client_encoding=UTF8",
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

# ─── ETL step definitions ─────────────────────────────────
# Each source table maps to its specific load SQL
ETL_STEPS = {
    "clients": ("dim_client", """
        INSERT INTO datawarehouse.dim_client (id_client, nom_complet, ville, date_naissance)
        SELECT s.id_client, s.prenom || ' ' || s.nom, s.ville, s.date_naissance
        FROM staging.clients s
        WHERE NOT EXISTS (SELECT 1 FROM datawarehouse.dim_client d WHERE d.id_client = s.id_client)
    """),
    "agences": ("dim_agence", """
        INSERT INTO datawarehouse.dim_agence (id_agence, nom_agence, ville, region)
        SELECT s.id_agence, s.nom_agence, s.ville, s.region
        FROM staging.agences s
        WHERE NOT EXISTS (SELECT 1 FROM datawarehouse.dim_agence d WHERE d.id_agence = s.id_agence)
    """),
    "comptes": ("dim_compte", """
        INSERT INTO datawarehouse.dim_compte (id_compte, id_client, type_compte, date_ouverture, statut)
        SELECT s.id_compte, s.id_client, s.type_compte, s.date_ouverture, s.statut
        FROM staging.comptes s
        WHERE NOT EXISTS (SELECT 1 FROM datawarehouse.dim_compte d WHERE d.id_compte = s.id_compte)
    """),
    "transactions": ("fait_transactions", """
        INSERT INTO datawarehouse.fait_transactions
            (id_transaction, sk_compte, sk_client, date_transaction, montant, type_operation, description)
        SELECT t.id_transaction, c.sk_compte, cl.sk_client,
               t.date_transaction, t.montant, t.type_operation, t.description
        FROM staging.transactions t
        LEFT JOIN datawarehouse.dim_compte c ON t.id_compte = c.id_compte
        LEFT JOIN datawarehouse.dim_client cl ON c.id_client = cl.id_client
        WHERE NOT EXISTS (SELECT 1 FROM datawarehouse.fait_transactions f WHERE f.id_transaction = t.id_transaction)
    """),
}

# Correct execution order (transactions must come last)
STEP_ORDER = ["clients", "agences", "comptes", "transactions"]

def extract_pipeline_plan(definition):
    """
    Read a pipeline's JSON definition and return a list of execution steps.
    Each step = { source_table, transforms: [...] }
    Transformations are matched to sources by following the edges.
    """
    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])

    # Index nodes by id
    node_by_id = {n["id"]: n for n in nodes}

    # Find all source nodes
    plan = []
    for node in nodes:
        data = node.get("data", {})
        if data.get("type") != "source":
            continue
        config = data.get("config", {})
        source_table = config.get("source_table")
        if not source_table:
            continue

        # Follow edges from this source to collect transformations in the chain
        transforms = []
        visited = set()

        def follow(node_id):
            for edge in edges:
                if edge.get("source") == node_id and edge.get("target") not in visited:
                    target_id = edge.get("target")
                    visited.add(target_id)
                    target = node_by_id.get(target_id)
                    if target:
                        tdata = target.get("data", {})
                        if tdata.get("type") == "transform":
                            tconfig = tdata.get("config", {})
                            # Each transform node carries its own type + config
                            transforms.append({
                                "type": tconfig.get("transform_kind", "filter"),
                                "config": tconfig,
                            })
                        follow(target_id)

        follow(node["id"])
        plan.append({"source_table": source_table, "transforms": transforms})

    # Sort so dimensions load before the fact table (referential integrity)
    plan.sort(key=lambda p: STEP_ORDER.index(p["source_table"])
              if p["source_table"] in STEP_ORDER else 99)
    return plan

def execute_pipeline_steps(steps, source_label="Manual"):
    """Run the specific ETL steps and return results."""
    logs = []
    errors = []
    total_loaded = 0
    start_time = datetime.now()

    # If no specific steps, run all (backward compatible)
    if not steps:
        steps = STEP_ORDER

    try:
        conn = get_connection()
        cursor = conn.cursor()

        for step in steps:
            if step not in ETL_STEPS:
                continue
            table_name, sql = ETL_STEPS[step]
            try:
                cursor.execute(sql)
                c = cursor.rowcount
                total_loaded += c
                logs.append(f"✅ {table_name}: {c} new records loaded")
            except Exception as e:
                errors.append(f"❌ {table_name} failed: {str(e)}")
                conn.rollback()

        conn.commit()

        # Record in history
        duration = (datetime.now() - start_time).total_seconds()
        status = "success" if not errors else "partial" if logs else "failed"
        cursor.execute("""
            INSERT INTO datawarehouse.pipeline_history (status, records_loaded, duration_sec, details)
            VALUES (%s, %s, %s, %s)
        """, (status, total_loaded, duration, f"[{source_label}]\n" + "\n".join(logs + errors)))
        conn.commit()

        cursor.close()
        conn.close()
    except Exception as e:
        errors.append(f"❌ Database connection failed: {str(e)}")

    duration = (datetime.now() - start_time).total_seconds()
    status = "success" if not errors else "partial" if logs else "failed"

    return {
        "status": status,
        "message": "\n".join(logs + errors),
        "logs": logs,
        "errors": errors,
        "records_loaded": total_loaded,
        "duration": f"{duration:.2f}s",
    }

# Maps each source table to its destination + insert columns + how to build them
DEST_CONFIG = {
    "clients": {
        "dest_table": "datawarehouse.dim_client",
        "dest_cols": ["id_client", "nom_complet", "ville", "date_naissance"],
        "select_map": "s.id_client, s.prenom || ' ' || s.nom, s.ville, s.date_naissance",
        "key_col": "id_client",
        "joins": "",
    },
    "agences": {
        "dest_table": "datawarehouse.dim_agence",
        "dest_cols": ["id_agence", "nom_agence", "ville", "region"],
        "select_map": "s.id_agence, s.nom_agence, s.ville, s.region",
        "key_col": "id_agence",
        "joins": "",
    },
    "comptes": {
        "dest_table": "datawarehouse.dim_compte",
        "dest_cols": ["id_compte", "id_client", "type_compte", "date_ouverture", "statut"],
        "select_map": "s.id_compte, s.id_client, s.type_compte, s.date_ouverture, s.statut",
        "key_col": "id_compte",
        "joins": "",
    },
    "transactions": {
        "dest_table": "datawarehouse.fait_transactions",
        "dest_cols": ["id_transaction", "sk_compte", "sk_client", "sk_agence",
                      "sk_date", "date_transaction", "montant",
                      "type_operation", "description"],
        "select_map": ("s.id_transaction, c.sk_compte, cl.sk_client, ag.sk_agence, "
                       "TO_CHAR(s.date_transaction,'YYYYMMDD')::INT, "
                       "s.date_transaction, s.montant, s.type_operation, s.description"),
        "key_col": "id_transaction",
        "joins": ("LEFT JOIN datawarehouse.dim_compte c  ON s.id_compte = c.id_compte "
                  "LEFT JOIN datawarehouse.dim_client cl ON c.id_client = cl.id_client "
                  "LEFT JOIN datawarehouse.dim_agence ag ON cl.ville   = ag.ville"),
    },
}

def execute_transformed_pipeline(plan, source_label="Manual", mode="incremental"):
    """
    Execute a pipeline plan with real transformations.
    mode = 'incremental' (insert new only) or 'full_refresh' (reload all).
    """
    logs = []
    errors = []
    total_loaded = 0
    start_time = datetime.now()

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # In full refresh, empty the fact table first so the dimensions
        # can then be cleared without violating referential integrity.
        if mode == "full_refresh" and any(
                s["source_table"] == "transactions" for s in plan):
            try:
                cursor.execute("DELETE FROM datawarehouse.fait_transactions")
                logs.append("🔄 fait_transactions: cleared before the dimensions")
            except Exception as e:
                errors.append(f"❌ Could not clear the fact table: {str(e)}")
                conn.rollback()

        for step in plan:
            source = step["source_table"]
            transforms = step.get("transforms", [])

            if source not in DEST_CONFIG:
                logs.append(f"⚠️ {source}: skipped (not supported in transform mode yet)")
                continue

            dc = DEST_CONFIG[source]

            inner_sql, summary = transformations.build_select(source, transforms)
            if not inner_sql:
                errors.append(f"❌ {source}: could not build transformation SQL")
                continue

            dest_cols_str = ", ".join(dc["dest_cols"])

            # ── Full refresh: clear the destination first ──
            if mode == "full_refresh":
                try:
                    # Use DELETE (safer than TRUNCATE with FKs); CASCADE handles dependents
                    cursor.execute(f"DELETE FROM {dc['dest_table']}")
                    logs.append(f"🔄 {dc['dest_table'].split('.')[-1]}: cleared for full refresh")
                except Exception as e:
                    errors.append(f"❌ Could not clear {source}: {str(e)}")
                    conn.rollback()
                    continue

            # ── Build the INSERT (with joins for fact tables) ──
            joins = dc.get("joins", "")
            if mode == "full_refresh":
                insert_sql = f"""
                    INSERT INTO {dc['dest_table']} ({dest_cols_str})
                    SELECT {dc['select_map']}
                    FROM ( {inner_sql} ) AS s
                    {joins}
                """
            else:
                insert_sql = f"""
                    INSERT INTO {dc['dest_table']} ({dest_cols_str})
                    SELECT {dc['select_map']}
                    FROM ( {inner_sql} ) AS s
                    {joins}
                    WHERE NOT EXISTS (
                        SELECT 1 FROM {dc['dest_table']} d
                        WHERE d.{dc['key_col']} = s.{dc['key_col']}
                    )
                """

            try:
                cursor.execute(insert_sql)
                c = cursor.rowcount
                total_loaded += c
                msg = f"✅ {dc['dest_table'].split('.')[-1]}: {c} rows loaded"
                if summary:
                    msg += f" ({'; '.join(summary)})"
                logs.append(msg)
            except Exception as e:
                errors.append(f"❌ {source} failed: {str(e)}")
                conn.rollback()

        conn.commit()

        duration = (datetime.now() - start_time).total_seconds()
        status = "success" if not errors else "partial" if logs else "failed"
        cursor.execute("""
            INSERT INTO datawarehouse.pipeline_history (status, records_loaded, duration_sec, details)
            VALUES (%s, %s, %s, %s)
        """, (status, total_loaded, duration, f"[{source_label} / {mode}]\n" + "\n".join(logs + errors)))
        conn.commit()

        cursor.close()
        conn.close()
    except Exception as e:
        errors.append(f"❌ Database connection failed: {str(e)}")

    duration = (datetime.now() - start_time).total_seconds()
    status = "success" if not errors else "partial" if logs else "failed"

    return {
        "status": status,
        "message": "\n".join(logs + errors),
        "logs": logs,
        "errors": errors,
        "records_loaded": total_loaded,
        "duration": f"{duration:.2f}s",
    }

# ─── CRUD operations ──────────────────────────────────────
def save_pipeline(name, description, definition, created_by):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        INSERT INTO datawarehouse.pipelines (name, description, definition, created_by)
        VALUES (%s, %s, %s, %s)
        RETURNING id, name, description, created_by, created_at
    """, (name, description, Json(definition), created_by))
    result = dict(cursor.fetchone())
    conn.commit()
    cursor.close()
    conn.close()
    return result

def list_pipelines():
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT id, name, description, created_by, created_at
        FROM datawarehouse.pipelines
        ORDER BY created_at DESC
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [dict(r) for r in rows]

def get_pipeline(pipeline_id):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM datawarehouse.pipelines WHERE id = %s", (pipeline_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return dict(row) if row else None

def delete_pipeline(pipeline_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM datawarehouse.pipelines WHERE id = %s", (pipeline_id,))
    conn.commit()
    cursor.close()
    conn.close()

def run_saved_pipeline(pipeline_id, source_label="Manual", mode="incremental"):
    """Load a pipeline definition and execute it with real transformations."""
    pipeline = get_pipeline(pipeline_id)
    if not pipeline:
        return {"status": "failed", "message": "Pipeline not found", "records_loaded": 0}
    plan = extract_pipeline_plan(pipeline["definition"])
    if not plan:
        return {"status": "failed", "message": "No valid sources in pipeline", "records_loaded": 0}
    return execute_transformed_pipeline(plan, source_label=f"{source_label}: {pipeline['name']}", mode=mode)