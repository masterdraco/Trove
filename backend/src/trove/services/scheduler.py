from __future__ import annotations

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlmodel import Session, select

from trove.db import get_engine
from trove.models.feed import FeedRow
from trove.models.task import TaskRow
from trove.services import feed_poller, task_engine

log = structlog.get_logger()

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


async def _execute_task(task_id: int) -> None:
    with Session(get_engine()) as session:
        task = session.get(TaskRow, task_id)
        if task is None or not task.enabled:
            return
        log.info("scheduler.running", task=task.name)
        await task_engine.run_task(session, task, dry_run=False)


def schedule_task(task: TaskRow) -> None:
    sched = get_scheduler()
    if task.id is None:
        return
    job_id = f"task:{task.id}"
    sched.remove_job(job_id) if sched.get_job(job_id) else None
    if not task.enabled or not task.schedule_cron:
        return
    try:
        trigger = CronTrigger.from_crontab(task.schedule_cron, timezone="UTC")
    except ValueError as e:
        log.warning("scheduler.bad_cron", task=task.name, cron=task.schedule_cron, error=str(e))
        return
    sched.add_job(_execute_task, trigger=trigger, args=[task.id], id=job_id, replace_existing=True)
    log.info("scheduler.scheduled", task=task.name, cron=task.schedule_cron)


def unschedule_task(task_id: int) -> None:
    sched = get_scheduler()
    job_id = f"task:{task_id}"
    if sched.get_job(job_id):
        sched.remove_job(job_id)


async def _execute_feed(feed_id: int) -> None:
    with Session(get_engine()) as session:
        feed = session.get(FeedRow, feed_id)
        if feed is None or not feed.enabled:
            return
        log.info("scheduler.polling_feed", name=feed.name)
        await feed_poller.poll_feed(session, feed)


def schedule_feed(feed: FeedRow) -> None:
    sched = get_scheduler()
    if feed.id is None:
        return
    job_id = f"feed:{feed.id}"
    if sched.get_job(job_id):
        sched.remove_job(job_id)
    if not feed.enabled:
        return
    interval = max(60, int(feed.poll_interval_seconds or 600))
    sched.add_job(
        _execute_feed,
        trigger=IntervalTrigger(seconds=interval),
        args=[feed.id],
        id=job_id,
        replace_existing=True,
        next_run_time=None,  # wait for first interval
    )
    log.info("scheduler.feed_scheduled", name=feed.name, interval_s=interval)


def unschedule_feed(feed_id: int) -> None:
    sched = get_scheduler()
    job_id = f"feed:{feed_id}"
    if sched.get_job(job_id):
        sched.remove_job(job_id)


def load_all_tasks() -> None:
    with Session(get_engine()) as session:
        rows = session.exec(select(TaskRow)).all()
        for task in rows:
            schedule_task(task)


def load_all_feeds() -> None:
    with Session(get_engine()) as session:
        rows = session.exec(select(FeedRow)).all()
        for feed in rows:
            schedule_feed(feed)


def start_scheduler() -> None:
    sched = get_scheduler()
    if not sched.running:
        sched.start()
    load_all_tasks()
    load_all_feeds()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
