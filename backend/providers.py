"""Framework-independent provider failures and safe invocation boundary."""

import logging

from fastapi import HTTPException

from backend.campus import CampusDataError

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """C/D may raise this without importing FastAPI. Messages stay server-side."""

    def __init__(self, code: str, status: int = 503):
        if status not in (400, 501, 503):
            raise ValueError('Provider status must be 400, 501 or 503')
        self.code = code
        self.status = status
        super().__init__(code)


def invoke(operation, *args):
    try:
        return operation(*args)
    except ProviderError as exc:
        # Provider details may include paths/secrets: expose only controlled codes.
        code = {400: 'provider_invalid_parameters', 501: 'provider_not_supported',
                503: 'provider_unavailable'}[exc.status]
        raise HTTPException(exc.status, detail={'code': code}) from exc
    except CampusDataError as exc:
        raise CampusDataError(exc.code, 'Provider source data unavailable or invalid') from exc
    except HTTPException as exc:
        # Keep the fixture adapter's published machine code, never external messages.
        if exc.status_code == 501:
            raise HTTPException(501, detail={'code': 'dispatch_input_not_supported'}) from exc
        status = exc.status_code if exc.status_code in (400, 503) else 500
        raise HTTPException(status, detail={'code': 'provider_error'}) from exc
    except (OSError, TimeoutError) as exc:
        raise HTTPException(503, detail={'code': 'provider_unavailable'}) from exc
    except Exception as exc:
        logger.exception('Unexpected provider error')
        raise HTTPException(500, detail={'code': 'provider_internal_error'}) from exc
