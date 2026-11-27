"""Owner-authorized cancellation of one exact remote version; never delete or push."""
import os
import time
from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.kernels.types.kernels_api_service import ApiCancelKernelSessionRequest
from reconcile_smoke import REF

def status_name(response):
    return str(response.status).split(".")[-1].lower().replace("_","")

def main():
    if not os.environ.get("KAGGLE_API_TOKEN"):
        raise RuntimeError("TOKEN_REQUIRED")
    api = KaggleApi()
    api.authenticate()
    response = api.kernels_status(REF)
    state = status_name(response)
    print("EXACT_STATUS_BEFORE="+state, flush=True)
    if state in {"complete","error","cancelacknowledged"}:
        print("ALREADY_TERMINAL_NO_CANCEL_NEEDED", flush=True)
        return
    if state not in {"queued","running"}:
        print("BLOCKED_UNRECOGNIZED_OR_PENDING_CANCEL_STATUS", flush=True)
        return
    # The exact version status response must explicitly supply the session ID.
    # Version number, kernel id and inferred ids are never used.
    sid = getattr(response, "kernel_session_id", None)
    if type(sid) is not int or sid <= 1:
        print("BLOCKED_SESSION_ID_NOT_EXPOSED", flush=True)
        return
    second = api.kernels_status(REF)
    if getattr(second,"kernel_session_id",None)!=sid or status_name(second) not in {"queued","running"}:
        print("BLOCKED_SESSION_CHANGED",flush=True)
        return
    request=ApiCancelKernelSessionRequest()
    request.kernel_session_id=sid
    with api.build_kaggle_client() as client:
        result=client.kernels.kernels_api_client.cancel_kernel_session(request)
    if getattr(result,"error_message",None):
        print("CANCEL_REJECTED",flush=True)
        return
    print("CANCEL_REQUEST_ACCEPTED_NOT_TERMINAL",flush=True)
    for _ in range(3):
        time.sleep(10)
        state=status_name(api.kernels_status(REF))
        print("EXACT_STATUS_AFTER="+state,flush=True)
        if state in {"complete","error","cancelacknowledged"}:
            break

if __name__=="__main__":
    main()
