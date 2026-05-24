"""路由集中挂载。"""
from . import auth, gas_sources, gc_analyzers, metering_stations, readings

__all__ = ["auth", "gas_sources", "gc_analyzers", "metering_stations", "readings"]
