#!/usr/bin/env python3
"""
app.py — Key Plan Visual Web App
Gordoniz Servicios Inmobiliarios

Uso:
    pip install flask requests
    python app.py
    Abre http://localhost:5000 en el navegador
"""

from flask import Flask, render_template, request, jsonify
import requests
import time
import re
import os
from collections import defaultdict

app = Flask(__name__)

# Si se define la variable de entorno GOOGLE_API_KEY, no hace falta
# que el usuario la introduzca en el formulario.
SERVER_API_KEY = os.environ.get('GOOGLE_API_KEY', '')

CATEGORIAS_COLOR = {
    "restaurant": "#E53935", "cafe": "#E53935", "bar": "#E53935",
    "bakery": "#E53935", "food": "#E53935",
    "supermarket": "#43A047", "store": "#43A047", "clothing_store": "#43A047",
    "shoe_store": "#43A047", "electronics_store": "#43A047",
    "home_goods_store": "#43A047", "furniture_store": "#43A047",
    "hardware_store": "#43A047", "florist": "#43A047", "book_store": "#43A047",
    "jewelry_store": "#43A047", "pet_store": "#43A047", "shopping_mall": "#43A047",
    "bank": "#1E88E5", "atm": "#1E88E5", "insurance_agency": "#1E88E5",
    "finance": "#1E88E5",
    "pharmacy": "#8E24AA", "doctor": "#8E24AA", "dentist": "#8E24AA",
    "hospital": "#8E24AA", "gym": "#8E24AA", "spa": "#8E24AA",
    "hair_care": "#8E24AA", "beauty_salon": "#8E24AA",
    "parking": "#757575", "gas_station": "#757575", "car_dealer": "#757575",
    "lodging": "#FB8C00", "hotel": "#FB8C00",
    "school": "#00ACC1", "university": "#00ACC1", "library": "#00ACC1",
    "museum": "#00ACC1",
    "movie_theater": "#F4511E", "night_club": "#F4511E",
}

CATEGORIA_LABEL = {
    "restaurant": "Restauración", "cafe": "Restauración", "bar": "Restauración",
    "bakery": "Restauración", "food": "Restauración",
    "supermarket": "Comercio", "store": "Comercio", "clothing_store": "Comercio",
    "shoe_store": "Comercio", "electronics_store": "Comercio",
    "shopping_mall": "Comercio", "home_goods_store": "Comercio",
    "bank": "Banca", "atm": "Banca",
    "pharmacy": "Salud", "doctor": "Salud", "dentist": "Salud",
    "gym": "Salud", "beauty_salon": "Salud", "hair_care": "Salud",
    "lodging": "Alojamiento", "hotel": "Alojamiento",
    "parking": "Transporte", "gas_station": "Transporte",
    "school": "Educación", "university": "Educación",
    "movie_theater": "Ocio", "night_club": "Ocio",
}


def geocode(address, api_key):
    r = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"address": address, "key": api_key, "language": "es"},
        timeout=10
    )
    data = r.json()
    if data["status"] != "OK":
        raise ValueError(f"Geocoding error: {data['status']}")
    loc = data["results"][0]["geometry"]["location"]
    return loc["lat"], loc["lng"], data["results"][0]["formatted_address"]


def fetch_places_at(lat, lng, radius, api_key, seen):
    """Busca negocios en un punto concreto y devuelve los nuevos (no vistos)."""
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {"location": f"{lat},{lng}", "radius": radius, "key": api_key, "language": "es"}
    new_places = []
    page = 0
    while page < 3:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if data["status"] not in ("OK", "ZERO_RESULTS"):
            break
        for p in data.get("results", []):
            pid = p.get("place_id")
            if pid and pid not in seen:
                seen.add(pid)
                new_places.append(p)
        token = data.get("next_page_token")
        if not token:
            break
        params = {"pagetoken": token, "key": api_key}
        time.sleep(2)
        page += 1
    return new_places


def nearby_places(lat, lng, radius, api_key):
    """
    Para radios pequeños (≤500m): una sola búsqueda central.
    Para radios grandes (>500m): cuadrícula de puntos solapados para superar
    el límite de 60 resultados de la API de Google Places.
    """
    import math

    seen = set()
    places = []

    if radius <= 500:
        # Búsqueda simple central
        places = fetch_places_at(lat, lng, radius, api_key, seen)
    else:
        # Cuadrícula de búsquedas con radio de celda = radius/3
        # para garantizar solapamiento y cobertura completa
        cell_r = min(radius // 3, 500)  # máx 500m por celda (límite razonable API)
        # Grados por metro (aproximado)
        deg_per_m_lat = 1 / 111320
        deg_per_m_lng = 1 / (111320 * math.cos(math.radians(lat)))
        step = cell_r * 1.4  # paso entre centros de celda
        # Rango de la cuadrícula
        n_steps = math.ceil(radius / step)
        search_points = []
        for i in range(-n_steps, n_steps + 1):
            for j in range(-n_steps, n_steps + 1):
                clat = lat + i * step * deg_per_m_lat
                clng = lng + j * step * deg_per_m_lng
                # Solo incluir puntos dentro del radio original
                dist = math.sqrt((i * step) ** 2 + (j * step) ** 2)
                if dist <= radius:
                    search_points.append((clat, clng))
        for clat, clng in search_points:
            new = fetch_places_at(clat, clng, cell_r, api_key, seen)
            places.extend(new)

    return places


def extract_street(vicinity):
    """Extrae el nombre de calle de la dirección de Google."""
    if not vicinity:
        return "Zona"
    # Tomar solo la primera parte antes de la coma
    parts = vicinity.split(",")
    street = parts[0].strip()
    # Quitar el número
    street = re.sub(r'\s+\d+.*$', '', street).strip()
    return street if street else "Zona"


def place_color(types):
    for t in types:
        if t in CATEGORIAS_COLOR:
            return CATEGORIAS_COLOR[t]
    return "#546E7A"


def place_category(types):
    for t in types:
        if t in CATEGORIA_LABEL:
            return CATEGORIA_LABEL[t]
    return "Otros"


BRAND_DOMAINS = {
    # Moda / Ropa
    'zara': 'zara.com', 'mango': 'mango.com', 'bershka': 'bershka.com',
    'stradivarius': 'stradivarius.com', 'pull&bear': 'pullandbear.com',
    'pull bear': 'pullandbear.com', 'massimo dutti': 'massimodutti.com',
    'h&m': 'hm.com', 'primark': 'primark.com', 'calzedonia': 'calzedonia.com',
    'intimissimi': 'intimissimi.com', 'tezenis': 'tezenis.com',
    'cortefiel': 'cortefiel.com', 'springfield': 'e-springfield.com',
    'women secret': 'womensecret.com', 'women\'s secret': 'womensecret.com',
    'decimas': 