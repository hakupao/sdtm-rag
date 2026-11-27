import datetime as _real, server.web_search as ws
class _D(_real.date):
    @classmethod
    def today(cls): return cls(2026, 11, 26)
class _M: pass
m = _M(); m.date = _D; m.datetime = _real.datetime; m.timezone = _real.timezone; m.timedelta = _real.timedelta
ws._dt = m
