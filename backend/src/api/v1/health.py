from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def health_check() -> dict[str, str]:
    """Return API health status.

    Returns:
        A simple health payload for liveness checks.
    """
    return {"status": "ok"}
