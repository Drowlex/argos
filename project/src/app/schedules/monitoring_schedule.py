from dagster import schedule, RunRequest, ScheduleEvaluationContext
from app.jobs import monitoring_job


@schedule(
    job=monitoring_job.server_monitoring,
    cron_schedule="0 10,17 * * *",
    execution_timezone="America/Mexico_City",
)
def monitoring_daily_schedule(context: ScheduleEvaluationContext):
    """
    Ejecuta el monitoreo automáticamente dos veces al día:
    - 10:00 AM
    - 05:00 PM (17:00)
    Hora Ciudad de México (America/Mexico_City).
    """
    return RunRequest(
        run_key=None,
        run_config=None,
    )
