from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
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

# Global scheduler instance
scheduler = BackgroundScheduler()

# ─── The actual pipeline job ──────────────────────────────
def execute_pipeline_job(schedule_id, schedule_name, pipeline_id=None):
    """This runs automatically when a schedule triggers."""
    print(f"\n⏰ [{datetime.now().strftime('%H:%M:%S')}] Running scheduled: {schedule_name}")
    try:
        import pipelines
        if pipeline_id:
            result = pipelines.run_saved_pipeline(pipeline_id, source_label="Scheduled")
        else:
            # No specific pipeline → run full ETL
            result = pipelines.execute_pipeline_steps([], source_label=f"Scheduled: {schedule_name}")

        # Update last_run on the schedule
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE datawarehouse.schedules SET last_run = NOW() WHERE id = %s",
            (schedule_id,)
        )
        conn.commit()
        cursor.close()
        conn.close()

        print(f"✅ Scheduled '{schedule_name}' done: {result['records_loaded']} records loaded")
    except Exception as e:
        print(f"❌ Scheduled '{schedule_name}' failed: {e}")

# ─── Register a schedule with APScheduler ─────────────────
def add_schedule_to_scheduler(schedule):
    """Convert a DB schedule row into an APScheduler job."""
    job_id = f"schedule_{schedule['id']}"

    # Remove existing job if it exists
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    if not schedule['is_active']:
        return

    freq = schedule['frequency']
    trigger = None

    if freq == 'hourly':
        trigger = CronTrigger(minute=0)  # every hour at :00
    elif freq == 'daily':
        hour, minute = (schedule['run_time'] or "08:00").split(":")
        trigger = CronTrigger(hour=int(hour), minute=int(minute))
    elif freq == 'weekly':
        hour, minute = (schedule['run_time'] or "08:00").split(":")
        day = (schedule['day_of_week'] or "mon").lower()[:3]
        trigger = CronTrigger(day_of_week=day, hour=int(hour), minute=int(minute))

    if trigger:
        scheduler.add_job(
            execute_pipeline_job,
            trigger=trigger,
            id=job_id,
            args=[schedule['id'], schedule['name'], schedule.get('pipeline_id')],
            replace_existing=True
        )
        print(f"📅 Registered schedule: {schedule['name']} ({freq})")

# ─── Load all active schedules on startup ─────────────────
def load_all_schedules():
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM datawarehouse.schedules WHERE is_active = TRUE")
        schedules = cursor.fetchall()
        cursor.close()
        conn.close()
        for s in schedules:
            add_schedule_to_scheduler(dict(s))
        print(f"📅 Loaded {len(schedules)} active schedule(s)")
    except Exception as e:
        print(f"⚠️ Could not load schedules: {e}")

def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        load_all_schedules()
        print("✅ Scheduler started")

def remove_schedule_from_scheduler(schedule_id):
    job_id = f"schedule_{schedule_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)