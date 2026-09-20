"""Strict comparator for SPARC reproduction candidates; not a validity claim."""
from __future__ import annotations
import math
BIND=("model","artifact","inputs","dataset_version","species","modality","metric","unit")
def compare(reference:dict,candidate:dict,*,atol:float,rtol:float=0.0)->dict:
    if any(isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or t < 0 for t in (atol, rtol)):
        return {"status":"invalid_tolerance", "validated":False}
    missing = [k for k in BIND if reference.get(k) in (None, "") or candidate.get(k) in (None, "")]
    if missing:
        return {"status":"incomparable", "missing_binding":missing, "validated":False}
    mismatch={k:(reference.get(k),candidate.get(k)) for k in BIND if reference.get(k)!=candidate.get(k)}
    if mismatch: return {"status":"incomparable","binding_mismatch":mismatch,"validated":False}
    if reference.get("status")!="ok" or candidate.get("status")!="ok":
        return {"status":"not_compared","reference_status":reference.get("status"),
                "candidate_status":candidate.get("status"),"validated":False}
    r,c=reference.get("value"),candidate.get("value")
    if isinstance(r,bool) or isinstance(c,bool) or not isinstance(r,(int,float)) or not isinstance(c,(int,float)) or not math.isfinite(r) or not math.isfinite(c):
        return {"status":"invalid_numeric_output","validated":False}
    err=abs(c-r); tol=atol+rtol*abs(r)
    if not math.isfinite(err) or not math.isfinite(tol):
        return {"status":"invalid_numeric_output","validated":False}
    return {"status":"pass" if err<=tol else "fail","absolute_error":err,"tolerance":tol,
            "validated":False,"interpretation":"numerical reproduction only; not biological or clinical validation"}


def reproduction_outcome(reference, candidate, *, atol, rtol=0.0):
    """Diagnostic comparison only; not an execution gate or predeclaration evidence.

    New candidate invocations must use contract.execute. These results cannot
    establish model qualification or override a missing reproduction contract.
    """
    result = compare(reference, candidate, atol=atol, rtol=rtol)
    status = result['status']
    result['outcome'] = {'pass': 'PASS', 'fail': 'FAIL', 'incomparable': 'INCOMPARABLE',
                         'invalid_numeric_output': 'FAIL', 'invalid_tolerance': 'INCOMPARABLE'}.get(status, 'BLOCKED')
    if status == 'not_compared' and reference.get('status') == 'ok' and candidate.get('status') == 'failed':
        result['outcome'] = 'FAIL'
    return result
