"""Strict comparator for SPARC reproduction candidates; not a validity claim."""
from __future__ import annotations
import math
BIND=("model","artifact","inputs","dataset_version","species","modality","metric","unit")
def compare(reference:dict,candidate:dict,*,atol:float,rtol:float=0.0)->dict:
    mismatch={k:(reference.get(k),candidate.get(k)) for k in BIND if reference.get(k)!=candidate.get(k)}
    if mismatch: return {"status":"incomparable","binding_mismatch":mismatch,"validated":False}
    if reference.get("status")!="ok" or candidate.get("status")!="ok":
        return {"status":"not_compared","reference_status":reference.get("status"),
                "candidate_status":candidate.get("status"),"validated":False}
    r,c=reference.get("value"),candidate.get("value")
    if not isinstance(r,(int,float)) or not isinstance(c,(int,float)) or not math.isfinite(r) or not math.isfinite(c):
        return {"status":"invalid_numeric_output","validated":False}
    err=abs(c-r); tol=atol+rtol*abs(r)
    return {"status":"pass" if err<=tol else "fail","absolute_error":err,"tolerance":tol,
            "validated":False,"interpretation":"numerical reproduction only; not biological or clinical validation"}
