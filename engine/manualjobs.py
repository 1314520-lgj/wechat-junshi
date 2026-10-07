"""Bounded cancellation for user-owned pasted-chat requests, including races.

Only process memory: no transcripts or secrets. A short tombstone makes cancel
before registration effective without touching another request or live reading.
"""
from collections import OrderedDict
from threading import Event,Lock
import time

class ManualJobs:
    def __init__(self,capacity=64,ttl=300):
        self.capacity=capacity;self.ttl=ttl;self.entries=OrderedDict();self.lock=Lock()
    def _prune(self):
        now=time.monotonic()
        for key,(_,active,expires) in list(self.entries.items()):
            if not active and expires<=now:self.entries.pop(key,None)
        while len(self.entries)>=self.capacity:
            idle=next((key for key,(_,active,_) in self.entries.items() if not active),None)
            if idle is None:raise ValueError('已有过多生成任务，请稍后重试')
            self.entries.pop(idle)
    def start(self,identity):
        with self.lock:
            previous=self.entries.get(identity)
            if previous and previous[1]:raise ValueError('请求编号重复，请重新生成')
            if previous and previous[2]>time.monotonic():event=previous[0]
            else:self._prune();event=Event()
            self.entries[identity]=(event,True,time.monotonic()+self.ttl)
            return event
    def cancel(self,identity):
        with self.lock:
            previous=self.entries.get(identity)
            if previous:event,active,_=previous
            else:self._prune();event=Event();active=False
            event.set();self.entries[identity]=(event,active,time.monotonic()+self.ttl)
    def finish(self,identity,event):
        with self.lock:
            current=self.entries.get(identity)
            if current and current[0] is event:self.entries.pop(identity,None)

jobs=ManualJobs()
