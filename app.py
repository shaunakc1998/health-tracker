import os
import base64
import requests
import logging
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import secrets
import json
import hashlib

# Database imports - use PostgreSQL on Render, SQLite locally
DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL:
    # Running on Render with PostgreSQL
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from urllib.parse import urlparse
    
    # Parse the DATABASE_URL
    result = urlparse(DATABASE_URL)
    db_config = {
        'database': result.path[1:],
        'user': result.username,
        'password': result.password,
        'host': result.hostname,
        'port': result.port
    }
else:
    # Running locally with SQLite
    import sqlite3

# --- 1. ROBUST LOGGING SETUP ---
# This will log detailed information to both the console and a file named app.log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

# --- CONFIGURATION ---
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FATSECRET_ACCESS_TOKEN = os.getenv("FATSECRET_ACCESS_TOKEN") # Switched to Access Token for simplicity

app = Flask(__name__, template_folder='templates', static_folder='static')

# IMPORTANT: Use a fixed secret key for session persistence across restarts
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    # Generate a persistent secret key if not in environment
    SECRET_KEY = 'your-fixed-secret-key-change-this-in-production-' + secrets.token_hex(16)
    logging.warning("Using generated SECRET_KEY. Set SECRET_KEY environment variable for production!")

app.secret_key = SECRET_KEY
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True if using HTTPS
app.config['SESSION_COOKIE_NAME'] = 'health_tracker_session'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)  # Session lasts 7 days
app.config['SESSION_REFRESH_EACH_REQUEST'] = False  # Don't refresh session on every request

DATABASE = 'database.db'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# --- 2. STARTUP CHECKS ---
if not GEMINI_API_KEY:
    logging.warning("GEMINI_API_KEY environment variable not set. Meal analysis will fail.")
if not FATSECRET_ACCESS_TOKEN:
    logging.warning("FATSECRET_ACCESS_TOKEN environment variable not set. Nutrition lookup will fail.")

# --- DATABASE HELPERS ---
def get_db():
    if DATABASE_URL:
        # PostgreSQL for production (Render)
        conn = psycopg2.connect(
            database=db_config['database'],
            user=db_config['user'],
            password=db_config['password'],
            host=db_config['host'],
            port=db_config['port'],
            cursor_factory=RealDictCursor
        )
        return conn
    else:
        # SQLite for local development
        db = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        return db

def execute_db_query(query, params=None, commit=False, fetchone=False):
    """Execute a database query with proper parameter handling for both PostgreSQL and SQLite"""
    db = get_db()
    cursor = db.cursor()
    
    # Convert query for PostgreSQL if needed
    if DATABASE_URL:
        # Replace ? with %s for PostgreSQL
        query = query.replace('?', '%s')
        # Handle INSERT OR REPLACE
        if 'INSERT OR REPLACE' in query:
            # Extract table and columns for ON CONFLICT
            import re
            match = re.search(r'INSERT OR REPLACE INTO (\w+)\s*\((.*?)\)', query)
            if match:
                table = match.group(1)
                columns = match.group(2)
                # Assume first column is unique
                first_col = columns.split(',')[0].strip()
                query = query.replace('INSERT OR REPLACE', 'INSERT')
                query = query.rstrip(')') + f') ON CONFLICT ({first_col}) DO UPDATE SET '
                # Add update clause for all columns
                col_list = [c.strip() for c in columns.split(',')]
                updates = [f"{c} = EXCLUDED.{c}" for c in col_list if c != first_col]
                query += ', '.join(updates)
    
    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        if commit:
            db.commit()
        
        if fetchone:
            result = cursor.fetchone()
        else:
            result = cursor.fetchall()
        
        # Get lastrowid for inserts
        if query.strip().upper().startswith('INSERT'):
            if DATABASE_URL:
                # For PostgreSQL, we need to add RETURNING id
                if 'RETURNING id' not in query:
                    db.close()
                    # Re-execute with RETURNING
                    db = get_db()
                    cursor = db.cursor()
                    query = query.rstrip(';') + ' RETURNING id'
                    if params:
                        cursor.execute(query, params)
                    else:
                        cursor.execute(query)
                    if commit:
                        db.commit()
                    result = cursor.fetchone()
                    lastrowid = result['id'] if result else None
                else:
                    lastrowid = result['id'] if result else None
            else:
                lastrowid = cursor.lastrowid
            cursor.close()
            db.close()
            return lastrowid
        
        cursor.close()
        db.close()
        return result
        
    except Exception as e:
        db.close()
        raise e

def execute_query(query, params=None, commit=False):
    """Execute a query with proper cursor handling for both databases"""
    db = get_db()
    
    if DATABASE_URL:
        # PostgreSQL
        cursor = db.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        if commit:
            db.commit()
            
        if query.strip().upper().startswith('SELECT'):
            result = cursor.fetchall()
            cursor.close()
            db.close()
            return result
        elif query.strip().upper().startswith('INSERT'):
            # Get the last inserted id for PostgreSQL
            if 'RETURNING id' not in query:
                query = query.rstrip(';') + ' RETURNING id'
                cursor.execute(query, params)
            last_id = cursor.fetchone()['id'] if cursor.rowcount > 0 else None
            if commit:
                db.commit()
            cursor.close()
            db.close()
            return last_id
        else:
            cursor.close()
            db.close()
            return None
    else:
        # SQLite
        cursor = db.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        if commit:
            db.commit()
            
        if query.strip().upper().startswith('SELECT'):
            result = cursor.fetchall()
        elif query.strip().upper().startswith('INSERT'):
            result = cursor.lastrowid
        else:
            result = None
            
        db.close()
        return result

def init_db():
    with app.app_context():
        db = get_db()
        
        if DATABASE_URL:
            # PostgreSQL schema
            cursor = db.cursor()
            
            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(255) UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    email VARCHAR(255) UNIQUE,
                    created_at TIMESTAMP NOT NULL,
                    name VARCHAR(255),
                    age INTEGER,
                    height REAL,
                    target_calories INTEGER DEFAULT 2000
                )
            ''')
        else:
            # SQLite schema
            cursor = db.cursor()
            
            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    email TEXT UNIQUE,
                    created_at TEXT NOT NULL,
                    name TEXT,
                    age INTEGER,
                    height REAL,
                    target_calories INTEGER DEFAULT 2000
                )
            ''')
        
        # Vitals table
        if DATABASE_URL:
            # PostgreSQL
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS vitals (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    date DATE NOT NULL,
                    weight REAL,
                    bmi REAL,
                    body_fat_percentage REAL,
                    skeletal_muscle_percentage REAL,
                    fat_free_mass REAL,
                    subcutaneous_fat REAL,
                    visceral_fat REAL,
                    body_water_percentage REAL,
                    muscle_mass REAL,
                    bone_mass REAL,
                    protein_percentage REAL,
                    bmr REAL,
                    metabolic_age INTEGER,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
        else:
            # SQLite
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS vitals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    weight REAL,
                    bmi REAL,
                    body_fat_percentage REAL,
                    skeletal_muscle_percentage REAL,
                    fat_free_mass REAL,
                    subcutaneous_fat REAL,
                    visceral_fat REAL,
                    body_water_percentage REAL,
                    muscle_mass REAL,
                    bone_mass REAL,
                    protein_percentage REAL,
                    bmr REAL,
                    metabolic_age INTEGER,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
        
        # Meals table
        if DATABASE_URL:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS meals (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    date DATE NOT NULL,
                    meal_type VARCHAR(50) NOT NULL,
                    food_items TEXT,
                    calories REAL,
                    protein REAL,
                    fat REAL,
                    carbohydrates REAL,
                    image_data TEXT,
                    created_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
        else:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS meals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    meal_type TEXT NOT NULL,
                    food_items TEXT,
                    calories REAL,
                    protein REAL,
                    fat REAL,
                    carbohydrates REAL,
                    image_data TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
        
        # Activities table
        if DATABASE_URL:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS activities (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    date DATE NOT NULL,
                    activity_name VARCHAR(255) NOT NULL,
                    duration_minutes INTEGER,
                    calories_burned REAL,
                    notes TEXT,
                    created_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
        else:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS activities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    activity_name TEXT NOT NULL,
                    duration_minutes INTEGER,
                    calories_burned REAL,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
        
        # Daily summary table
        if DATABASE_URL:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_summary (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    date DATE NOT NULL,
                    total_calories_consumed REAL DEFAULT 0,
                    total_calories_burned REAL DEFAULT 0,
                    net_calories REAL DEFAULT 0,
                    total_protein REAL DEFAULT 0,
                    total_fat REAL DEFAULT 0,
                    total_carbs REAL DEFAULT 0,
                    water_intake_ml REAL DEFAULT 0,
                    notes TEXT,
                    UNIQUE(user_id, date),
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
        else:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_summary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    total_calories_consumed REAL DEFAULT 0,
                    total_calories_burned REAL DEFAULT 0,
                    net_calories REAL DEFAULT 0,
                    total_protein REAL DEFAULT 0,
                    total_fat REAL DEFAULT 0,
                    total_carbs REAL DEFAULT 0,
                    water_intake_ml REAL DEFAULT 0,
                    notes TEXT,
                    UNIQUE(user_id, date),
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
        
        # Cache tables
        if DATABASE_URL:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS api_cache (
                    id SERIAL PRIMARY KEY,
                    cache_key VARCHAR(255) UNIQUE NOT NULL,
                    response_data TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    expires_at TIMESTAMP NOT NULL
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS food_cache (
                    id SERIAL PRIMARY KEY,
                    food_name VARCHAR(255) UNIQUE NOT NULL,
                    calories REAL,
                    protein REAL,
                    fat REAL,
                    carbohydrates REAL,
                    serving_size VARCHAR(50) DEFAULT '100g',
                    last_updated TIMESTAMP NOT NULL
                )
            ''')
        else:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS api_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cache_key TEXT UNIQUE NOT NULL,
                    response_data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS food_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    food_name TEXT UNIQUE NOT NULL,
                    calories REAL,
                    protein REAL,
                    fat REAL,
                    carbohydrates REAL,
                    serving_size TEXT DEFAULT '100g',
                    last_updated TEXT NOT NULL
                )
            ''')
        
        db.commit()


# --- EXTERNAL API HELPERS ---
def allowed_file(filename):
    """Checks if the file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_cache_key(data_string):
    """Generate a cache key from input data"""
    return hashlib.md5(data_string.encode()).hexdigest()

def get_cached_response(cache_key, cache_type='api_cache'):
    """Check if we have a cached response"""
    db = get_db()
    cursor = db.cursor()
    
    if DATABASE_URL:
        cursor.execute(f'''
            SELECT response_data FROM {cache_type}
            WHERE cache_key = %s AND expires_at > %s
        ''', (cache_key, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    else:
        cursor.execute(f'''
            SELECT response_data FROM {cache_type}
            WHERE cache_key = ? AND expires_at > ?
        ''', (cache_key, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    
    result = cursor.fetchone()
    db.close()
    if result:
        logging.info(f"Cache hit for key: {cache_key[:8]}...")
        return json.loads(result['response_data'])
    return None

def save_to_cache(cache_key, data, hours=24):
    """Save response to cache"""
    db = get_db()
    cursor = db.cursor()
    
    expires_at = (datetime.now() + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    
    if DATABASE_URL:
        cursor.execute('''
            INSERT INTO api_cache (cache_key, response_data, created_at, expires_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (cache_key) DO UPDATE SET
                response_data = EXCLUDED.response_data,
                created_at = EXCLUDED.created_at,
                expires_at = EXCLUDED.expires_at
        ''', (cache_key, json.dumps(data), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), expires_at))
    else:
        cursor.execute('''
            INSERT OR REPLACE INTO api_cache (cache_key, response_data, created_at, expires_at)
            VALUES (?, ?, ?, ?)
        ''', (cache_key, json.dumps(data), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), expires_at))
    
    db.commit()
    db.close()
    logging.info(f"Cached response for key: {cache_key[:8]}...")

def analyze_image_with_gemini(image_data_base64):
    """Analyze image with Gemini API - with caching"""
    
    # Check cache first (cache for 7 days for same images)
    cache_key = get_cache_key(image_data_base64[:100])  # Use first 100 chars for key
    cached_result = get_cached_response(cache_key)
    if cached_result:
        return cached_result
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    # More efficient prompt - ask for less verbose response
    prompt = "List only the food items in this image, separated by commas. Be concise. Example: eggs, toast, coffee"
    
    payload = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": image_data_base64}}]}]}
    
    try:
        logging.info("Calling Gemini API...")
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        
        text_content = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
        if not text_content:
            logging.warning("Gemini API returned an empty response.")
            return []
        
        logging.info(f"Gemini API identified: {text_content}")
        food_items = [item.strip() for item in text_content.split(',')]
        
        # Cache the result for 7 days
        save_to_cache(cache_key, food_items, hours=168)
        
        return food_items

    except requests.exceptions.RequestException as e:
        logging.error(f"Error calling Gemini API: {e}")
        return None
    except (KeyError, IndexError) as e:
        logging.error(f"Error parsing Gemini response: {e} | Response: {result}")
        return None

def get_cached_food_nutrition(food_name):
    """Get nutrition from local cache"""
    db = get_db()
    cursor = db.cursor()
    
    if DATABASE_URL:
        cursor.execute('''
            SELECT calories, protein, fat, carbohydrates 
            FROM food_cache 
            WHERE LOWER(food_name) = LOWER(%s)
        ''', (food_name,))
    else:
        cursor.execute('''
            SELECT calories, protein, fat, carbohydrates 
            FROM food_cache 
            WHERE LOWER(food_name) = LOWER(?)
        ''', (food_name,))
    
    result = cursor.fetchone()
    db.close()
    if result:
        logging.info(f"Found cached nutrition for: {food_name}")
        return {
            "calories": result['calories'] * 1.5,  # Adjust for serving size
            "protein": result['protein'] * 1.5,
            "fat": result['fat'] * 1.5,
            "carbohydrates": result['carbohydrates'] * 1.5
        }
    return None

def save_food_to_cache(food_name, nutrition):
    """Save food nutrition to cache"""
    db = get_db()
    cursor = db.cursor()
    
    # Save base values (per 100g)
    if DATABASE_URL:
        cursor.execute('''
            INSERT INTO food_cache 
            (food_name, calories, protein, fat, carbohydrates, last_updated)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (food_name) DO UPDATE SET
                calories = EXCLUDED.calories,
                protein = EXCLUDED.protein,
                fat = EXCLUDED.fat,
                carbohydrates = EXCLUDED.carbohydrates,
                last_updated = EXCLUDED.last_updated
        ''', (food_name, 
              nutrition['calories'] / 1.5,  # Store per 100g
              nutrition['protein'] / 1.5,
              nutrition['fat'] / 1.5,
              nutrition['carbohydrates'] / 1.5,
              datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    else:
        cursor.execute('''
            INSERT OR REPLACE INTO food_cache 
            (food_name, calories, protein, fat, carbohydrates, last_updated)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (food_name, 
              nutrition['calories'] / 1.5,  # Store per 100g
              nutrition['protein'] / 1.5,
              nutrition['fat'] / 1.5,
              nutrition['carbohydrates'] / 1.5,
              datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    
    db.commit()
    db.close()

def get_nutrition_from_fatsecret(food_item):
    """
    Get nutrition with caching to minimize API calls
    """
    # First check local cache
    cached_nutrition = get_cached_food_nutrition(food_item)
    if cached_nutrition:
        return cached_nutrition
    
    # Built-in nutrition database (per 100g serving)
    NUTRITION_ESTIMATES = {
        'chicken': {"calories": 165, "protein": 31, "fat": 3.6, "carbohydrates": 0},
        'potato': {"calories": 77, "protein": 2, "fat": 0.1, "carbohydrates": 17},
        'green beans': {"calories": 31, "protein": 1.8, "fat": 0.2, "carbohydrates": 7},
        'butternut squash': {"calories": 45, "protein": 1, "fat": 0.1, "carbohydrates": 12},
        'rice': {"calories": 130, "protein": 2.7, "fat": 0.3, "carbohydrates": 28},
        'bread': {"calories": 265, "protein": 9, "fat": 3.2, "carbohydrates": 49},
        'egg': {"calories": 155, "protein": 13, "fat": 11, "carbohydrates": 1.1},
        'salmon': {"calories": 208, "protein": 20, "fat": 13, "carbohydrates": 0},
        'beef': {"calories": 250, "protein": 26, "fat": 15, "carbohydrates": 0},
        'pasta': {"calories": 131, "protein": 5, "fat": 1.1, "carbohydrates": 25},
        'apple': {"calories": 52, "protein": 0.3, "fat": 0.2, "carbohydrates": 14},
        'banana': {"calories": 89, "protein": 1.1, "fat": 0.3, "carbohydrates": 23},
        'broccoli': {"calories": 34, "protein": 2.8, "fat": 0.4, "carbohydrates": 7},
        'carrot': {"calories": 41, "protein": 0.9, "fat": 0.2, "carbohydrates": 10},
        'cheese': {"calories": 402, "protein": 25, "fat": 33, "carbohydrates": 1.3},
        'milk': {"calories": 42, "protein": 3.4, "fat": 1, "carbohydrates": 5},
        'yogurt': {"calories": 59, "protein": 10, "fat": 0.4, "carbohydrates": 3.6},
        'avocado': {"calories": 160, "protein": 2, "fat": 15, "carbohydrates": 9},
        'tomato': {"calories": 18, "protein": 0.9, "fat": 0.2, "carbohydrates": 3.9},
        'lettuce': {"calories": 15, "protein": 1.4, "fat": 0.2, "carbohydrates": 2.9}
    }
    
    # Try to match food item with estimates
    food_lower = food_item.lower().strip().rstrip('.')
    
    # First try exact match
    for key, nutrition in NUTRITION_ESTIMATES.items():
        if key in food_lower or food_lower in key:
            logging.info(f"Using estimated nutrition for '{food_item}' (matched with '{key}')")
            # Adjust for typical serving size (assuming ~150g average serving)
            result = {
                "calories": nutrition["calories"] * 1.5,
                "protein": nutrition["protein"] * 1.5,
                "fat": nutrition["fat"] * 1.5,
                "carbohydrates": nutrition["carbohydrates"] * 1.5
            }
            # Save to cache for future use
            save_food_to_cache(food_item, result)
            return result
    
    if not FATSECRET_ACCESS_TOKEN:
        logging.warning(f"No nutrition estimate found for '{food_item}' and FatSecret token not configured")
        # Return generic values for unknown foods
        return {"calories": 100, "protein": 5, "fat": 3, "carbohydrates": 15}

    # Try FatSecret API if token is available
    url = "https://platform.fatsecret.com/rest/server.api"
    params = {
        "method": "foods.search",
        "search_expression": food_item,
        "format": "json"
    }
    headers = {"Authorization": f"Bearer {FATSECRET_ACCESS_TOKEN}"}
    
    try:
        logging.info(f"Calling FatSecret API for '{food_item}'...")
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        # Log the response for debugging
        logging.debug(f"FatSecret response for '{food_item}': {data}")
        
        # Check if we got an error response
        if 'error' in data:
            logging.error(f"FatSecret API error: {data['error']}")
            # Return generic values
            return {"calories": 100, "protein": 5, "fat": 3, "carbohydrates": 15}
        
        # Try to parse the response
        foods = data.get('foods', {})
        if not foods:
            logging.warning(f"No foods found in FatSecret response for '{food_item}'")
            return {"calories": 100, "protein": 5, "fat": 3, "carbohydrates": 15}
            
        food_list = foods.get('food', [])
        if not food_list:
            logging.warning(f"Empty food list in FatSecret response for '{food_item}'")
            return {"calories": 100, "protein": 5, "fat": 3, "carbohydrates": 15}
            
        # Handle both single food and list of foods
        if isinstance(food_list, dict):
            food = food_list
        else:
            food = food_list[0] if food_list else {}
            
        description = food.get('food_description', '')
        
        if not description:
            logging.warning(f"No food description in FatSecret response for '{food_item}'")
            return {"calories": 100, "protein": 5, "fat": 3, "carbohydrates": 15}
        
        # Parse nutrition from description
        # Format: "Per 100g - Calories: 165kcal | Fat: 3.57g | Carbs: 0.00g | Protein: 31.02g"
        nutrition = {"calories": 0, "protein": 0, "fat": 0, "carbohydrates": 0}
        
        parts = description.split('|')
        for part in parts:
            part = part.strip()
            if 'Calories:' in part:
                try:
                    cal_str = part.split(':')[1].strip()
                    nutrition['calories'] = float(cal_str.replace('kcal', ''))
                except:
                    pass
            elif 'Fat:' in part:
                try:
                    fat_str = part.split(':')[1].strip()
                    nutrition['fat'] = float(fat_str.replace('g', ''))
                except:
                    pass
            elif 'Carbs:' in part:
                try:
                    carb_str = part.split(':')[1].strip()
                    nutrition['carbohydrates'] = float(carb_str.replace('g', ''))
                except:
                    pass
            elif 'Protein:' in part:
                try:
                    prot_str = part.split(':')[1].strip()
                    nutrition['protein'] = float(prot_str.replace('g', ''))
                except:
                    pass
        
        # If we got valid nutrition data, return it
        if any(v > 0 for v in nutrition.values()):
            logging.info(f"Successfully parsed FatSecret nutrition for '{food_item}': {nutrition}")
            return nutrition
        else:
            logging.warning(f"Could not parse nutrition from FatSecret for '{food_item}'")
            return {"calories": 100, "protein": 5, "fat": 3, "carbohydrates": 15}

    except requests.exceptions.RequestException as e:
        logging.error(f"Error calling FatSecret API: {e}")
        return {"calories": 100, "protein": 5, "fat": 3, "carbohydrates": 15}
    except Exception as e:
        logging.error(f"Unexpected error parsing FatSecret response for '{food_item}': {e}")
        return {"calories": 100, "protein": 5, "fat": 3, "carbohydrates": 15}

# --- AUTHENTICATION HELPERS ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            # Check if it's an API request or a page request
            if request.path.startswith('/api/'):
                return jsonify({"status": "error", "message": "Login required"}), 401
            else:
                return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

def update_daily_summary(user_id, date_str):
    """Update daily summary with totals from meals and activities"""
    db = get_db()
    cursor = db.cursor()
    
    # Get total calories consumed
    cursor.execute('''
        SELECT SUM(calories) as total_cal, SUM(protein) as total_prot, 
               SUM(fat) as total_fat, SUM(carbohydrates) as total_carbs
        FROM meals 
        WHERE user_id = ? AND date = ?
    ''', (user_id, date_str))
    meal_totals = cursor.fetchone()
    
    # Get total calories burned
    cursor.execute('''
        SELECT SUM(calories_burned) as total_burned
        FROM activities 
        WHERE user_id = ? AND date = ?
    ''', (user_id, date_str))
    activity_totals = cursor.fetchone()
    
    total_consumed = meal_totals['total_cal'] or 0
    total_burned = activity_totals['total_burned'] or 0
    net_calories = total_consumed - total_burned
    
    # Update or insert daily summary
    cursor.execute('''
        INSERT OR REPLACE INTO daily_summary 
        (user_id, date, total_calories_consumed, total_calories_burned, net_calories,
         total_protein, total_fat, total_carbs)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, date_str, total_consumed, total_burned, net_calories,
          meal_totals['total_prot'] or 0, meal_totals['total_fat'] or 0, 
          meal_totals['total_carbs'] or 0))
    
    db.commit()

# --- API ENDPOINTS ---
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login_page'))

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('dashboard.html')

# --- AUTHENTICATION ENDPOINTS ---
@app.route('/api/signup', methods=['POST'])
def signup():
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        email = data.get('email', '').strip()
        name = data.get('name', '').strip()
        
        # Validation
        if not username or not password:
            return jsonify({"status": "error", "message": "Username and password are required"}), 400
        
        if len(username) < 3:
            return jsonify({"status": "error", "message": "Username must be at least 3 characters"}), 400
        
        if len(password) < 6:
            return jsonify({"status": "error", "message": "Password must be at least 6 characters"}), 400
        
        if not username.replace('_', '').isalnum():
            return jsonify({"status": "error", "message": "Username can only contain letters, numbers, and underscores"}), 400
        
        if email and '@' not in email:
            return jsonify({"status": "error", "message": "Invalid email format"}), 400
        
        db = get_db()
        cursor = db.cursor()
        
        # Check if user exists
        cursor.execute('SELECT id FROM users WHERE username = ? OR (email = ? AND email != "")', 
                      (username, email))
        if cursor.fetchone():
            return jsonify({"status": "error", "message": "Username or email already exists"}), 400
        
        # Create user
        password_hash = generate_password_hash(password)
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute('''
            INSERT INTO users (username, password_hash, email, name, created_at, target_calories)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (username, password_hash, email or None, name or username, created_at, 2000))
        
        db.commit()
        
        # Auto-login after signup
        user_id = cursor.lastrowid
        session['user_id'] = user_id
        session['username'] = username
        session.permanent = True  # Make session permanent on signup
        
        logging.info(f"New user registered: {username} (ID: {user_id})")
        return jsonify({"status": "success", "message": "Account created successfully", "user_id": user_id}), 201
        
    except Exception as e:
        logging.error(f"Signup error: {e}")
        return jsonify({"status": "error", "message": "An error occurred during signup"}), 500

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        remember = data.get('remember', False)
        
        if not username or not password:
            return jsonify({"status": "error", "message": "Username and password are required"}), 400
        
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('SELECT id, password_hash FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        
        if not user or not check_password_hash(user['password_hash'], password):
            logging.warning(f"Failed login attempt for username: {username}")
            return jsonify({"status": "error", "message": "Invalid username or password"}), 401
        
        session['user_id'] = user['id']
        session['username'] = username
        
        # Make session permanent if "remember me" is checked
        if remember:
            session.permanent = True
        
        logging.info(f"User logged in: {username}")
        return jsonify({"status": "success", "message": "Logged in successfully"}), 200
        
    except Exception as e:
        logging.error(f"Login error: {e}")
        return jsonify({"status": "error", "message": "An error occurred during login"}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"status": "success", "message": "Logged out successfully"}), 200

@app.route('/api/user/profile', methods=['GET', 'PUT'])
@login_required
def user_profile():
    try:
        user_id = session['user_id']
        db = get_db()
        cursor = db.cursor()
        
        if request.method == 'GET':
            cursor.execute('SELECT username, email, name, age, height, target_calories FROM users WHERE id = ?', (user_id,))
            user = cursor.fetchone()
            if user:
                return jsonify(dict(user))
            return jsonify({"status": "error", "message": "User not found"}), 404
        
        else:  # PUT
            data = request.json
            
            # Validation
            age = data.get('age')
            height = data.get('height')
            target_calories = data.get('target_calories', 2000)
            
            if age is not None:
                try:
                    age = int(age)
                    if age < 1 or age > 150:
                        return jsonify({"status": "error", "message": "Invalid age (must be 1-150)"}), 400
                except (ValueError, TypeError):
                    age = None
            
            if height is not None:
                try:
                    height = float(height)
                    if height < 50 or height > 300:
                        return jsonify({"status": "error", "message": "Invalid height (must be 50-300 cm)"}), 400
                except (ValueError, TypeError):
                    height = None
            
            try:
                target_calories = int(target_calories)
                if target_calories < 500 or target_calories > 10000:
                    return jsonify({"status": "error", "message": "Invalid calorie target (must be 500-10000)"}), 400
            except (ValueError, TypeError):
                target_calories = 2000
            
            cursor.execute('''
                UPDATE users 
                SET name = ?, age = ?, height = ?, target_calories = ?
                WHERE id = ?
            ''', (data.get('name'), age, height, target_calories, user_id))
            db.commit()
            return jsonify({"status": "success", "message": "Profile updated"}), 200
            
    except Exception as e:
        logging.error(f"Profile update error: {e}")
        return jsonify({"status": "error", "message": "Failed to update profile"}), 500

# --- VITALS ENDPOINTS ---
@app.route('/api/vitals', methods=['POST', 'GET'])
@login_required
def vitals_route():
    user_id = session['user_id']
    db = get_db()
    if request.method == 'POST':
        data = request.json
        date_str = data.get('date', datetime.now().strftime("%Y-%m-%d"))
        cursor = db.cursor()
        
        cursor.execute('''
            INSERT INTO vitals (user_id, date, weight, bmi, body_fat_percentage, 
                              skeletal_muscle_percentage, fat_free_mass, subcutaneous_fat, 
                              visceral_fat, body_water_percentage, muscle_mass, bone_mass, 
                              protein_percentage, bmr, metabolic_age) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, date_str, data.get('weight'), data.get('bmi'), 
              data.get('body_fat_percentage'), data.get('skeletal_muscle_percentage'),
              data.get('fat_free_mass'), data.get('subcutaneous_fat'), 
              data.get('visceral_fat'), data.get('body_water_percentage'),
              data.get('muscle_mass'), data.get('bone_mass'), 
              data.get('protein_percentage'), data.get('bmr'), data.get('metabolic_age')))
        
        db.commit()
        logging.info(f"New vitals entry added for user {user_id}")
        return jsonify({"status": "success", "message": "Vitals added successfully!"}), 201
    
    else:  # GET
        date_from = request.args.get('from', (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"))
        date_to = request.args.get('to', datetime.now().strftime("%Y-%m-%d"))
        
        cursor = db.cursor()
        cursor.execute('''
            SELECT * FROM vitals 
            WHERE user_id = ? AND date BETWEEN ? AND ?
            ORDER BY date ASC
        ''', (user_id, date_from, date_to))
        
        vitals = [dict(row) for row in cursor.fetchall()]
        return jsonify(vitals)

# --- MEAL ENDPOINTS ---
@app.route('/api/meal', methods=['POST', 'GET'])
@login_required
def meal_route():
    user_id = session['user_id']
    db = get_db()
    
    if request.method == 'GET':
        # Get meals for a specific date or date range
        date_str = request.args.get('date', datetime.now().strftime("%Y-%m-%d"))
        cursor = db.cursor()
        
        cursor.execute('''
            SELECT * FROM meals 
            WHERE user_id = ? AND date = ?
            ORDER BY 
                CASE meal_type 
                    WHEN 'breakfast' THEN 1 
                    WHEN 'lunch' THEN 2 
                    WHEN 'snacks' THEN 3 
                    WHEN 'dinner' THEN 4 
                END
        ''', (user_id, date_str))
        
        meals = [dict(row) for row in cursor.fetchall()]
        return jsonify(meals)
    
    else:  # POST - Add new meal
        meal_type = request.form.get('meal_type', 'snacks')
        date_str = request.form.get('date', datetime.now().strftime("%Y-%m-%d"))
        
        # Check if photo is provided for analysis
        if 'photo' in request.files and request.files['photo'].filename:
            return analyze_meal_with_photo(user_id, meal_type, date_str)
        else:
            # Manual entry
            data = request.get_json() if request.is_json else request.form
            return add_manual_meal(user_id, data, date_str)

def analyze_meal_with_photo(user_id, meal_type, date_str):
    """Analyze meal from photo and save to database"""
    logging.info(f"Analyzing meal photo for user {user_id}, meal type: {meal_type}")
    
    # Get database connection
    db = get_db()
    
    # Get portion multiplier from form (default to 1.5 for 150g if not provided)
    portion_multiplier = float(request.form.get('portion_multiplier', 1.5))
    
    # --- 5. BETTER FILE VALIDATION ---
    if 'photo' not in request.files or not request.files['photo'].filename:
        logging.warning("Meal analysis request failed: No photo provided.")
        return jsonify({"status": "error", "message": "No photo file provided."}), 400
        
    photo = request.files['photo']
    if not allowed_file(photo.filename):
        logging.warning(f"Meal analysis request failed: Invalid file type '{photo.filename}'.")
        return jsonify({"status": "error", "message": "Invalid file type. Please use JPG, JPEG, or PNG."}), 400
    
    try:
        image_bytes = photo.read()
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        food_items = analyze_image_with_gemini(image_base64)
        if food_items is None:
            return jsonify({"status": "error", "message": "Could not analyze image with AI. Check server logs."}), 500
        if not food_items:
            return jsonify({"status": "error", "message": "AI could not identify any food in the image."}), 400

        total_nutrition = {"calories": 0, "protein": 0, "fat": 0, "carbohydrates": 0}
        nutrition_breakdown = []  # Store individual item nutrition for logging
        
        # Apply user-selected portion multiplier instead of fixed 1.5
        for item in food_items:
            base_nutrition = get_nutrition_from_fatsecret(item)
            if base_nutrition:
                # Adjust nutrition based on user-selected portion size
                # Note: base_nutrition already has 1.5x multiplier, so we adjust from there
                adjustment_factor = portion_multiplier / 1.5
                adjusted_nutrition = {
                    "calories": base_nutrition["calories"] * adjustment_factor,
                    "protein": base_nutrition["protein"] * adjustment_factor,
                    "fat": base_nutrition["fat"] * adjustment_factor,
                    "carbohydrates": base_nutrition["carbohydrates"] * adjustment_factor
                }
                
                nutrition_breakdown.append({
                    "food": item,
                    "nutrition": adjusted_nutrition,
                    "portion_grams": portion_multiplier * 100  # Convert to grams for display
                })
                
                for key in total_nutrition:
                    total_nutrition[key] += adjusted_nutrition[key]
        
        # Log detailed breakdown with portion sizes
        logging.info("=" * 60)
        logging.info("MEAL NUTRITION BREAKDOWN:")
        logging.info(f"Identified foods: {', '.join(food_items)}")
        logging.info(f"Portion multiplier: {portion_multiplier} ({portion_multiplier * 100:.0f}g per item)")
        logging.info("-" * 60)
        for item_data in nutrition_breakdown:
            logging.info(f"Food: {item_data['food']} (~{item_data.get('portion_grams', 150):.0f}g)")
            logging.info(f"  Calories: {item_data['nutrition']['calories']:.1f} kcal")
            logging.info(f"  Protein: {item_data['nutrition']['protein']:.1f} g")
            logging.info(f"  Fat: {item_data['nutrition']['fat']:.1f} g")
            logging.info(f"  Carbs: {item_data['nutrition']['carbohydrates']:.1f} g")
        logging.info("-" * 60)
        logging.info(f"TOTAL NUTRITION:")
        logging.info(f"  Calories: {total_nutrition['calories']:.1f} kcal")
        logging.info(f"  Protein: {total_nutrition['protein']:.1f} g")
        logging.info(f"  Fat: {total_nutrition['fat']:.1f} g")
        logging.info(f"  Carbs: {total_nutrition['carbohydrates']:.1f} g")
        logging.info("=" * 60)
        
        # Save meal to database
        cursor = db.cursor()
        cursor.execute('''
            INSERT INTO meals (user_id, date, meal_type, food_items, calories, 
                             protein, fat, carbohydrates, image_data, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, date_str, meal_type, ', '.join(food_items),
              total_nutrition['calories'], total_nutrition['protein'],
              total_nutrition['fat'], total_nutrition['carbohydrates'],
              image_base64, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        
        db.commit()
        
        # Update daily summary
        update_daily_summary(user_id, date_str)
        
        # Include breakdown in response for transparency
        return jsonify({
            "status": "success",
            "meal_id": cursor.lastrowid,
            "meal_type": meal_type,
            "date": date_str,
            "food_items": food_items, 
            "nutrition": total_nutrition,
            "breakdown": nutrition_breakdown
        })

    except Exception as e:
        logging.error(f"An unexpected error occurred during meal analysis: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "An internal server error occurred."}), 500

def add_manual_meal(user_id, data, date_str):
    """Add meal with manual nutrition entry"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        meal_type = data.get('meal_type', 'snacks')
        food_items = data.get('food_items', '').strip()
        
        # Validate inputs
        if not food_items:
            return jsonify({"status": "error", "message": "Food items are required"}), 400
        
        try:
            calories = max(0, float(data.get('calories', 0)))
            protein = max(0, float(data.get('protein', 0)))
            fat = max(0, float(data.get('fat', 0)))
            carbohydrates = max(0, float(data.get('carbohydrates', 0)))
        except (ValueError, TypeError):
            return jsonify({"status": "error", "message": "Invalid nutrition values"}), 400
        
        # Sanity checks
        if calories > 5000:
            return jsonify({"status": "error", "message": "Calories value seems too high (max 5000)"}), 400
        
        cursor.execute('''
            INSERT INTO meals (user_id, date, meal_type, food_items, calories, 
                             protein, fat, carbohydrates, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, date_str, meal_type, food_items, calories, protein, 
              fat, carbohydrates, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        
        db.commit()
        
        # Update daily summary
        update_daily_summary(user_id, date_str)
        
        return jsonify({
            "status": "success",
            "meal_id": cursor.lastrowid,
            "message": "Meal added successfully"
        }), 201
        
    except Exception as e:
        logging.error(f"Error adding manual meal: {e}")
        return jsonify({"status": "error", "message": "Failed to add meal"}), 500

# --- ACTIVITY/EXERCISE ENDPOINTS ---
@app.route('/api/activity', methods=['POST', 'GET', 'DELETE'])
@login_required
def activity_route():
    try:
        user_id = session['user_id']
        db = get_db()
        cursor = db.cursor()
        
        if request.method == 'GET':
            date_str = request.args.get('date', datetime.now().strftime("%Y-%m-%d"))
            
            cursor.execute('''
                SELECT * FROM activities 
                WHERE user_id = ? AND date = ?
                ORDER BY created_at DESC
            ''', (user_id, date_str))
            
            activities = [dict(row) for row in cursor.fetchall()]
            return jsonify(activities)
        
        elif request.method == 'POST':
            data = request.json
            date_str = data.get('date', datetime.now().strftime("%Y-%m-%d"))
            
            # Validation
            activity_name = data.get('activity_name', '').strip()
            if not activity_name:
                return jsonify({"status": "error", "message": "Activity name is required"}), 400
            
            try:
                duration_minutes = max(0, int(data.get('duration_minutes', 0)))
                calories_burned = max(0, float(data.get('calories_burned', 0)))
            except (ValueError, TypeError):
                return jsonify({"status": "error", "message": "Invalid duration or calories value"}), 400
            
            if calories_burned > 2000:
                return jsonify({"status": "error", "message": "Calories burned seems too high (max 2000)"}), 400
            
            cursor.execute('''
                INSERT INTO activities (user_id, date, activity_name, duration_minutes, 
                                      calories_burned, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, date_str, activity_name, duration_minutes,
                  calories_burned, data.get('notes', ''),
                  datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            
            db.commit()
            
            # Update daily summary
            update_daily_summary(user_id, date_str)
            
            logging.info(f"Activity added for user {user_id}: {activity_name}")
            return jsonify({"status": "success", "activity_id": cursor.lastrowid}), 201
        
        else:  # DELETE
            activity_id = request.args.get('id')
            
            if not activity_id:
                return jsonify({"status": "error", "message": "Activity ID required"}), 400
            
            # Get date before deleting for summary update
            cursor.execute('SELECT date FROM activities WHERE id = ? AND user_id = ?', 
                          (activity_id, user_id))
            activity = cursor.fetchone()
            
            if activity:
                date_str = activity['date']
                cursor.execute('DELETE FROM activities WHERE id = ? AND user_id = ?', 
                             (activity_id, user_id))
                db.commit()
                
                # Update daily summary
                update_daily_summary(user_id, date_str)
                
                return jsonify({"status": "success", "message": "Activity deleted"}), 200
            
            return jsonify({"status": "error", "message": "Activity not found"}), 404
            
    except Exception as e:
        logging.error(f"Activity route error: {e}")
        return jsonify({"status": "error", "message": "An error occurred"}), 500

# --- DAILY SUMMARY ENDPOINT ---
@app.route('/api/daily-summary/<date_str>')
@login_required
def daily_summary(date_str):
    user_id = session['user_id']
    db = get_db()
    cursor = db.cursor()
    
    # Get or create daily summary
    cursor.execute('''
        SELECT * FROM daily_summary 
        WHERE user_id = ? AND date = ?
    ''', (user_id, date_str))
    
    summary = cursor.fetchone()
    
    if not summary:
        # Create summary if doesn't exist
        update_daily_summary(user_id, date_str)
        cursor.execute('''
            SELECT * FROM daily_summary 
            WHERE user_id = ? AND date = ?
        ''', (user_id, date_str))
        summary = cursor.fetchone()
    
    # Get user's target calories
    cursor.execute('SELECT target_calories FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    
    result = dict(summary) if summary else {}
    result['target_calories'] = user['target_calories'] if user else 2000
    result['remaining_calories'] = result['target_calories'] - (result.get('total_calories_consumed', 0) - result.get('total_calories_burned', 0))
    
    return jsonify(result)

# --- CALENDAR DATA ENDPOINT ---
@app.route('/api/calendar/<year>/<month>')
@login_required
def calendar_data(year, month):
    user_id = session['user_id']
    db = get_db()
    cursor = db.cursor()
    
    # Get all daily summaries for the month
    start_date = f"{year}-{month:02d}-01"
    if int(month) == 12:
        end_date = f"{int(year)+1}-01-01"
    else:
        end_date = f"{year}-{int(month)+1:02d}-01"
    
    cursor.execute('''
        SELECT date, total_calories_consumed, total_calories_burned, net_calories
        FROM daily_summary 
        WHERE user_id = ? AND date >= ? AND date < ?
    ''', (user_id, start_date, end_date))
    
    summaries = [dict(row) for row in cursor.fetchall()]
    
    # Get user's target for comparison
    cursor.execute('SELECT target_calories FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    target = user['target_calories'] if user else 2000
    
    # Format for calendar display
    calendar_data = {}
    for summary in summaries:
        day = int(summary['date'].split('-')[2])
        calendar_data[day] = {
            'consumed': summary['total_calories_consumed'],
            'burned': summary['total_calories_burned'],
            'net': summary['net_calories'],
            'status': 'good' if summary['net_calories'] <= target else 'over'
        }
    
    return jsonify(calendar_data)

# --- MAIN EXECUTION ---
# Initialize database on startup (for both local and production)
with app.app_context():
    try:
        init_db()
        logging.info("Database initialized successfully")
    except Exception as e:
        logging.error(f"Error initializing database: {e}")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
