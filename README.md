# Fronius Solar Power Monitor

A web-based monitoring application for Fronius solar inverters that provides real-time and historical power generation/consumption data visualization.

![Screenshot of Fronius Solar Power Monitor](assets/screenshot.png)

## Features

- Real-time power monitoring
- Historical data visualization with interactive charts
- Cost calculation based on power import/export rates
- Responsive web interface
- Automatic data collection every 10 seconds
- Local database storage for historical analysis

## Prerequisites

- Python 3.8 or higher
- Fronius inverter on the same network
- Network access to the inverter's API endpoint

## Installation

1. Clone this repository:
```bash
git clone https://github.com/josh-abram/fronius-solar-monitor
cd fronius-monitor
```

2. Install required dependencies:
```bash
pip install -r requirements.txt
```

3. Configure the application:
   - Copy `.env.example` to `.env`
   - Edit `.env` and update the configuration values as needed (see Configuration section below)

## Usage

1. Start the application:
```bash
python fronius.py
```

2. Access the web interface:
   - Open your browser and navigate to `http://localhost:8080`
   - For remote access within your network, use your machine's IP address

## Configuration

All configuration is managed through the `.env` file. Copy `.env.example` to `.env` and modify the following settings:

### Inverter Settings
- `FRONIUS_INVERTER_IP`: IP address of your Fronius inverter (default: 192.168.68.250)

### Database Settings  
- `FRONIUS_DATABASE`: SQLite database filename (default: power_data.db)

### Server Settings
- `SERVER_HOST`: Server host address (default: 0.0.0.0)
- `SERVER_PORT`: Server port (default: 8080)

### Data Collection
- `FRONIUS_POLL_INTERVAL`: Data collection interval in seconds (default: 10)

### Timezone
- `FRONIUS_TIMEZONE`: Timezone for data timestamps (default: Australia/Sydney)
  - Use IANA timezone names (e.g., 'America/New_York', 'Europe/London')

### Power Rates
- `FRONIUS_IMPORT_RATE`: Cost per kWh when importing from grid (default: 0.297)
- `FRONIUS_EXPORT_RATE`: Credit per kWh when exporting to grid (default: 0.035)

## Data Storage

The application uses SQLite for data storage:
- Database file: `power_data.db`
- Automatic table creation on first run
- Stores timestamp, grid power, load power, and status

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

- Built using Flask web framework
- Uses Chart.js for data visualization
- Designed for Fronius inverters using their Solar API