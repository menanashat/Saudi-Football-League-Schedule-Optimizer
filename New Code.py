import calendar
import streamlit as st
import pandas as pd
import numpy as np
import datetime
import joblib
import os
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import uuid
import requests  # Added for API calls
import json  # Added for ecocide events
import random
from requests.exceptions import RequestException
import base64
import random
from streamlit.components.v1 import html as st_html  # Rename to avoid conflict
import math
from datetime import timedelta
from typing import Dict
from functools import lru_cache
import unicodedata # Added for Excel loading
import re # Added for Excel loading


# Set page configuration
st.set_page_config(
    page_title="Saudi Football League Schedule Optimizer",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Define team logos dictionary
# Define team logos dictionary with verified URLs or reliable placeholders
team_logos = {
    'Al-Taawoun': 'Al-Taawoun.png',
    'Al-Hilal': 'Al-Hilal.png',
    'Al-Nassr': 'Al-Nassr.png',
    'Al-Ittihad': 'Al-Ittihad.png',
    'Al-Ahli': 'Al-Ahli.png',
    'Al-Shabab': 'Al-Shabab.png',
    'Al-Ettifaq': 'Al-Ettifaq.png',
    'Al-Fateh': 'Al-Fateh.png',
    'Al-Fayha': 'Al-Fayha.png',
    'Al-Raed': 'Al-Raed.png',
    'Abha': 'Abha.png',
    'Al-Khaleej': 'Al-Khaleej.png',
    'Damac': 'Damac.png',
    'Al-Okhdood': 'Al-Okhdood.png',
    'Al-Wehda': 'Al-Wehda.png',
    'Al-Hazem': 'Al-Hazem.png',
    'Al-Qadisiyah': 'Al-Qadisiyah.png',
    'Al-Batin': 'Al-Batin.png',
    'Al-Faisaly': 'Al-Faisaly.png',
    'Al-Ain': 'Al-Ain.png',
    'NEOM':'NEOM.png',
    'Al-Najma':'Al-Najma.png',
    'Al-riyadh':'Al-riyadh.png',
    'Al-Kholood':'Al-Kholood.png'
}


class MatchScenario:
    def __init__(self, scenario_id, match_id, home_team, away_team, date, time, city, stadium, 
                 suitability_score, attendance_percentage, profit, is_selected=False, is_available=True):
        self.scenario_id = scenario_id
        self.match_id = match_id
        self.home_team = home_team
        self.away_team = away_team
        self.date = date
        self.time = time
        self.city = city
        self.stadium = stadium
        self.suitability_score = suitability_score
        self.attendance_percentage = attendance_percentage
        self.profit = profit
        self.is_selected = is_selected
        self.is_available = is_available
    
    def to_dict(self):
        return {
            'scenario_id': self.scenario_id,
            'match_id': self.match_id,
            'home_team': self.home_team,
            'away_team': self.away_team,
            'date': self.date,
            'time': self.time,
            'city': self.city,
            'stadium': self.stadium,
            'suitability_score': self.suitability_score,
            'attendance_percentage': self.attendance_percentage,
            'profit': self.profit,
            'is_selected': self.is_selected,
            'is_available': self.is_available
        }

class ScenarioManager:
    def __init__(self):
        self.scenarios = {}  # {match_id: [MatchScenario, ...]}
        self.selected_scenarios = {}  # {match_id: scenario_id}
        self.week_scenarios = {}  # {week: {day: [scenario_ids]}}
    
    def add_scenario(self, scenario):
        """Add a scenario to the manager"""
        if scenario.match_id not in self.scenarios:
            self.scenarios[scenario.match_id] = []
        self.scenarios[scenario.match_id].append(scenario)
    
    def get_scenarios_for_match(self, match_id):
        """Get all scenarios for a specific match"""
        return self.scenarios.get(match_id, [])
    
    def select_scenario(self, match_id, scenario_id):
        """Select a scenario and remove it from other days"""
        if match_id in self.scenarios:
            for scenario in self.scenarios[match_id]:
                scenario.is_selected = (scenario.scenario_id == scenario_id)
            self.selected_scenarios[match_id] = scenario_id
            self._remove_scenario_from_others(match_id, scenario_id)
    
    def _remove_scenario_from_others(self, selected_match_id, selected_scenario_id):
        """Remove the selected scenario from other matches to avoid conflicts"""
        selected_scenario = None
        for scenario in self.scenarios.get(selected_match_id, []):
            if scenario.scenario_id == selected_scenario_id:
                selected_scenario = scenario
                break
        
        if not selected_scenario:
            return
        
        for match_id, scenarios in self.scenarios.items():
            if match_id == selected_match_id:
                continue
            self.scenarios[match_id] = [
                s for s in scenarios 
                if not self._scenarios_conflict(selected_scenario, s)
            ]
    
    def _scenarios_conflict(self, scenario1, scenario2):
        """Check if two scenarios conflict (same time/date/stadium or team conflicts)"""
        if scenario1.date == scenario2.date and scenario1.stadium == scenario2.stadium:
            return True
        if scenario1.date == scenario2.date:
            teams1 = {scenario1.home_team, scenario1.away_team}
            teams2 = {scenario2.home_team, scenario2.away_team}
            if teams1.intersection(teams2):
                return True
        return False
    
    def get_available_scenarios_for_day(self, date):
        """Get all available scenarios for a specific day"""
        day_scenarios = []
        for match_id, scenarios in self.scenarios.items():
            for scenario in scenarios:
                if scenario.date == date and not scenario.is_selected:
                    day_scenarios.append(scenario)
        return day_scenarios



@lru_cache(maxsize=128)
def is_team_available(team, match_date):
    """
    Check if a team is available on a given date, including a 2-day buffer.
    Returns True if available, False if unavailable.
    """
    unavailable_dates = TEAM_UNAVAILABILITY.get(team, [])
    # Apply a 2-day buffer around each unavailability date
    unavailable_with_buffer = set()
    for date in unavailable_dates:
        unavailable_with_buffer.add(date)
        unavailable_with_buffer.add(date - datetime.timedelta(days=2))
        unavailable_with_buffer.add(date - datetime.timedelta(days=1))
        unavailable_with_buffer.add(date + datetime.timedelta(days=1))
        unavailable_with_buffer.add(date + datetime.timedelta(days=2))

    return match_date not in unavailable_with_buffer

TEAM_UNAVAILABILITY = {
    'Al-Ittihad': [
        datetime.date(2025, 9, 15), datetime.date(2025, 9, 30), datetime.date(2025, 10, 20),
        datetime.date(2025, 11, 4), datetime.date(2025, 11, 24), datetime.date(2025, 12, 23),
        datetime.date(2026, 2, 10), datetime.date(2026, 2, 17)
    ],
    'Al-Ahli': [
        datetime.date(2025, 9, 15), datetime.date(2025, 9, 29), datetime.date(2025, 10, 20),
        datetime.date(2025, 11, 4), datetime.date(2025, 11, 24), datetime.date(2025, 12, 22),
        datetime.date(2026, 2, 9), datetime.date(2026, 2, 16)
    ],
    'Al-Hilal': [
        datetime.date(2025, 9, 16), datetime.date(2025, 9, 29), datetime.date(2025, 10, 21),
        datetime.date(2025, 11, 3), datetime.date(2025, 11, 25), datetime.date(2025, 12, 22),
        datetime.date(2026, 2, 9), datetime.date(2026, 2, 16)
    ],
    'Al-Nassr': [
        datetime.date(2025, 9, 17), datetime.date(2025, 10, 1), datetime.date(2025, 10, 22),
        datetime.date(2025, 11, 5), datetime.date(2025, 11, 26), datetime.date(2025, 12, 24)
    ],
    'Al-Shabab': [
        datetime.date(2025, 10, 1), datetime.date(2025, 10, 21), datetime.date(2025, 11, 5),
        datetime.date(2025, 12, 24), datetime.date(2026, 2, 1), datetime.date(2026, 2, 17)
    ]
}

STADIUM_UNAVAILABILITY = {
    'King Abdullah Sports City Stadium (The Jewel)': {
        'unavailable': (datetime.date(2025, 12, 1), datetime.date(2025, 12, 31)),
        'alternative': 'Prince Abdullah Al Faisal (Jeddah)'
    },
    'Al-Ettifaq Club Stadium': {
        'unavailable': (datetime.date(2025, 11, 24), datetime.date(2025, 12, 28)),
        'alternative': 'Prince Mohammed bin Fahad (Dammam)'
    },
    'Taawoun Club Stadium (Buraydah)': {
        'unavailable': (datetime.date(2025, 10, 5), datetime.date(2025, 11, 8)),
        'alternative': 'King Abdullah Sports City (Buraydah)'
    },
    'Al Hazem Club Stadium': {
        'unavailable': (datetime.date(2025, 10, 5), datetime.date(2025, 11, 8)),
        'alternative': 'King Abdullah Sports City (Buraydah)'
    },
    'Damac Club Stadium (Khamis Mushait)': {
        'unavailable': (datetime.date(2025, 10, 5), datetime.date(2025, 11, 5)),
        'alternative': 'Prince Sultan Sports City (Abha)'
    },
    'Prince Sultan Sports City (Abha)': {
        'unavailable': (datetime.date(2025, 9, 25), datetime.date(2025, 10, 26)),
        'alternative': 'Damac Club Stadium (Khamis Mushait)'
    }
}


def get_alternative_stadium(stadium, match_date):
    """
    Get the alternative stadium if the primary stadium is unavailable.
    Returns the original stadium if available, or the alternative.
    """
    stadium_info = STADIUM_UNAVAILABILITY.get(stadium, {})
    if stadium_info:
        start_date, end_date = stadium_info['unavailable']
        if start_date <= match_date <= end_date:
            return stadium_info['alternative']
    return stadium


def check_rest_period(schedule, team, match_date):
    """
    Ensure at least 2 days rest between matches for a team.
    Returns True if rest period is satisfied, False otherwise.
    """
    min_rest_days = 2
    for _, match in schedule.iterrows():
        if match['home_team'] == team or match['away_team'] == team:
            existing_date = pd.to_datetime(match['date']).date()
            if abs((match_date - existing_date).days) < min_rest_days:
                return False
    return True








@lru_cache(maxsize=1000)
def get_prayer_times_unified(city, date, prayer='all'):
    """
    Fetch prayer times for a given city and date from the Aladhan API using Umm Al-Qura method.
    Map 'Unknown' city to 'Riyadh' and handle invalid or future dates with fallbacks.
    """
    # Default to Riyadh if city is 'Unknown'
    if city == 'Unknown':
        city = 'Riyadh'
        st.warning(f"City 'Unknown' detected. Defaulting to 'Riyadh' for prayer times.")

    # Validate date
    if date is None:
        date = datetime.date.today()
        st.warning(f"No date provided for prayer times. Using today's date: {date}")

    # City mapping for Aladhan API
    city_mapping = {
        'Riyadh': 'Riyadh',
        'Jeddah': 'Jeddah',
        'Dammam': 'Dammam',
        'Buraidah': 'Buraidah',
        'Al-Mubarraz': 'Al Mubarraz',
        'Khamis Mushait': 'Khamis Mushait',
        'Abha': 'Abha',
        'Al Khobar': 'Al Khobar',
        'Saihat': 'Saihat',
        'Al Majmaah': 'Al Majmaah',
        'Ar Rass': 'Ar Rass',
        'Unaizah': 'Unaizah',
        'NEOM': 'Tabuk'  # NEOM may not be in API, use closest city
    }

    # Fallback prayer times for Jeddah in October (approximate, based on Umm Al-Qura)
    jeddah_fallback_times = {
        'fajr': '04:45',
        'dhuhr': '12:00',
        'asr': '15:30',
        'maghrib': '17:45',
        'isha': '19:15'
    }

    api_city = city_mapping.get(city, city)
    date_str = date.strftime('%d-%m-%Y') if isinstance(date, (datetime.date, datetime.datetime)) else str(date)

    # Check if date is in the future (beyond 2025)
    current_date = datetime.date.today()
    if date > current_date + datetime.timedelta(days=365):
        st.warning(f"Date {date_str} is too far in the future for Aladhan API. Using fallback times for {city}.")
        if city == 'Jeddah':
            return {
                'timings': jeddah_fallback_times,
                'minutes': {
                    'fajr_minutes': time_string_to_minutes(jeddah_fallback_times['fajr']),
                    'dhuhr_minutes': time_string_to_minutes(jeddah_fallback_times['dhuhr']),
                    'asr_minutes': time_string_to_minutes(jeddah_fallback_times['asr']),
                    'maghrib_minutes': time_string_to_minutes(jeddah_fallback_times['maghrib']),
                    'isha_minutes': time_string_to_minutes(jeddah_fallback_times['isha'])
                }
            }
        else:
            return {'error': f'No fallback times available for {city} on future date {date_str}'}

    try:
        url = f"http://api.aladhan.com/v1/timingsByCity/{date_str}?city={api_city}&country=Saudi%20Arabia&method=4"
        response = requests.get(url)
        data = response.json()

        if response.status_code != 200 or data.get('code') != 200:
            st.error(f"API request failed for {city} on {date_str}: Status {response.status_code}, Response: {data.get('status', 'Unknown error')}")
            if city == 'Jeddah':
                st.warning(f"Using fallback prayer times for Jeddah on {date_str} (Umm Al-Qura method).")
                return {
                    'timings': jeddah_fallback_times,
                    'minutes': {
                        'fajr_minutes': time_string_to_minutes(jeddah_fallback_times['fajr']),
                        'dhuhr_minutes': time_string_to_minutes(jeddah_fallback_times['dhuhr']),
                        'asr_minutes': time_string_to_minutes(jeddah_fallback_times['asr']),
                        'maghrib_minutes': time_string_to_minutes(jeddah_fallback_times['maghrib']),
                        'isha_minutes': time_string_to_minutes(jeddah_fallback_times['isha'])
                    }
                }
            return {'error': f'API request failed for {city} on {date_str}'}

        timings = data['data']['timings']
        prayer_times = {
            'timings': {
                'fajr': timings['Fajr'],
                'dhuhr': timings['Dhuhr'],
                'asr': timings['Asr'],
                'maghrib': timings['Maghrib'],
                'isha': timings['Isha']
            },
            'minutes': {
                'fajr_minutes': time_string_to_minutes(timings['Fajr']),
                'dhuhr_minutes': time_string_to_minutes(timings['Dhuhr']),
                'asr_minutes': time_string_to_minutes(timings['Asr']),
                'maghrib_minutes': time_string_to_minutes(timings['Maghrib']),
                'isha_minutes': time_string_to_minutes(timings['Isha'])
            }
        }
        return prayer_times

    except Exception as e:
        st.error(f"Unexpected error fetching prayer times for {city} on {date_str}: {e}")
        if city == 'Jeddah':
            st.warning(f"Using fallback prayer times for Jeddah on {date_str} (Umm Al-Qura method).")
            return {
                'timings': jeddah_fallback_times,
                'minutes': {
                    'fajr_minutes': time_string_to_minutes(jeddah_fallback_times['fajr']),
                    'dhuhr_minutes': time_string_to_minutes(jeddah_fallback_times['dhuhr']),
                    'asr_minutes': time_string_to_minutes(jeddah_fallback_times['asr']),
                    'maghrib_minutes': time_string_to_minutes(jeddah_fallback_times['maghrib']),
                    'isha_minutes': time_string_to_minutes(jeddah_fallback_times['isha'])
                }
            }
        return {'error': f'Error fetching prayer times: {str(e)}'}

# add this to Full schulde and 2 day rest
def calculate_match_times_for_city_and_date(city, match_date, teams_data=None):
    """
    Calculates match start times based on Maghrib and Isha prayer times for a given city and date.
    Returns a dict with 'maghrib_time', 'isha_time', 'maghrib_slots', 'isha_slots'.
    """
    # Default time slots
    default_maghrib_slots = {'Thursday': '19:00', 'Friday': '16:00', 'Saturday': '12:00'}
    default_isha_slots = {'Thursday': '21:00', 'Friday': '18:00', 'Saturday': '16:00'}

    # Check teams_data for custom slots
    maghrib_slots = default_maghrib_slots
    isha_slots = default_isha_slots
    if teams_data is not None and 'maghrib_slots' in teams_data.columns and 'isha_slots' in teams_data.columns:
        city_data = teams_data[teams_data['city'] == city]
        if not city_data.empty:
            maghrib_slots = city_data['maghrib_slots'].iloc[0] if pd.notna(city_data['maghrib_slots'].iloc[0]) else default_maghrib_slots
            isha_slots = city_data['isha_slots'].iloc[0] if pd.notna(city_data['isha_slots'].iloc[0]) else default_isha_slots

    try:
        prayer_data = get_prayer_times_unified(city, match_date, prayer=None)
        
        if 'error' not in prayer_data and 'timings' in prayer_data:
            maghrib_time_str = prayer_data['timings'].get('maghrib')
            isha_time_str = prayer_data['timings'].get('isha')
            st.write(f"API prayer times for {city} on {match_date}: Maghrib {maghrib_time_str}, Isha {isha_time_str}")
        else:
            maghrib_time_str = None
            isha_time_str = None
            st.warning(f"API error or no timings for {city} on {match_date}: {prayer_data.get('error', 'No timings')}")
        
        if not maghrib_time_str or not isha_time_str:
            st.warning(f"Using default prayer times for {city} on {match_date}.")
            maghrib_time_str = "17:45" if city == 'Jeddah' else "17:48"
            isha_time_str = "19:15" if city == 'Jeddah' else "19:18"
        
        # Validate time format
        try:
            maghrib_hour, maghrib_minute = map(int, maghrib_time_str.split(":"))
            isha_hour, isha_minute = map(int, isha_time_str.split(":"))
            return {
                "maghrib_time": maghrib_time_str,
                "isha_time": isha_time_str,
                "maghrib_slots": maghrib_slots,
                "isha_slots": isha_slots
            }
        except ValueError as e:
            st.error(f"Error parsing prayer times for {city} on {match_date}: {e}. Using defaults.")
            return {
                "maghrib_time": "17:45" if city == 'Jeddah' else "17:48",
                "isha_time": "19:15" if city == 'Jeddah' else "19:18",
                "maghrib_slots": maghrib_slots,
                "isha_slots": isha_slots
            }
    except Exception as e:
        st.error(f"Unexpected error in API call for {city} on {match_date}: {e}. Using defaults.")
        return {
            "maghrib_time": "17:45" if city == 'Jeddah' else "17:48",
            "isha_time": "19:15" if city == 'Jeddah' else "19:18",
            "maghrib_slots": maghrib_slots,
            "isha_slots": isha_slots
        }
def time_string_to_minutes(time_str: str) -> int:
    """Convert HH:MM format to minutes since midnight"""
    hours, minutes = map(int, time_str.split(':'))
    return hours * 60 + minutes



# CSS styling
st.markdown("""
    <style>
        .main-header {
            font-size: 2.5rem;
            color: #1e3d59;
            text-align: center;
            margin-bottom: 1rem;
        }
        .sub-header {
            font-size: 1.8rem;
            color: #1e3d59;
            margin-top: 2rem;
            margin-bottom: 1rem;
        }
        .card {
            border-radius: 5px;
            background-color: #f5f5f5;
            padding: 1rem;
            margin-bottom: 1rem;
        }
        .metric-card {
            background-color: #f0f8ff;
            border-left: 5px solid #1e3d59;
            padding: 1rem;
            margin-bottom: 1rem;
        }
        .highlight {
            color: #ff6e40;
            font-weight: bold;
        }
        .good {
            color: #2e7d32;
            font-weight: bold;
        }
        .warning {
            color: #ff6e40;
            font-weight: bold;
        }
        .bad {
            color: #d32f2f;
            font-weight: bold;
        }
        .team-logo {
            width: 30px;
            height: 30px;
            margin-right: 5px;
        }
        .match-card {
            background-color: white;
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            padding: 1rem;
            margin-bottom: 1rem;
        }
        .match-header {
            font-weight: bold;
            color: #1e3d59;
        }
        .match-time {
            color: #ff6e40;
            font-weight: bold;
        }
        .match-venue {
            color: #666;
            font-style: italic;
        }
        .match-teams {
            font-size: 1.2rem;
            margin: 0.5rem 0;
        }
        .match-stats {
            display: flex;
            justify-content: space-between;
            margin-top: 0.5rem;
        }
        .calendar-day {
            background-color: #f5f5f5;
            border-radius: 5px;
            padding: 0.5rem;
            margin: 0.2rem;
            text-align: center;
        }
        .calendar-day-header {
            font-weight: bold;
            margin-bottom: 0.5rem;
        }
        .calendar-time-slot {
            background-color: white;
            border-radius: 3px;
            padding: 0.3rem;
            margin: 0.2rem 0;
            font-size: 0.9rem;
        }
        .calendar-time-slot:hover {
            background-color: #e0e0e0;
            cursor: pointer;
        }
        .suitable {
            border-left: 3px solid #2e7d32;
        }
        .unsuitable {
            border-left: 3px solid #d32f2f;
        }
        .recommendation-card {
            background-color: #e8f5e9;
            border-left: 5px solid #4caf50;
            border-radius: 5px;
            padding: 0.8rem;
            margin-bottom: 0.8rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .recommendation-header {
            font-weight: bold;
            color: #1b5e20;
            margin-bottom: 0.3rem;
        }
        .recommendation-details {
            font-size: 0.95rem;
            color: #333;
        }
        .ecocide-event-card {
            background-color: #d1e7dd;
            border-left: 5px solid #198754;
            border-radius: 5px;
            padding: 0.8rem;
            margin-bottom: 0.8rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .ecocide-event-header {
            font-weight: bold;
            color: #0f5132;
            margin-bottom: 0.3rem;
        }
        .ecocide-event-details {
            font-size: 0.95rem;
            color: #333;
        }
        /* Matchday Simulation Styles */
        .matchday-header {
            text-align: center;
            font-size: 1.5rem;
            font-weight: bold;
            color: #1e3d59;
            margin: 2rem 0 1rem 0;
            padding: 1rem;
            background-color: #f8f9fa;
            border-radius: 8px;
        }
        .timezone-info {
            text-align: center;
            font-size: 0.9rem;
            color: #666;
            margin-bottom: 1.5rem;
        }
.match-row {
    background-color: white;
    border-radius: 12px;
    box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    padding: 1rem 2rem;
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: relative;
    transition: transform 0.2s ease, box-shadow 0.2s ease; /* smooth transition */
}

.match-row:hover {
    transform: scale(1.02); /* slight zoom */
    box-shadow: 0 8px 16px rgba(0,0,0,0.2); /* stronger shadow */
    cursor: pointer; /* pointer cursor on hover */
}

.left-side {
    display: flex;
    align-items: center;
    gap: 20px;
    flex: 1;
}

.team-section.home {
    display: flex;
    align-items: center;
    gap: 10px;
    justify-content: flex-start;
    flex: 1;
}

.team-section.away {
    display: flex;
    align-items: center;
    gap: 10px;
    justify-content: flex-end;
    flex: 1;
}

.time-day-box {
    position: absolute;
    left: 50%;
    transform: translateX(-50%);
    background: linear-gradient(135deg, #1e3d59 0%, #ff6e40 100%);
    color: white;
    padding: 1rem 1.5rem;
    border-radius: 15px;
    font-weight: bold;
    font-size: 1rem;
    min-width: 120px;
    text-align: center;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    z-index: 10;
}

.team-logo {
    width: 80px;
    height: 90px;
}
.team-name {
 
    font-weight: bold;
    font-size: 30px;
}
.time-display {
    font-size: 16px;
    font-weight: bold;
}
.day-display {
    font-size: 14px;
    color: gray;
}
        .team-logo {
            width: 40px;
            height: 40px;
            object-fit: contain;
            margin: 0 8px;
            border-radius: 50%;
            background-color: #ffffff;
            padding: 3px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.1);
        }
        .team-logo-placeholder {
            width: 40px;
            height: 40px;
            background-color: #1e3d59;
            border-radius: 50%;
            color: white;
            font-size: 0.9rem;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 8px;
            font-weight: bold;
            border: 2px solid #ffffff;
            box-shadow: 0 2px 6px rgba(0,0,0,0.1);
        }
    </style>
    """, unsafe_allow_html=True)


def correct_team_locations(teams_data):
    """
    Ensure teams_data has required columns ['team', 'city', 'stadium', 'stadium_capacity'].
    Maps missing columns from team_locations and preserves existing columns.
    """
    team_locations = {
        'Al-Khaleej': {'city': 'Saihat', 'stadium': 'Mohammed Bin Fahd Stadium', 'stadium_capacity': 20000},
        'Al-Ettifaq': {'city': 'Dammam', 'stadium': 'Al-Ettifaq Club Stadium', 'stadium_capacity': 15000},
        'Al-Taawoun': {'city': 'Buraidah', 'stadium': 'Taawoun Club Stadium', 'stadium_capacity': 25000},
        'Al-Fateh': {'city': 'Al-Mubarraz', 'stadium': 'Al-Fateh Club Stadium', 'stadium_capacity': 20000},
        'Al-Hilal': {'city': 'Riyadh', 'stadium': 'Kingdom Arena', 'stadium_capacity': 30000},
        'Al-Ahli': {'city': 'Jeddah', 'stadium': 'Alinma Stadium', 'stadium_capacity': 30000},
        'Al-Ittihad': {'city': 'Jeddah', 'stadium': 'King Abdullah Sports City Stadium (The Jewel)', 'stadium_capacity': 60000},
        'Damac': {'city': 'Khamis Mushait', 'stadium': 'Damac Club Stadium (Khamis Mushait)', 'stadium_capacity': 20000},
        'Al-Okhdood': {'city': 'Abha', 'stadium': 'Prince Hathloul bin Abdulaziz Sport Staduim', 'stadium_capacity': 20000},
        'Al-Hazem': {'city': 'Abha', 'stadium': 'Al Hazem Club Stadium', 'stadium_capacity': 20000},
        'Al-Qadisiyah': {'city': 'Al Khobar', 'stadium': 'Mohammed Bin Fahd Stadiu', 'stadium_capacity': 20000},
        'Al-Shabab': {'city': 'Riyadh', 'stadium': 'Prince Khalid bin Sultan bin Abdul Aziz Stadium (Shabab Club Stadium)', 'stadium_capacity': 20000},
        'Al-Nassr': {'city': 'Riyadh', 'stadium': 'King Saud University Stadium (Al-Oul Park)', 'stadium_capacity': 25000},
        'Al-Fayha': {'city': 'Al Majmaah', 'stadium': 'Al Majmaah Sports City', 'stadium_capacity': 20000},
        'Al-Kholood': {'city': 'Ar Rass', 'stadium': 'Al Hazem Club Stadium', 'stadium_capacity': 20000},
        'Al-riyadh': {'city': 'Riyadh', 'stadium': 'Prince Faisal bin Fahd Stadium', 'stadium_capacity': 15000},
        'Al-Najma': {'city': 'Unaizah', 'stadium': 'King Abdullah Sport City', 'stadium_capacity': 20000},
        'NEOM': {'city': 'NEOM', 'stadium': 'NEOM Stadium', 'stadium_capacity': 20000}
    }

    # Log input teams_data
    # st.write(f"Input teams_data to correct_team_locations:\n{teams_data}")

    # Ensure teams_data is a DataFrame
    if not isinstance(teams_data, pd.DataFrame):
        st.error("teams_data must be a pandas DataFrame.")
        raise ValueError("teams_data must be a pandas DataFrame.")

    # Rename columns if necessary
    teams_data = teams_data.rename(columns={
        'home_city': 'city',
        'home_stadium': 'stadium'
    })

    # Add missing required columns
    for col in ['city', 'stadium', 'stadium_capacity']:
        if col not in teams_data.columns:
            teams_data[col] = teams_data['team'].map(
                {team: data[col] for team, data in team_locations.items()}
            ).fillna('Unknown' if col in ['city', 'stadium'] else 20000)

    # Validate all teams have valid mappings
    unmatched_teams = set(teams_data['team']) - set(team_locations.keys())
    if unmatched_teams:
        st.error(f"Teams not found in team_locations: {unmatched_teams}. Assigning 'Unknown' city.")
        for team in unmatched_teams:
            teams_data.loc[teams_data['team'] == team, 'city'] = 'Unknown'
            teams_data.loc[teams_data['team'] == team, 'stadium'] = 'Unknown Stadium'
            teams_data.loc[teams_data['team'] == team, 'stadium_capacity'] = 20000

    # Log output teams_data
    # st.write(f"teams_data after correction in correct_team_locations:\n{teams_data}")

    return teams_data


def determine_winner(match, teams_data):
    """
    Determines the winner of a match based on team strength and randomness.
    """
    home_team = match['home_team']
    away_team = match['away_team']
    
    home_team_data = teams_data[teams_data['team'] == home_team]
    away_team_data = teams_data[teams_data['team'] == away_team]
    
    home_strength = home_team_data['strength'].values[0] if not home_team_data.empty else 'medium'
    away_strength = away_team_data['strength'].values[0] if not away_team_data.empty else 'medium'
    
    strength_scores = {'strong': 0.5, 'medium': 0.3, 'weak': 0.2}
    home_score = strength_scores.get(home_strength, 0.3)
    away_score = strength_scores.get(away_strength, 0.3)
    
    home_score += 0.1  # Home advantage
    
    total = home_score + away_score + 0.2
    home_prob = home_score / total
    away_prob = away_score / total
    draw_prob = 0.2 / total
    
    outcome = np.random.choice(
        [home_team, away_team, None],
        p=[home_prob, away_prob, draw_prob]
    )
    
    is_draw = outcome is None
    winner = outcome if not is_draw else None
    
    return winner, is_draw


@st.cache_data
def load_data():
    try:
        attendance_model = joblib.load('best_model_attendance_percentage.pkl')
        profit_model = joblib.load('best_model_profit.pkl')
        models_loaded = True
    except FileNotFoundError:
        st.warning("Model files not found. Using default predictions.")
        attendance_model = None
        profit_model = None
        models_loaded = False

    # Updated data dictionary with all 18 teams
    data = {
        'team': [
            'Al-Taawoun', 'Al-Hilal', 'Al-Nassr', 'Al-Ittihad', 'Al-Ahli', 'Al-Shabab',
            'Al-Ettifaq', 'Al-Fateh', 'Al-Fayha', 'Al-Khaleej', 'Al-Okhdood', 'Al-Hazem',
            'Al-Qadisiyah', 'Al-riyadh', 'Al-Najma', 'Al-Kholood', 'Damac', 'NEOM'
        ],
        'home_city': [
            'Buraidah', 'Riyadh', 'Riyadh', 'Jeddah', 'Jeddah', 'Riyadh',
            'Dammam', 'Al-Mubarraz', 'Al Majmaah', 'Saihat', 'Abha', 'Abha',
            'Al Khobar', 'Riyadh', 'Unaizah', 'Ar Rass', 'Khamis Mushait', 'NEOM'
        ],
        'home_stadium': [
            'Taawoun Club Stadium (Buraydah)', 'Kingdom Arena', 'King Saud University Stadium (Al-Oul Park)',
            'King Abdullah Sports City Stadium (The Jewel)', 'Alinma Stadium',
            'Prince Khalid bin Sultan bin Abdul Aziz Stadium (Shabab Club Stadium)', 'Al-Ettifaq Club Stadium',
            'Al-Fateh Club Stadium', 'Al Majmaah Sports City', 'Mohammed Bin Fahd Stadium',
            'Prince Hathloul bin Abdulaziz Sport Staduim', 'Al Hazem Club Stadium', 'Mohammed Bin Fahd Stadiu',
            'Prince Faisal bin Fahd Stadium', 'King Abdullah Sport City', 'Al Hazem Club Stadium',
            'Damac Club Stadium (Khamis Mushait)', 'NEOM Stadium'
        ],
        'stadium_capacity': [
            25000, 30000, 25000, 60000, 30000, 20000,
            15000, 20000, 20000, 20000, 20000, 20000,
            20000, 15000, 20000, 20000, 20000, 20000
        ],
        'strength': [
            'strong', 'strong', 'strong', 'strong', 'strong', 'medium',
            'medium', 'medium', 'medium', 'medium', 'weak', 'weak',
            'medium', 'weak', 'weak', 'weak', 'medium', 'medium'
        ]
    }
    teams_data = pd.DataFrame(data)
    teams_data = correct_team_locations(teams_data)

    weather_data = pd.DataFrame({
        'city': ['Riyadh', 'Jeddah', 'Dammam', 'Buraidah', 'Al-Mubarraz', 'Khamis Mushait', 'Abha', 'Al Khobar', 'Saihat', 'Al Majmaah', 'Ar Rass', 'Unaizah', 'NEOM'],
        'month': [9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9],
        'temperature': [35, 32, 33, 34, 33, 28, 27, 33, 34, 34, 34, 34, 30],
        'humidity': [30, 60, 55, 35, 50, 40, 45, 55, 50, 35, 35, 35, 25]
    })

    return teams_data, weather_data, attendance_model, profit_model, models_loaded




@lru_cache(maxsize=1)
def load_match_schedule_from_files():
    """
    Robust loader for schedule.xlsx (sheet 'Table 1').
    Detects week column, extracts home/away pairs by finding the 'X' separators,
    supports mixed English/Arabic formats, and returns {week: [(home, away), ...], ...}.
    Ensures all team names are mapped to standard names using CLEAN_TEAM_NAMES.
    """
    # Define team name mappings with normalized keys
    CLEAN_TEAM_NAMES = {
        'AL ITTIHAD': 'Al-Ittihad',
        'AL ETTIFAQ': 'Al-Ettifaq',
        'AL TAAWOUN': 'Al-Taawoun',
        'AL HILAL': 'Al-Hilal',
        'AL NASSR': 'Al-Nassr',
        'AL AHLI': 'Al-Ahli',
        'AL SHABAB': 'Al-Shabab',
        'AL FATEH': 'Al-Fateh',
        'AL FAYHA': 'Al-Fayha',
        'AL KHALEEJ': 'Al-Khaleej',
        'AL OKHDOOD': 'Al-Okhdood',
        'AL HAZEM': 'Al-Hazem',
        'AL QADISIYAH': 'Al-Qadisiyah',
        'AL QADSIAH': 'Al-Qadisiyah',
        'AL RIYADH': 'Al-riyadh',
        'AL NAJMAH': 'Al-Najma',
        'AL KHOLOOD': 'Al-Kholood',
        'DAMAC': 'Damac',
        'NEOM': 'NEOM',
        # Handle common variations
        'AL-ITTIHAD': 'Al-Ittihad',
        'ALITTIHAD': 'Al-Ittihad',
        'AL ITTIHAD ': 'Al-Ittihad',
        'AL_ETTIFAQ': 'Al-Ettifaq',
        'AL-ETTIFAQ': 'Al-Ettifaq',
        'AL ETTIFAQ ': 'Al-Ettifaq',
        'AL NAJMA': 'Al-Najma',
        'AL-NAJMAH': 'Al-Najma',
        'AL NAJMAH ': 'Al-Najma',
        'AL_KHOLOOD': 'Al-Kholood',
        'AL-KHOLOOD': 'Al-Kholood',
        'AL KHOLOOD ': 'Al-Kholood',
        'AL-QADSIAH': 'Al-Qadisiyah',
        'AL QADSIAH ': 'Al-Qadisiyah'
    }

    def normalize_team_name(name):
        """Normalize team name by removing non-printable characters, non-breaking spaces, and converting to uppercase."""
        if not isinstance(name, str) or pd.isna(name):
            st.warning(f"Invalid team name encountered: {name}. Treating as empty.")
            return ''
        # Normalize Unicode characters (e.g., convert non-breaking spaces to regular spaces)
        name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('ASCII')
        # Replace multiple spaces with single space and remove leading/trailing spaces
        name = re.sub(r'\s+', ' ', name.strip()).upper()
        return name

    try:
        file_path = 'schedule.xlsx'
        if not os.path.exists(file_path):
            st.error("Error: The 'schedule.xlsx' file was not found. Please ensure it's in the app directory.")
            return None

        df = pd.read_excel(file_path, sheet_name='Table 1', engine='openpyxl')
        df = df.dropna(how='all')  # drop entirely empty rows
        if df.shape[0] == 0:
            st.error("Error: 'Table 1' appears empty.")
            return None

        cols = list(df.columns)

        # 1) Detect the week column (prefer English 'WEEK', else any column containing 'أسبوع')
        week_col = None
        for c in cols:
            if str(c).strip().lower() == 'week':
                week_col = c
                break
        if week_col is None:
            for c in cols:
                if 'أسبوع' in str(c):
                    week_col = c
                    break
        if week_col is None:
            st.error(f"Could not detect a week column automatically. Columns found: {cols}")
            return None

        # 2) Build a week Series (forward-fill) and cast to int where possible
        week_series = df[week_col].ffill().astype(str).str.strip().replace('', pd.NA)

        def to_int_safe(x):
            try:
                return int(float(x))
            except Exception:
                return pd.NA

        week_series = week_series.apply(to_int_safe)

        # 3) Extract matches by locating 'X' separators per row and taking prev/next columns
        extracted = []
        for idx, row in df.iterrows():
            wk = week_series.loc[idx]
            if pd.isna(wk):
                continue

            # indices where the cell equals 'X' (case-insensitive)
            x_indices = [j for j, c in enumerate(cols) if str(row[c]).strip().upper() == 'X']

            pairs = []
            for j in x_indices:
                if j - 1 >= 0 and j + 1 < len(cols):
                    home_val = str(row[cols[j - 1]]).strip()
                    away_val = str(row[cols[j + 1]]).strip()
                    # sanity checks
                    if (home_val and away_val
                        and home_val.upper() != 'NAN' and away_val.upper() != 'NAN'
                        and home_val.upper() != 'X' and away_val.upper() != 'X'):
                        pairs.append((home_val, away_val, cols[j - 1], cols[j + 1]))

            # prefer English pair if present, then Arabic, else first found
            selected = None
            for p in pairs:
                if 'TEAMS' in str(p[2]).upper() or 'TEAM' in str(p[2]).upper():
                    selected = p
                    break
            if selected is None:
                for p in pairs:
                    if 'فريق' in str(p[2]):
                        selected = p
                        break
            if selected is None and pairs:
                selected = pairs[0]

            if selected:
                home, away = selected[0], selected[1]
                extracted.append({'week': int(wk), 'home_team': home, 'away_team': away})

        if not extracted:
            st.error("No matches parsed. Please check the Excel structure (looks for 'X' separators and adjacent team columns).")
            return None

        parsed_df = pd.DataFrame(extracted)


        # Normalize team names
        normalized_teams = set()
        for col in ['home_team', 'away_team']:
            parsed_df[col] = parsed_df[col].apply(normalize_team_name)
            normalized_teams.update(parsed_df[col].dropna())

        # Map to standard names
        unmapped_teams = set()
        for col in ['home_team', 'away_team']:
            parsed_df[col] = parsed_df[col].apply(
                lambda x: CLEAN_TEAM_NAMES.get(x, x) if x else x
            )
            # Track unmapped teams
            unmapped_teams.update(parsed_df[col][~parsed_df[col].isin(CLEAN_TEAM_NAMES.values())])

        # Check for unmapped teams
        if unmapped_teams:
            st.error(f"Unmapped team names in schedule.xlsx: {unmapped_teams}. Please update CLEAN_TEAM_NAMES with these entries.")
            raise ValueError(f"Unmapped team names: {unmapped_teams}")

        # Log cleaned team names
        cleaned_teams = set(parsed_df['home_team'].tolist() + parsed_df['away_team'].tolist())
        # st.write(f"Cleaned team names in schedule.xlsx: {cleaned_teams}")

        # Validate against expected teams
        expected_teams = {
            'Al-Taawoun', 'Al-Hilal', 'Al-Nassr', 'Al-Ittihad', 'Al-Ahli', 'Al-Shabab',
            'Al-Ettifaq', 'Al-Fateh', 'Al-Fayha', 'Al-Khaleej', 'Al-Okhdood', 'Al-Hazem',
            'Al-Qadisiyah', 'Al-riyadh', 'Al-Najma', 'Al-Kholood', 'Damac', 'NEOM'
        }
        if not cleaned_teams.issubset(expected_teams):
            invalid_teams = cleaned_teams - expected_teams
            st.error(f"Invalid team names after mapping: {invalid_teams}. Expected teams: {expected_teams}")
            raise ValueError(f"Invalid team names: {invalid_teams}")

        # Group into dict {week: [(home, away), ...]}
        matches_by_week = {}
        for week, grp in parsed_df.groupby('week'):
            matches_by_week[int(week)] = [(r['home_team'], r['away_team']) for _, r in grp.iterrows()]

        return matches_by_week

    except Exception as e:
        st.error(f"Error loading schedule from files: {e}")
        return None
    

    



def validate_and_redistribute_matches(matches_from_excel, week_start_dates, matches_per_week=9):
    """Validate and redistribute matches to enforce 3-match-per-day limit."""
    redistributed = {week: [] for week in matches_from_excel}
    for week in matches_from_excel:
        thu_date = week_start_dates.get(week)
        if not thu_date:
            continue
        days = [thu_date + datetime.timedelta(days=d) for d in range(3)]  # Thu, Fri, Sat
        day_capacities = {day: 3 for day in days}
        original_pairings = matches_from_excel[week]
        st.write(f"Original pairings for week {week}: {len(original_pairings)} matches")
        
        for home, away in original_pairings:
            assigned = False
            # Prioritize original implied days if possible, but enforce limit
            for day in days:  # Try in order: Thu > Fri > Sat
                if day_capacities[day] > 0:
                    redistributed[week].append((home, away, day))
                    day_capacities[day] -= 1
                    assigned = True
                    st.write(f"Assigned {home} vs {away} to {day}")
                    break
            if not assigned:
                st.error(f"Cannot assign {home} vs {away} in week {week}: All days full.")
        
        st.write(f"Redistributed week {week}: {[(h, a, d.strftime('%Y-%m-%d')) for h, a, d in redistributed[week]]}")
    return redistributed


def display_week_scenarios(week_number, matches_from_excel):
    """
    Display matches for a week, showing available scenarios (even if zero), with day count tracking.
    """
    st.markdown(f"### Week {week_number} Match Scenarios")
    if not matches_from_excel:
        st.error("No matches loaded from Excel.")
        return

    pairings = matches_from_excel.get(week_number, [])
    if not pairings:
        st.info(f"No matches found for week {week_number}.")
        return

    week_start_dates = {
        7: datetime.date(2025, 10, 30),  # Thursday
        8: datetime.date(2025, 11, 6),   # Thursday
        9: datetime.date(2025, 11, 21),  # Friday
        10: datetime.date(2025, 12, 19), # Friday
        11: datetime.date(2025, 12, 25), # Thursday
        12: datetime.date(2025, 12, 29), # Monday
        13: datetime.date(2026, 1, 2),   # Friday
        14: datetime.date(2026, 1, 8),   # Thursday
        15: datetime.date(2026, 1, 12),  # Monday
        16: datetime.date(2026, 1, 16),  # Friday
        17: datetime.date(2026, 1, 20),  # Tuesday
        18: datetime.date(2026, 1, 24),  # Saturday
        19: datetime.date(2026, 1, 28),  # Wednesday
        20: datetime.date(2026, 2, 1),   # Friday
        21: datetime.date(2026, 2, 5),   # Thursday
        22: datetime.date(2026, 2, 12),  # Monday
        23: datetime.date(2026, 2, 19),  # Friday
        24: datetime.date(2026, 2, 26),  # Tuesday
        25: datetime.date(2026, 3, 5),   # Saturday
        26: datetime.date(2026, 3, 12),  # Wednesday
        27: datetime.date(2026, 4, 3),   # Friday
        28: datetime.date(2026, 4, 9),   # Thursday
        29: datetime.date(2026, 4, 23),  # Monday
        30: datetime.date(2026, 4, 28),  # Friday
        31: datetime.date(2026, 5, 2),   # Tuesday
        32: datetime.date(2026, 5, 7),   # Saturday
        33: datetime.date(2026, 5, 13),  # Wednesday
        34: datetime.date(2026, 5, 21),  # Wednesday
    }
    thu_date = week_start_dates.get(week_number)
    if not thu_date:
        st.error(f"No start date defined for week {week_number}.")
        return
    days = [thu_date + datetime.timedelta(days=d) for d in range(3)]
    day_names = [day.strftime('%A') for day in days]

    selected_count = 0
    for home, away in pairings:
        match_key = (home, away)
        match_id = st.session_state.week_match_ids.get(week_number, {}).get(match_key)
        if match_id is None:
            st.write(f"Debug: No match_id found for {home} vs {away} in week {week_number}")
            continue

        if match_id in st.session_state.scenario_manager.selected_scenarios:
            selected_count += 1
            # Show selected scenario details
            scenario_id = st.session_state.scenario_manager.selected_scenarios[match_id]
            scenarios = st.session_state.scenario_manager.get_scenarios_for_match(match_id)
            selected_scenario = None
            for scenario in scenarios:
                if scenario.scenario_id == scenario_id:
                    selected_scenario = scenario
                    break
            
            if selected_scenario:
                day_name = datetime.datetime.strptime(selected_scenario.date, '%Y-%m-%d').strftime('%A')
                st.markdown(f"""
                <div style="background-color: #d4edda; border: 2px solid #28a745; border-radius: 10px; padding: 15px; margin: 10px 0;">
                    <div style="font-weight: bold; color: #155724; font-size: 18px;">✅ {home} vs {away} (SELECTED)</div>
                    <div style="color: #155724; margin-top: 5px;">
                        📅 {selected_scenario.date} ({day_name}) 🕐 {selected_scenario.time}<br>
                        🏟️ {selected_scenario.stadium} ({selected_scenario.city})<br>
                        📊 Score: {selected_scenario.suitability_score} | 👥 Attendance: {selected_scenario.attendance_percentage}% | 💰 Profit: ${selected_scenario.profit:,}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # Add button to deselect if needed
                if st.button(f"Deselect Match", key=f"deselect_{match_id}_{week_number}"):
                    # Remove from selected scenarios
                    del st.session_state.scenario_manager.selected_scenarios[match_id]
                    # Update day counts
                    current_date = datetime.datetime.strptime(selected_scenario.date, '%Y-%m-%d').date()
                    if st.session_state.day_counts.get(current_date, 0) > 0:
                        st.session_state.day_counts[current_date] -= 1
                    st.success(f"Deselected {home} vs {away}")
                    st.rerun()
            else:
                st.markdown(f"✅ {home} vs {away} (Selected - scenario details not found)")
            continue

        scenarios = st.session_state.scenario_manager.get_scenarios_for_match(match_id)
        if not scenarios:
            st.warning(f"No scenarios generated for {home} vs {away}. Check generation or filters.")
            continue

        available_scenarios = [
            s for s in scenarios
            if datetime.datetime.strptime(s.date, '%Y-%m-%d').date() in days and
            (s.is_available or st.session_state.day_counts.get(datetime.datetime.strptime(s.date, '%Y-%m-%d').date(), 0) < 3)
        ]

        st.subheader(f"{home} vs {away}")
        if not available_scenarios:
            st.info("No available scenarios (all days may be full or filtered by prayer times or team unavailability).")
            continue

        st.markdown("<div style='font-size: 0.9rem; color: #666;'>Select one scenario</div>", unsafe_allow_html=True)

        day_counts_str = ", ".join([f"{day_names[i]} ({st.session_state.day_counts.get(day, 0)}/3)" for i, day in enumerate(days)])
        st.markdown(f"<div style='font-size: 0.8rem; color: #888;'>Current day assignments: {day_counts_str}</div>", unsafe_allow_html=True)

        cols = st.columns(3)
        for i, scenario in enumerate(available_scenarios):
            with cols[i % 3]:
                card_color = "#e8f5e9" if scenario.suitability_score > 80 else "#fff3e0" if scenario.suitability_score > 60 else "#ffebee"
                border_color = "#4caf50" if scenario.suitability_score > 80 else "#ff9800" if scenario.suitability_score > 60 else "#f44336"
                availability_message = "" if scenario.is_available else "<div style='color: #d32f2f; font-weight: bold;'>⚠️ Unavailable: Team conflict</div>"

                day_name = datetime.datetime.strptime(scenario.date, '%Y-%m-%d').strftime('%A')
                st.markdown(
                    f"""
                    <div style="background-color: {card_color}; border-radius: 10px; padding: 15px; margin: 10px 0; border: 2px solid {border_color};">
                        <div style="font-weight: bold;">📅 {scenario.date} ({day_name}) 🕐 {scenario.time}</div>
                        <div>🏟️ {scenario.stadium} ({scenario.city})</div>
                        <div>📊 Score: {scenario.suitability_score}</div>
                        <div>👥 Attendance: {scenario.attendance_percentage}%</div>
                        <div>💰 Profit: ${scenario.profit:,}</div>
                        {availability_message}
                    </div>
                    """, unsafe_allow_html=True
                )
                if scenario.is_available:
                    if st.button(f"Select", key=f"select_{scenario.scenario_id}_{week_number}_{match_id}"):
                        current_date = datetime.datetime.strptime(scenario.date, '%Y-%m-%d').date()
                        if st.session_state.day_counts.get(current_date, 0) >= 3:
                            st.error(f"Cannot select: {current_date} is full (3 matches).")
                        else:
                            # Update day counts
                            st.session_state.day_counts[current_date] = st.session_state.day_counts.get(current_date, 0) + 1
                            
                            # Select the scenario
                            st.session_state.scenario_manager.select_scenario(match_id, scenario.scenario_id)
                            
                            # Store selected match details for calendar and other tabs
                            st.session_state.selected_match_id = match_id
                            st.session_state.match_teams = [home, away]
                            st.session_state.match_date = scenario.date
                            st.session_state.match_time = scenario.time
                            st.session_state.match_stadium = scenario.stadium
                            st.session_state.match_city = scenario.city
                            
                            # Add to schedule_df if it exists
                            if 'schedule_df' in st.session_state:
                                # Create a new row for the selected match
                                new_match = pd.DataFrame([{
                                    'match_id': match_id,
                                    'home_team': home,
                                    'away_team': away,
                                    'date': scenario.date,
                                    'time': scenario.time,
                                    'city': scenario.city,
                                    'stadium': scenario.stadium,
                                    'suitability_score': scenario.suitability_score,
                                    'attendance_percentage': scenario.attendance_percentage,
                                    'profit': scenario.profit,
                                    'week': week_number,
                                    'is_selected': True
                                }])
                                
                                # Remove any existing entry for this match_id and add the new one
                                if 'match_id' in st.session_state.schedule_df.columns:
                                    st.session_state.schedule_df = st.session_state.schedule_df[
                                        st.session_state.schedule_df['match_id'] != match_id
                                    ]
                                st.session_state.schedule_df = pd.concat([st.session_state.schedule_df, new_match], ignore_index=True)
                            
                            st.success(f"Selected {scenario.date} {scenario.time} for {home} vs {away}.")
                            st.write(f"Debug: Stored - match_id: {match_id}, teams: {home} vs {away}, date: {scenario.date}")
                            
                            # Remove scenarios from other matches that conflict with this date/stadium
                            if st.session_state.day_counts[current_date] >= 3:
                                for m_id in st.session_state.scenario_manager.scenarios:
                                    if m_id not in st.session_state.scenario_manager.selected_scenarios:
                                        st.session_state.scenario_manager.scenarios[m_id] = [
                                            s for s in st.session_state.scenario_manager.scenarios[m_id]
                                            if datetime.datetime.strptime(s.date, '%Y-%m-%d').date() != current_date
                                        ]
                            
                            st.rerun()
                else:
                    st.button(f"Select", key=f"select_{scenario.scenario_id}_{week_number}_{match_id}", disabled=True)

    if selected_count == len(pairings):
        st.success(f"All {len(pairings)} matches selected for week {week_number}!")

def extract_team_city_data(df):
    return df[['team', 'home_city', 'home_stadium', 'strength']].copy()






def get_available_stadiums_for_city(teams_data, match_date, exclude_stadium=None):
    """
    Get a list of available stadiums, respecting unavailability periods.
    """
    all_stadiums = teams_data["home_stadium"].unique().tolist()
    available_stadiums = []
    
    for stadium in all_stadiums:
        alt_stadium = get_alternative_stadium(stadium, match_date)
        if alt_stadium != stadium or stadium not in STADIUM_UNAVAILABILITY:
            if alt_stadium != exclude_stadium:
                available_stadiums.append(alt_stadium)
        elif stadium != exclude_stadium:
            available_stadiums.append(stadium)
    
    return available_stadiums


# ---------- Helper: Encode local PNG as Base64 ----------
@st.cache_data
def get_base64_of_image(path):
    try:
        if os.path.exists(path):
            with open(path, "rb") as img_file:
                return base64.b64encode(img_file.read()).decode()
        else:
            return None
    except Exception:
        return None

def check_weather_suitability(weather_data, city, date):
    """Check if weather is suitable for a match in the given city and date."""
    if weather_data is None or weather_data.empty:
        return True, "No weather data available, assuming suitable"
    
    date_column = 'Date'
    city_column = 'city'
    temp_column = 'temperature'
    precip_column = 'precipitation'
    
    required_columns = [city_column, date_column, temp_column, precip_column]
    missing_columns = [col for col in required_columns if col not in weather_data.columns]
    if missing_columns:
        # print(f"Warning: Missing columns {missing_columns} in weather_data. Assuming suitable weather.")
        return True, f"Missing columns {missing_columns}, assuming suitable"
    
    if not pd.api.types.is_datetime64_any_dtype(weather_data[date_column]):
        weather_data[date_column] = pd.to_datetime(weather_data[date_column], errors='coerce')
    
    try:
        weather_row = weather_data[
            (weather_data[city_column] == city) & 
            (weather_data[date_column].dt.date == date)
        ]
        if weather_row.empty:
            return True, "No weather data for date/city, assuming suitable"
        
        temperature = weather_row[temp_column].iloc[0]
        precipitation = weather_row[precip_column].iloc[0]
        
        if temperature > 40 or precipitation > 10:
            return False, f"Unsuitable weather: temperature {temperature}°C, precipitation {precipitation}mm"
        return True, "Weather suitable"
    except Exception as e:
        print(f"Error processing weather data for {city} on {date}: {str(e)}")
        return True, f"Error in weather data processing: {str(e)}, assuming suitable"
    
def is_international_stop_day(check_date, afc_df):
    """Check if a date falls within a FIFA International Window."""
    if afc_df is not None and not afc_df.empty:
        for _, event in afc_df.iterrows():
            if event['category'] == "FIFA International Window":
                try:
                    event_start = event["start_date"].date()
                    event_end = event["end_date"].date()
                    if event_start <= check_date <= event_end:
                        return True, f"FIFA International Window ({event['event']}) from {event_start} to {event_end}"
                except:
                    continue
    return False, ""

def generate_full_schedule_with_isha(teams_data, weather_data, attendance_model, profit_model, models_loaded, start_date, end_date, selected_teams=None, selected_cities=None, selected_time_filters=None, matches_per_week=9, matches_from_excel=None):
    st.write("Starting scenario generation for weeks 7 to 34...")
    scenario_manager = st.session_state.scenario_manager
    scenario_manager.scenarios = {}
    scenario_manager.selected_scenarios = {}

    match_id_counter = 0
    scenario_id_counter = 0
    total_scenarios_generated = 0

    if 'day_counts' not in st.session_state:
        st.session_state.day_counts = {}

    if not matches_from_excel:
        st.error("No matches provided.")
        return pd.DataFrame()

    weeks_to_process = [w for w in matches_from_excel if 7 <= w <= 34]
    if not weeks_to_process:
        weeks_to_process = list(range(7, 35))

    week_start_dates = {
        7: datetime.date(2025, 10, 30),  # Thursday
        8: datetime.date(2025, 11, 6),   # Thursday
        9: datetime.date(2025, 11, 21),  # Friday
        10: datetime.date(2025, 12, 19), # Friday
        11: datetime.date(2025, 12, 25), # Thursday
        12: datetime.date(2025, 12, 29), # Monday
        13: datetime.date(2026, 1, 2),   # Friday
        14: datetime.date(2026, 1, 8),   # Thursday
        15: datetime.date(2026, 1, 12),  # Monday
        16: datetime.date(2026, 1, 16),  # Friday
        17: datetime.date(2026, 1, 20),  # Tuesday
        18: datetime.date(2026, 1, 24),  # Saturday
        19: datetime.date(2026, 1, 28),  # Wednesday
        20: datetime.date(2026, 2, 1),   # Sunday
        21: datetime.date(2026, 2, 5),   # Thursday
        22: datetime.date(2026, 2, 12),  # Thursday
        23: datetime.date(2026, 2, 19),  # Thursday
        24: datetime.date(2026, 2, 26),  # Thursday
        25: datetime.date(2026, 3, 5),   # Thursday
        26: datetime.date(2026, 3, 12),  # Thursday
        27: datetime.date(2026, 4, 3),   # Friday
        28: datetime.date(2026, 4, 9),   # Thursday
        29: datetime.date(2026, 4, 23),  # Thursday
        30: datetime.date(2026, 4, 28),  # Tuesday
        31: datetime.date(2026, 5, 2),   # Saturday
        32: datetime.date(2026, 5, 7),   # Thursday
        33: datetime.date(2026, 5, 13),  # Wednesday
        34: datetime.date(2026, 5, 21),  # Thursday
    }

    # Redistribute to enforce limits
    redistributed_matches = validate_and_redistribute_matches(matches_from_excel, week_start_dates)

    st.session_state.week_match_ids = {week: {} for week in weeks_to_process}

    for week in weeks_to_process:
        pairings = redistributed_matches.get(week, [])
        for home_team, away_team, preferred_date in pairings:
            match_id = match_id_counter
            st.session_state.week_match_ids[week][(home_team, away_team)] = match_id
            match_id_counter += 1
            st.write(f"Match ID {match_id}: {home_team} vs {away_team} (preferred: {preferred_date})")

    teams_data_normalized = teams_data.copy()
    teams_data_normalized['team_lower'] = teams_data_normalized['team'].str.lower()

    season_end_date = datetime.date(2026, 5, 21)  # Extended to cover all weeks up to 34

    default_time_slots = [
        ('Monday', '18:00'), ('Monday', '19:00'), ('Monday', '21:00'),
        ('Tuesday', '18:00'), ('Tuesday', '19:00'), ('Tuesday', '21:00'),
        ('Wednesday', '18:00'), ('Wednesday', '19:00'), ('Wednesday', '21:00'),
        ('Thursday', '18:00'), ('Thursday', '19:00'), ('Thursday', '21:00'),
        ('Friday', '16:00'), ('Friday', '18:00'), ('Friday', '21:00'),
        ('Saturday', '12:00'), ('Saturday', '16:00'), ('Saturday', '21:00'),
        ('Sunday', '12:00'), ('Sunday', '16:00'), ('Sunday', '21:00')
    ]
    extra_time_slots = [
        ('Monday', '15:00'), ('Monday', '17:00'),
        ('Tuesday', '15:00'), ('Tuesday', '17:00'),
        ('Wednesday', '15:00'), ('Wednesday', '17:00'),
        ('Thursday', '15:00'), ('Thursday', '17:00'),
        ('Friday', '15:00'), ('Friday', '17:00'),
        ('Saturday', '15:00'), ('Saturday', '17:00'),
        ('Sunday', '15:00'), ('Sunday', '17:00')
    ]

    for week in weeks_to_process:
        thu_this_week = week_start_dates.get(week)
        if not thu_this_week:
            st.warning(f"No start date defined for week {week}. Skipping.")
            continue
        days = [thu_this_week + datetime.timedelta(days=d) for d in range(3)]
        day_names = [days[i].strftime('%A') for i in range(len(days))]
        st.write(f"Week {week} days: {days}, day_names: {day_names}")

        for day in days:
            day_name = day.strftime('%A')
            if day_name not in st.session_state.day_counts:
                st.session_state.day_counts[day_name] = {day: 0}
            elif day not in st.session_state.day_counts[day_name]:
                st.session_state.day_counts[day_name][day] = 0

        available_days = [d for d in days if st.session_state.day_counts.get(d.strftime('%A'), {}).get(d, 0) < 3]
        if not available_days:
            st.warning(f"No available days for week {week}.")
            continue

        current_assignments = {day_name: st.session_state.day_counts.get(day_name, {}).get(next(d for d in days if d.strftime('%A') == day_name), 0) for day_name in day_names}
        st.write("Current day assignments:", ", ".join([f"{day} ({count}/3)" for day, count in current_assignments.items()]))

        pairings = redistributed_matches.get(week, [])
        for home_team, away_team, preferred_date in pairings:
            match_id = st.session_state.week_match_ids[week].get((home_team, away_team))
            if match_id is None:
                st.warning(f"No match ID for {home_team} vs {away_team} in week {week}. Skipping.")
                continue

            home_team_info = teams_data_normalized[teams_data_normalized['team_lower'] == home_team.lower()].iloc[0]
            away_team_info = teams_data_normalized[teams_data_normalized['team_lower'] == away_team.lower()].iloc[0]
            actual_city = home_team_info['city']
            actual_stadium = get_alternative_stadium(home_team_info['stadium'], preferred_date)

            scenarios_for_match = []
            match_scenarios_total = 0
            used_slots_per_day = {day: set() for day in available_days}

            day_order = [preferred_date] + [d for d in available_days if d != preferred_date]
            for day in day_order:
                if day not in available_days or match_scenarios_total >= 9:
                    continue
                day_of_week = day_names[days.index(day)]
                applicable_slots = [(dow, time) for dow, time in default_time_slots if dow == day_of_week]
                is_available = is_team_available(home_team, day) and is_team_available(away_team, day)
                for _, initial_time in applicable_slots:
                    if initial_time in used_slots_per_day[day] or match_scenarios_total >= 9:
                        continue

                    calculated = calculate_match_times_for_city_and_date(actual_city, day, teams_data_normalized)
                    isha_time_str = calculated.get('isha_time', 'N/A')
                    maghrib_time_str = calculated.get('maghrib_time', 'N/A')
                    maghrib_slots = calculated.get('maghrib_slots', {
                        'Monday': '19:00',
                        'Tuesday': '19:00',
                        'Wednesday': '19:00',
                        'Thursday': '19:00',
                        'Friday': '16:00',
                        'Saturday': '12:00',
                        'Sunday': '12:00'
                    })
                    isha_slots = calculated.get('isha_slots', {
                        'Monday': '21:00',
                        'Tuesday': '21:00',
                        'Wednesday': '21:00',
                        'Thursday': '21:00',
                        'Friday': '18:00',
                        'Saturday': '16:00',
                        'Sunday': '16:00'
                    })

                    default_maghrib = "17:45" if actual_city == 'Jeddah' else "17:48"
                    default_isha = "19:15" if actual_city == 'Jeddah' else "19:18"

                    if isha_time_str == 'N/A' or maghrib_time_str == 'N/A':
                        st.warning(f"Prayer times missing for {actual_city} on {day}. Using defaults (Maghrib: {default_maghrib}, Isha: {default_isha}).")
                        maghrib_time_str = default_maghrib
                        isha_time_str = default_isha

                    try:
                        maghrib_hour, maghrib_minute = map(int, maghrib_time_str.split(":"))
                        maghrib_datetime = datetime.datetime(day.year, day.month, day.day, maghrib_hour, maghrib_minute)
                        isha_hour, isha_minute = map(int, isha_time_str.split(":"))
                        isha_datetime = datetime.datetime(day.year, day.month, day.day, isha_hour, isha_minute)
                    except ValueError as e:
                        st.error(f"Error parsing prayer times for {actual_city} on {day}: {e}. Using defaults.")
                        maghrib_hour, maghrib_minute = map(int, default_maghrib.split(":"))
                        maghrib_datetime = datetime.datetime(day.year, day.month, day.day, maghrib_hour, maghrib_minute)
                        isha_hour, isha_minute = map(int, default_isha.split(":"))
                        isha_datetime = datetime.datetime(day.year, day.month, day.day, isha_hour, isha_minute)

                    proposed_start_dt = datetime.datetime.combine(day, datetime.datetime.strptime(initial_time, '%H:%M').time())
                    duration = datetime.timedelta(minutes=52)
                    proposed_end_dt = proposed_start_dt + duration
                    buffer = datetime.timedelta(minutes=30)

                    if initial_time == '21:00':
                        start_time = '21:00'
                        prayer_key = 'None'
                        prayer_time_str = 'N/A'
                    elif initial_time == maghrib_slots.get(day_of_week):
                        if proposed_end_dt > maghrib_datetime - buffer:
                            start_dt = maghrib_datetime - duration - buffer
                            start_time = start_dt.strftime('%H:%M')
                            prayer_key = 'Maghrib'
                            prayer_time_str = maghrib_time_str
                        else:
                            start_time = initial_time
                            prayer_key = 'None'
                            prayer_time_str = 'N/A'
                    elif initial_time == isha_slots.get(day_of_week):
                        if proposed_end_dt > isha_datetime - buffer:
                            start_dt = isha_datetime - duration - buffer
                            start_time = start_dt.strftime('%H:%M')
                            prayer_key = 'Isha'
                            prayer_time_str = isha_time_str
                        else:
                            start_time = initial_time
                            prayer_key = 'None'
                            prayer_time_str = 'N/A'
                    else:
                        if proposed_end_dt > maghrib_datetime - buffer:
                            start_dt = maghrib_datetime - duration - buffer
                            start_time = start_dt.strftime('%H:%M')
                            prayer_key = 'Maghrib'
                            prayer_time_str = maghrib_time_str
                        elif proposed_end_dt > isha_datetime - buffer:
                            start_dt = isha_datetime - duration - buffer
                            start_time = start_dt.strftime('%H:%M')
                            prayer_key = 'Isha'
                            prayer_time_str = isha_time_str
                        else:
                            start_time = initial_time
                            prayer_key = 'None'
                            prayer_time_str = 'N/A'

                    scenario = MatchScenario(
                        scenario_id=scenario_id_counter,
                        match_id=match_id,
                        home_team=home_team,
                        away_team=away_team,
                        date=day.strftime('%Y-%m-%d'),
                        time=start_time,
                        city=actual_city,
                        stadium=actual_stadium,
                        suitability_score=100 if is_available else 0,
                        attendance_percentage=random.randint(40, 95) if is_available else 0,
                        profit=random.randint(3000, 10000) if is_available else 0,
                        is_available=is_available
                    )
                    scenarios_for_match.append(scenario)
                    scenario_id_counter += 1
                    match_scenarios_total += 1
                    used_slots_per_day[day].add(start_time)
                    if is_available:
                        day_name = day.strftime('%A')
                        st.session_state.day_counts[day_name][day] += 1
                    total_scenarios_generated += 1
                    st.write(f"Scenario {match_scenarios_total} for {home_team} vs {away_team}: {day} {start_time} (adjusted from {prayer_time_str} for {prayer_key}, {'Available' if is_available else 'Unavailable'})")

            if match_scenarios_total < 9:
                for day in available_days:
                    if match_scenarios_total >= 9:
                        break
                    day_of_week = day_names[days.index(day)]
                    extra_slots = [(dow, time) for dow, time in extra_time_slots if dow == day_of_week]
                    is_available = is_team_available(home_team, day) and is_team_available(away_team, day)
                    for _, initial_time in extra_slots:
                        if initial_time in used_slots_per_day[day] or match_scenarios_total >= 9:
                            continue

                        calculated = calculate_match_times_for_city_and_date(actual_city, day, teams_data_normalized)
                        isha_time_str = calculated.get('isha_time', 'N/A')
                        maghrib_time_str = calculated.get('maghrib_time', 'N/A')
                        maghrib_slots = calculated.get('maghrib_slots', {
                            'Monday': '19:00',
                            'Tuesday': '19:00',
                            'Wednesday': '19:00',
                            'Thursday': '19:00',
                            'Friday': '16:00',
                            'Saturday': '12:00',
                            'Sunday': '12:00'
                        })
                        isha_slots = calculated.get('isha_slots', {
                            'Monday': '21:00',
                            'Tuesday': '21:00',
                            'Wednesday': '21:00',
                            'Thursday': '21:00',
                            'Friday': '18:00',
                            'Saturday': '16:00',
                            'Sunday': '16:00'
                        })

                        default_maghrib = "17:45" if actual_city == 'Jeddah' else "17:48"
                        default_isha = "19:15" if actual_city == 'Jeddah' else "19:18"

                        if isha_time_str == 'N/A' or maghrib_time_str == 'N/A':
                            st.warning(f"Prayer times missing for {actual_city} on {day}. Using defaults (Maghrib: {default_maghrib}, Isha: {default_isha}).")
                            maghrib_time_str = default_maghrib
                            isha_time_str = default_isha

                        try:
                            maghrib_hour, maghrib_minute = map(int, maghrib_time_str.split(":"))
                            maghrib_datetime = datetime.datetime(day.year, day.month, day.day, maghrib_hour, maghrib_minute)
                            isha_hour, isha_minute = map(int, isha_time_str.split(":"))
                            isha_datetime = datetime.datetime(day.year, day.month, day.day, isha_hour, isha_minute)
                        except ValueError as e:
                            st.error(f"Error parsing prayer times for {actual_city} on {day}: {e}. Using defaults.")
                            maghrib_hour, maghrib_minute = map(int, default_maghrib.split(":"))
                            maghrib_datetime = datetime.datetime(day.year, day.month, day.day, maghrib_hour, maghrib_minute)
                            isha_hour, isha_minute = map(int, default_isha.split(":"))
                            isha_datetime = datetime.datetime(day.year, day.month, day.day, isha_hour, isha_minute)

                        proposed_start_dt = datetime.datetime.combine(day, datetime.datetime.strptime(initial_time, '%H:%M').time())
                        duration = datetime.timedelta(minutes=52)
                        proposed_end_dt = proposed_start_dt + duration
                        buffer = datetime.timedelta(minutes=30)

                        if initial_time == '21:00':
                            start_time = '21:00'
                            prayer_key = 'None'
                            prayer_time_str = 'N/A'
                        elif initial_time == maghrib_slots.get(day_of_week):
                            if proposed_end_dt > maghrib_datetime - buffer:
                                start_dt = maghrib_datetime - duration - buffer
                                start_time = start_dt.strftime('%H:%M')
                                prayer_key = 'Maghrib'
                                prayer_time_str = maghrib_time_str
                            else:
                                start_time = initial_time
                                prayer_key = 'None'
                                prayer_time_str = 'N/A'
                        elif initial_time == isha_slots.get(day_of_week):
                            if proposed_end_dt > isha_datetime - buffer:
                                start_dt = isha_datetime - duration - buffer
                                start_time = start_dt.strftime('%H:%M')
                                prayer_key = 'Isha'
                                prayer_time_str = isha_time_str
                            else:
                                start_time = initial_time
                                prayer_key = 'None'
                                prayer_time_str = 'N/A'
                        else:
                            if proposed_end_dt > maghrib_datetime - buffer:
                                start_dt = maghrib_datetime - duration - buffer
                                start_time = start_dt.strftime('%H:%M')
                                prayer_key = 'Maghrib'
                                prayer_time_str = maghrib_time_str
                            elif proposed_end_dt > isha_datetime - buffer:
                                start_dt = isha_datetime - duration - buffer
                                start_time = start_dt.strftime('%H:%M')
                                prayer_key = 'Isha'
                                prayer_time_str = isha_time_str
                            else:
                                start_time = initial_time
                                prayer_key = 'None'
                                prayer_time_str = 'N/A'

                        scenario = MatchScenario(
                            scenario_id=scenario_id_counter,
                            match_id=match_id,
                            home_team=home_team,
                            away_team=away_team,
                            date=day.strftime('%Y-%m-%d'),
                            time=start_time,
                            city=actual_city,
                            stadium=actual_stadium,
                            suitability_score=100 if is_available else 0,
                            attendance_percentage=random.randint(40, 95) if is_available else 0,
                            profit=random.randint(3000, 10000) if is_available else 0,
                            is_available=is_available
                        )
                        scenarios_for_match.append(scenario)
                        scenario_id_counter += 1
                        match_scenarios_total += 1
                        used_slots_per_day[day].add(start_time)
                        if is_available:
                            day_name = day.strftime('%A')
                            st.session_state.day_counts[day_name][day] += 1
                        st.write(f"Extra scenario {match_scenarios_total} for {home_team} vs {away_team}: {day} {start_time}")

            scenarios_for_match = scenarios_for_match[:9]
            for scenario in scenarios_for_match:
                if match_id not in scenario_manager.scenarios:
                    scenario_manager.scenarios[match_id] = []
                scenario_manager.scenarios[match_id].append(scenario)

            st.write(f"Generated {len(scenarios_for_match)} scenarios for match {match_id}")

    scenarios_df = pd.DataFrame([s.to_dict() for match_scenarios in scenario_manager.scenarios.values() for s in match_scenarios])
    if not scenarios_df.empty:
        scenarios_df = scenarios_df.sort_values(by=['date', 'time'])
    return scenarios_df

def check_afc_conflicts(schedule_df, afc_df):
    if schedule_df.empty:
        st.warning("Schedule DataFrame is empty. No conflicts to check.")
        return schedule_df

    # Identify date column
    date_column = None
    possible_date_columns = ['date', 'match_date', 'game_date']
    for col in possible_date_columns:
        if col in schedule_df.columns:
            date_column = col
            break
    
    if date_column is None:
        st.error("No date column found in schedule_df. Expected one of: " + ", ".join(possible_date_columns))
        return schedule_df
    
    schedule_df['afc_conflict'] = False
    schedule_df['conflict_reason'] = ''
    schedule_df['international_stop'] = False
    schedule_df['auto_rescheduled'] = False
    schedule_df['original_date'] = schedule_df[date_column].copy()
    
    international_teams = [
        'Al Hilal', 'Al Nassr', 'Al Ahli', 'Al Ittihad', 'Al Shabab',
        'Persepolis', 'Esteghlal', 'Sepahan',
        'Al Ain', 'Al Wahda', 'Shabab Al Ahli',
        'Al Sadd', 'Al Duhail', 'Al Rayyan'
    ]
    
    conflicts_found = []
    
    for idx, match in schedule_df.iterrows():
        match_date = pd.to_datetime(match[date_column]).date()
        home_team = match['home_team']
        away_team = match['away_team']
        
        for _, afc_event in afc_df.iterrows():
            try:
                afc_start = afc_event['start_date'].date() if isinstance(afc_event['start_date'], (pd.Timestamp, datetime.datetime)) else pd.to_datetime(afc_event['start_date']).date()
                afc_end = afc_event['end_date'].date() if isinstance(afc_event['end_date'], (pd.Timestamp, datetime.datetime)) else pd.to_datetime(afc_event['end_date']).date()
                if afc_start <= match_date <= afc_end:
                    schedule_df.at[idx, 'afc_conflict'] = True
                    schedule_df.at[idx, 'conflict_reason'] = f"Conflicts with {afc_event['event']}"
                    
                    if 'FIFA Int\'l Window' in afc_event['event']:
                        if home_team in international_teams or away_team in international_teams:
                            schedule_df.at[idx, 'international_stop'] = True
                            international_teams_involved = []
                            if home_team in international_teams:
                                international_teams_involved.append(home_team)
                            if away_team in international_teams:
                                international_teams_involved.append(away_team)
                            schedule_df.at[idx, 'conflict_reason'] += f" (International teams on duty: {', '.join(international_teams_involved)})"
                    
                    new_date = find_available_date(schedule_df, afc_df, match_date, idx)
                    if new_date:
                        schedule_df.at[idx, date_column] = new_date.strftime('%Y-%m-%d')
                        schedule_df.at[idx, 'auto_rescheduled'] = True
                        schedule_df.at[idx, 'afc_conflict'] = False
                        schedule_df.at[idx, 'conflict_reason'] = f"Auto-rescheduled from {match_date} due to {afc_event['event']}"
                    
                    conflicts_found.append({
                        'match_id': match.get('match_id', idx),
                        'teams': f"{home_team} vs {away_team}",
                        'original_date': match_date,
                        'new_date': new_date if new_date else None,
                        'afc_event': afc_event['event'],
                        'resolved': new_date is not None
                    })
                    break
            except Exception as e:
                st.error(f"Error processing AFC event dates in check_afc_conflicts: {e}")
                st.write(f"AFC event: {afc_event.to_dict()}, match_date: {match_date}")
                continue
    
    if 'conflict_summary' not in st.session_state:
        st.session_state.conflict_summary = []
    st.session_state.conflict_summary.extend(conflicts_found)
    
    return schedule_df


def find_available_date(schedule_df, afc_df, original_date, exclude_idx, max_days_offset=14):
    for offset in range(1, max_days_offset + 1):
        for direction in [-1, 1]:
            candidate_date = original_date + datetime.timedelta(days=offset * direction)
            afc_conflict = False
            for _, afc_event in afc_df.iterrows():
                afc_start = afc_event['start_date'].date()
                afc_end = afc_event['end_date'].date()
                if afc_start <= candidate_date <= afc_end:
                    afc_conflict = True
                    break
            if afc_conflict:
                continue
            existing_conflict = False
            for idx, match in schedule_df.iterrows():
                if idx == exclude_idx:
                    continue
                if pd.to_datetime(match['date']).date() == candidate_date:
                    existing_conflict = True
                    break
            if not existing_conflict:
                return candidate_date
    return None



def get_week_number(match_date, start_date):
    """Calculate week number based on match date relative to September 27, 2025."""
    # Use September 27, 2025, as the start of Week 1
    calendar_start_date = datetime.date(2025, 8, 28)
    
    # Convert match_date to date object if it's a datetime or string
    if isinstance(match_date, str):
        match_date = pd.to_datetime(match_date).date()
    elif isinstance(match_date, pd.Timestamp):
        match_date = match_date.date()
    elif isinstance(match_date, datetime.datetime):
        match_date = match_date.date()
    
    # Convert start_date to date object if it's a datetime (though not used)
    if isinstance(start_date, datetime.datetime):
        start_date = start_date.date()
    
    # Calculate the difference in days from calendar_start_date
    delta_days = (match_date - calendar_start_date).days
    
    # Assign week number only for dates on or after September 27, 2025
    if delta_days >= 0:
        week_number = (delta_days // 7) + 1
        return max(1, week_number)
    else:
        return 0  # Or return "" for no week number, depending on your display preference

import html


def show_afc_replica_calendar_tab():
    event_color_map = {
        "Match": "#0d6efd", "ACL Elite": "#0d6efd", "ACL Two": "#0dcaf0",
        "ACGL": "#d63384", "AWCL": "#ffc107", "Asian Cup Qualifiers": "#0d6efd",
        "FIFA International Window": "#dc3545", "FIFA Event": "#dc3545",
        "Tournament": "#6f42c1", "Qualifiers": "#198754", "Other": "#6c757d",
    }

    afc_events_from_image = [
        {"event": "AQ 9", "start_date": "2025-06-09", "end_date": "2025-06-09", "category": "Asian Cup Qualifiers"},
        {"event": "AQ 10", "start_date": "2025-06-10", "end_date": "2025-06-10", "category": "Asian Cup Qualifiers"},
        {"event": "ACQ FR2", "start_date": "2025-06-12", "end_date": "2025-06-12", "category": "Asian Cup Qualifiers"},
        {"event": "FIFA Int'l Window (Men's)", "start_date": "2025-06-02", "end_date": "2025-06-10", "category": "FIFA International Window"},
        {"event": "FIFA Club World Cup 2025", "start_date": "2025-06-15", "end_date": "2025-07-13", "category": "FIFA Event"},
        {"event": "Women's Asian Cup 2026 Qualifiers", "start_date": "2025-06-23", "end_date": "2025-07-01", "category": "Qualifiers"},
        {"event": "FIFA Int'l Window (Women's)", "start_date": "2025-06-16", "end_date": "2025-06-24", "category": "FIFA International Window"},
        {"event": "PS1", "start_date": "2025-07-29", "end_date": "2025-07-29", "category": "ACL Two"}, 
        {"event": "PS1", "start_date": "2025-07-30", "end_date": "2025-07-30", "category": "ACL Two"},
        {"event": "PS2", "start_date": "2025-08-05", "end_date": "2025-08-05", "category": "ACL Two"}, 
        {"event": "PS2", "start_date": "2025-08-06", "end_date": "2025-08-06", "category": "ACL Two"},
        {"event": "PS3", "start_date": "2025-08-12", "end_date": "2025-08-12", "category": "ACL Two"}, 
        {"event": "PS3", "start_date": "2025-08-13", "end_date": "2025-08-13", "category": "ACL Two"},
        {"event": "U23 Asian Cup 2026 Qualifiers", "start_date": "2025-08-18", "end_date": "2025-08-26", "category": "Qualifiers"},
        {"event": "AWCL - Prelim Stage", "start_date": "2025-08-25", "end_date": "2025-08-31", "category": "AWCL"},
        {"event": "FIFA Int'l Window (Men's)", "start_date": "2025-09-01", "end_date": "2025-09-09", "category": "FIFA International Window"},
        {"event": "MD1 (W)", "start_date": "2025-09-16", "end_date": "2025-09-16", "category": "ACL Elite"}, 
        {"event": "MD1 (E)", "start_date": "2025-09-17", "end_date": "2025-09-17", "category": "ACL Elite"},
        {"event": "MD2 (W)", "start_date": "2025-09-30", "end_date": "2025-09-30", "category": "ACL Elite"}, 
        {"event": "MD2 (E)", "start_date": "2025-10-01", "end_date": "2025-10-01", "category": "ACL Elite"},
        {"event": "Futsal Asian Cup 2026 Qualifiers", "start_date": "2025-09-15", "end_date": "2025-09-26", "category": "Qualifiers"},
    ]
    
    if 'afc_events' not in st.session_state:
        st.session_state.afc_events = afc_events_from_image
    
    afc_df = pd.DataFrame(afc_events_from_image)
    afc_df['start_date'] = pd.to_datetime(afc_df['start_date'])
    afc_df['end_date'] = pd.to_datetime(afc_df['end_date'])

    # Initialize all_events with AFC events
    all_events = []
    for _, row in afc_df.iterrows(): 
        all_events.append(row.to_dict())

    # Add selected matches from scenario manager with week numbers
    scenario_manager = st.session_state.scenario_manager
    for match_id, scenario_id in scenario_manager.selected_scenarios.items():
        # Find the selected scenario
        scenarios = scenario_manager.get_scenarios_for_match(match_id)
        selected_scenario = None
        for scenario in scenarios:
            if scenario.scenario_id == scenario_id:
                selected_scenario = scenario
                break
        
        if selected_scenario:
            # Find the week number for this match_id
            week_number = None
            for week, match_ids in st.session_state.week_match_ids.items():
                if match_id in match_ids.values():
                    week_number = week
                    break
            
            match_date = datetime.datetime.strptime(selected_scenario.date, '%Y-%m-%d')
            all_events.append({
                'match_id': match_id,
                'home_team': selected_scenario.home_team,
                'away_team': selected_scenario.away_team,
                'event': f"{selected_scenario.home_team} vs {selected_scenario.away_team} (Selected)",
                'category': 'Match',
                'start_date': match_date,
                'end_date': match_date,
                'date': match_date.date(),
                'time': selected_scenario.time,
                'stadium': selected_scenario.stadium,
                'city': selected_scenario.city,
                'week': week_number  # Store the actual week number
            })

    # Convert to DataFrame and handle dates
    events_df = pd.DataFrame(all_events)
    if not events_df.empty:
        events_df['start_date'] = pd.to_datetime(events_df['start_date'])
        events_df = events_df.sort_values(by='start_date').reset_index(drop=True)
    
    # Debug information
    selected_matches = events_df[events_df['event'].str.contains('Selected', na=False)]
    st.write(f"Total events in calendar: {len(events_df)}")
    st.write(f"Selected matches in calendar: {len(selected_matches)}")

    # CSS for calendar
    st.markdown("""
        <style>
            .selected-match { background-color: #28a745 !important; color: white !important; }
            .selected-match:hover { background-color: #218838 !important; }
            .match-event { background-color: #0d6efd; color: white; }
            .event-indicator { 
                width: 100%; height: 25px; border-radius: 3px; font-size: 9px; 
                text-align: center; margin-bottom: 2px; padding: 2px; 
                cursor: pointer; display: block; overflow: hidden;
            }
            .day-cell { 
                background-color: white; border: 1px solid #e9ecef; 
                min-height: 80px; padding: 5px; margin-bottom: 2px;
            }
            .month-container { 
                border: 1px solid #dee2e6; border-radius: 8px; 
                background-color: white; margin: 5px; min-width: 200px;
            }
            .month-label { 
                background: #6c757d; color: white; font-weight: bold; 
                text-align: center; padding: 10px;
            }
            .year-section { 
                display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 20px;
            }
        </style>
    """, unsafe_allow_html=True)
    
    # Generate calendar HTML safely
    calendar_html = '<div class="afc-calendar-wrapper">'
    
    # Focus on months that have selected matches
    current_year = 2025
    months_to_show = [10, 11]  # October and November where your matches are
    
    calendar_html += f'<div class="year-section">'
    
    for month_num in months_to_show:
        month_name = calendar.month_name[month_num]
        days_in_month = calendar.monthrange(current_year, month_num)[1]
        
        month_events = events_df[
            (pd.to_datetime(events_df['start_date']).dt.year == current_year) &
            (pd.to_datetime(events_df['start_date']).dt.month == month_num)
        ].copy()
        
        calendar_html += '<div class="month-container">'
        calendar_html += f'<div class="month-label">{month_name.upper()} {current_year}</div>'
        calendar_html += '<div class="days-grid">'
        
        for day in range(1, days_in_month + 1):
            current_date = datetime.date(current_year, month_num, day)
            
            calendar_html += f'<div class="day-cell">'
            calendar_html += f'<div style="font-weight: bold; margin-bottom: 5px;">{day}</div>'
            
            day_events = month_events[
                pd.to_datetime(month_events['start_date']).dt.date == current_date
            ]
            
            for _, event in day_events.iterrows():
                if event['category'] == 'Match':
                    event_text = str(event['event'])
                    is_selected = "(Selected)" in event_text
                    
                    # Clean the team names
                    if ' vs ' in event_text:
                        teams = event_text.replace(" (Selected)", "").split(' vs ')
                        home_team = teams[0].strip()
                        away_team = teams[1].strip() if len(teams) > 1 else "Unknown"
                    else:
                        home_team = "Unknown"
                        away_team = "Unknown"
                    
                    # Escape HTML to prevent encoding issues
                    safe_home = html.escape(home_team)
                    safe_away = html.escape(away_team)
                    safe_time = html.escape(str(event.get('time', 'TBD')))
                    
                    event_class = "selected-match" if is_selected else "match-event"
                    short_match = f"{safe_home[:10]} vs {safe_away[:10]}"
                    
                    calendar_html += f'''<div class="event-indicator {event_class}" 
                                    title="{safe_home} vs {safe_away} at {safe_time}">
                                    {short_match}
                                    </div>'''
            
            calendar_html += '</div>'
        
        calendar_html += '</div></div>'
    
    calendar_html += '</div></div>'

    # Show selected matches summary
    if len(selected_matches) > 0:
        st.subheader("Selected Matches Summary")
        for _, match in selected_matches.iterrows():
            match_date = pd.to_datetime(match['start_date']).date()
            st.write(f"✅ {match['event']} on {match_date} at {match.get('time', 'TBD')}")

    # Show which months contain selected matches
    selected_months = selected_matches['start_date'].dt.month.unique() if len(selected_matches) > 0 else []
    if len(selected_months) > 0:
        month_names = [calendar.month_name[m] for m in selected_months]

    # CSS for calendar (unchanged)
    st.markdown("""
        <style>
            .afc-calendar-wrapper { background-color: #e9ecef; padding: 15px; border: 1px solid #dee2e6; border-radius: 8px; }
            .year-section { margin-bottom: 30px; border: 2px solid #495057; border-radius: 10px; background-color: #f8f9fa; padding: 15px; display: flex; flex-direction: row; flex-wrap: nowrap; overflow-x: auto; gap: 10px; }
            .year-header { background: linear-gradient(135deg, #343a40, #495057); color: white; text-align: center; font-weight: bold; padding: 15px; font-size: 24px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
            .month-container { display: flex; flex-direction: column; border: 1px solid #dee2e6; border-radius: 8px; background-color: white; box-shadow: 0 2px 4px rgba(0,0,0,0.1); min-width: 240px; max-width: 240px; flex: 0 0 auto; }
            .month-label { background: linear-gradient(135deg, #6c757d, #495057); color: white; font-weight: bold; text-align: center; padding: 10px; font-size: 16px; width: 100%; display: flex; align-items: center; justify-content: center; }
            .days-grid { display: flex; flex-direction: column; background-color: #e9ecef; padding: 10px; max-height: 600px; overflow-y: auto; }
            .day-cell { background-color: white; border: 1px solid #e9ecef; min-height: 100px; padding: 5px; position: relative; display: flex; flex-direction: column; align-items: center; border-radius: 4px; margin-bottom: 2px; min-width: 220px; max-height: 300px; overflow-y: auto; }
            .day-number { font-weight: bold; font-size: 14px; color: #495057; margin-bottom: 5px; }
            .day-name { font-size: 10px; color: #6c757d; margin-bottom: 5px; }
            .event-indicator { width: 100%; height: 30px; border-radius: 3px; font-size: 10px; color: white; text-align: left; line-height: 30px; margin-bottom: 2px; cursor: pointer; transition: all 0.3s ease; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 0 4px; display: flex; align-items: center; justify-content: space-between; }
            .event-indicator:hover { transform: scale(1.05); box-shadow: 0 2px 4px rgba(0,0,0,0.2); z-index: 1; }
            .match-event { background-color: #0d6efd; }
            .match-event:hover { background-color: #0b5ed7; }
            .selected-match { background-color: #28a745 !important; }
            .selected-match:hover { background-color: #218838 !important; }
            .afc-event { background-color: #dc3545; }
            .weekend { background-color: #f8f9fa; }
            .today { background-color: #fff3cd; border: 2px solid #ffc107; }
            .year-section::-webkit-scrollbar { height: 8px; }
            .year-section::-webkit-scrollbar-track { background: #f1f1f1; border-radius: 4px; }
            .year-section::-webkit-scrollbar-thumb { background: #888; border-radius: 4px; }
            .year-section::-webkit-scrollbar-thumb:hover { background: #555; }
            .days-grid::-webkit-scrollbar { width: 8px; }
            .days-grid::-webkit-scrollbar-track { background: #f1f1f1; border-radius: 4px; }
            .days-grid::-webkit-scrollbar-thumb { background: #888; border-radius: 4px; }
            .days-grid::-webkit-scrollbar-thumb:hover { background: #555; }
        </style>
    """, unsafe_allow_html=True)

    # JavaScript for navigation (unchanged)
    st.markdown("""
        <script>
            function handleMatchClick(homeTeam, awayTeam, weekNumber, matchDate, matchId) {
                console.log('Match clicked:', homeTeam, 'vs', awayTeam, 'Week:', weekNumber, 'Match ID:', matchId);
                const clickedElement = event.target.closest('.event-indicator');
                if (clickedElement) {
                    clickedElement.style.transform = 'scale(0.95)';
                    clickedElement.style.opacity = '0.8';
                    setTimeout(() => {
                        clickedElement.style.transform = 'scale(1)';
                        clickedElement.style.opacity = '1';
                    }, 150);
                }
                window.parent.postMessage({
                    type: 'streamlit:setComponentValue',
                    value: {
                        navigate_to_tab1: true,
                        selected_team: homeTeam,
                        selected_week: weekNumber,
                        match_teams: [homeTeam, awayTeam],
                        match_date: matchDate,
                        match_id: matchId
                    }
                }, '*');
            }
        </script>
    """, unsafe_allow_html=True)
    
    st.header("🏆 Competition Calendar")
    st.write("Enhanced calendar view with months side by side, vertically stacked days, and larger event indicators")

    calendar_html = '<div class="afc-calendar-wrapper">'

    start_date = datetime.date(2025, 9, 1)  # Changed to include September and October
    end_date = datetime.date(2026, 6, 30)
    current_year = start_date.year
    while current_year <= end_date.year:
        calendar_html += f'<div class="year-section">'
        calendar_html += f'<div class="year-header">{current_year}</div>'
        
        start_month = 9 if current_year == 2025 else 1  # Changed to start from September
        end_month = 6 if current_year == 2026 else 12
        
        for month_num in range(start_month, end_month + 1):
            month_name = calendar.month_name[month_num]
            days_in_month = calendar.monthrange(current_year, month_num)[1]
            
            month_events = events_df[
                (pd.to_datetime(events_df['start_date']).dt.year == current_year) &
                (pd.to_datetime(events_df['start_date']).dt.month == month_num)
            ].copy()
            
            calendar_html += '<div class="month-container">'
            calendar_html += f'<div class="month-label">{month_name.upper()}</div>'
            calendar_html += '<div class="days-grid">'
                        
            for day in range(1, days_in_month + 1):
                current_date = datetime.date(current_year, month_num, day)
                weekday = current_date.weekday()
                day_name = calendar.day_name[weekday][:3]
                
                today = datetime.date.today()
                is_today = current_date == today
                is_weekend = weekday >= 5
                
                day_class = "day-cell"
                if is_weekend:
                    day_class += " weekend"
                if is_today:
                    day_class += " today"
                
                calendar_html += f'<div class="{day_class}">'
                calendar_html += f'<div class="day-number">{day}</div>'
                calendar_html += f'<div class="day-name">{day_name}</div>'
                
                day_events = month_events[
                    pd.to_datetime(month_events['start_date']).dt.date == current_date
                ]
                for _, event in day_events.iterrows():
                    if event['category'] == 'Match':
                        # Get week number directly from the event data if available
                        week_number = event.get('week', None)
                        
                        # If week number is not in event data, try to get it from the match_id
                        if week_number is None:
                            match_id = event.get('match_id')
                            if match_id is not None:
                                # Find the week for this match_id in session state
                                for week, match_ids in st.session_state.week_match_ids.items():
                                    if match_id in match_ids.values():
                                        week_number = week
                                        break
                        
                        # Fallback to calculation only if we can't find it anywhere else
                        if week_number is None:
                            week_number = get_week_number(current_date, datetime.date(2025, 9, 27))
                        
                        teams = event['event'].split(' vs ')
                        home_team = teams[0].replace(" ⚠️ CONFLICT", "").replace(" (Selected)", "") if len(teams) > 0 else ""
                        away_team = teams[1].replace(" ⚠️ CONFLICT", "").replace(" (Selected)", "") if len(teams) > 1 else ""
                        is_selected = "(Selected)" in event['event']
                        match_id = event.get('match_id', f"match_{current_date.strftime('%Y%m%d')}_{home_team.replace(' ', '_')}_{away_team.replace(' ', '_')}")
                        match_time = event.get('time', 'TBD')
                        stadium = event.get('stadium', 'TBD')
                        full_match = f"{home_team} vs {away_team}"
                        short_match = f"{home_team[:15]}{'...' if len(home_team) > 15 else ''} vs {away_team[:15]}{'...' if len(away_team) > 15 else ''}"
                        
                        # Use different CSS class for selected matches
                        event_class = "selected-match" if is_selected else "match-event"
                        title_prefix = "✅ SELECTED" if is_selected else "🏆"
                        
                        calendar_html += f'''<div class="event-indicator {event_class}" 
                                        onclick="handleMatchClick('{home_team}', '{away_team}', {week_number}, '{current_date.strftime('%Y-%m-%d')}', '{match_id}')"
                                        title="{title_prefix} {full_match} - Week {week_number} - {match_time} at {stadium} - Click to view in Weekly Calendar (Tab 1)"
                                        style="max-height: 30px; overflow: hidden; display: flex; align-items: center;">
                                        <span style="font-weight: bold; font-size: 10px; white-space: nowrap;">
                                        {short_match}
                                        </span>
                                        <div style="font-size: 8px; opacity: 0.9; margin-left: 5px;">W{week_number}</div>
                                        </div>'''
                    else:
                        color = event_color_map.get(event['category'], '#6c757d')
                        calendar_html += f'''<div class="event-indicator afc-event" 
                                        style="background-color: {color}; max-height: 30px; overflow: hidden; display: flex; align-items: center;"
                                        title="📅 {event['event']} ({event['category']})">
                                        <span style="font-size: 10px; white-space: nowrap;">
                                        {event['event'][:40]}{'...' if len(event['event']) > 40 else ''}
                                        </span>
                                        </div>'''
                
                calendar_html += '</div>'
            
            calendar_html += '</div></div>'
        
        calendar_html += '</div>'
        current_year += 1

    calendar_html += '</div>'
    st.markdown(calendar_html, unsafe_allow_html=True)

    if st.session_state.get('navigate_to_tab1', False):
        st.session_state.selected_week = st.session_state.get('selected_week', 1)
        match_teams = st.session_state.get('match_teams', [])
        st.success(f"Navigating to Tab 1 for week {st.session_state.selected_week}")
        if match_teams:
            st.info(f"🏆 Teams: {' vs '.join(match_teams)}")
        st.session_state.navigate_to_tab1 = False
        st.rerun()

    # Analytics (unchanged)
    analytics_df = pd.DataFrame([
        {'Month': event['start_date'].strftime('%B'), 'Category': event['category'], 'Event': event['event']}
        for _, event in events_df.iterrows()
    ])
    
    if not analytics_df.empty:
        st.header("📊 Calendar Analytics")
        col1, col2 = st.columns(2)
        
        with col1:
            events_per_month = analytics_df.groupby("Month").size().reset_index(name="count")
            month_order = [calendar.month_name[i] for i in range(1, 13)]
            events_per_month["Month"] = pd.Categorical(events_per_month["Month"], categories=month_order, ordered=True)
            events_per_month = events_per_month.sort_values("Month")
            fig1 = px.bar(events_per_month, x="Month", y="count", 
                         title="Total Events per Month", 
                         labels={"count": "Number of Events"},
                         color_discrete_sequence=['#0d6efd'])
            st.plotly_chart(fig1, use_container_width=True)

        with col2:
            event_types_freq = analytics_df["Category"].value_counts().reset_index()
            event_types_freq.columns = ["Category", "count"]
            fig2 = px.pie(event_types_freq, values="count", names="Category", 
                         title="Event Types Distribution", 
                         color="Category", 
                         color_discrete_map=event_color_map)
            st.plotly_chart(fig2, use_container_width=True)

        if 'schedule_df' in st.session_state:
            schedule_df_copy = st.session_state.schedule_df.copy()
            if 'afc_conflict' in schedule_df_copy.columns:
                conflicts = schedule_df_copy[schedule_df_copy['afc_conflict'] == True]
                if not conflicts.empty:
                    st.warning(f"⚠️ {len(conflicts)} matches have conflicts with AFC events")
                    with st.expander("View Conflicted Matches"):
                        display_columns = ['home_team', 'away_team', 'date']
                        if 'conflict_reason' in schedule_df_copy.columns:
                            display_columns.append('conflict_reason')
                        st.dataframe(schedule_df_copy[schedule_df_copy['afc_conflict'] == True][display_columns])

                        

def get_base64_image(image_path):
    """
    Encodes an image file to a base64 string.
    """
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    except FileNotFoundError:
        return ""
# Preload Base64 logos once
team_logos_base64 = {team: get_base64_of_image(path) for team, path in team_logos.items()}



def main():
    st.markdown('<h1 style="text-align: center; color: #1e3d59;">⚽ Saudi Football League Schedule Optimizer</h1>', unsafe_allow_html=True)
    st.markdown('<h3 style="text-align: center; color: #666;">Scenario-Based Match Selection System</h3>', unsafe_allow_html=True)
    
    # Load data
    teams_data, weather_data, attendance_model, profit_model, models_loaded = load_data()
    teams_data['team_lower'] = teams_data['team'].str.lower()  # Normalize for lookups

    # Load and debug matches
    matches_from_excel = load_match_schedule_from_files()
    if matches_from_excel is None:
        st.error("Failed to load matches. Check 'schedule.xlsx' and logs.")
        return
    if not any(7 <= w <= 12 for w in matches_from_excel.keys()):
        st.error("No weeks 7-12 found in matches_from_excel.")
        return

    # Define week start dates for weeks 7 to 34
    week_start_dates = {
        7: datetime.date(2025, 10, 30),  # Thursday
        8: datetime.date(2025, 11, 6),   # Thursday
        9: datetime.date(2025, 11, 21),  # Friday
        10: datetime.date(2025, 12, 19), # Friday
        11: datetime.date(2025, 12, 25), # Thursday
        12: datetime.date(2025, 12, 29), # Monday
        13: datetime.date(2026, 1, 2),   # Friday
        14: datetime.date(2026, 1, 8),   # Thursday
        15: datetime.date(2026, 1, 12),  # Monday
        16: datetime.date(2026, 1, 16),  # Friday
        17: datetime.date(2026, 1, 20),  # Tuesday
        18: datetime.date(2026, 1, 24),  # Saturday
        19: datetime.date(2026, 1, 28),  # Wednesday
        20: datetime.date(2026, 2, 1),   # Sunday
        21: datetime.date(2026, 2, 5),   # Thursday
        22: datetime.date(2026, 2, 12),  # Thursday
        23: datetime.date(2026, 2, 19),  # Thursday
        24: datetime.date(2026, 2, 26),  # Thursday
        25: datetime.date(2026, 3, 5),   # Thursday
        26: datetime.date(2026, 3, 12),  # Thursday
        27: datetime.date(2026, 4, 3),   # Friday
        28: datetime.date(2026, 4, 9),   # Thursday
        29: datetime.date(2026, 4, 23),  # Thursday
        30: datetime.date(2026, 4, 28),  # Tuesday
        31: datetime.date(2026, 5, 2),   # Saturday
        32: datetime.date(2026, 5, 7),   # Thursday
        33: datetime.date(2026, 5, 13),  # Wednesday
        34: datetime.date(2026, 5, 21),  # Thursday
    }

# Initialize session state
    if 'scenario_manager' not in st.session_state:
        st.session_state.scenario_manager = ScenarioManager()
    if 'week_match_ids' not in st.session_state:
        st.session_state.week_match_ids = {w: {} for w in range(7, 35)}
    if 'day_counts' not in st.session_state:
        st.session_state.day_counts = {}
    if 'schedule_df' not in st.session_state:
        st.session_state.schedule_df = pd.DataFrame()
    if 'week_start' not in st.session_state:
        st.session_state.week_start = 7
    if 'week_end' not in st.session_state:
        st.session_state.week_end = 12
    if 'selected_week' not in st.session_state:
        st.session_state.selected_week = 7
    if 'active_tab' not in st.session_state:
        st.session_state.active_tab = None

    # Sidebar
    st.sidebar.header("League Date Range")
    start_date = st.sidebar.date_input("Start Date", datetime.date(2025, 8, 28))
    end_date = st.sidebar.date_input("End Date", datetime.date(2025, 5, 21))

    st.sidebar.header("Batch Selection")
    batch_options = ["Batch 1 (W7-W12)", "Batch 2 (W13-W18)", "Batch 3 (W19-W24)", "Batch 4 (W25-W30)", "Batch 5 (W31-W34)"]
    batch = st.sidebar.selectbox("Select Batch", batch_options, index=0)
    batch_week_ranges = {
        "Batch 1 (W7-W12)": (7, 12, 6),
        "Batch 2 (W13-W18)": (13, 18, 6),
        "Batch 3 (W19-W24)": (19, 24, 6),
        "Batch 4 (W25-W30)": (25, 30, 6),
        "Batch 5 (W31-W34)": (31, 34, 4)
    }
    start_week, end_week, max_weeks = batch_week_ranges[batch]
    
    # Store week range in session state
    st.session_state.week_start = start_week
    st.session_state.week_end = end_week

    st.sidebar.header(f"Week Selection (Weeks {start_week}–{end_week})")
    week_number = st.sidebar.slider("Select Week", start_week, end_week, start_week)
    st.session_state.selected_week = week_number  # Sync with slider

    st.sidebar.header("Match Settings")
    selected_teams = st.sidebar.multiselect("Team Filters", teams_data['team'].unique())
    selected_cities = st.sidebar.multiselect("Location Filters", teams_data['city'].unique())
    time_filters = st.sidebar.multiselect("Time Filters", ['12:00', '16:00', '18:00', '19:00', '21:00'])

    matches_per_week = st.sidebar.slider("Matches per Week", 5, 12, 9)

    start_date_dt = datetime.datetime.combine(start_date, datetime.datetime.min.time())
    end_date_dt = datetime.datetime.combine(end_date, datetime.datetime.min.time())

    if st.sidebar.button("Reset Schedule"):
        st.session_state.scenario_manager = type('obj', (object,), {'scenarios': {}, 'selected_scenarios': {}})()
        st.session_state.week_match_ids = {w: {} for w in range(7, 35)}
        st.session_state.day_counts = {}
        st.session_state.schedule_df = pd.DataFrame()
        st.session_state.selected_week = 7
        st.rerun()

    if st.sidebar.button("Generate Scenarios"):
        st.session_state.schedule_df = generate_full_schedule_with_isha(
            teams_data=teams_data,
            weather_data=weather_data,
            attendance_model=attendance_model,
            profit_model=profit_model,
            models_loaded=models_loaded,
            start_date=start_date_dt,
            end_date=end_date_dt,
            matches_from_excel=matches_from_excel,
            matches_per_week=matches_per_week
        )

        st.sidebar.success(f"Generated {len(st.session_state.schedule_df)} scenarios!")
        st.rerun()


    # Tabs
    tab1, tab2, tab6 = st.tabs([
        "Weekly Scheduling", "Calendar", "Fixture"
    ])

    with tab1:
        st.write("Weekly Scheduling Tab")
        if not st.session_state.schedule_df.empty:
            year = 2025 if week_number < 13 else 2026
            week_data = st.session_state.schedule_df[st.session_state.schedule_df['date'].str.startswith(f'{year}-{week_number:02}')]
            # st.write(f"Displaying matches for Week {week_number}")
            # st.dataframe(week_data)
            display_week_scenarios(week_number, matches_from_excel)

    with tab2:
        show_afc_replica_calendar_tab()

    with tab6:
        st.markdown('<h2 class="sub-header">Matchday Simulation</h2>', unsafe_allow_html=True)
        
        # Check if a match was selected
        selected_match_id = st.session_state.get('selected_match_id')
        if selected_match_id:
            home_team, away_team = st.session_state.get('match_teams', ['Unknown', 'Unknown'])
            match_date = st.session_state.get('match_date', 'N/A')
            match_time = st.session_state.get('match_time', 'N/A')
            match_stadium = st.session_state.get('match_stadium', 'N/A')
            
            # Display selected match with ACTUAL logos
            home_logo_base64 = team_logos_base64.get(home_team, '')
            away_logo_base64 = team_logos_base64.get(away_team, '')
            
            home_logo_html = f'<img src="data:image/png;base64,{home_logo_base64}" style="width: 50px; height: 50px; margin-right: 10px; border-radius: 50%;" alt="{home_team} Logo">' if home_logo_base64 else f'<div style="width: 50px; height: 50px; background: #1e3d59; border-radius: 50%; color: white; display: flex; align-items: center; justify-content: center; margin-right: 10px;">{home_team[:2]}</div>'
            away_logo_html = f'<img src="data:image/png;base64,{away_logo_base64}" style="width: 50px; height: 50px; margin-left: 10px; border-radius: 50%;" alt="{away_team} Logo">' if away_logo_base64 else f'<div style="width: 50px; height: 50px; background: #1e3d59; border-radius: 50%; color: white; display: flex; align-items: center; justify-content: center; margin-left: 10px;">{away_team[:2]}</div>'
            
            st.markdown(
                f"""
                <div style="display: flex; align-items: center; justify-content: center; margin-bottom: 20px;">
                    {home_logo_html}
                    <span style="font-size: 1.5em; font-weight: bold;">{home_team} VS {away_team}</span>
                    {away_logo_html}
                </div>
                <div style="text-align: center;">
                    <p><strong>Date:</strong> {match_date}</p>
                    <p><strong>Time:</strong> {match_time}</p>
                    <p><strong>Stadium:</strong> {match_stadium}</p>
                </div>
                """, unsafe_allow_html=True
            )
        else:
            st.info("No match selected. Please select a match from the Weekly Scheduling tab.")
        
        # Get selected matches from scenario manager
        scenario_manager = st.session_state.scenario_manager
        selected_scenarios = scenario_manager.selected_scenarios
        
        if not selected_scenarios:
            st.info("No matches have been selected yet. Please select matches in the Weekly Scheduling tab.")
        else:
            # Create a list of selected matches with their details and week numbers
            selected_matches = []
            
            for match_id, scenario_id in selected_scenarios.items():
                # Find the selected scenario details
                scenarios = scenario_manager.get_scenarios_for_match(match_id)
                selected_scenario = None
                for scenario in scenarios:
                    if scenario.scenario_id == scenario_id:
                        selected_scenario = scenario
                        break
                
                if selected_scenario:
                    # Find the week number for this match_id
                    week_number = None
                    for week, match_ids in st.session_state.week_match_ids.items():
                        if match_id in match_ids.values():
                            week_number = week
                            break
                    
                    selected_matches.append({
                        'match_id': match_id,
                        'home_team': selected_scenario.home_team,
                        'away_team': selected_scenario.away_team,
                        'date': selected_scenario.date,
                        'time': selected_scenario.time,
                        'stadium': selected_scenario.stadium,
                        'city': selected_scenario.city,
                        'week': week_number  # Include week number for filtering
                    })
            
            # Get the currently selected week from the sidebar
            selected_week = st.session_state.selected_week
            
            # Filter selected matches by the SPECIFIC selected week only
            week_selected_matches = [
                match for match in selected_matches
                if match['week'] == selected_week
            ]
            
            # Apply team and city filters if any
            if selected_teams:
                week_selected_matches = [
                    match for match in week_selected_matches
                    if match['home_team'] in selected_teams or match['away_team'] in selected_teams
                ]
            
            if selected_cities:
                week_selected_matches = [
                    match for match in week_selected_matches
                    if match['city'] in selected_cities
                ]
            
            if not week_selected_matches:
                st.info(f"No selected matches found for Week {selected_week} with current filters.")
                # Show how many matches are selected in other weeks for debugging
                other_weeks_matches = [match for match in selected_matches if match['week'] != selected_week]
                if other_weeks_matches:
                    week_counts = {}
                    for match in other_weeks_matches:
                        week = match['week']
                        week_counts[week] = week_counts.get(week, 0) + 1
                    week_summary = ", ".join([f"Week {w}: {c} matches" for w, c in sorted(week_counts.items())])
                    st.info(f"Matches selected in other weeks: {week_summary}")
            else:
                st.markdown(f"<div style='text-align: center; font-size: 1.5rem; font-weight: bold; color: #1e3d59; margin: 2rem 0 1rem 0; padding: 1rem; background-color: #f8f9fa; border-radius: 8px;'>Selected Matches - Week {selected_week}</div>", unsafe_allow_html=True)
                st.markdown(f"<div style='text-align: center; font-size: 0.9rem; color: #666; margin-bottom: 1.5rem;'>{len(week_selected_matches)} matches confirmed for this week</div>", unsafe_allow_html=True)

                # Sort by date and time
                week_selected_matches.sort(key=lambda x: (x['date'], x['time']))

                # Display only selected matches for the specific week
                for match in week_selected_matches:
                    home_team = match['home_team']
                    away_team = match['away_team']
                    match_time = match['time']
                    match_day = datetime.datetime.strptime(match['date'], '%Y-%m-%d').strftime('%A')
                    match_date = match['date']
                    match_id = match['match_id']

                    # Check if this match should be highlighted
                    highlight_style = "border: 3px solid #28a745; background-color: #f8fff9;" if selected_match_id == match_id else "border: 2px solid #28a745;"

                    # Get logos with inline styles
                    home_logo_base64 = team_logos_base64.get(home_team, '')
                    away_logo_base64 = team_logos_base64.get(away_team, '')
                    
                    if home_logo_base64:
                        home_logo_html = f'<img src="data:image/png;base64,{home_logo_base64}" style="width: 80px; height: 80px; object-fit: contain; border-radius: 50%; background-color: #ffffff; padding: 5px; box-shadow: 0 2px 6px rgba(0,0,0,0.1);" alt="{home_team} Logo">'
                    else:
                        initials = ''.join([word[0] for word in home_team.split('-')[:2]]).upper()
                        home_logo_html = f'<div style="width: 80px; height: 80px; background-color: #1e3d59; border-radius: 50%; color: white; font-size: 1.2rem; display: flex; align-items: center; justify-content: center; font-weight: bold; border: 3px solid #ffffff; box-shadow: 0 2px 6px rgba(0,0,0,0.1);">{initials}</div>'
                    
                    if away_logo_base64:
                        away_logo_html = f'<img src="data:image/png;base64,{away_logo_base64}" style="width: 80px; height: 80px; object-fit: contain; border-radius: 50%; background-color: #ffffff; padding: 5px; box-shadow: 0 2px 6px rgba(0,0,0,0.1);" alt="{away_team} Logo">'
                    else:
                        initials = ''.join([word[0] for word in away_team.split('-')[:2]]).upper()
                        away_logo_html = f'<div style="width: 80px; height: 80px; background-color: #1e3d59; border-radius: 50%; color: white; font-size: 1.2rem; display: flex; align-items: center; justify-content: center; font-weight: bold; border: 3px solid #ffffff; box-shadow: 0 2px 6px rgba(0,0,0,0.1);">{initials}</div>'

                    st.markdown(f"""
                    <div style="background-color: white; border-radius: 12px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); padding: 1rem 2rem; margin-bottom: 1rem; display: flex; align-items: center; justify-content: space-between; position: relative; {highlight_style}" id="match_{match_id}">
                        <div style="position: absolute; top: 10px; right: 10px; background-color: #28a745; color: white; padding: 5px 10px; border-radius: 15px; font-size: 12px; font-weight: bold;">
                            ✅ CONFIRMED
                        </div>
                        <div style="display: flex; align-items: center; gap: 20px; flex: 1;">
                            <div style="display: flex; align-items: center; gap: 10px; justify-content: flex-start; flex: 1;">
                                {home_logo_html}
                                <div style="font-weight: bold; font-size: 30px;">{home_team}</div>
                            </div>
                            <div style="position: absolute; left: 50%; transform: translateX(-50%); background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 1rem 1.5rem; border-radius: 15px; font-weight: bold; font-size: 1rem; min-width: 140px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.2); z-index: 10;">
                                <div style="font-size: 16px; font-weight: bold;">{match_time}</div>
                                <div style="font-size: 14px; color: #ddd;">{match_day}</div>
                                <div style="font-size: 13px; color: #eee; margin-top: 3px;">{match_date}</div>
                            </div>
                        </div>
                        <div style="display: flex; align-items: center; gap: 10px; justify-content: flex-end; flex: 1;">
                            <div style="font-weight: bold; font-size: 30px;">{away_team}</div>
                            {away_logo_html}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                
                # Show summary with week-specific information
                st.markdown(f"""
                <div style="background-color: #e8f5e9; border: 2px solid #28a745; border-radius: 10px; padding: 15px; margin-top: 20px;">
                    <div style="font-weight: bold; color: #155724; font-size: 16px;">📊 Week {selected_week} Summary</div>
                    <div style="color: #155724; margin-top: 5px;">
                        • Total confirmed matches for Week {selected_week}: {len(week_selected_matches)}<br>
                        • All matches have been scheduled and confirmed<br>
                        • Ready for matchday execution
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # Auto-scroll to highlighted match if one is selected
                if selected_match_id:
                    st.markdown(f"""
                    <script>
                    setTimeout(function() {{
                        var element = document.getElementById('match_{selected_match_id}');
                        if (element) {{
                            element.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                        }}
                    }}, 100);
                    </script>
                    """, unsafe_allow_html=True)
                    
                    # Clear the selected match after displaying
                    st.session_state.selected_match_id = None
                    st.session_state.active_tab = "Weekly Calendar"

if __name__ == "__main__":
    main()



