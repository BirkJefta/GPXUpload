import os
from datetime import datetime, time, timezone
import uuid
import gpxpy
import gpxpy.gpx
from rdp import rdp
import requests
from PIL import Image
import io
import json
import supabase
from supabase import create_client, Client
import time as time_module
from math import radians, cos, sin, asin, sqrt



url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

supabase_client = create_client(url, key)

#adapter classes to make json look like gpx.

class PointAdapter:
    def __init__(self, lon, lat, time_str):
        self.longitude = lon
        self.latitude = lat
        self.time = datetime.fromisoformat(time_str.replace("Z", "+00:00")) if time_str else None

class SegmentAdapter:
    def __init__(self, points, distance_nm):
        self.points = points
        self.distance_nm = distance_nm
    def length_2d(self):
        return self.distance_nm * 1852

#methods to create track objects to save in db.
track_object = {
    "p_name": None,
    "p_new_name": None,
    "p_date": None,
    "p_start_lat": None,
    "p_start_lon": None,
    "p_end_lat": None,
    "p_end_lon": None,
    "p_duration_min": None,
    "p_distance_nm": None,
    "p_route_data": None,
    "p_geom": None,
    "p_thumbnail_url": None,
    "p_notes": None,
    "p_start_time": None,
    "p_end_time": None
}

def add_tracks(track_payload):
    try:
        response = supabase_client.rpc("insert_new_track", track_payload).execute()
        return response.data 
    except Exception as e:
        raise Exception(f"Database error: {str(e)}")



#this method creates track objects from a string of possibly many gpx tracks.
def process_gpx(gpx_string):
    gpx = gpxpy.parse(gpx_string)
    status_codes = []
    test_tracks = gpx.tracks

    for track in test_tracks:
        for segment in track.segments:
            try:
                payload = new_track_object(track, segment)
                track_id = add_tracks(payload) 
                status_codes.append({"name": track.name, "status": "success", "id": track_id})
                time_module.sleep(0.5)
            except Exception as e:
                            status_codes.append({
                                "name": track.name, 
                                "status": "error", 
                                "message": str(e)
                            })

    return status_codes
        
    
        
def new_track_object(track,segment):
    if not segment.points or len(segment.points) < 2:
        raise Exception("Track segment contains less than 2 points, cannot create track object.")
    name = track.name
    new_name = is_name_a_date(name)
    start_time = segment.points[0].time
    end_time= segment.points[-1].time
    distance_nm = calculate_distance(segment)
    duration_min = calculate_time(start_time, end_time)
    geom_wkt, time_list, raw_list_for_api = simplify_coords(segment.points, eps=0.0001)
    route_data = route_data_builder(time_list)
    buffer = create_thumbnail(geom_wkt, raw_list_for_api)
    thumbnail_url = save_thumbnail_to_storage(buffer) if buffer else None
    if not thumbnail_url:
        raise Exception("Thumbnail URL blev ikke genereret korrekt.")
    track_payload = {
        "p_name": name,
        "p_new_name": new_name,
        "p_date": start_time.isoformat() if start_time else None,
        "p_start_lat": segment.points[0].latitude,
        "p_start_lon": segment.points[0].longitude,
        "p_end_lat": segment.points[-1].latitude,
        "p_end_lon": segment.points[-1].longitude,
        "p_duration_min": duration_min,
        "p_distance_nm": round(distance_nm, 2),
        "p_geom": geom_wkt,
        "p_route_data": route_data,
        "p_start_time": start_time.isoformat() if start_time else None,
        "p_end_time": end_time.isoformat() if end_time else None,
        "p_notes": "",
        "p_thumbnail_url": thumbnail_url
    }
    return track_payload


    


def is_name_a_date(name):
    if not name:
        return True
    name = str(name).strip()
    for fmt in ('%Y-%m-%d', '%d.%m.%Y %H.%M', '%d.%m.%Y %H:%M', '%d.%m.%Y', '%Y-%m-%dT%H:%M:%SZ'):
        try:
            datetime.strptime(name, fmt)
            return True
        except (ValueError, TypeError):
            continue
    return False


def calculate_distance(segment):
    distance = segment.length_2d() / 1852
    return distance


def calculate_time(start_time, end_time):
    if not start_time or not end_time:
        return None

    duration = end_time - start_time

    if duration.total_seconds() < 0:
        return None

    return int(duration.total_seconds() / 60)


    




def simplify_coords(points, eps):
    raw_points = points
    coords = [[p.latitude, p.longitude] for p in raw_points]
    mask = rdp(coords, epsilon=eps, return_mask=True)

    simplified_lon_lat_strings = []
    timestamps = []
    raw_list_for_api = [] 

    for i in range(len(raw_points)):
        if mask[i]:
            p = raw_points[i]
            simplified_lon_lat_strings.append(f"{p.longitude} {p.latitude}")
            raw_list_for_api.append([p.longitude, p.latitude]) 
            timestamps.append(p.time.isoformat() if p.time else None)
    
    #if not enough points then use all points, otherwise a linestring cant be created and the track will fail to save.
    if len(simplified_lon_lat_strings) < 2:
        simplified_lon_lat_strings = [
            f"{p.longitude} {p.latitude}" for p in raw_points
        ]
        raw_list_for_api = [[p.longitude, p.latitude] for p in raw_points]
        timestamps = [p.time.isoformat() if p.time else None for p in raw_points]
            
    wkt_geom = f"LINESTRING({', '.join(simplified_lon_lat_strings)})"
    return wkt_geom, timestamps, raw_list_for_api



def route_data_builder(timestamps):
    return {
        "points_metadata": {
            "timestamps": timestamps
        },
        "general_metadata": {}
    }



def create_thumbnail(geom_wkt, simplified_coords):
    geoapify_api_key = os.environ.get("GEOAPIFY_API_KEY")
    url = f"https://maps.geoapify.com/v1/staticmap?apiKey={geoapify_api_key}"
    
    purple_color = "#8e44ad"
    green_color = '#27ae60'
    red_color ='#e74c3c'
    
    start_lon = float(simplified_coords[0][0])
    start_lat = float(simplified_coords[0][1])
    end_lon = float(simplified_coords[-1][0])
    end_lat = float(simplified_coords[-1][1])
    
    body = {
        "style": "klokantech-basic",
        "width": 800,
        "height": 600,
        "format": "png",
        "geometries": [
            {
                "type": "polyline",
                "linecolor": purple_color,
                "linewidth": 3,
                "lineopacity": 1,
                "value": [{"lon": float(p[0]), "lat": float(p[1])} for p in simplified_coords]
            }
        ],
        "markers": [
            {
                "type": "awesome",
                "color": green_color,
                "icon": "circle",
                "lon": start_lon, 
                "lat": start_lat
            },
            {
                "type": "awesome",
                "color": red_color,
                "icon": "flag-checkered",
                "lon": end_lon, 
                "lat": end_lat
            }
        ]
    }
    response = requests.post(url, json=body)
    if response.status_code == 200:
        image = Image.open(io.BytesIO(response.content))
        buffer = io.BytesIO()
        image.save(buffer, format="WEBP", quality=80)
        buffer.seek(0) 
        return buffer
    else:
        raise Exception(f"Geoapify API error {response.status_code}")
        return None


    


def save_thumbnail_to_storage(buffer):
    new_id = str(uuid.uuid4())
    filepath = f"thumbnails/{new_id}.webp"

    try:
        supabase_client.storage.from_('thumbnails').upload(
            path=filepath,
            file=buffer.getvalue(),
            file_options={"content-type": "image/webp"}
        )

        public_url = supabase_client.storage.from_('thumbnails').get_public_url(filepath)
        return public_url
    except Exception as e:
        raise Exception(f"could not save thumbnail to storage: {str(e)}")
    
#JSON METHODS

def haversine_distance(lat1, lon1, lat2, lon2):
    
    R = 3440.065 # earth radius in nautical miles
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return 2 * R * asin(sqrt(a))

def calculate_json_distance(coords):
    total_dist = 0
    for i in range(len(coords) - 1):
        lon1, lat1 = coords[i][0], coords[i][1]
        lon2, lat2 = coords[i+1][0], coords[i+1][1]
        
        total_dist += haversine_distance(lat1, lon1, lat2, lon2) 
        
    return total_dist

def process_json_data(json_data):
    props = json_data.get("properties", {})
    coords = json_data.get("geometry", {}).get("coordinates", [])
    times = props.get("times", [])
    
    
    adapted_points = [PointAdapter(c[0], c[1], times[i] if i < len(times) else None) 
                      for i, c in enumerate(coords)]
    
    total_distance_nm = calculate_json_distance(coords)

    json_segment = SegmentAdapter(adapted_points, total_distance_nm)
    
    
    json_track = type('Json_track', (object,), {'name': props.get("name")})

    try:
        payload = new_track_object(json_track, json_segment)
        track_id = add_tracks(payload)
        return {"name": json_track.name, "status": "success", "id": track_id}
    except Exception as e:
        return {"name": json_track.name, "status": "error", "message": str(e)}


