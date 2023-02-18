"""Main API handler.
"""

import re
import json
from os import getenv
from urllib.parse import unquote
import urllib3
import yaml
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from urllib3.exceptions import MaxRetryError, LocationValueError
from dns.rdatatype import UnknownRdatatype
from dns.resolver import NXDOMAIN

from api import main
from api.inspection.technology.response import APIResponse
from api.inspection.inspection import Inspection, InvalidWebsiteException
from api.dns.dnslookup import DNSLookup
from api.dns.whois import WhoisLookup, WhoisResult
from api.schemas import InspectionSchema, DNSProbeAllSchema, WhoisSchema, InvalidRequestSchema

router = APIRouter()

@router.get("/inspect/{site_url:path}", tags=["Inspection"], response_model=InspectionSchema,
responses={400: {"model": InvalidRequestSchema}})
async def inspect_site(site_url: str) -> dict:
	"""The specified URL will be in-turn called by the system. The system will then perform various inspections on the
	response data and the connection to calculate what technology the website is running. In certain conditions, if the
	site is detected to be using a known REST API, useful data will also be harvested from their endpoint.

	This is request-intensive, and results in a slow repsonse currently. To counter this, a caching engine is used to
	serve repeat requests with the same data.
	"""

	# Check for inspection instructions, and reloads them if they've expired.
	def_def_url = 'https://gist.githubusercontent.com/soup-bowl/ca302eb775278a581cd4e7e2ea4122a1/raw/definitions.yml'
	defs = None
	has_defs = await main.app.state.rcache.get_value('InspectionDefs')
	if has_defs is None:
		def_url = getenv('WTAPI_DEFINITION_URL', def_def_url)
		def_file = urllib3.PoolManager().request('GET', def_url)
		if def_file.status == 200:
			print("Loaded latest definition file from GitHub.")
			resp = def_file.data.decode('utf-8')
			defs = yaml.safe_load(resp)
			await main.app.state.rcache.set_value('InspectionDefs', resp, 2629800)
		else:
			print("Unable to download definitions file.")
	else:
		defs = yaml.safe_load(has_defs)

	site_url = unquote(site_url)

	# Check for an existing cached version and return that.
	cache_contents = await main.app.state.rcache.get_value(f"InspectionCache-{site_url}".lower())
	if cache_contents is not None:
		return json.loads(cache_contents)

	reply = APIResponse()
	reply.url = site_url if bool(re.search('^https?://.*', site_url)) else 'https://' + site_url

	try:
		inspector = Inspection(url=reply.url, config=defs)
		reply.success = True
		reply.inspection = inspector.get_site_details().asdict()
	except InvalidWebsiteException as error:
		reply.success = False
		reply.message = str(error)
	except MaxRetryError:
		reply.success = False
		reply.message = 'Invalid URL or permission denied'
	except LocationValueError:
		reply.success = False
		reply.message = 'No URL specified'

	if reply.success is True:
		cache_contents = await main.app.state.rcache.set_value(
			f"InspectionCache-{site_url}".lower(),
			json.dumps(reply.asdict()),
			86400
		)

		return reply.asdict()

	return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=reply.asdict())

@router.get("/dns/{site_url:path}", tags=["DNS"], response_model=DNSProbeAllSchema,
responses={400: {"model": InvalidRequestSchema}})
async def dns_lookup(site_url: str):
	"""This endpoint checks all the common DNS endpoints for records against the input URL.
	"""

	cache_contents = await main.app.state.rcache.get_value(f"DnsCache-{site_url}".lower())
	if cache_contents is not None:
		return json.loads(cache_contents)

	probe = DNSLookup().probe_all(site_url)
	
	if probe['success'] is False:
		return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={
			"success": False, "message": probe['message']
		})
	
	cache_contents = await main.app.state.rcache.set_value(
		f"DnsCache-{site_url}".lower(),
		json.dumps(probe),
		1800
	)

	return probe

@router.get("/whois/{site_url:path}", tags=["DNS"], response_model=WhoisSchema,
responses={400: {"model": InvalidRequestSchema}})
async def whois_lookup(site_url: str) -> dict:
	"""Performs a WHOIS lookup on the URL specified. This helps to ascertain ownership information at a high level.

	For more info, see: https://en.wikipedia.org/wiki/WHOIS

	This does not aim to provide full WHOIS information. This is due to the rise of WHOIS information protection, the
	contact-level information is no longer useful. Instead this provides info such as registration and expiration dates,
	and registrar used.
	"""

	# Check for an existing cached version and return that.
	cache_contents = await main.app.state.rcache.get_value(f"WhoisCache-{site_url}".lower())
	if cache_contents is not None:
		return json.loads(cache_contents)

	lookup_result = WhoisLookup().lookup(site_url)
	if isinstance(lookup_result, WhoisResult):
		response = lookup_result.asdict()
		response['success'] = True

		cache_contents = await main.app.state.rcache.set_value(
			f"WhoisCache-{site_url}".lower(),
			json.dumps(response),
			86400
		)

		return response

	return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={
		'success': False,
		'message': lookup_result
	})
