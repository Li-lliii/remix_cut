from platform_app.modules.digital_humans.api import router as digital_humans_router
from platform_app.api.final_videos import router as final_videos_router
from platform_app.api.lip_sync import router as lip_sync_router
from platform_app.api.product_docs import router as product_docs_router
from platform_app.api.remix import router as remix_router
from platform_app.api.roles import router as roles_router
from platform_app.api.smart_clips import router as smart_clip_router
from platform_app.api.videos import router as videos_router


def get_api_routers():
    return [
        roles_router,
        product_docs_router,
        digital_humans_router,
        videos_router,
        remix_router,
        smart_clip_router,
        lip_sync_router,
        final_videos_router,
    ]
