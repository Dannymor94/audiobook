"""Delete only the owner-approved throwaway notebook. Never submit."""
import os
from kaggle.api.kaggle_api_extended import KaggleApi
from requests.exceptions import HTTPError

OWNER="dannymorozov"
SLUG="audiobook-public-smoke-46019695614"
KERNEL=f"{OWNER}/{SLUG}"
REF=f"{KERNEL}/1"

def main():
    if not os.environ.get("KAGGLE_API_TOKEN"):
        raise RuntimeError("TOKEN_REQUIRED")
    api=KaggleApi()
    api.authenticate()
    # Read exact version before deletion. Unexpected lookup failure blocks.
    try:
        response=api.kernels_status(REF)
    except HTTPError as exc:
        print("PRECHECK_HTTP_STATUS="+str(exc.response.status_code),flush=True)
        return
    print("EXACT_STATUS_BEFORE="+str(response.status),flush=True)
    # Explicit owner approval in the current conversation covers this one
    # disposable notebook, including its sole experimental version.
    api.kernels_delete(KERNEL,no_confirm=True)
    print("DELETE_REQUEST_SUCCEEDED",flush=True)
    try:
        after=api.kernels_status(REF)
    except HTTPError as exc:
        print("POST_DELETE_HTTP_STATUS="+str(exc.response.status_code),flush=True)
    except ValueError:
        print("POST_DELETE_VERSION_INACCESSIBLE",flush=True)
    else:
        print("EXACT_STATUS_AFTER="+str(after.status),flush=True)
    # Inaccessibility/deletion does not independently prove worker stopped.
    print("REMOTE_STOP_UNPROVEN_KEEP_RESERVATION",flush=True)

if __name__=="__main__":
    main()
