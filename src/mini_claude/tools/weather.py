"""Weather tool using wttr.in free API - no API key needed."""

from typing import Dict, Any

import requests

from .base import BaseTool, register_tool


class WeatherTool(BaseTool):
    """Get weather forecasts using the free wttr.in API."""

    @property
    def name(self) -> str:
        return "weather"

    @property
    def description(self) -> str:
        return (
            "Get current weather and forecast for a city. "
            "Returns temperature, conditions, humidity, wind speed, and a 3-day forecast. "
            "Use this instead of web_search for ANY weather-related query."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name (Chinese or English, e.g. '长沙' or 'Changsha')",
                },
                "days": {
                    "type": "integer",
                    "description": "Number of forecast days (1-3, default: 2)",
                    "default": 2,
                },
            },
            "required": ["city"],
        }

    async def execute(self, city: str, days: int = 2) -> str:
        """Get weather for a city."""
        try:
            # wttr.in returns JSON weather data - free, no API key
            url = f"https://wttr.in/{city}"
            params = {
                "format": "j1",
            }
            headers = {"User-Agent": "curl/8.0"}
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            current = data["current_condition"][0]
            weather_info = data["weather"]
            location = data["nearest_area"][0]

            area_name = location["areaName"][0]["value"]
            country = location["country"][0]["value"]

            output = f"Weather for {area_name}, {country}:\n\n"

            # Current conditions
            output += "**Current Conditions:**\n"
            output += f"- Temperature: {current['temp_C']}°C (feels like {current['FeelsLikeC']}°C)\n"
            output += f"- Weather: {current['weatherDesc'][0]['value']}\n"
            output += f"- Humidity: {current['humidity']}%\n"
            output += f"- Wind: {current['winddir16Point']} {current['windspeedKmph']} km/h\n"
            output += f"- Visibility: {current['visibility']} km\n"
            output += f"- UV Index: {current['uvIndex']}\n\n"

            # Forecast
            output += f"**{min(days, len(weather_info))}-Day Forecast:**\n"
            for i, day in enumerate(weather_info[:days]):
                date = day["date"]
                high = day["maxtempC"]
                low = day["mintempC"]
                avg = day["avgtempC"]
                condition = day["hourly"][4]["weatherDesc"][0]["value"]  # midday condition
                sun_hours = day["astronomy"][0].get("sunshine_hours", "N/A")

                output += f"\n{date}:\n"
                output += f"  High: {high}°C / Low: {low}°C (avg {avg}°C)\n"
                output += f"  Condition: {condition}\n"
                output += f"  Sun Hours: {sun_hours}\n"

            return output

        except requests.exceptions.Timeout:
            return f"Error: Weather request for '{city}' timed out. Please try again."
        except requests.exceptions.HTTPError:
            return f"Error: Could not find weather for '{city}'. Check the city name (use Chinese or English)."
        except requests.exceptions.ConnectionError:
            return "Error: Could not connect to weather service. Please check your internet connection."
        except Exception as e:
            return f"Weather error: {type(e).__name__}: {str(e)}"


register_tool(WeatherTool())
