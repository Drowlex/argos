from app.jobs import test_job, monitoring_job
from app.schedules import test_schedule, monitoring_schedule
from dagster import repository

# @repository
def test():
    __jobs      = [test_job.test_hello, test_job.test_operacion, test_job.test_greetings, test_job.test_calculator]
    __schedules = [test_schedule.test_sch_operacion]
    __sensors   = []
    return __jobs + __schedules + __sensors



@repository
def monitoring():
    __jobs      = [monitoring_job.server_monitoring]
    __schedules = [monitoring_schedule.monitoring_daily_schedule]
    return __jobs + __schedules