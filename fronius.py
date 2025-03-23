import os
from flask import Flask, jsonify, render_template, request
import requests
from datetime import datetime
import pytz
import sqlite3
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# Configuration constants - can be overridden by environment variables
INVERTER_IP = os.getenv('FRONIUS_INVERTER_IP', '192.168.68.250')
DATABASE = os.getenv('FRONIUS_DATABASE', 'power_data.db')
TIMEZONE = os.getenv('FRONIUS_TIMEZONE', 'Australia/Sydney')
POLL_INTERVAL = int(os.getenv('FRONIUS_POLL_INTERVAL', '10'))  # seconds
PORT = int(os.getenv('FRONIUS_PORT', '8080'))
HOST = os.getenv('FRONIUS_HOST', '0.0.0.0')
IMPORT_RATE = float(os.getenv('FRONIUS_IMPORT_RATE', '0.297'))  # $ per kWh
EXPORT_RATE = float(os.getenv('FRONIUS_EXPORT_RATE', '0.035'))  # $ per kWh

# Initialize SQLite database
def init_db():
    """Initialize SQLite database with the power_data table if it doesn't exist.
    
    Table Schema:
    - id: Auto-incrementing primary key
    - timestamp: Timestamp of the reading in ISO format
    - p_grid: Power flow to/from grid in watts (positive = drawing, negative = feeding)
    - p_load: Total household power consumption in watts
    - status: Current status ('pulling' or 'generating')
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    # Create table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS power_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            p_grid REAL NOT NULL,
            p_load REAL,
            status TEXT NOT NULL
        )
    ''')
    # Add index on timestamp if it doesn't exist
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_timestamp 
        ON power_data(timestamp)
    ''')
    conn.commit()
    conn.close()

# Function to collect data from the inverter and store it in the database
def collect_data():
    """Fetch real-time power data from Fronius inverter and store in database."""
    try:
        url = f"http://{INVERTER_IP}/solar_api/v1/GetPowerFlowRealtimeData.fcgi"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()

        site_data = data.get('Body', {}).get('Data', {}).get('Site', {})
        if not site_data:
            app.logger.error("Invalid API response structure")
            return

        p_grid = site_data.get('P_Grid', 0.0)
        p_pv = site_data.get('P_PV', 0.0)
        p_load = site_data.get('P_Load', None)

        if p_load is None:
            p_load = p_pv - p_grid

        status = "pulling" if p_grid > 0 else "generating"

        # Get the configured timezone
        local_tz = pytz.timezone(TIMEZONE)
        local_time = datetime.now(local_tz).isoformat()

        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO power_data (timestamp, p_grid, p_load, status)
                VALUES (?, ?, ?, ?)
            ''', (local_time, p_grid, p_load, status))

        app.logger.info(f"Data collected at {local_time}")
    except requests.RequestException as e:
        app.logger.error(f"Error connecting to inverter: {e}")
    except Exception as e:
        app.logger.error(f"Error collecting data: {e}")

# Home route serving the main HTML page
@app.route("/")
def home():
    return render_template("index.html")

# API route to retrieve the latest net power data
@app.route("/net_power")
def net_power():
    """API endpoint returning latest power reading from database.
    
    Returns JSON with:
    - timestamp: Time of reading
    - p_grid: Power exchange with grid (W)
    - p_load: House consumption (W)
    - status: 'pulling' or 'generating'
    """
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT timestamp, p_grid, p_load, status FROM power_data
            ORDER BY id DESC LIMIT 1
        ''')
        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({"error": "No data available"})

        timestamp, p_grid, p_load, status = row
        return jsonify({
            "timestamp": timestamp,
            "p_grid": p_grid,
            "p_load": p_load,
            "status": status
        })
    except Exception as e:
        return jsonify({"error": str(e)})

# API route to retrieve historical data within a time range
@app.route("/historical_data")
def historical_data():
    """API endpoint returning historical power data within specified time range."""
    try:
        start = request.args.get('start', '')
        end = request.args.get('end', '')

        local_tz = pytz.timezone(TIMEZONE)

        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()

            if start and end:
                start_time = datetime.fromisoformat(start).astimezone(local_tz)
                end_time = datetime.fromisoformat(end).astimezone(local_tz)
            else:
                now = datetime.now(local_tz)
                start_time = datetime(now.year, now.month, now.day, tzinfo=local_tz)
                end_time = now

            # Calculate time difference in hours
            hours_diff = (end_time - start_time).total_seconds() / 3600

            # Choose aggregation interval based on time range
            if hours_diff <= 24:
                # Hourly aggregation for up to 24 hours
                group_by = "strftime('%Y-%m-%d %H:00', timestamp)"
                interval = "hour"
            elif hours_diff <= 24 * 30:
                # Daily aggregation for up to 30 days
                group_by = "strftime('%Y-%m-%d', timestamp)"
                interval = "day"
            else:
                # Weekly aggregation for longer periods
                group_by = "strftime('%Y-%W', timestamp)"
                interval = "week"

            # Perform aggregation in SQL
            query = f"""
                WITH time_series AS (
                    SELECT 
                        {group_by} as period,
                        AVG(p_grid) as avg_p_grid,
                        AVG(p_load) as avg_p_load,
                        MIN(timestamp) as period_start,
                        MAX(timestamp) as period_end
                    FROM power_data
                    WHERE timestamp BETWEEN ? AND ?
                    GROUP BY period
                    ORDER BY period
                )
                SELECT 
                    period_start as timestamp,
                    avg_p_grid as p_grid,
                    avg_p_load as p_load,
                    CASE WHEN avg_p_grid > 0 THEN 'pulling' ELSE 'generating' END as status,
                    (julianday(period_end) - julianday(period_start)) * 24 as duration_hours
                FROM time_series
            """
            
            cursor.execute(query, (start_time.isoformat(), end_time.isoformat()))
            rows = cursor.fetchall()

            if not rows:
                return jsonify({"error": "No data available for the selected time range."})

            filtered_data = []
            total_cost = 0.0
            total_kWh_drawn = 0.0
            total_kWh_generated = 0.0

            for row in rows:
                timestamp, p_grid, p_load, status, duration_hours = row
                
                # Calculate energy in kWh
                energy_kWh = (p_grid / 1000) * duration_hours

                if p_grid > 0:
                    total_kWh_drawn += energy_kWh
                    total_cost += energy_kWh * IMPORT_RATE
                elif p_grid < 0:
                    total_kWh_generated += abs(energy_kWh)
                    total_cost -= abs(energy_kWh) * EXPORT_RATE

                filtered_data.append({
                    "timestamp": timestamp,
                    "p_grid": energy_kWh,  # Store as kWh instead of watts
                    "p_load": p_load * duration_hours / 1000 if p_load is not None else None,
                    "status": status
                })

            return jsonify({
                "data": filtered_data,
                "total_cost": total_cost,
                "total_kWh_drawn": total_kWh_drawn,
                "total_kWh_generated": total_kWh_generated,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "interval": interval
            })

    except Exception as e:
        app.logger.error(f"Error retrieving historical data: {e}")
        return jsonify({"error": str(e)})

# Initialize database and set up data collection
if __name__ == "__main__":
    # Configure logging
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    init_db()
    app.logger.info("Database initialized")

    # Set up the scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=collect_data, trigger="interval", seconds=POLL_INTERVAL)
    scheduler.start()
    app.logger.info(f"Scheduler started with {POLL_INTERVAL} second interval")

    try:
        app.logger.info(f"Starting server on {HOST}:{PORT}")
        app.run(host=HOST, port=PORT, debug=False)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        app.logger.info("Application shutdown complete")
