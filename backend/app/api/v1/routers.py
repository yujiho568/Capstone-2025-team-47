from fastapi import APIRouter
from app.api.v1.endpoints import user, credentials, results,ueba_results


api_router = APIRouter()
api_router.include_router(user.router)
api_router.include_router(credentials.router)
api_router.include_router(ueba_results.router)    # /ueba-results/{user_id}
api_router.include_router(results.router)     # /results/{user_id}/import-s3