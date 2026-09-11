from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import auth
import scheduler
import pipelines
import pandas as pd
import io
import forecasting
from fastapi.responses import StreamingResponse
import csv
import os
from dotenv import load_dotenv


app = FastAPI(title="BIAT ETL - No-Code Pipeline API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# Staging table column definitions
STAGING_SCHEMAS = {
    "clients":      ["id_client", "nom", "prenom", "date_naissance", "ville", "solde"],
    "comptes":      ["id_compte", "id_client", "type_compte", "date_ouverture", "solde", "statut"],
    "agences":      ["id_agence", "nom_agence", "ville", "region", "telephone"],
    "transactions": ["id_transaction", "id_compte", "date_transaction", "montant", "type_operation", "description"],
}

class Pipeline(BaseModel):
    nodes: List[Any]
    edges: List[Any]

def ensure_history_table():
    """Create the pipeline history table if it doesn't exist."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS datawarehouse.pipeline_history (
            id              SERIAL PRIMARY KEY,
            executed_at     TIMESTAMP DEFAULT NOW(),
            status          VARCHAR(20),
            records_loaded  INT,
            duration_sec    NUMERIC(10,2),
            details         TEXT
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()

@app.on_event("startup")
def startup():
    try:
        ensure_history_table()
    except Exception as e:
        print(f"Startup warning: {e}")
    try:
        scheduler.start_scheduler()
    except Exception as e:
        print(f"Scheduler startup warning: {e}")

@app.get("/")
def root():
    return {"message": "BIAT ETL No-Code Pipeline API is running !"}

# ─── STATS ENDPOINTS ──────────────────────────────────────
@app.get("/db-stats")
def get_db_stats():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        stats = {}
        tables = [
            ("dim_client", "datawarehouse"),
            ("dim_compte", "datawarehouse"),
            ("dim_agence", "datawarehouse"),
            ("fait_transactions", "datawarehouse"),
        ]
        for table, schema in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {schema}.{table}")
            stats[table] = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return {"stats": stats}
    except Exception as e:
        return {"error": str(e)}

@app.get("/staging-stats")
def get_staging_stats():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        stats = {}
        for table in STAGING_SCHEMAS.keys():
            cursor.execute(f"SELECT COUNT(*) FROM staging.{table}")
            stats[table] = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return {"stats": stats}
    except Exception as e:
        return {"error": str(e)}

# ─── DATA PREVIEW ─────────────────────────────────────────
@app.get("/preview/{schema}/{table}")
def preview_table(schema: str, table: str, limit: int = 10):
    allowed_schemas = ["staging", "datawarehouse"]
    if schema not in allowed_schemas:
        return {"error": "Invalid schema"}
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(f"SELECT * FROM {schema}.{table} LIMIT %s", (limit,))
        rows = cursor.fetchall()
        colnames = [desc[0] for desc in cursor.description]
        cursor.execute(f"SELECT COUNT(*) FROM {schema}.{table}")
        total = cursor.fetchone()["count"]
        cursor.close()
        conn.close()
        return {
            "columns": colnames,
            "rows": [dict(r) for r in rows],
            "total": total,
            "showing": len(rows)
        }
    except Exception as e:
        return {"error": str(e)}

# ─── FILE UPLOAD (CSV + Excel) ────────────────────────────
@app.post("/upload")
async def upload_file(file: UploadFile = File(...), target_table: str = Form(...)):
    if target_table not in STAGING_SCHEMAS:
        return {"error": f"Unknown target table: {target_table}"}

    try:
        contents = await file.read()
        filename = file.filename.lower()

        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(contents))
        elif filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            return {"error": "Unsupported file type. Use .csv or .xlsx"}

        expected_cols = STAGING_SCHEMAS[target_table]

        missing = [c for c in expected_cols if c not in df.columns]
        if missing:
            return {
                "error": f"Missing columns: {missing}",
                "expected": expected_cols,
                "found": list(df.columns)
            }

        df = df[expected_cols]

        conn = get_connection()
        cursor = conn.cursor()
        inserted = 0
        for _, row in df.iterrows():
            placeholders = ",".join(["%s"] * len(expected_cols))
            cols = ",".join(expected_cols)
            cursor.execute(
                f"INSERT INTO staging.{target_table} ({cols}) VALUES ({placeholders})",
                tuple(row[c] for c in expected_cols)
            )
            inserted += 1
        conn.commit()
        cursor.close()
        conn.close()

        return {
            "status": "success",
            "message": f"✅ Uploaded {inserted} rows into staging.{target_table}",
            "rows_inserted": inserted,
            "filename": file.filename
        }
    except Exception as e:
        return {"error": str(e)}

# ─── RUN PIPELINE ─────────────────────────────────────────
@app.post("/run-pipeline")
def run_pipeline(pipeline: Pipeline):
    logs = []
    errors = []
    total_loaded = 0
    start_time = datetime.now()

    try:
        conn = get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO datawarehouse.dim_client
                    (id_client, nom_complet, ville, date_naissance)
                SELECT s.id_client, s.prenom || ' ' || s.nom, s.ville, s.date_naissance
                FROM staging.clients s
                WHERE NOT EXISTS (
                    SELECT 1 FROM datawarehouse.dim_client d WHERE d.id_client = s.id_client
                )
            """)
            c = cursor.rowcount; total_loaded += c
            logs.append(f"✅ dim_client: {c} new records loaded")
        except Exception as e:
            errors.append(f"❌ dim_client failed: {str(e)}"); conn.rollback()

        try:
            cursor.execute("""
                INSERT INTO datawarehouse.dim_agence
                    (id_agence, nom_agence, ville, region)
                SELECT s.id_agence, s.nom_agence, s.ville, s.region
                FROM staging.agences s
                WHERE NOT EXISTS (
                    SELECT 1 FROM datawarehouse.dim_agence d WHERE d.id_agence = s.id_agence
                )
            """)
            c = cursor.rowcount; total_loaded += c
            logs.append(f"✅ dim_agence: {c} new records loaded")
        except Exception as e:
            errors.append(f"❌ dim_agence failed: {str(e)}"); conn.rollback()

        try:
            cursor.execute("""
                INSERT INTO datawarehouse.dim_compte
                    (id_compte, id_client, type_compte, date_ouverture, statut)
                SELECT s.id_compte, s.id_client, s.type_compte, s.date_ouverture, s.statut
                FROM staging.comptes s
                WHERE NOT EXISTS (
                    SELECT 1 FROM datawarehouse.dim_compte d WHERE d.id_compte = s.id_compte
                )
            """)
            c = cursor.rowcount; total_loaded += c
            logs.append(f"✅ dim_compte: {c} new records loaded")
        except Exception as e:
            errors.append(f"❌ dim_compte failed: {str(e)}"); conn.rollback()

        try:
            cursor.execute("""
                INSERT INTO datawarehouse.fait_transactions
                    (id_transaction, sk_compte, sk_client,
                     date_transaction, montant, type_operation, description)
                SELECT t.id_transaction, c.sk_compte, cl.sk_client,
                       t.date_transaction, t.montant, t.type_operation, t.description
                FROM staging.transactions t
                LEFT JOIN datawarehouse.dim_compte c ON t.id_compte = c.id_compte
                LEFT JOIN datawarehouse.dim_client cl ON c.id_client = cl.id_client
                WHERE NOT EXISTS (
                    SELECT 1 FROM datawarehouse.fait_transactions f
                    WHERE f.id_transaction = t.id_transaction
                )
            """)
            c = cursor.rowcount; total_loaded += c
            logs.append(f"✅ fait_transactions: {c} new records loaded")
        except Exception as e:
            errors.append(f"❌ fait_transactions failed: {str(e)}"); conn.rollback()

        conn.commit()

        duration = (datetime.now() - start_time).total_seconds()
        status = "success" if not errors else "partial" if logs else "failed"
        cursor.execute("""
            INSERT INTO datawarehouse.pipeline_history
                (status, records_loaded, duration_sec, details)
            VALUES (%s, %s, %s, %s)
        """, (status, total_loaded, duration, "\n".join(logs + errors)))
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
        "timestamp": datetime.now().isoformat()
    }


# ─── PIPELINE HISTORY ─────────────────────────────────────
@app.get("/history")
def get_history(limit: int = 10):
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT id, executed_at, status, records_loaded, duration_sec
            FROM datawarehouse.pipeline_history
            ORDER BY executed_at DESC
            LIMIT %s
        """, (limit,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return {"history": [dict(r) for r in rows]}
    except Exception as e:
        return {"error": str(e)}

# ═══════════════════════════════════════════════════════════
#  AUTHENTICATION ENDPOINTS
# ═══════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    username: str
    password: str

class CreateUserRequest(BaseModel):
    username: str
    full_name: str
    password: str
    role: str

def get_current_user(authorization: str = Header(None)):
    """Extract and validate the user from the JWT token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ")[1]
    payload = auth.decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload

@app.post("/login")
def login(req: LoginRequest):
    user = auth.authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = auth.create_access_token({
        "username": user["username"],
        "role": user["role"],
        "full_name": user["full_name"]
    })
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "username": user["username"],
            "full_name": user["full_name"],
            "role": user["role"]
        }
    }

@app.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return {
        "username": current_user["username"],
        "role": current_user["role"],
        "full_name": current_user.get("full_name")
    }

@app.get("/users")
def get_users(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"users": auth.list_users()}

@app.post("/users")
def add_user(req: CreateUserRequest, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        auth.create_user(req.username, req.full_name, req.password, req.role)
        return {"message": f"User {req.username} created successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ═══════════════════════════════════════════════════════════
#  SCHEDULER ENDPOINTS
# ═══════════════════════════════════════════════════════════

class CreateScheduleRequest(BaseModel):
    name: str
    frequency: str
    run_time: str = "08:00"
    day_of_week: str = "mon"
    pipeline_id: Optional[int] = None

@app.get("/schedules")
def get_schedules(current_user: dict = Depends(get_current_user)):
    try:
        conn = auth.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT id, name, frequency, run_time, day_of_week,
                   is_active, created_by, created_at, last_run, pipeline_id
            FROM datawarehouse.schedules
            ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return {"schedules": [dict(r) for r in rows]}
    except Exception as e:
        return {"error": str(e)}

@app.post("/schedules")
def create_schedule(req: CreateScheduleRequest, current_user: dict = Depends(get_current_user)):
    if current_user["role"] not in ["admin", "operator"]:
        raise HTTPException(status_code=403, detail="Operator or Admin access required")
    try:
        conn = auth.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            INSERT INTO datawarehouse.schedules
                (name, frequency, run_time, day_of_week, created_by, pipeline_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
        """, (req.name, req.frequency, req.run_time, req.day_of_week,
              current_user["username"], req.pipeline_id))
        new_schedule = dict(cursor.fetchone())
        conn.commit()
        cursor.close()
        conn.close()

        scheduler.add_schedule_to_scheduler(new_schedule)

        return {"message": f"Schedule '{req.name}' created", "schedule": new_schedule}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/schedules/{schedule_id}/toggle")
def toggle_schedule(schedule_id: int, current_user: dict = Depends(get_current_user)):
    if current_user["role"] not in ["admin", "operator"]:
        raise HTTPException(status_code=403, detail="Operator or Admin access required")
    try:
        conn = auth.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            UPDATE datawarehouse.schedules
            SET is_active = NOT is_active
            WHERE id = %s
            RETURNING *
        """, (schedule_id,))
        updated = dict(cursor.fetchone())
        conn.commit()
        cursor.close()
        conn.close()

        if updated["is_active"]:
            scheduler.add_schedule_to_scheduler(updated)
        else:
            scheduler.remove_schedule_from_scheduler(schedule_id)

        return {"message": "Schedule updated", "schedule": updated}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: int, current_user: dict = Depends(get_current_user)):
    if current_user["role"] not in ["admin", "operator"]:
        raise HTTPException(status_code=403, detail="Operator or Admin access required")
    try:
        conn = auth.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM datawarehouse.schedules WHERE id = %s", (schedule_id,))
        conn.commit()
        cursor.close()
        conn.close()

        scheduler.remove_schedule_from_scheduler(schedule_id)

        return {"message": "Schedule deleted"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ═══════════════════════════════════════════════════════════
#  SAVED PIPELINES ENDPOINTS
# ═══════════════════════════════════════════════════════════

class SavePipelineRequest(BaseModel):
    name: str
    description: str = ""
    definition: dict

@app.get("/pipelines")
def get_pipelines(current_user: dict = Depends(get_current_user)):
    try:
        return {"pipelines": pipelines.list_pipelines()}
    except Exception as e:
        return {"error": str(e)}

@app.get("/pipelines/{pipeline_id}")
def get_one_pipeline(pipeline_id: int, current_user: dict = Depends(get_current_user)):
    try:
        p = pipelines.get_pipeline(pipeline_id)
        if not p:
            raise HTTPException(status_code=404, detail="Pipeline not found")
        return {"pipeline": p}
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}

@app.post("/pipelines")
def create_pipeline(req: SavePipelineRequest, current_user: dict = Depends(get_current_user)):
    if current_user["role"] not in ["admin", "operator"]:
        raise HTTPException(status_code=403, detail="Operator or Admin access required")
    try:
        result = pipelines.save_pipeline(
            req.name, req.description, req.definition, current_user["username"]
        )
        return {"message": f"Pipeline '{req.name}' saved", "pipeline": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class RunPipelineRequest(BaseModel):
    mode: str = "incremental"

@app.post("/pipelines/{pipeline_id}/run")
def run_pipeline_by_id(pipeline_id: int, req: RunPipelineRequest = RunPipelineRequest(), current_user: dict = Depends(get_current_user)):
    if current_user["role"] not in ["admin", "operator"]:
        raise HTTPException(status_code=403, detail="Operator or Admin access required")
    try:
        result = pipelines.run_saved_pipeline(pipeline_id, source_label="Manual", mode=req.mode)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/pipelines/{pipeline_id}")
def remove_pipeline(pipeline_id: int, current_user: dict = Depends(get_current_user)):
    if current_user["role"] not in ["admin", "operator"]:
        raise HTTPException(status_code=403, detail="Operator or Admin access required")
    try:
        pipelines.delete_pipeline(pipeline_id)
        return {"message": "Pipeline deleted"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ═══════════════════════════════════════════════════════════
#  DASHBOARD ANALYTICS ENDPOINTS
# ═══════════════════════════════════════════════════════════

@app.get("/dashboard/kpis")
def dashboard_kpis(current_user: dict = Depends(get_current_user)):
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        kpis = {}

        cursor.execute("SELECT COUNT(*) AS c FROM datawarehouse.dim_client")
        kpis["total_clients"] = cursor.fetchone()["c"]

        cursor.execute("SELECT COUNT(*) AS c FROM datawarehouse.dim_compte")
        kpis["total_accounts"] = cursor.fetchone()["c"]

        cursor.execute("SELECT COUNT(*) AS c FROM datawarehouse.dim_agence")
        kpis["total_branches"] = cursor.fetchone()["c"]

        cursor.execute("SELECT COUNT(*) AS c FROM datawarehouse.fait_transactions")
        kpis["total_transactions"] = cursor.fetchone()["c"]

        cursor.execute("SELECT COALESCE(SUM(montant), 0) AS s FROM datawarehouse.fait_transactions")
        kpis["total_amount"] = float(cursor.fetchone()["s"])

        cursor.execute("""
            SELECT COUNT(*) AS c FROM datawarehouse.dim_compte WHERE statut = 'Actif'
        """)
        kpis["active_accounts"] = cursor.fetchone()["c"]

        cursor.close()
        conn.close()
        return {"kpis": kpis}
    except Exception as e:
        return {"error": str(e)}

@app.get("/dashboard/transactions-by-type")
def transactions_by_type(current_user: dict = Depends(get_current_user)):
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT type_operation AS name, COUNT(*) AS count, COALESCE(SUM(montant),0) AS total
            FROM datawarehouse.fait_transactions
            GROUP BY type_operation
            ORDER BY count DESC
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return {"data": [{"name": r["name"], "count": r["count"], "total": float(r["total"])} for r in rows]}
    except Exception as e:
        return {"error": str(e)}

@app.get("/dashboard/transactions-by-region")
def transactions_by_region(current_user: dict = Depends(get_current_user)):
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT a.region AS name, COUNT(t.id_transaction) AS count
            FROM datawarehouse.fait_transactions t
            JOIN datawarehouse.dim_compte c ON t.sk_compte = c.sk_compte
            JOIN datawarehouse.dim_client cl ON c.id_client = cl.id_client
            JOIN datawarehouse.dim_agence a ON cl.ville = a.ville
            GROUP BY a.region
            ORDER BY count DESC
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        if not rows:
            cursor2_conn = get_connection()
            c2 = cursor2_conn.cursor(cursor_factory=RealDictCursor)
            c2.execute("""
                SELECT region AS name, COUNT(*) AS count
                FROM datawarehouse.dim_agence
                GROUP BY region ORDER BY count DESC
            """)
            rows = c2.fetchall()
            c2.close()
            cursor2_conn.close()
        return {"data": [{"name": r["name"], "count": r["count"]} for r in rows]}
    except Exception as e:
        return {"error": str(e)}

@app.get("/dashboard/account-types")
def account_types(current_user: dict = Depends(get_current_user)):
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT type_compte AS name, COUNT(*) AS count
            FROM datawarehouse.dim_compte
            GROUP BY type_compte
            ORDER BY count DESC
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return {"data": [{"name": r["name"], "count": r["count"]} for r in rows]}
    except Exception as e:
        return {"error": str(e)}

@app.get("/dashboard/clients-by-city")
def clients_by_city(current_user: dict = Depends(get_current_user)):
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT ville AS name, COUNT(*) AS count
            FROM datawarehouse.dim_client
            GROUP BY ville
            ORDER BY count DESC
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return {"data": [{"name": r["name"], "count": r["count"]} for r in rows]}
    except Exception as e:
        return {"error": str(e)}

# ═══════════════════════════════════════════════════════════
#  SMART UPLOAD WITH COLUMN MAPPING
# ═══════════════════════════════════════════════════════════

@app.post("/upload/inspect")
async def inspect_file(file: UploadFile = File(...)):
    """Read a file and return its columns + a preview, without inserting."""
    try:
        contents = await file.read()
        filename = file.filename.lower()

        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(contents))
        elif filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            return {"error": "Unsupported file type. Use .csv or .xlsx"}

        preview = df.head(5).fillna("").astype(str).to_dict(orient="records")

        return {
            "columns": list(df.columns),
            "preview": preview,
            "row_count": len(df),
            "filename": file.filename
        }
    except Exception as e:
        return {"error": str(e)}

class MappedImportRequest(BaseModel):
    target_table: str
    mapping: dict
    rows: List[dict]

@app.post("/upload/import-mapped")
def import_mapped(req: MappedImportRequest, current_user: dict = Depends(get_current_user)):
    if current_user["role"] not in ["admin", "operator"]:
        raise HTTPException(status_code=403, detail="Operator or Admin access required")

    if req.target_table not in STAGING_SCHEMAS:
        return {"error": f"Unknown target table: {req.target_table}"}

    expected_cols = STAGING_SCHEMAS[req.target_table]

    unmapped = [c for c in expected_cols if c not in req.mapping or not req.mapping[c]]
    if unmapped:
        return {"error": f"These columns are not mapped: {unmapped}"}

    try:
        conn = get_connection()
        cursor = conn.cursor()
        inserted = 0

        for row in req.rows:
            values = []
            for sys_col in expected_cols:
                file_col = req.mapping[sys_col]
                val = row.get(file_col, None)
                if val == "" or val is None:
                    val = None
                values.append(val)

            placeholders = ",".join(["%s"] * len(expected_cols))
            cols = ",".join(expected_cols)
            cursor.execute(
                f"INSERT INTO staging.{req.target_table} ({cols}) VALUES ({placeholders})",
                tuple(values)
            )
            inserted += 1

        conn.commit()
        cursor.close()
        conn.close()

        return {
            "status": "success",
            "message": f"✅ Imported {inserted} rows into staging.{req.target_table}",
            "rows_inserted": inserted
        }
    except Exception as e:
        return {"error": str(e)}
    

# ═══════════════════════════════════════════════════════════
#  DATA ASSISTANT (CHATBOT) ENDPOINT
# ═══════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    message: str

def run_scalar(query):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(query)
    result = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return result

def run_query(query):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute(query)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/chat")
def chat(req: ChatRequest, current_user: dict = Depends(get_current_user)):
    msg = req.message.lower().strip()

    try:
        # ─── Clients ──────────────────────────────────────
        if ("how many" in msg or "combien" in msg or "number" in msg or "total" in msg) and ("client" in msg):
            count = run_scalar("SELECT COUNT(*) FROM datawarehouse.dim_client")
            return {"reply": f"👤 You currently have **{count} clients** in your data warehouse."}

        # ─── Accounts ─────────────────────────────────────
        if ("how many" in msg or "combien" in msg or "number" in msg or "total" in msg) and ("account" in msg or "compte" in msg):
            count = run_scalar("SELECT COUNT(*) FROM datawarehouse.dim_compte")
            active = run_scalar("SELECT COUNT(*) FROM datawarehouse.dim_compte WHERE statut = 'Actif'")
            return {"reply": f"🏦 You have **{count} accounts** in total, of which **{active} are active**."}

        # ─── Branches ─────────────────────────────────────
        if ("how many" in msg or "combien" in msg or "number" in msg) and ("branch" in msg or "agence" in msg):
            count = run_scalar("SELECT COUNT(*) FROM datawarehouse.dim_agence")
            return {"reply": f"🏢 There are **{count} branches** registered."}

        # ─── Transactions count ───────────────────────────
        if ("how many" in msg or "combien" in msg or "number" in msg) and ("transaction" in msg):
            count = run_scalar("SELECT COUNT(*) FROM datawarehouse.fait_transactions")
            return {"reply": f"💳 There are **{count} transactions** recorded."}

        # ─── Total amount / volume ────────────────────────
        if ("amount" in msg or "montant" in msg or "volume" in msg or "money" in msg or "sum" in msg) and "transaction" in msg or "total volume" in msg:
            total = run_scalar("SELECT COALESCE(SUM(montant), 0) FROM datawarehouse.fait_transactions")
            return {"reply": f"💰 The total transaction volume is **{total:,.2f} TND**."}

        # ─── Top branch by accounts ───────────────────────
        if ("which" in msg or "quelle" in msg or "most" in msg or "top" in msg) and ("branch" in msg or "agence" in msg):
            rows = run_query("""
                SELECT region, COUNT(*) AS c
                FROM datawarehouse.dim_agence
                GROUP BY region ORDER BY c DESC LIMIT 1
            """)
            if rows:
                return {"reply": f"🏢 The region with the most branches is **{rows[0]['region']}** with {rows[0]['c']} branches."}

        # ─── Transactions by type ─────────────────────────
        if ("type" in msg) and ("transaction" in msg or "operation" in msg):
            rows = run_query("""
                SELECT type_operation, COUNT(*) AS c
                FROM datawarehouse.fait_transactions
                GROUP BY type_operation ORDER BY c DESC
            """)
            if rows:
                lines = ", ".join([f"{r['type_operation']} ({r['c']})" for r in rows])
                return {"reply": f"💳 Transactions by type: {lines}."}
            return {"reply": "No transactions found yet."}

        # ─── Account types ────────────────────────────────
        if ("type" in msg) and ("account" in msg or "compte" in msg):
            rows = run_query("""
                SELECT type_compte, COUNT(*) AS c
                FROM datawarehouse.dim_compte
                GROUP BY type_compte ORDER BY c DESC
            """)
            if rows:
                lines = ", ".join([f"{r['type_compte']} ({r['c']})" for r in rows])
                return {"reply": f"🏦 Account types: {lines}."}

        # ─── Top city by clients ──────────────────────────
        if ("city" in msg or "ville" in msg) and ("most" in msg or "top" in msg or "which" in msg):
            rows = run_query("""
                SELECT ville, COUNT(*) AS c
                FROM datawarehouse.dim_client
                GROUP BY ville ORDER BY c DESC LIMIT 1
            """)
            if rows:
                return {"reply": f"📍 The city with the most clients is **{rows[0]['ville']}** with {rows[0]['c']} clients."}

        # ─── Summary / overview ───────────────────────────
        if "summary" in msg or "overview" in msg or "resume" in msg or "stats" in msg:
            clients = run_scalar("SELECT COUNT(*) FROM datawarehouse.dim_client")
            accounts = run_scalar("SELECT COUNT(*) FROM datawarehouse.dim_compte")
            branches = run_scalar("SELECT COUNT(*) FROM datawarehouse.dim_agence")
            trans = run_scalar("SELECT COUNT(*) FROM datawarehouse.fait_transactions")
            total = run_scalar("SELECT COALESCE(SUM(montant),0) FROM datawarehouse.fait_transactions")
            return {"reply": f"📊 **Data Warehouse Summary**\n👤 {clients} clients\n🏦 {accounts} accounts\n🏢 {branches} branches\n💳 {trans} transactions\n💰 {total:,.2f} TND total volume"}

        # ─── Help ─────────────────────────────────────────
        if "help" in msg or "aide" in msg or "what can you" in msg:
            return {"reply": "🤖 I can answer questions about your data warehouse! Try asking:\n• How many clients do we have?\n• Total transaction volume?\n• Which region has the most branches?\n• Transactions by type\n• Give me a summary"}

        # ─── Fallback ─────────────────────────────────────
        return {"reply": "🤔 I'm not sure how to answer that. Try asking about clients, accounts, branches, transactions, or type 'help' to see what I can do."}

    except Exception as e:
        return {"reply": f"⚠️ Sorry, I had trouble accessing the data: {str(e)}"}
    

# ─── RUN CANVAS PIPELINE (with transformations) ───────────
class RunCanvasRequest(BaseModel):
    nodes: List[Any]
    edges: List[Any]
    mode: str = "incremental"

@app.post("/run-canvas")
def run_canvas(req: RunCanvasRequest, current_user: dict = Depends(get_current_user)):
    if current_user["role"] not in ["admin", "operator"]:
        raise HTTPException(status_code=403, detail="Operator or Admin access required")
    try:
        definition = {"nodes": req.nodes, "edges": req.edges}
        plan = pipelines.extract_pipeline_plan(definition)
        if not plan:
            return {
                "status": "failed",
                "message": "⚠️ No configured source found on the canvas. Add and configure a Source block.",
                "records_loaded": 0,
                "duration": "0.00s",
            }
        result = pipelines.execute_transformed_pipeline(plan, source_label="Canvas", mode=req.mode)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ═══════════════════════════════════════════════════════════
#  FORECASTING ENDPOINTS
# ═══════════════════════════════════════════════════════════

@app.get("/forecast/metrics")
def forecast_metrics(current_user: dict = Depends(get_current_user)):
    """List the time series available for forecasting."""
    return {"metrics": forecasting.available_metrics()}

@app.get("/forecast/{metric}")
def forecast_metric(
    metric: str,
    horizon: int = 6,
    method: str = "auto",
    current_user: dict = Depends(get_current_user),
):
    """
    Run the forecasting protocol on a given metric.
      metric  : transactions_count | transactions_amount | account_openings
      horizon : number of months to forecast (1-24)
      method  : auto | moving_average | linear_regression | holt_linear | holt_winters
    """
    try:
        horizon = max(1, min(24, horizon))
        return forecasting.forecast(metric, horizon=horizon, method=method)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        return {"error": str(e)}

# ═══════════════════════════════════════════════════════════
#  FULL ETL (all tables, no canvas needed)
# ═══════════════════════════════════════════════════════════

class FullETLRequest(BaseModel):
    mode: str = "incremental"

@app.post("/run-full-etl")
def run_full_etl(req: FullETLRequest = FullETLRequest(),
                 current_user: dict = Depends(get_current_user)):
    """Load every staging table into the warehouse, in the correct order."""
    if current_user["role"] not in ["admin", "operator"]:
        raise HTTPException(status_code=403, detail="Operator or Admin access required")
    try:
        plan = [{"source_table": s, "transforms": []}
                for s in ["clients", "agences", "comptes", "transactions"]]
        return pipelines.execute_transformed_pipeline(
            plan, source_label="Full ETL", mode=req.mode
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
# ═══════════════════════════════════════════════════════════
#  DASHBOARD V2 — evolution, growth, rankings
# ═══════════════════════════════════════════════════════════

def _months_filter(months):
    """Return a SQL interval condition, or empty string for 'all'."""
    if months and months > 0:
        return f"AND t.date_transaction >= (CURRENT_DATE - INTERVAL '{int(months)} months')"
    return ""

@app.get("/dashboard/overview")
def dashboard_overview(months: int = 12, current_user: dict = Depends(get_current_user)):
    """KPIs with period-over-period growth."""
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        p = int(months) if months and months > 0 else 1200   # 'all' ≈ 100 years

        cur.execute(f"""
            WITH cur AS (
                SELECT COUNT(*) AS n, COALESCE(SUM(montant),0) AS amt
                FROM datawarehouse.fait_transactions t
                WHERE t.date_transaction >= (CURRENT_DATE - INTERVAL '{p} months')
            ),
            prev AS (
                SELECT COUNT(*) AS n, COALESCE(SUM(montant),0) AS amt
                FROM datawarehouse.fait_transactions t
                WHERE t.date_transaction >= (CURRENT_DATE - INTERVAL '{p*2} months')
                  AND t.date_transaction <  (CURRENT_DATE - INTERVAL '{p} months')
            )
            SELECT cur.n AS cur_n, cur.amt AS cur_amt,
                   prev.n AS prev_n, prev.amt AS prev_amt
            FROM cur, prev
        """)
        r = cur.fetchone()

        cur.execute("SELECT COUNT(*) AS n FROM datawarehouse.dim_client")
        clients = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM datawarehouse.dim_compte")
        accounts = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM datawarehouse.dim_compte WHERE statut='Actif'")
        active = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM datawarehouse.dim_agence")
        branches = cur.fetchone()["n"]

        cur.close(); conn.close()

        def growth(c, pv):
            c = float(c or 0); pv = float(pv or 0)
            if pv == 0:
                return None
            return round((c - pv) / pv * 100, 1)

        cur_n = int(r["cur_n"] or 0); cur_amt = float(r["cur_amt"] or 0)
        return {
            "clients": clients,
            "accounts": accounts,
            "active_accounts": active,
            "active_rate": round(active / accounts * 100, 1) if accounts else 0,
            "branches": branches,
            "transactions": cur_n,
            "volume": round(cur_amt, 2),
            "avg_transaction": round(cur_amt / cur_n, 2) if cur_n else 0,
            "growth_transactions": growth(r["cur_n"], r["prev_n"]),
            "growth_volume": growth(r["cur_amt"], r["prev_amt"]),
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/dashboard/evolution")
def dashboard_evolution(months: int = 12, current_user: dict = Depends(get_current_user)):
    """Monthly transaction count and amount."""
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        p = int(months) if months and months > 0 else 1200
        cur.execute(f"""
            SELECT TO_CHAR(date_transaction,'YYYY-MM') AS period,
                   COUNT(*) AS count,
                   COALESCE(SUM(montant),0)::float AS amount
            FROM datawarehouse.fait_transactions
            WHERE date_transaction >= (CURRENT_DATE - INTERVAL '{p} months')
            GROUP BY 1 ORDER BY 1
        """)
        rows = cur.fetchall()
        cur.close(); conn.close()
        return {"data": [{"period": r["period"],
                          "count": r["count"],
                          "amount": round(float(r["amount"]), 2)} for r in rows]}
    except Exception as e:
        return {"error": str(e)}

@app.get("/dashboard/top-accounts")
def dashboard_top_accounts(limit: int = 8, current_user: dict = Depends(get_current_user)):
    """Accounts ranked by total transaction volume."""
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT c.id_compte, c.type_compte, c.statut,
                   cl.nom_complet, cl.ville,
                   COUNT(t.id_transaction) AS tx_count,
                   COALESCE(SUM(t.montant),0)::float AS total
            FROM datawarehouse.fait_transactions t
            JOIN datawarehouse.dim_compte c ON t.sk_compte = c.sk_compte
            LEFT JOIN datawarehouse.dim_client cl ON c.id_client = cl.id_client
            GROUP BY c.id_compte, c.type_compte, c.statut, cl.nom_complet, cl.ville
            ORDER BY total DESC
            LIMIT %s
        """, (int(limit),))
        rows = cur.fetchall()
        cur.close(); conn.close()
        return {"data": [{
            "id_compte": r["id_compte"], "type_compte": r["type_compte"],
            "statut": r["statut"], "client": r["nom_complet"], "ville": r["ville"],
            "tx_count": r["tx_count"], "total": round(float(r["total"]), 2),
        } for r in rows]}
    except Exception as e:
        return {"error": str(e)}

# ═══════════════════════════════════════════════════════════
#  EXPORT / DOWNLOAD ENDPOINTS
# ═══════════════════════════════════════════════════════════

# Whitelist of exportable tables (prevents arbitrary table access)
EXPORTABLE = {
    "staging": ["clients", "comptes", "agences", "transactions"],
    "datawarehouse": ["dim_client", "dim_compte", "dim_agence",
                      "fait_transactions", "pipeline_history"],
}

def _csv_response(rows, columns, filename):
    """Build a downloadable CSV response from a list of dict rows."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({c: r.get(c) for c in columns})
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

def _excel_response(sheets, filename):
    """Build a downloadable multi-sheet Excel file. sheets = {name: list_of_dicts}"""
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for sheet_name, data in sheets.items():
            df = pd.DataFrame(data if data else [{}])
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    out.seek(0)
    return StreamingResponse(
        out,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

def _stamp():
    return datetime.now().strftime("%Y%m%d_%H%M")


@app.get("/export/table/{schema}/{table}")
def export_table(schema: str, table: str, current_user: dict = Depends(get_current_user)):
    """Download the full content of a table as a CSV file."""
    if schema not in EXPORTABLE or table not in EXPORTABLE[schema]:
        raise HTTPException(status_code=400, detail="This table cannot be exported")
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(f"SELECT * FROM {schema}.{table}")
        rows = [dict(r) for r in cur.fetchall()]
        columns = [d[0] for d in cur.description]
        cur.close(); conn.close()
        return _csv_response(rows, columns, f"{schema}_{table}_{_stamp()}.csv")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/export/dashboard")
def export_dashboard(months: int = 12, current_user: dict = Depends(get_current_user)):
    """Download the whole dashboard as a multi-sheet Excel workbook."""
    try:
        p = int(months) if months and months > 0 else 1200
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # KPIs
        cur.execute("SELECT COUNT(*) AS n FROM datawarehouse.dim_client")
        clients = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM datawarehouse.dim_compte")
        accounts = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM datawarehouse.dim_compte WHERE statut='Actif'")
        active = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM datawarehouse.dim_agence")
        branches = cur.fetchone()["n"]
        cur.execute(f"""
            SELECT COUNT(*) AS n, COALESCE(SUM(montant),0)::float AS amt
            FROM datawarehouse.fait_transactions
            WHERE date_transaction >= (CURRENT_DATE - INTERVAL '{p} months')
        """)
        r = cur.fetchone()
        n_tx, vol = r["n"], float(r["amt"] or 0)

        kpis = [
            {"Indicator": "Clients", "Value": clients},
            {"Indicator": "Accounts", "Value": accounts},
            {"Indicator": "Active accounts", "Value": active},
            {"Indicator": "Activity rate (%)", "Value": round(active/accounts*100, 1) if accounts else 0},
            {"Indicator": "Branches", "Value": branches},
            {"Indicator": "Transactions (period)", "Value": n_tx},
            {"Indicator": "Volume (TND)", "Value": round(vol, 2)},
            {"Indicator": "Average transaction (TND)", "Value": round(vol/n_tx, 2) if n_tx else 0},
            {"Indicator": "Period (months)", "Value": months if months else "All"},
            {"Indicator": "Exported on", "Value": datetime.now().strftime("%Y-%m-%d %H:%M")},
        ]

        cur.execute(f"""
            SELECT TO_CHAR(date_transaction,'YYYY-MM') AS period,
                   COUNT(*) AS transactions,
                   ROUND(COALESCE(SUM(montant),0)::numeric,2) AS amount
            FROM datawarehouse.fait_transactions
            WHERE date_transaction >= (CURRENT_DATE - INTERVAL '{p} months')
            GROUP BY 1 ORDER BY 1
        """)
        evolution = [dict(x) for x in cur.fetchall()]

        cur.execute("""
            SELECT type_operation AS operation, COUNT(*) AS transactions,
                   ROUND(COALESCE(SUM(montant),0)::numeric,2) AS amount
            FROM datawarehouse.fait_transactions
            GROUP BY 1 ORDER BY 2 DESC
        """)
        by_type = [dict(x) for x in cur.fetchall()]

        cur.execute("""
            SELECT type_compte AS account_type, COUNT(*) AS accounts
            FROM datawarehouse.dim_compte GROUP BY 1 ORDER BY 2 DESC
        """)
        acc_types = [dict(x) for x in cur.fetchall()]

        cur.execute("""
            SELECT ville AS city, COUNT(*) AS clients
            FROM datawarehouse.dim_client GROUP BY 1 ORDER BY 2 DESC
        """)
        by_city = [dict(x) for x in cur.fetchall()]

        cur.execute("""
            SELECT c.id_compte AS account, cl.nom_complet AS client, cl.ville AS city,
                   c.type_compte AS type, c.statut AS status,
                   COUNT(t.id_transaction) AS transactions,
                   ROUND(COALESCE(SUM(t.montant),0)::numeric,2) AS total
            FROM datawarehouse.fait_transactions t
            JOIN datawarehouse.dim_compte c ON t.sk_compte = c.sk_compte
            LEFT JOIN datawarehouse.dim_client cl ON c.id_client = cl.id_client
            GROUP BY 1,2,3,4,5 ORDER BY total DESC LIMIT 25
        """)
        top_accounts = [dict(x) for x in cur.fetchall()]

        cur.close(); conn.close()

        return _excel_response({
            "KPIs": kpis,
            "Monthly evolution": evolution,
            "By operation type": by_type,
            "Account types": acc_types,
            "Clients by city": by_city,
            "Top accounts": top_accounts,
        }, f"dashboard_{_stamp()}.xlsx")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/export/forecast/{metric}")
def export_forecast(metric: str, horizon: int = 6, method: str = "auto",
                    current_user: dict = Depends(get_current_user)):
    """Download a forecast (history, projection, method comparison) as Excel."""
    try:
        horizon = max(1, min(24, horizon))
        result = forecasting.forecast(metric, horizon=horizon, method=method)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        summary = [
            {"Field": "Series", "Value": result["label"]},
            {"Field": "Unit", "Value": result["unit"]},
            {"Field": "Selected method", "Value": result["selected_label"]},
            {"Field": "Automatically selected", "Value": "Yes" if result["auto_selected"] else "No"},
            {"Field": "Months of history", "Value": result["months_available"]},
            {"Field": "Training size", "Value": result["train_size"]},
            {"Field": "Test size", "Value": result["test_size"]},
            {"Field": "Horizon (months)", "Value": result["horizon"]},
            {"Field": "Exported on", "Value": datetime.now().strftime("%Y-%m-%d %H:%M")},
        ]

        history = [{"Period": h["period"], "Actual": h["value"]} for h in result["history"]]
        forecast_rows = [{"Period": f["period"], "Forecast": f["value"],
                          "Lower bound": f["lower"], "Upper bound": f["upper"]}
                         for f in result["forecast"]]
        comparison = [{"Method": c["label"], "Models": c["models"],
                       "MAE": c["MAE"], "RMSE": c["RMSE"],
                       "MAPE (%)": c["MAPE"], "R2": c["R2"],
                       "Selected": "Yes" if c["method"] == result["selected_method"] else ""}
                      for c in result["comparison"]]
        backtest = [{"Period": b["period"], "Actual": b["actual"],
                     "Predicted": b["predicted"],
                     "Error": round(b["actual"] - b["predicted"], 2)}
                    for b in result["backtest"]]

        return _excel_response({
            "Summary": summary,
            "History": history,
            "Forecast": forecast_rows,
            "Method comparison": comparison,
            "Backtest": backtest,
        }, f"forecast_{metric}_{_stamp()}.xlsx")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))