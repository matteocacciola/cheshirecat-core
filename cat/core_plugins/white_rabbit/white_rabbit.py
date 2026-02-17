from datetime import datetime, timedelta
from typing import List
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_SUBMITTED
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from pydantic import BaseModel, Field
from pytz import utc

from cat import log, utils
from cat.db.database import get_db
from cat.utils import singleton


class JobStatus(utils.Enum):
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    REMOVED = "removed"


class Job(BaseModel):
    id: str
    name: str
    next_run: datetime | None = None
    status: JobStatus = Field(default=JobStatus.SCHEDULED)


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

        self._client_db = get_db()
        self._prefix_lock_key = "white_rabbit:lock"
        self._prefix_status_key = "white_rabbit:status"

        # Use Redis as job store for persistence across restarts
        jobstores = {
            "default": RedisJobStore(
                jobs_key="white_rabbit:jobs", run_times_key="white_rabbit:run_times", redis_client=self._client_db
            )
        }

        executors = {
            "default": ThreadPoolExecutor(20),
            "processpool": ProcessPoolExecutor(5),
        }

        job_defaults = {"coalesce": False, "max_instances": 10}

        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=utc,
        )

        # Listen to submission, execution and error events to track status accurately
        self.scheduler.add_listener(self._job_submitted_listener, EVENT_JOB_SUBMITTED)
        self.scheduler.add_listener(self._job_ended_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

        self.jobs: List[str] = []

        log.debug("WhiteRabbit: Starting scheduler")

        try:
            self.scheduler.start()
            log.debug("WhiteRabbit: Scheduler started")
            self._is_running = True
        except Exception as e:
            log.error("WhiteRabbit: Error during scheduler start: ", e)
            self._is_running = False

    def __del__(self):
        self.shutdown()

    def _status_key(self, job_id: str) -> str:
        return f"{self._prefix_status_key}:{job_id}"

    def _set_job_status(self, job_id: str, status: JobStatus):
        if status in [JobStatus.COMPLETED, JobStatus.REMOVED]:
            # No need to retain completed or removed status; clean up
            self._client_db.delete(self._status_key(job_id))
        else:
            self._client_db.set(self._status_key(job_id), str(status))

    def _get_job_status(self, job_id: str) -> JobStatus:
        raw = self._client_db.get(self._status_key(job_id))
        if raw is None:
            return JobStatus.SCHEDULED  # Default for jobs with no explicit status set yet
        return JobStatus(raw.decode() if isinstance(raw, bytes) else raw)

    def _job_submitted_listener(self, event):
        """Triggered when a job is submitted for execution."""
        self._set_job_status(event.job_id, JobStatus.RUNNING)
        log.debug(f"WhiteRabbit: job {event.job_id} is now running.")

    def _job_ended_listener(self, event):
        """Triggered when a job ends (success or error)."""
        if event.exception:
            log.error(
                f"WhiteRabbit: error during the execution of job {event.job_id} "
                f"started at {event.scheduled_run_time}. Error: {event.traceback}"
            )
        else:
            log.info(
                f"WhiteRabbit: executed job {event.job_id} started at {event.scheduled_run_time}. "
                f"Value returned: {event.retval}"
            )

        self._set_job_status(event.job_id, JobStatus.COMPLETED)

        # Remove one-shot jobs from our tracking list after completion
        if event.job_id in self.jobs:
            job = self.scheduler.get_job(event.job_id)
            if job is None:
                self.jobs.remove(event.job_id)

    def acquire_lock(self, event: str) -> bool:
        lock_key = f"{self._prefix_lock_key}:{event}"
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

    def shutdown(self):
        for job_id in self.jobs.copy():
            self.remove_job(job_id)

        if self._is_running:
            log.info("WhiteRabbit: Scheduler stopped")
            self.scheduler.shutdown(wait=True)
            self._is_running = False

    def get_job(self, job_id: str) -> Job | None:
        """
        Gets a scheduled job.

        Args:
            job_id (str): The id assigned to the job.

        Returns:
            Job | None: A Job object if the job exists, otherwise None.
        """
        job = self.scheduler.get_job(job_id)
        if not job:
            return None

        return Job(
            id=job.id,
            name=job.name,
            next_run=job.next_run_time,
            status=self._get_job_status(job.id),
        )

    def get_jobs(self) -> List[Job]:
        """
        Returns a list of scheduled jobs.

        Returns:
            List[Job]: A list of Job objects.
        """
        return [
            Job(
                id=job.id,
                name=job.name,
                next_run=job.next_run_time,
                status=self._get_job_status(job.id),
            )
            for job in self.scheduler.get_jobs()
        ]

    def pause_job(self, job_id: str) -> bool:
        """
        Pauses a scheduled job.

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
        Resumes a paused job.

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
        Removes a scheduled job.

        Args:
            job_id (str): The id assigned to the job.

        Returns:
            bool: The outcome of the removal.
        """
        try:
            self.scheduler.remove_job(job_id)
            self.jobs.remove(job_id)
            self._set_job_status(job_id, JobStatus.REMOVED)
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
        Schedule a one-shot job.

        Args:
            job (function): The function to be called.
            job_id (str): The id assigned to the job.
            days (int): Days to wait.
            hours (int): Hours to wait.
            minutes (int): Minutes to wait.
            seconds (int): Seconds to wait.
            milliseconds (int): Milliseconds to wait.
            microseconds (int): Microseconds to wait.
            **kwargs: The arguments to pass to the function.

        Returns:
            The job id.
        """
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
        Schedule an interval job.

        Args:
            job (function): The function to be called.
            job_id (str): The id assigned to the job.
            start_date (datetime): Start date. If None the job starts instantaneously.
            end_date (datetime): End date. If None the job never ends.
            days (int): Days interval.
            hours (int): Hours interval.
            minutes (int): Minutes interval.
            seconds (int): Seconds interval.
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
        Schedule a cron job.

        Args:
            job (function): The function to be called.
            job_id (str): The id assigned to the job.
            start_date (datetime): Start date. If None the job starts instantaneously.
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
        Schedule a chat message.

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
