from cat import hook, log, run_sync_or_async, CatProcedureType
from cat.core_plugins.white_rabbit.white_rabbit import WhiteRabbit
from cat.db import crud


@hook
def before_lizard_bootstrap(lizard):
    # Start scheduling system and attach it to the BillTheLizard core class
    lizard.white_rabbit = WhiteRabbit()

    try:
        settings = lizard.plugin_manager.get_plugin().load_settings()
        interval_job_days = int(settings["embed_procedures_every_n_days"])
    except ValueError:
        interval_job_days = None

    if not interval_job_days:
        return

    # Schedule MCP tools re-embedding every 7 days
    def re_embed_mcp_tools():
        """Re-embed MCP tools for all CheshireCat instances"""
        ccat_ids = crud.get_agents_main_keys()
        try:
            for ccat_id in ccat_ids:
                if (ccat := lizard.get_cheshire_cat(ccat_id)) is None:
                    continue

                run_sync_or_async(ccat.embed_procedures, pt=CatProcedureType.MCP)
            log.info("WhiteRabbit: Successfully re-embedded MCP tools for all cats")
        except Exception as e:
            log.error(f"WhiteRabbit: Error re-embedding MCP tools: {e}")

    lizard.white_rabbit.schedule_interval_job(
        job=re_embed_mcp_tools,
        job_id="re_embed_mcp_tools",
        days=interval_job_days,
    )


@hook(priority=0)
def before_lizard_shutdown(lizard) -> None:
    if hasattr(lizard, "white_rabbit"):
        lizard.white_rabbit.shutdown()
        lizard.white_rabbit = None
