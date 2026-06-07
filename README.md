Readme made using Gemini

# Sail Log Processor

This program processes sailing tracks from either a **GPX** or **GeoJSON** file, extracts relevant navigation metrics, and automatically saves the processed data to a database.

## Architecture & Hosting
* **Database:** Powered by [Supabase](https://supabase.com/) (PostgreSQL with PostGIS).
* **Hosting:** Deployed on [Render.com](https://render.com/).

> ⚠️ **Configuration Note:** Remember to update the database connection strings and file paths to match your own environment settings before running the program.

---

## Database Functions (RPC)

To handle complex spatial queries and automatic naming conventions, this backend relies on a custom database function.

### `insert_new_track`
This function is called when uploading a new track. It automatically detects nearby starting and ending marinas within a 1,000-meter radius using PostGIS geography types and formats the track name accordingly.

#### Arguments

| Parameter | Type | Format / Details |
| :--- | :--- | :--- |
| `p_date` | `string` | `timestamp with time zone` |
| `p_distance_nm` | `number` | `double precision` (Distance in Nautical Miles) |
| `p_duration_min` | `number` | `integer` (Duration in minutes) |
| `p_start_lat` | `number` | `double precision` |
| `p_start_lon` | `number` | `double precision` |
| `p_end_lat` | `number` | `double precision` |
| `p_end_lon` | `number` | `double precision` |
| `p_start_time` | `string` | `timestamp with time zone` |
| `p_end_time` | `string` | `timestamp with time zone` |
| `p_geom` | `string` | `extensions.geography` (Full track geography line) |
| `p_name` | `string` | `text` (Optional/Default name string) |
| `p_new_name` | `boolean`| `boolean` (Triggers automatic naming) |
| `p_notes` | `string` | `text` |
| `p_route_data` | `json` | `jsonb` |
| `p_thumbnail_url`| `string` | `text` |

#### SQL Function Definition

```sql
CREATE OR REPLACE FUNCTION insert_new_track(
  p_date timestamp with time zone,
  p_distance_nm double precision,
  p_duration_min integer,
  p_start_lat double precision,
  p_start_lon double precision,
  p_end_lat double precision,
  p_end_lon double precision,
  p_start_time timestamp with time zone,
  p_end_time timestamp with time zone,
  p_geom geography,
  p_name text,
  p_new_name boolean,
  p_notes text,
  p_route_data json,
  p_thumbnail_url text
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  v_track_id uuid;
  v_start_marina uuid;
  v_end_marina uuid;
  v_start_name text;
  v_end_name text;
  v_final_name text;
  v_date_str text;
BEGIN
  -- 1. Find start marina (Radius 1000m) using KNN distance operator (<->)
  SELECT id, name INTO v_start_marina, v_start_name
  FROM marinas 
  WHERE ST_DWithin(geom, ST_MakePoint(p_start_lon, p_start_lat)::geography, 1000)
  ORDER BY geom <-> ST_MakePoint(p_start_lon, p_start_lat)::geography 
  LIMIT 1;

  -- 2. Find end marina (Radius 1000m)
  SELECT id, name INTO v_end_marina, v_end_name
  FROM marinas 
  WHERE ST_DWithin(geom, ST_MakePoint(p_end_lon, p_end_lat)::geography, 1000)
  ORDER BY geom <-> ST_MakePoint(p_end_lon, p_end_lat)::geography 
  LIMIT 1;

  -- 3. Handle automatic track naming
  IF p_new_name = TRUE OR p_name IS NULL OR p_name = '' THEN
    -- Standardize date/time format
    v_date_str := COALESCE(
      regexp_replace(NULLIF(p_name, ''), '(\d{2})\.(\d{2})$', '\1:\2'), 
      to_char(p_date, 'DD.MM.YYYY HH24:MI')
    );

    -- Construct final name: "Start Marina - End Marina - Date"
    v_final_name := COALESCE(v_start_name, 'Ukendt havn') || ' - ' || 
                    COALESCE(v_end_name, 'Ukendt havn') || ' - ' || 
                    v_date_str;
  ELSE
    v_final_name := p_name;
  END IF;

  -- 4. Fallback safeguard
  IF v_final_name IS NULL OR v_final_name = '' THEN
    v_final_name := 'Uden navn - ' || to_char(p_date, 'DD.MM.YYYY HH24:MI');
  END IF;

  -- 5. Insert record into database
  INSERT INTO tracks (
    name,   
    date, 
    duration_min, 
    distance_nm, 
    route_data, 
    geom, 
    thumbnail_url, 
    notes, 
    start_time, 
    end_time,
    marina_start_id, 
    marina_end_id
  )
  VALUES (
    v_final_name, 
    p_date, 
    p_duration_min, 
    p_distance_nm, 
    p_route_data::jsonb,      
    p_geom::geography,        
    p_thumbnail_url, 
    p_notes, 
    p_start_time, 
    p_end_time,
    v_start_marina,
    v_end_marina
  )
  RETURNING id INTO v_track_id;

  RETURN v_track_id;

EXCEPTION WHEN OTHERS THEN
  RAISE EXCEPTION 'Error creating track: %', SQLERRM;
END;
$$;
