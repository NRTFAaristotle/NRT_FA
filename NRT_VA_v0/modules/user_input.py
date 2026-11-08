"""
user_input_M.py
User input and output selection for the Wildfire Rapid Assessment Tool.
The module:
- collects and validates event information;
- collects the LSA SAF credentials;
- allows the user to select the outputs to generate;
- stores the resulting configuration in a single object.
"""
from dataclasses import dataclass
from datetime import datetime
from getpass import getpass
from modules.download_auxiliary import _get_cdse_credentials

@dataclass
class UserConfig:
    fire_name: str

    start: datetime
    end: datetime

    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float

    user: str
    password: str

    output_perimeter: bool
    output_landcover: bool
    output_landcover_burned: bool
    output_activity: bool
    output_frp_propagator: bool
    output_histograms: bool
    output_statistics: bool
    output_emissions: bool

    product_frp: bool = True
    product_triangulation: bool = True
    product_geometry: bool = True

def _ask_fire_name():
    while True:
        value = input("Output name: ").strip()
        if value:
            return value
        print("Invalid input. Please enter a fire name.")

def _ask_datetime(prompt):
    while True:
        value = input(prompt).strip()
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            print("Invalid date/time format.")
            print("Use: YYYY-MM-DD HH:MM")
def _ask_end_datetime(start):
    while True:
        end = _ask_datetime("End date/time (YYYY-MM-DD HH:MM): ")
        if end > start:
            return end
        print("Invalid input. End date/time must be after the start date/time.")

def _ask_latitude(prompt):
    while True:
        try:
            value = float(input(prompt))
            if -90 <= value <= 90:
                return value
            raise ValueError
        except ValueError:
            print("Invalid latitude.")
            print("Latitude must be between -90 and 90.")

def _ask_longitude(prompt):
    while True:
        try:
            value = float(input(prompt))
            if -180 <= value <= 180:
                return value
            raise ValueError
        except ValueError:
            print("Invalid longitude.")
            print("Longitude must be between -180 and 180.")

def _ask_max_latitude(lat_min):
    while True:
        lat_max = _ask_latitude("Maximum latitude: ")
        if lat_max > lat_min:
            return lat_max
        print("Maximum latitude must be greater than minimum latitude.")

def _ask_max_longitude(lon_min):
    while True:
        lon_max = _ask_longitude("Maximum longitude: ")
        if lon_max > lon_min:
            return lon_max
        print("Maximum longitude must be greater than minimum longitude.")

def _ask_username():
    while True:
        value = input("Username: ").strip()
        if value:
            return value
        print("Invalid input. Username cannot be empty.")

def _ask_password():
    while True:
        value = getpass("Password: ")
        if value:
            return value
        print("Invalid input. Password cannot be empty.")

def _select_outputs():
    valid_outputs = {1, 2, 3, 4, 5, 6, 7, 8, 9}
    while True:
        print("=" * 55)
        print("OUTPUT SELECTION")
        print("=" * 55)
        print("Available outputs:")
        print("1 - Perimeter + Elevation + Rivers + Population + Hourly Growth")
        print("2 - Land Cover + Perimeter")
        print("3 - Land Cover + Perimeter + Burned Area")
        print("4 - Activity + Perimeter + Elevation + Rivers + Population")
        print("5 - FRP Propagator GIF")
        print("6 - Fire Activity Histograms")
        print("7 - Statistics")
        print("8 - FREM Emissions GIF")
        print("9 - All outputs")

        selection = input("Enter the output numbers separated by commas: ").strip()
        if not selection:
            print("Please select at least one output.")
            continue
        try:
            selected_outputs = [int(value.strip()) for value in selection.split(",") if value.strip()]
        except ValueError:
            print("Invalid input.")
            print("Enter numbers separated by commas.")
            print("Example: 1,3,4,8")
            continue

        selected_outputs = sorted(set(selected_outputs))
        invalid_outputs = [value for value in selected_outputs if value not in valid_outputs]
        if invalid_outputs:
            print(f"Invalid output number(s): {invalid_outputs}")
            print("Please select only outputs 1, 2, 3, 4, 5, 6, 7, 8, or 9.")
            continue
        if 9 in selected_outputs:
            return [1, 2, 3, 4, 5, 6, 7, 8]
        return selected_outputs
def get_user_inputs():
    print("=" * 55)
    print("WILDFIRE RAPID ANALYSIS TOOL")
    print("=" * 55)

    fire_name = _ask_fire_name()
    # TIME
    start = _ask_datetime("Start date/time (YYYY-MM-DD HH:MM): ")
    end = _ask_end_datetime(start)

    print("Study area")
    print("-" * 20)
    lat_min = _ask_latitude("Minimum latitude: ")
    lat_max = _ask_max_latitude(lat_min)
    lon_min = _ask_longitude("Minimum longitude: ")
    lon_max = _ask_max_longitude(lon_min)

    print("LSA SAF credentials")
    print("-" * 20)
    user = _ask_username()
    password = _ask_password()
    selected_outputs = _select_outputs()
    
    if 3 in selected_outputs:
        print("\nCOPERNICUS CDSE CREDENTIALS")
        print("-" * 30)
        _get_cdse_credentials()
        
    config = UserConfig(
        fire_name=fire_name,
        start=start,
        end=end,
        lat_min=lat_min,
        lat_max=lat_max,
        lon_min=lon_min,
        lon_max=lon_max,
        user=user,
        password=password,
        output_perimeter=(1 in selected_outputs),
        output_landcover=(2 in selected_outputs),
        output_landcover_burned=(3 in selected_outputs),
        output_activity=(4 in selected_outputs),
        output_frp_propagator=(5 in selected_outputs),
        output_histograms=(6 in selected_outputs),
        output_statistics=(7 in selected_outputs),
        output_emissions=(8 in selected_outputs))

    print("=" * 55)
    print("USER INPUTS COMPLETED")
    print("=" * 55)
    print(f"Fire: {config.fire_name}")
    print(f"Period: {config.start} → {config.end}")
    print( f"Area: "f"Lat {config.lat_min} to {config.lat_max} | "f"Lon {config.lon_min} to {config.lon_max}")
    print("Selected outputs:")
    for output in selected_outputs:
        print(f"  Output {output}")
    return config