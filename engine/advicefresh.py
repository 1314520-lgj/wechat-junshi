"""Independent finite-time gate for suggestions; never grants input authority."""
import math
import time
ADVICE_TTL_SECONDS=300

def advice_fresh(analysis,now=None):
    if not isinstance(analysis,dict):return False
    stamp=analysis.get('ts');now=time.time() if now is None else now
    for value in (stamp,now):
        if isinstance(value,bool) or not isinstance(value,(int,float)) :return False
        try:
            if not math.isfinite(value):return False
        except (OverflowError,ValueError):return False
    return stamp>0 and 0<=now-stamp<ADVICE_TTL_SECONDS
