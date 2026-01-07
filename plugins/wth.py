from fastapi import APIRouter
from fastapi.responses import JSONResponse
import aiohttp
import asyncio
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
import os
import pytz
import pycountry
import requests
import tempfile
import io
from utils import LOGGER

router = APIRouter(prefix="/wth")

FONT_CACHE = {}

def download_font(url, size):
    cache_key = f"{url}_{size}"
    if cache_key in FONT_CACHE:
        return FONT_CACHE[cache_key]
    
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            font = ImageFont.truetype(io.BytesIO(response.content), size)
            FONT_CACHE[cache_key] = font
            LOGGER.info(f"Font cached successfully: {cache_key}")
            return font
        else:
            LOGGER.error(f"Font download failed with status {response.status_code}")
    except Exception as e:
        LOGGER.error(f"Failed to download font from {url}: {str(e)}")
    
    return ImageFont.load_default()

def get_timezone_from_coordinates(lat, lon):
    return pytz.timezone('UTC')

def get_country_name(country_code):
    try:
        country = pycountry.countries.get(alpha_2=country_code)
        return country.name if country else country_code
    except Exception:
        return country_code

def create_weather_image(weather_data, output_path):
    current = weather_data["current"]
    
    try:
        timezone = get_timezone_from_coordinates(weather_data["lat"], weather_data["lon"])
        local_time = datetime.now(timezone)
        time_text = local_time.strftime("%I:%M %p")
    except Exception as e:
        LOGGER.error(f"Time formatting failed: {str(e)}")
        time_text = datetime.now().strftime("%I:%M %p")
    
    img_width, img_height = 1920, 1080
    background_color = (15, 23, 42)
    white = (255, 255, 255)
    light_gray = (203, 213, 225)
    accent_blue = (59, 130, 246)
    
    img = Image.new("RGB", (img_width, img_height), color=background_color)
    draw = ImageDraw.Draw(img)
    
    font_url_bold = "https://github.com/google/fonts/raw/main/ofl/inter/static/Inter_18pt-Bold.ttf"
    font_url_semibold = "https://github.com/google/fonts/raw/main/ofl/inter/static/Inter_18pt-SemiBold.ttf"
    font_url_regular = "https://github.com/google/fonts/raw/main/ofl/inter/static/Inter_18pt-Regular.ttf"
    font_url_medium = "https://github.com/google/fonts/raw/main/ofl/inter/static/Inter_18pt-Medium.ttf"
    
    try:
        font_temp_huge = download_font(font_url_bold, 180)
        font_title_large = download_font(font_url_bold, 72)
        font_subtitle = download_font(font_url_semibold, 48)
        font_body = download_font(font_url_regular, 42)
        font_small = download_font(font_url_medium, 38)
    except Exception as e:
        LOGGER.error(f"Font loading failed: {str(e)}")
        font_temp_huge = ImageFont.load_default()
        font_title_large = ImageFont.load_default()
        font_subtitle = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_small = ImageFont.load_default()
    
    header_y = 60
    draw.text((80, header_y), "Current Weather", font=font_title_large, fill=white)
    draw.text((img_width - 80, header_y), time_text, font=font_body, fill=light_gray, anchor="ra")
    
    draw.line([(80, header_y + 100), (img_width - 80, header_y + 100)], fill=accent_blue, width=4)
    
    temp_y = 280
    temp_text = f"{current['temperature']}°"
    draw.text((img_width // 2, temp_y), temp_text, font=font_temp_huge, fill=white, anchor="mm")
    
    condition_y = temp_y + 140
    condition_text = current["weather"]
    draw.text((img_width // 2, condition_y), condition_text, font=font_subtitle, fill=light_gray, anchor="mm")
    
    realfeel_y = condition_y + 80
    realfeel_text = f"Feels like {current['feels_like']}°C"
    draw.text((img_width // 2, realfeel_y), realfeel_text, font=font_body, fill=light_gray, anchor="mm")
    
    info_y = 700
    info_spacing = 280
    
    humidity_x = 300
    draw.text((humidity_x, info_y), "Humidity", font=font_small, fill=light_gray, anchor="mm")
    draw.text((humidity_x, info_y + 60), f"{current['humidity']}%", font=font_subtitle, fill=white, anchor="mm")
    
    wind_x = humidity_x + info_spacing
    draw.text((wind_x, info_y), "Wind Speed", font=font_small, fill=light_gray, anchor="mm")
    draw.text((wind_x, info_y + 60), f"{current['wind_speed']} km/h", font=font_subtitle, fill=white, anchor="mm")
    
    sunrise_x = wind_x + info_spacing
    draw.text((sunrise_x, info_y), "Sunrise", font=font_small, fill=light_gray, anchor="mm")
    draw.text((sunrise_x, info_y + 60), current['sunrise'], font=font_subtitle, fill=white, anchor="mm")
    
    sunset_x = sunrise_x + info_spacing
    draw.text((sunset_x, info_y), "Sunset", font=font_small, fill=light_gray, anchor="mm")
    draw.text((sunset_x, info_y + 60), current['sunset'], font=font_subtitle, fill=white, anchor="mm")
    
    country_name = get_country_name(weather_data['country_code'])
    location_text = f"{weather_data['city']}, {country_name}"
    draw.text((80, img_height - 80), location_text, font=font_body, fill=light_gray)
    
    coords_text = f"Lat: {weather_data['lat']:.2f}° | Lon: {weather_data['lon']:.2f}°"
    draw.text((img_width - 80, img_height - 80), coords_text, font=font_small, fill=light_gray, anchor="ra")
    
    img.save(output_path, quality=95, optimize=True)
    LOGGER.info(f"High-quality weather image saved: {output_path}")
    return output_path

async def fetch_data(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
            if response.status == 200:
                return await response.json()
            else:
                LOGGER.error(f"Fetch failed with status {response.status} for {url}")
    except asyncio.TimeoutError:
        LOGGER.error(f"Timeout error for {url}")
    except Exception as e:
        LOGGER.error(f"Fetch error for {url}: {str(e)}")
    return None

def upload_to_tmpfiles(file_path):
    try:
        with open(file_path, 'rb') as f:
            files = {'file': f}
            response = requests.post('https://tmpfiles.org/api/v1/upload', files=files, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    url = data['data']['url']
                    url = url.replace('tmpfiles.org/', 'tmpfiles.org/dl/')
                    LOGGER.info(f"Image uploaded successfully: {url}")
                    return url
            LOGGER.error(f"Upload failed with status {response.status_code}: {response.text}")
    except Exception as e:
        LOGGER.error(f"Upload to tmpfiles failed: {str(e)}")
    return None

async def get_weather_data(city):
    async with aiohttp.ClientSession() as session:
        geocode_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en&format=json"
        geocode_data = await fetch_data(session, geocode_url)
        
        if not geocode_data or "results" not in geocode_data or not geocode_data["results"]:
            LOGGER.warning(f"No geocode results for city: {city}")
            return None
        
        result = geocode_data["results"][0]
        lat, lon = result["latitude"], result["longitude"]
        country_code = result.get("country_code", "").upper()
        
        LOGGER.info(f"Fetching weather for {city} at coordinates: {lat}, {lon}")
        
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}&"
            f"current=temperature_2m,relative_humidity_2m,apparent_temperature,weathercode,"
            f"wind_speed_10m,wind_direction_10m&"
            f"hourly=temperature_2m,apparent_temperature,relative_humidity_2m,weathercode,"
            f"precipitation_probability&"
            f"daily=temperature_2m_max,temperature_2m_min,sunrise,sunset,weathercode&"
            f"timezone=auto"
        )
        
        aqi_url = (
            f"https://air-quality-api.open-meteo.com/v1/air-quality?"
            f"latitude={lat}&longitude={lon}&"
            f"hourly=pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,ozone&"
            f"timezone=auto"
        )
        
        weather_data, aqi_data = await asyncio.gather(
            fetch_data(session, weather_url),
            fetch_data(session, aqi_url)
        )
        
        if not weather_data or not aqi_data:
            LOGGER.error(f"Failed to fetch weather or AQI data for {city}")
            return None
        
        current = weather_data["current"]
        hourly = weather_data["hourly"]
        daily = weather_data["daily"]
        aqi = aqi_data["hourly"]
        
        weather_code = {
            0: "Clear Sky", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
            45: "Foggy", 48: "Depositing Rime Fog", 51: "Light Drizzle", 53: "Moderate Drizzle",
            55: "Dense Drizzle", 61: "Slight Rain", 63: "Moderate Rain", 65: "Heavy Rain",
            66: "Light Freezing Rain", 67: "Heavy Freezing Rain", 71: "Slight Snow Fall",
            73: "Moderate Snow Fall", 75: "Heavy Snow Fall", 77: "Snow Grains", 80: "Slight Rain Showers",
            81: "Moderate Rain Showers", 82: "Violent Rain Showers", 95: "Thunderstorm",
            96: "Thunderstorm with Slight Hail", 99: "Thunderstorm with Heavy Hail"
        }
        
        hourly_forecast = []
        for i in range(min(12, len(hourly["time"]))):
            time_str = hourly["time"][i].split("T")[1][:5]
            hour = int(time_str[:2])
            time_format = f"{hour % 12 or 12} {'AM' if hour < 12 else 'PM'}"
            
            hourly_forecast.append({
                "time": time_format,
                "temperature": round(hourly["temperature_2m"][i], 1),
                "weather": weather_code.get(hourly["weathercode"][i], "Unknown"),
                "humidity": hourly["relative_humidity_2m"][i],
                "precipitation_probability": hourly["precipitation_probability"][i]
            })
        
        current_date = datetime.now()
        daily_forecast = []
        for i in range(min(7, len(daily["temperature_2m_max"]))):
            day_date = (current_date + timedelta(days=i))
            daily_forecast.append({
                "date": day_date.strftime('%Y-%m-%d'),
                "day": day_date.strftime('%a, %b %d'),
                "min_temp": round(daily["temperature_2m_min"][i], 1),
                "max_temp": round(daily["temperature_2m_max"][i], 1),
                "weather": weather_code.get(daily["weathercode"][i], "Unknown"),
                "sunrise": daily["sunrise"][i].split("T")[1][:5],
                "sunset": daily["sunset"][i].split("T")[1][:5]
            })
        
        pm25 = aqi["pm2_5"][0]
        if pm25 <= 12:
            aqi_level = "Good"
        elif pm25 <= 35:
            aqi_level = "Fair"
        elif pm25 <= 55:
            aqi_level = "Moderate"
        else:
            aqi_level = "Poor"
        
        try:
            timezone = get_timezone_from_coordinates(lat, lon)
            local_time = datetime.now(timezone)
            current_time = local_time.strftime("%I:%M %p")
            current_date_str = local_time.strftime("%Y-%m-%d")
        except Exception:
            current_time = datetime.now().strftime("%I:%M %p")
            current_date_str = datetime.now().strftime("%Y-%m-%d")
        
        LOGGER.info(f"Successfully fetched weather data for {city}")
        
        return {
            "status": "success",
            "location": {
                "city": city.capitalize(),
                "country": get_country_name(country_code),
                "country_code": country_code,
                "coordinates": {
                    "latitude": lat,
                    "longitude": lon
                }
            },
            "current": {
                "time": current_time,
                "date": current_date_str,
                "temperature": round(current["temperature_2m"], 1),
                "feels_like": round(current["apparent_temperature"], 1),
                "humidity": current["relative_humidity_2m"],
                "wind_speed": round(current["wind_speed_10m"], 1),
                "wind_direction": current["wind_direction_10m"],
                "weather": weather_code.get(current["weathercode"], "Unknown"),
                "weather_code": current["weathercode"],
                "sunrise": daily["sunrise"][0].split("T")[1][:5],
                "sunset": daily["sunset"][0].split("T")[1][:5]
            },
            "hourly_forecast": hourly_forecast,
            "daily_forecast": daily_forecast,
            "air_quality": {
                "level": aqi_level,
                "pm2_5": round(aqi["pm2_5"][0], 2),
                "pm10": round(aqi["pm10"][0], 2),
                "carbon_monoxide": round(aqi["carbon_monoxide"][0], 2),
                "nitrogen_dioxide": round(aqi["nitrogen_dioxide"][0], 2),
                "ozone": round(aqi["ozone"][0], 2)
            },
            "maps": {
                "temperature": f"https://openweathermap.org/weathermap?basemap=map&cities=true&layer=temperature&lat={lat}&lon={lon}&zoom=8",
                "clouds": f"https://openweathermap.org/weathermap?basemap=map&cities=true&layer=clouds&lat={lat}&lon={lon}&zoom=8",
                "precipitation": f"https://openweathermap.org/weathermap?basemap=map&cities=true&layer=precipitation&lat={lat}&lon={lon}&zoom=8",
                "wind": f"https://openweathermap.org/weathermap?basemap=map&cities=true&layer=wind&lat={lat}&lon={lon}&zoom=8",
                "pressure": f"https://openweathermap.org/weathermap?basemap=map&cities=true&layer=pressure&lat={lat}&lon={lon}&zoom=8"
            },
            "lat": lat,
            "lon": lon,
            "country_code": country_code,
            "city": city.capitalize()
        }

@router.get("")
async def get_weather(area: str = None):
    try:
        if not area:
            LOGGER.warning("Missing area parameter in request")
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "Missing 'area' parameter. Usage: /wth?area=London"
                }
            )
        
        LOGGER.info(f"Received weather request for area: {area}")
        
        weather_data = await get_weather_data(area)
        
        if not weather_data:
            LOGGER.error(f"No weather data found for area: {area}")
            return JSONResponse(
                status_code=404,
                content={
                    "status": "error",
                    "message": f"Weather data unavailable for '{area}'. Please check the city name."
                }
            )
        
        temp_dir = tempfile.gettempdir()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        image_path = os.path.join(temp_dir, f"weather_{area}_{timestamp}.png")
        
        LOGGER.info(f"Generating high-quality weather image at: {image_path}")
        create_weather_image(weather_data, image_path)
        
        LOGGER.info("Uploading image to tmpfiles.org")
        image_url = upload_to_tmpfiles(image_path)
        
        try:
            os.remove(image_path)
            LOGGER.info(f"Successfully removed local image: {image_path}")
        except Exception as e:
            LOGGER.error(f"Failed to remove image: {str(e)}")
        
        if image_url:
            weather_data["image_url"] = image_url
        else:
            weather_data["image_url"] = None
            weather_data["image_error"] = "Failed to upload image to hosting service"
        
        LOGGER.info(f"Successfully processed weather request for {area}")
        return JSONResponse(content=weather_data)
        
    except ValueError as e:
        LOGGER.error(f"Invalid input for weather lookup: {str(e)}")
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": str(e)
            }
        )
    except Exception as e:
        LOGGER.error(f"Error processing weather request: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Internal server error. Please try again later.",
                "error_details": str(e)
            }
        )
