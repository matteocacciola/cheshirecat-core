from cat import hook, log, run_sync_or_async, BillTheLizard, CatProcedureType
from cat.core_plugins.white_rabbit.white_rabbit import WhiteRabbit
import cat.db.cruds.settings as crud_settings


scheduled_job_id = "re_embed_mcp_tools"


# IMPORTANT: This function MUST live at a module level (not inside another function) so that APScheduler + Redis can
# pickle/serialize it by its fully qualified import path.
# All runtime context is passed explicitly via kwargs.
def re_embed_mcp_tools():
    """Re-embed MCP tools for all CheshireCat instances"""
    lizard = BillTheLizard()

    lock_acquired = lizard.white_rabbit.acquire_lock(scheduled_job_id)
    if not lock_acquired:
        return
    try:
        ccat_ids = crud_settings.get_agents_main_keys()
        # Track errors to ensure we don't leave things hanging
        for ccat_id in ccat_ids:
            if (ccat := lizard.get_cheshire_cat(ccat_id)) is None:
                continue
            try:
                run_sync_or_async(ccat.embed_procedures, pt=CatProcedureType.MCP)
                del ccat
            except Exception as e:
                log.error(f"WhiteRabbit: Failed re-embedding for Cat {ccat_id}: {e}")
    finally:
        # release the lock immediately
        lizard.white_rabbit.release_lock(scheduled_job_id)


@hook
def after_lizard_bootstrap(lizard: BillTheLizard):
    # Start scheduling system and attach it to the BillTheLizard core class
    lizard.white_rabbit = WhiteRabbit()

    try:
        settings = lizard.plugin_manager.get_plugin().load_settings()
        interval_job_days = int(settings["embed_procedures_every_n_days"])
    except (ValueError, KeyError):
        interval_job_days = None

    if not interval_job_days:
        return

    lizard.white_rabbit.schedule_interval_job(
        job=re_embed_mcp_tools,
        job_id=scheduled_job_id,
        days=interval_job_days,
        scheduled_job_id=scheduled_job_id,
    )


@hook(priority=0)
def before_lizard_shutdown(lizard) -> None:
    lizard.white_rabbit.shutdown()
    lizard.white_rabbit = None
