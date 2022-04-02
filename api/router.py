from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from urllib3.exceptions import MaxRetryError, LocationValueError

import api.main
from api.inspection.technology.response import APIResponse
from api.inspection.inspection import Inspection, InvalidWebsiteException
from api.database import SessionLocal
from api.models import RequestCacheService
from api.schemas import inspectionSchema, invalidRequestSchema

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=invalidRequestSchema)
async def root():
    return {
        "success": False,
        "message": "No URL specified"
    }

@router.get("/inspect/{site_url:path}", tags=["inspection"], response_model=inspectionSchema, responses={400: {"model": invalidRequestSchema}})
async def inspect_site(site_url: str, response: Response, db: SessionLocal = Depends(get_db)) -> dict:
    """The specified URL will be in-turn called by the system. The system will then perform various inspections on the
    response data and the connection to calculate what technology the website is running. In certain conditions, if the
    site is detected to be using a known REST API, useful data will also be harvested from their endpoint.

    This is request-intensive, and results in a slow repsonse currently. To counter this, a caching engine is used to
    serve repeat requests with the same data.

    Args:
        site_url (str): A URL-encoded string to a website to inspect.

    Returns:
        dict: Returns an API object.
    """
    reply     = APIResponse()
    reply.url = site_url

    try:
        inspector        = Inspection(reply.url, RequestCacheService(db), api.main.config)
        reply.success    = True
        reply.inspection = inspector.get_site_details().asdict()
    except InvalidWebsiteException as e:
        reply.success = False
        reply.message = str(e)
    except MaxRetryError as e:
        reply.success = False
        reply.message = 'Invalid URL or permission denied'
    except LocationValueError as e:
        reply.success = False
        reply.message = 'No URL specified'

    if reply.success == True:
        return reply.asdict()
    else:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=reply.asdict())
