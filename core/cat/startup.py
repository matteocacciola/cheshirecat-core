from contextlib import asynccontextmanager
from scalar_fastapi import get_scalar_api_reference
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from cat.db.database import get_db
from cat.env import get_env
from cat.exceptions import (
    LoadMemoryException,
    CustomValidationException,
    CustomNotFoundException,
    CustomForbiddenException
)
from cat.log import log
from cat.routes import (
    admins_router as admins,
    auth,
    auth_handler,
    base,
    embedder,
    file_manager,
    llm,
    chunker,
    memory_router as memory,
    plugins,
    rabbit_hole,
    settings,
    static,
    users,
    vector_database,
    websocket,
)
from cat.routes.openapi import get_openapi_configuration_function
from cat.routes.routes_utils import startup_app, shutdown_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    #       ^._.^
    #
    # loads Manager and plugins
    # Every endpoint can access the manager instance via request.app.state.lizard
    # - Not using middleware because I can't make it work with both http and websocket;
    # - Not using "Depends" because it only supports callables (not instances)
    # - Starlette allows this: https://www.starlette.io/applications/#storing-state-on-the-app-instance

    await startup_app(app)

    # startup message with admin, public and swagger addresses
    log.welcome()

    yield

    await shutdown_app(app)

    get_db().close()


def custom_generate_unique_id(route: APIRoute):
    return f"{route.name}"


# REST API
cheshire_cat_api = FastAPI(
    lifespan=lifespan,
    generate_unique_id_function=custom_generate_unique_id,
    docs_url=None,
    redoc_url=None,
    title="Cheshire-Cat API",
    license_info={"name": "GPL-3", "url": "https://www.gnu.org/licenses/gpl-3.0.en.html"},
)

# Configures the CORS middleware for the FastAPI app
cors_enabled = get_env("CCAT_CORS_ENABLED")
if cors_enabled == "true":
    cors_allowed_origins_str = get_env("CCAT_CORS_ALLOWED_ORIGINS")
    origins = cors_allowed_origins_str.split(",") if cors_allowed_origins_str else ["*"]
    cheshire_cat_api.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Add routers to the middleware stack.
cheshire_cat_api.include_router(base.router)
cheshire_cat_api.include_router(admins.router, prefix="/admins")
cheshire_cat_api.include_router(auth_handler.router, tags=["AuthHandler"], prefix="/auth_handler")
cheshire_cat_api.include_router(embedder.router, tags=["Embedder"], prefix="/embedder")
cheshire_cat_api.include_router(chunker.router, tags=["Chunking"], prefix="/chunking")
cheshire_cat_api.include_router(file_manager.router, tags=["File Manager"], prefix="/file_manager")
cheshire_cat_api.include_router(llm.router, tags=["Large Language Model"], prefix="/llm")
cheshire_cat_api.include_router(memory.router, prefix="/memory")
cheshire_cat_api.include_router(plugins.router, tags=["Plugins"], prefix="/plugins")
cheshire_cat_api.include_router(rabbit_hole.router, tags=["Rabbit Hole"], prefix="/rabbithole")
cheshire_cat_api.include_router(settings.router, tags=["Settings"], prefix="/settings")
cheshire_cat_api.include_router(auth.router, tags=["User Auth"], prefix="/auth")
cheshire_cat_api.include_router(users.router, tags=["Users"], prefix="/users")
cheshire_cat_api.include_router(vector_database.router, tags=["Vector Database"], prefix="/vector_database")
cheshire_cat_api.include_router(websocket.router, tags=["Websocket"])

# mount static files
# this cannot be done via fastapi.APIRouter:
# https://github.com/tiangolo/fastapi/discussions/9070

# static files (for plugins and other purposes)
static.mount(cheshire_cat_api)


@cheshire_cat_api.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    log.error(f"An unexpected error occurred: {exc}")
    return JSONResponse(status_code=500, content={"detail": {"error": str(exc)}})


@cheshire_cat_api.exception_handler(ValueError)
async def value_error_exception_handler(request, exc):
    log.error(f"An unexpected value error occurred: {exc}")
    return JSONResponse(status_code=500, content={"detail": {"error": str(exc)}})


@cheshire_cat_api.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    # Convert error objects to JSON-serializable format
    serializable_errors = []
    for error in exc.errors():
        serializable_error = {
            "loc": error.get("loc", []),
            "msg": str(error.get("msg", "")),
            "type": str(error.get("type", ""))
        }
        # Add context if it exists and is serializable
        if "ctx" in error:
            try:
                serializable_error["ctx"] = error["ctx"]
            except (TypeError, ValueError):
                # If ctx is not serializable, convert to string
                serializable_error["ctx"] = str(error["ctx"])

        serializable_errors.append(serializable_error)

    return JSONResponse(
        status_code=400,
        content={"detail": {"errors": serializable_errors}}
    )


@cheshire_cat_api.exception_handler(LoadMemoryException)
async def load_memory_exception_handler(request, exc):
    log.error(exc)
    return JSONResponse(status_code=500, content={"detail": {"error": str(exc)}})


@cheshire_cat_api.exception_handler(CustomValidationException)
async def custom_validation_exception_handler(request, exc):
    log.error(exc)
    return JSONResponse(status_code=400, content={"detail": {"error": str(exc)}})


@cheshire_cat_api.exception_handler(CustomNotFoundException)
async def custom_not_found_exception_handler(request, exc):
    log.error(exc)
    return JSONResponse(status_code=404, content={"detail": {"error": str(exc)}})


@cheshire_cat_api.exception_handler(CustomForbiddenException)
async def custom_forbidden_exception_handler(request, exc):
    log.error(exc)
    return JSONResponse(status_code=403, content={"detail": {"error": str(exc)}})


# openapi customization
cheshire_cat_api.openapi = get_openapi_configuration_function(cheshire_cat_api)

if get_env("CCAT_DEBUG") == "true":
    @cheshire_cat_api.get("/docs", include_in_schema=False)
    async def scalar_docs():
        return get_scalar_api_reference(
            openapi_url=cheshire_cat_api.openapi_url,
            title=cheshire_cat_api.title,
            scalar_favicon_url="https://cheshirecat.ai/wp-content/uploads/2023/10/Logo-Cheshire-Cat.svg",
        )
