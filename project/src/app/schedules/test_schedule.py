from dagster import schedule, RunRequest, ScheduleEvaluationContext
from app.jobs import test_job

@schedule(job=test_job.test_operacion, cron_schedule="*/2 * * * *") # every hour
def test_sch_operacion(context: ScheduleEvaluationContext):
    return RunRequest(
        run_key=None,
        run_config=None
    )
