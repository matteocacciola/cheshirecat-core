from datetime import datetime, timedelta
from typing import Dict, List
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from pydantic import BaseModel
from pytz import utc

from cat import log
from cat.db.database import get_db
from cat.utils import singleton


class Job(BaseModel):
    id: str
    name: str
    next_run: int | float


@singleton
class WhiteRabbit:
    """
    The WhiteRabbit

    Here the cron magic happens. This class is responsible for scheduling and executing jobs. It uses APScheduler under
    the hood, but we can easily swap it for another library if needed. The main idea is to have a centralized place to
    manage all the scheduled tasks in the system, from sending a message to re-embedding MCP tools periodically.
    """
    def __init__(self):
        log.debug("Initializing WhiteRabbit...")

        # Where the jobs are stored. We can also use an external db to have persistence
        jobstores = {"default": MemoryJobStore()}

        # Define execution pools
        executors = {
            "default": ThreadPoolExecutor(20),
            "processpool": ProcessPoolExecutor(5),
        }

        # Define basic rules for jobs
        job_defaults = {"coalesce": False, "max_instances": 10}

        # Creating the effective scheduler
        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=utc,
        )

        self._client_db = get_db()
        self._prefix_lock_key = "white_rabbit:lock"

        # Add our listener to the scheduler
        self.scheduler.add_listener(
            self._job_ended_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR
        )

        self.jobs: List[str] = []

        log.debug("WhiteRabbit: Starting scheduler")

        # Start the scheduler
        try:
            self.scheduler.start()
            log.debug("WhiteRabbit: Scheduler started")
            self._is_running = True
        except Exception as e:
            log.error("WhiteRabbit: Error during scheduler start: ", e)
            self._is_running = False

    def __del__(self):
        self.shutdown()

    def acquire_lock(self, event: str) -> bool:
        lock_key = f"{self._prefix_lock_key}:{event}"
        # for security reasons, the lock automatically expires after 1 hour
        # nx=True guarantees that only the first node that acquires the lock will proceed
        lock_acquired = self._client_db.set(lock_key, "locked", nx=True, ex=3600)

        debug_message = (
            f"WhiteRabbit: Lock acquired. Starting '{event}' event..."
            if lock_acquired
            else f"WhiteRabbit: Job '{event}' already in execution or handled by another node."
        )
        log.debug(debug_message)

        return lock_acquired

    def release_lock(self, event: str):
        lock_key = f"{self._prefix_lock_key}:{event}"
        self._client_db.delete(lock_key)
        log.debug(f"WhiteRabbit: Lock released for '{event}' event.")

    def _job_ended_listener(self, event):
        """
        Triggered when a job ends

        Args:
            event (apscheduler.events.JobExecutionEvent): Passed by the scheduler when the job ends. It contains information about the job.
        """
        if event.exception:
            log.error(
                f"WhiteRabbit: error during the execution of job {event.job_id} started at {event.scheduled_run_time}. Error: {event.traceback}"
            )
            return

        log.info(
            f"WhiteRabbit: executed job {event.job_id} started at {event.scheduled_run_time}. Value returned: {event.retval}"
        )

    def shutdown(self):
        for job_id in self.jobs.copy():
            self.remove_job(job_id)

        if self._is_running:
            log.info("WhiteRabbit: Scheduler stopped")
            self.scheduler.shutdown(wait=True)
            self._is_running = False

    def get_job(self, job_id: str) -> Job | None:
        """
        Gets a scheduled job

        Args:
            job_id (str): The id assigned to the job.

        Returns:
            Job | None: A Job object with id, name and next_run if the job exists, otherwise None.
        """
        job = self.scheduler.get_job(job_id)
        return Job(id=job.id, name=job.name, next_run=job.next_run_time) if job else None

    def get_jobs(self) -> List[Dict[str, str]]:
        """
        Returns a list of scheduled jobs

        Returns:
            List[Dict[str, str]]
                A list of jobs. Each job is a dictionary with id, name and next_run.
        """
        jobs = self.scheduler.get_jobs()

        return [
            {"id": job.id, "name": job.name, "next_run": job.next_run_time}
            for job in jobs
        ]

    def pause_job(self, job_id: str) -> bool:
        """
        Pauses a scheduled job

        Args:
            job_id (str): The id assigned to the job.

        Returns:
            bool: The outcome of the pause action.
        """
        try:
            self.scheduler.pause_job(job_id)
            log.info(f"WhiteRabbit: paused job {job_id}")
            return True
        except Exception as e:
            log.error(f"WhiteRabbit: error during job pause. {e}")
            return False

    def resume_job(self, job_id: str) -> bool:
        """
        Resumes a paused job

        Args:
            job_id (str): The id assigned to the job.

        Returns:
            bool: The outcome of the resume action.
        """
        try:
            self.scheduler.resume_job(job_id)
            log.info(f"WhiteRabbit: resumed job {job_id}")
            return True
        except Exception as e:
            log.error(f"WhiteRabbit: error during job resume. {e}")
            return False

    def remove_job(self, job_id: str) -> bool:
        """
        Removes a scheduled job

        Args:
            job_id (str): The id assigned to the job.

        Returns:
            bool: the outcome of the removal.
        """
        try:
            self.scheduler.remove_job(job_id)
            self.jobs.remove(job_id)
            log.info(f"WhiteRabbit: Removed job {job_id}")
            return True
        except Exception as e:
            log.error(f"WhiteRabbit: error during job removal. {e}")
            return False

    def schedule_job(
        self,
        job,
        job_id: str = None,
        days=0,
        hours=0,
        minutes=0,
        seconds=0,
        milliseconds=0,
        microseconds=0,
        **kwargs,
    ) -> str:
        """
        Schedule a job

        Args:
            job (function): The function to be called.
            job_id (str): The id assigned to the job.
            days (int): Days to wait.
            hours (int): Hours to wait.
            minutes (int): Minutes to wait.
            seconds (int): Seconds to wait.
            milliseconds (int): Milliseconds to wait.
            microseconds (int) Microseconds to wait.
            **kwargs: The arguments to pass to the function.

        Returns:
            The job id.
        """
        # Calculate time
        schedule = datetime.today() + timedelta(
            days=days,
            hours=hours,
            minutes=minutes,
            seconds=seconds,
            milliseconds=milliseconds,
            microseconds=microseconds,
        )

        # Check that the function is callable
        if not callable(job):
            log.error("WhiteRabbit: The job should be callable!")
            raise TypeError(f"TypeError: '{type(job)}' object is not callable")

        # Generate id if none
        if job_id is None:
            job_id = f"{job.__name__}-{schedule.strftime('%m/%d/%Y-%H:%M:%S')}"

        # Schedule the job
        self.scheduler.add_job(job, "date", id=job_id, run_date=schedule, kwargs=kwargs)
        self.jobs.append(job_id)

        return job_id

    def schedule_interval_job(
        self,
        job,
        job_id: str = None,
        start_date: datetime = None,
        end_date: datetime = None,
        days=0,
        hours=0,
        minutes=0,
        seconds=0,
        **kwargs,
    ) -> str:
        """
        Schedule an interval job

        Args:
            job (function): The function to be called.
            job_id (str): The id assigned to the job.
            start_date (datetime): Start date. If None the job can start instantaneously
            end_date (datetime): End date. If None the job never ends.
            days (int): Days to wait.
            hours (int): Hours to wait.
            minutes (int): Minutes to wait.
            seconds (int): Seconds to wait.
            **kwargs: The arguments to pass to the function.

        Returns:
            The job id.
        """
        # Check that the function is callable
        if not callable(job):
            log.error("WhiteRabbit: The job should be callable!")
            raise TypeError(f"TypeError: '{type(job)}' object is not callable")

        # Generate id if none
        if job_id is None:
            job_id = f"{job.__name__}-interval-{days}-{hours}-{minutes}-{seconds}"

        # Schedule the job
        self.scheduler.add_job(
            job,
            "interval",
            id=job_id,
            start_date=start_date,
            end_date=end_date,
            days=days,
            hours=hours,
            minutes=minutes,
            seconds=seconds,
            kwargs=kwargs,
        )
        self.jobs.append(job_id)

        return job_id

    def schedule_cron_job(
        self,
        job,
        job_id: str = None,
        start_date: datetime = None,
        end_date: datetime = None,
        year=None,
        month=None,
        day=None,
        week=None,
        day_of_week=None,
        hour=None,
        minute=None,
        second=None,
        **kwargs,
    ) -> str:
        """
        Schedule a cron job

        Args:
            job (function): The function to be called.
            job_id (str): The id assigned to the job.
            start_date (datetime): Start date. If None the job can start instantaneously
            end_date (datetime): End date. If None the job never ends.
            year (int | str): 4-digit year
            month (int | str): month (1-12)
            day (int | str): day of month (1-31)
            week (int | str): ISO week (1-53)
            day_of_week (int | str): number or name of weekday (0-6 or mon,tue,wed,thu,fri,sat,sun)
            hour (int | str): hour (0-23)
            minute (int | str): minute (0-59)
            second (int | str): second (0-59)
            **kwargs: The arguments to pass to the function.

        Returns:
            The job id.
        """
        # Check that the function is callable
        if not callable(job):
            log.error("WhiteRabbit: The job should be callable!")
            raise TypeError(f"TypeError: '{type(job)}' object is not callable")

        # Generate id if none
        if job_id is None:
            job_id = f"{job.__name__}-cron"

        # Schedule the job
        self.scheduler.add_job(
            job,
            "cron",
            id=job_id,
            start_date=start_date,
            end_date=end_date,
            year=year,
            month=month,
            day=day,
            week=week,
            day_of_week=day_of_week,
            hour=hour,
            minute=minute,
            second=second,
            kwargs=kwargs,
        )
        self.jobs.append(job_id)

        return job_id

    def schedule_chat_message(
        self,
        content: str,
        cat,
        days=0,
        hours=0,
        minutes=0,
        seconds=0,
        milliseconds=0,
        microseconds=0,
    ) -> str:
        """
        Schedule a chat message

        Args:
            content (str): The message to be sent.
            cat (StrayCat): Stray Cat instance.
            days (int): Days to wait.
            hours (int): Hours to wait.
            minutes (int): Minutes to wait.
            seconds (int): Seconds to wait.
            milliseconds (int): Milliseconds to wait.
            microseconds (int): Microseconds to wait.

        Returns:
            The job id.
        """
        # Calculate time
        schedule = datetime.today() + timedelta(
            days=days,
            hours=hours,
            minutes=minutes,
            seconds=seconds,
            milliseconds=milliseconds,
            microseconds=microseconds,
        )

        # Generate id
        job_id = f"send_ws_message-{schedule.strftime('%m/%d/%Y-%H:%M:%S')}"

        # Schedule the job
        self.scheduler.add_job(
            cat.notifier.send_ws_message,
            "date",
            id=job_id,
            run_date=schedule,
            kwargs={"content": content, "msg_type": "chat"},
        )
        self.jobs.append(job_id)

        return job_id
