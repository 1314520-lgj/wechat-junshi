"""Invalidate unobservable live context without deleting history or drafts."""
import time
def invalidate(state,reason,now=None):
    changed=state.get('_view_invalid_reason')!=reason or state.get('title_ready') or state.get('analysis') is not None
    state['title_ready']=False;state['last_area']=None
    state['analysis']=None;state['analysis_error']=None
    # An unobservable window has no live diagnostic frame. Keep observation
    # history and drafts, but do not expose the previous pixels as current.
    if reason in ('minimized','no-window','paused','capture-failed','capture-ended'):
        state['last_frame']=None;state['last_frame_at']=None
    state['_view_invalid_reason']=reason
    if changed:state['session_since']=time.time() if now is None else now
    return bool(changed)
