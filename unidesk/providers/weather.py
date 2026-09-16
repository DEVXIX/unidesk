"""Weather from open-meteo (no key), located by IP, city name or "lat,lon"."""
from __future__ import annotations

import datetime as dt
import re
import threading
import urllib.parse

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from .net import get_json

CODES = {
    0: ("clear sky", "sun"), 1: ("mainly clear", "sun"), 2: ("partly cloudy", "partly"), 3: ("overcast clouds", "cloud"),
    45: ("fog", "fog"), 48: ("rime fog", "fog"), 51: ("light drizzle", "rain"), 53: ("drizzle", "rain"),
    55: ("heavy drizzle", "rain"), 61: ("light rain", "rain"), 63: ("rain", "rain"), 65: ("heavy rain", "rain"),
    66: ("freezing rain", "rain"), 67: ("freezing rain", "rain"), 71: ("light snow", "snow"), 73: ("snow", "snow"),
    75: ("heavy snow", "snow"), 77: ("snow grains", "snow"), 80: ("rain showers", "rain"), 81: ("rain showers", "rain"),
    82: ("violent showers", "rain"), 85: ("snow showers", "snow"), 86: ("snow showers", "snow"),
    95: ("thunderstorm", "storm"), 96: ("thunderstorm, hail", "storm"), 99: ("thunderstorm, hail", "storm"),
}

SUMMARY = {
    "sun": "clear skies today", "moon": "a clear night", "partly": "a bit cloudy today", "cloud": "grey and cloudy",
    "fog": "foggy out there", "rain": "bring an umbrella", "snow": "snow today", "storm": "stormy, stay in",
}


class Weather(QObject):
    """Exposed to QML as `Weather`: `Weather.data.temp`, `.condition`, ..."""

    dataChanged = Signal()
    _ready = Signal("QVariant")

    def __init__(self):
        super().__init__()
        self._data = None
        self._settings = {"location": "auto", "units": "metric"}
        self._timer = QTimer(self, interval=15 * 60 * 1000, timeout=self.refresh)
        self._ready.connect(self._on_ready)

    def configure(self, settings: dict):
        settings = {"location": "auto", "units": "metric", **(settings or {})}
        if settings == self._settings:
            return
        self._settings = settings
        if self._timer.isActive():
            self.refresh()

    def start(self):
        if not self._timer.isActive():
            self._timer.start()
            self.refresh()

    def stop(self):
        self._timer.stop()

    @Slot()
    def refresh(self):
        threading.Thread(target=self._fetch, args=(dict(self._settings),), daemon=True).start()

    def _fetch(self, settings: dict):
        try:
            where = str(settings.get("location") or "auto").strip()
            pair = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*", where)
            place = ""
            if pair:
                lat, lon = float(pair.group(1)), float(pair.group(2))
            elif where.lower() != "auto":
                g = get_json(f"https://geocoding-api.open-meteo.com/v1/search?count=1&name={urllib.parse.quote(where)}") or {}
                r = (g.get("results") or [None])[0]
                if not r:
                    raise RuntimeError(f"no place called {where!r}")
                lat, lon, place = r["latitude"], r["longitude"], r["name"]
            else:
                ip = get_json("https://ipwho.is/")
                lat, lon, place = ip["latitude"], ip["longitude"], ip.get("city", "")

            imperial = settings.get("units") == "imperial"
            q = urllib.parse.urlencode({
                "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 1,
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,cloud_cover,wind_speed_10m,weather_code,visibility,is_day",
                "daily": "sunrise,sunset",
                "wind_speed_unit": "mph" if imperial else "ms",
                "temperature_unit": "fahrenheit" if imperial else "celsius",
            })
            w = get_json(f"https://api.open-meteo.com/v1/forecast?{q}")
            c = w["current"]
            condition, icon = CODES.get(int(c["weather_code"]), ("", "cloud"))
            if icon == "sun" and not c.get("is_day", 1):
                icon = "moon"

            def clock(iso: str) -> str:
                return dt.datetime.fromisoformat(iso).strftime("%I:%M %p").lstrip("0")

            self._ready.emit({
                "temp": c["temperature_2m"], "feelsLike": c["apparent_temperature"], "condition": condition,
                "icon": icon, "summary": SUMMARY[icon], "place": place, "humidity": c["relative_humidity_2m"],
                "clouds": c["cloud_cover"], "wind": c["wind_speed_10m"],
                "visibility": c["visibility"] / (1609.34 if imperial else 1000),
                "sunrise": clock(w["daily"]["sunrise"][0]), "sunset": clock(w["daily"]["sunset"][0]),
                "units": "imperial" if imperial else "metric",
            })
        except Exception as e:
            print(f"[unidesk] weather failed: {e}")
            QTimer.singleShot(0, lambda: None)

    @Slot("QVariant")
    def _on_ready(self, data):
        self._data = data
        self.dataChanged.emit()

    @Property("QVariant", notify=dataChanged)
    def data(self):
        return self._data
