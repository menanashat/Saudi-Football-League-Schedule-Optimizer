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
import io

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
    'NEOM':'NEOMlogo.png',
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
            # ONLY remove scenarios with TEAM conflicts on the same date
            # DO NOT remove based on stadium conflicts
            self.scenarios[match_id] = [
                s for s in scenarios 
                if not (s.date == selected_scenario.date and 
                       ({s.home_team, s.away_team}.intersection({selected_scenario.home_team, selected_scenario.away_team})))
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
    Returns tuple: (is_available, conflict_reason)
    
    Args:
        team (str): Name of the team to check
        match_date (datetime.date): Date to check availability for
    
    Returns:
        tuple: (bool, str) - (is_available, conflict_reason)
               If available: (True, "")
               If not available: (False, "will play at {date}")
    """
    TEAM_UNAVAILABILITY = {
    'Al-Ittihad': [
        datetime.date(2025, 9, 15),
        datetime.date(2025, 9, 30),
        datetime.date(2025, 10, 20),
        datetime.date(2025, 10, 28),
        datetime.date(2025, 11, 4),
        datetime.date(2025, 11, 24),
        datetime.date(2025, 12, 23),
        datetime.date(2026, 2, 10),
        datetime.date(2026, 2, 17)
    ],
    'Al-Ahli': [
        datetime.date(2025, 9, 15),
        datetime.date(2025, 9, 29),
        datetime.date(2025, 10, 20),
        datetime.date(2025, 10, 27),
        datetime.date(2025, 11, 4),
        datetime.date(2025, 11, 24),
        datetime.date(2025, 12, 22),
        datetime.date(2026, 2, 9),
        datetime.date(2026, 2, 16)
    ],
    'Al-Hilal': [
        datetime.date(2025, 9, 16),
        datetime.date(2025, 9, 29),
        datetime.date(2025, 10, 21),
        datetime.date(2025, 10, 28),
        datetime.date(2025, 11, 3),
        datetime.date(2025, 11, 25),
        datetime.date(2025, 12, 22),
        datetime.date(2026, 2, 9),
        datetime.date(2026, 2, 16)
    ],
    'Al-Nassr': [
        datetime.date(2025, 9, 17),
        datetime.date(2025, 10, 1),
        datetime.date(2025, 10, 22),
        datetime.date(2025, 10, 28),
        datetime.date(2025, 11, 5),
        datetime.date(2025, 11, 26),
        datetime.date(2025, 12, 24)
    ],
    'Al-Shabab': [
        datetime.date(2025, 10, 1),
        datetime.date(2025, 10, 21),
        datetime.date(2025, 10, 28),
        datetime.date(2025, 11, 5),
        datetime.date(2025, 12, 24),
        datetime.date(2026, 2, 1),
        datetime.date(2026, 2, 17)
    ],
 'Al-Ettifaq': [datetime.date(2025, 10, 24)],
    'Al-Fayha' : [
        datetime.date(2025, 10, 24)
    ],  
     'NEOM' : [
        datetime.date(2025, 10, 24)
    ],  
    'Al-Khaleej': [
        datetime.date(2025, 10, 27)
    ],
    'Al-Fateh': [
        datetime.date(2025, 10, 27)
    ],
    'Al-Okhdood': [
        datetime.date(2025, 10, 27)
    ],
    'Al-Batin': [
        datetime.date(2025, 10, 27)
    ],
    'Al-Qadisiyah': [
        datetime.date(2025, 10, 28)
    ],
    'Al-Kholood': [
        datetime.date(2025, 10, 28)
    ],
    'Al-Taawoun': [
        datetime.date(2025, 10, 27)
    ],
    'Al-riyadh': [
        datetime.date(2025, 10, 27)
    ],
    'Al-Najma': [
        datetime.date(2025, 10, 27)
    ],
    'Al-Hazem': [
        datetime.date(2025, 10, 28)
    ],
    'Al-Raed': [
        datetime.date(2025, 10, 28)
    ],
     'Damac': [
        datetime.date(2025, 10, 25)
    ]
}
    
    
    unavailable_dates = TEAM_UNAVAILABILITY.get(team, [])
    
    # First check if the exact match_date conflicts with any unavailable date
    for unavailable_date in unavailable_dates:
        if match_date == unavailable_date:
            return False, f"has scheduled match on {unavailable_date.strftime('%Y-%m-%d')}"
    
    # Apply a 2-day buffer around each unavailability date and find the closest conflict
    for unavailable_date in unavailable_dates:
        buffer_dates = [
            unavailable_date - datetime.timedelta(days=2),
            unavailable_date - datetime.timedelta(days=1),
            unavailable_date + datetime.timedelta(days=1),
            unavailable_date + datetime.timedelta(days=2)
        ]
        
        if match_date in buffer_dates:
            return False, f"will play at {unavailable_date.strftime('%Y-%m-%d')}"
    
    return True, ""


CITY_STADIUMS = {
    'Jeddah': [
        'Alinma Stadium',
        'Prince Abdullah Al-Faisal Stadium',
    ],
    'Riyadh': [
        'Kingdom Arena',
        'King Saud University Stadium (Al-Oul Park)',
        'Al-Shabab Club Stadium',
        'Prince Faisal bin Fahd Stadium'
    ],
    'Dammam': [
        'EGO Stadium',
        'Al-Fateh Club Stadium',
        'Prince Mohammed Bin Fahd Stadium'
    ],
    'Al Khobar': [
        'Prince Mohammed bin Fahd Stadium'
    ],
    'Buraydah': [
        'Al-Hazem Club Stadium',
        'Al-Taawoun Club Stadium (Buraydah)',
        'King Abdullah Sport City',
        'Al-Majmaah Sports City'
    ],
    'Ar Rass': [
        'Al-Taawoun Club Stadium',
        'Al-Majmaah Sports City'
    ],
    'Al-Ahsa': [
        'Al-Fateh Club Stadium',
        'Prince Mohammed bin Fahd Stadium',
        'EGO Stadium',
    ],
    'Al-Majmaah': [
        'Al-Majmaah Sports City',
        'Al-Taawoun Club Stadium',
        'Al-Hazem Club Stadium'
    ],
    'Khamis Mushait': [
        'Damac Club Stadium (Khamis Mushait)'
    ],
    'Abha': [
       'Prince Sultan bin Abdulaziz Sports City(Abha)'
    ],
    'NEOM': [
        'King Khalid Sports City Stadium'
    ],
    'Unaizah': [
        'King Abdullah Sport City'
    ],
    'Najran': [
        'Prince Hathloul Sport City'
    ],
    'Tabuk': [
        'King Khalid Sports City Stadium'
    ]
}


STADIUM_UNAVAILABILITY = {
    'Alinma Stadium': {
        'unavailable': (datetime.date(2025, 12, 1), datetime.date(2025, 12, 31)),
        'alternative': 'Prince Abdullah Al Faisal (Jeddah)'
    },
    'Al-Ettifaq Club Stadium': {
        'unavailable': (datetime.date(2025, 11, 24), datetime.date(2025, 12, 28)),
        'alternative': 'Prince Mohammed bin Fahd Stadium (Dammam)'
    },
    'Al-Taawoun Club Stadium (Buraydah)': {
        'unavailable': (datetime.date(2025, 10, 5), datetime.date(2025, 11, 8)),
        'alternative': 'King Abdullah Sport City'
    },
    'Al-Hazem Club Stadium': {
        'unavailable': (datetime.date(2025, 10, 5), datetime.date(2025, 11, 8)),
        'alternative': 'King Abdullah Sports City'
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

# Team stadium mappings (primary and alternative stadiums)
TEAM_STADIUMS = {
    'Al-Ittihad': {
        'primary': 'Alinma Stadium',
        'city': 'Jeddah',
        'alternatives': ['Prince Abdullah Al-Faisal Stadium']
    },
    'Al-Hilal': {
        'primary': 'Kingdom Arena',
        'city': 'Riyadh',
        'alternatives': ['Prince Faisal bin Fahd Stadium']
    },
    'Al-Nassr': {
        'primary': 'King Saud University Stadium (Al-Oul Park)',
        'city': 'Riyadh',
        'alternatives': ['Prince Faisal bin Fahd Stadium']
    },
    'Al-Qadisiyah': {
        'primary': 'Prince Mohammed Bin Fahd Stadium',
        'city': 'Dammam',
        'alternatives': []
    },
    'Al-Ahli': {
        'primary': 'Alinma Stadium',
        'city': 'Jeddah',
        'alternatives': ['Prince Abdullah Al-Faisal Stadium']
    },
    'Al-Shabab': {
        'primary': 'Al-Shabab Club Stadium',
        'city': 'Riyadh',
        'alternatives': ['Prince Faisal bin Fahd Stadium']
    },
    'Al-Ettifaq': {
        'primary': 'EGO Stadium',
        'city': 'Dammam',
        'alternatives': []
    },
    'Al-Taawoun': {
        'primary': 'Al-Taawoun Club Stadium (Buraydah)',
        'city': 'Buraydah',
        'alternatives': []
    },
    'Al-Kholood': {
        'primary': 'Al-Hazem Club Stadium',
        'city': 'Ar Rass',
        'alternatives': ['King Abdullah Sports City']
    },
    'Al-Fateh': {
        'primary': 'Al-Fateh Club Stadium',
        'city': 'Al-Ahsa',
        'alternatives': []
    },
    'Al-riyadh': {
        'primary': 'Prince Faisal bin Fahd Stadium',
        'city': 'Riyadh',
        'alternatives': []
    },
    'Al-Khaleej': {
        'primary': 'Prince Mohammed Bin Fahd Stadium',
        'city': 'Dammam',
        'alternatives': []
    },
    'Al-Fayha': {
        'primary': 'Al-Majmaah Sports City',
        'city': 'Al-Majmaah',
        'alternatives': ['King Abdullah Sports City']
    },
    'Damac': {
        'primary': 'Damac Club Stadium (Khamis Mushait)',
        'city': 'Khamis Mushait',
        'alternatives': ['Prince Sultan Sports City (Abha)']
    },
    'Al-Okhdood': {
        'primary': 'Prince Hathloul Sport City',
        'city': 'Najran',
        'alternatives': []
    },
    'NEOM': {
        'primary': 'King Khalid Sports City Stadium',
        'city': 'NEOM',
        'alternatives': []
    },
    'Al-Najma': {
        'primary': 'King Abdullah Sport City',
        'city': 'Buraydah',
        'alternatives': []
    },
    'Al-Hazem': {
        'primary': 'Al-Hazem Club Stadium',
        'city': 'Ar Rass',
        'alternatives': ['King Abdullah Sports City']
    }
}

def is_stadium_available(stadium, match_date):
    """Check if a stadium is available on a given date."""
    if stadium in STADIUM_UNAVAILABILITY:
        unavailable_start, unavailable_end = STADIUM_UNAVAILABILITY[stadium]['unavailable']
        if unavailable_start <= match_date <= unavailable_end:
            return False
    return True


def get_stadium_bookings(scenario_manager):
    """
    Get all stadium bookings from selected scenarios.
    Returns dict: {(stadium_name, date): [time_slots]} for full day bookings
    """
    bookings = {}
    for match_id, scenario_id in scenario_manager.selected_scenarios.items():
        scenarios = scenario_manager.get_scenarios_for_match(match_id)
        for scenario in scenarios:
            if scenario.scenario_id == scenario_id:
                # Book the stadium for the ENTIRE day, not just one time slot
                key = (scenario.stadium, scenario.date)
                if key not in bookings:
                    bookings[key] = []
                # Store all time slots for this stadium on this date
                bookings[key].append({
                    'time': scenario.time,
                    'match_id': match_id,
                    'home_team': scenario.home_team,
                    'away_team': scenario.away_team
                })
                break
    return bookings


def get_available_stadiums_for_team(team, match_date, match_time, current_match_id=None, scenario_manager=None):
    """
    Get list of available and unavailable stadiums for a team on a specific date and time.
    Returns tuple: (available_stadiums, unavailable_stadiums)
    
    Available stadiums are ordered as:
    1. Primary stadium (if available)
    2. Alternative stadiums defined for the team (if available)
    3. Other stadiums in the same city (if available)
    
    available_stadiums: [(stadium_name, city, stadium_type, is_selectable), ...]
        is_selectable: False if stadium is booked for ANY time on this date
    unavailable_stadiums: [(stadium_name, city, stadium_type, reason), ...]
    """
    if team not in TEAM_STADIUMS:
        return [], []
    
    team_info = TEAM_STADIUMS[team]
    team_city = team_info['city']
    available_stadiums = []
    unavailable_stadiums = []
    
    # Get current stadium bookings (now organized by date instead of time)
    stadium_bookings = {}
    if scenario_manager:
        stadium_bookings = get_stadium_bookings(scenario_manager)
    
    # Track which stadiums we've already processed
    processed_stadiums = set()
    
    # Helper function to check if stadium is booked for the entire day
    def is_stadium_booked_full_day(stadium_name, date_str):
        """Check if stadium is booked for ANY time slot on this date"""
        booking_key = (stadium_name, date_str)
        if booking_key in stadium_bookings:
            # Check if any booking is for a different match
            bookings = stadium_bookings[booking_key]
            for booking in bookings:
                if current_match_id is None or booking['match_id'] != current_match_id:
                    return True, booking
        return False, None
    
    # Convert match_date to string format for consistency
    match_date_str = match_date.strftime('%Y-%m-%d') if isinstance(match_date, datetime.date) else match_date
    
    # 1. Check primary stadium
    primary_stadium = team_info['primary']
    processed_stadiums.add(primary_stadium)
    
    if is_stadium_available(primary_stadium, match_date):
        is_booked, booking_info = is_stadium_booked_full_day(primary_stadium, match_date_str)
        if is_booked:
            # Stadium is booked for the entire day
            reason = f"Booked for entire day on {match_date_str} ({booking_info['home_team']} vs {booking_info['away_team']} at {booking_info['time']})"
            unavailable_stadiums.append((
                primary_stadium, 
                team_city, 
                'Primary', 
                reason
            ))
        else:
            # Stadium is available for all time slots
            available_stadiums.append((primary_stadium, team_city, 'Primary', True))
    else:
        # Get unavailability reason
        if primary_stadium in STADIUM_UNAVAILABILITY:
            unavailable_start, unavailable_end = STADIUM_UNAVAILABILITY[primary_stadium]['unavailable']
            reason = f"Unavailable from {unavailable_start.strftime('%Y-%m-%d')} to {unavailable_end.strftime('%Y-%m-%d')}"
            unavailable_stadiums.append((primary_stadium, team_city, 'Primary', reason))
            
            # Add the automatic alternative if not already processed
            alt = STADIUM_UNAVAILABILITY[primary_stadium]['alternative']
            if alt not in processed_stadiums:
                processed_stadiums.add(alt)
                if is_stadium_available(alt, match_date):
                    is_booked, booking_info = is_stadium_booked_full_day(alt, match_date_str)
                    if is_booked:
                        reason = f"Booked for entire day on {match_date_str} ({booking_info['home_team']} vs {booking_info['away_team']} at {booking_info['time']})"
                        unavailable_stadiums.append((alt, team_city, 'Alternative', reason))
                    else:
                        available_stadiums.append((alt, team_city, 'Alternative', True))
    
    # 2. Check alternative stadiums defined for the team
    for alt_stadium in team_info['alternatives']:
        if alt_stadium not in processed_stadiums:
            processed_stadiums.add(alt_stadium)
            
            if is_stadium_available(alt_stadium, match_date):
                is_booked, booking_info = is_stadium_booked_full_day(alt_stadium, match_date_str)
                if is_booked:
                    reason = f"Booked for entire day on {match_date_str} ({booking_info['home_team']} vs {booking_info['away_team']} at {booking_info['time']})"
                    unavailable_stadiums.append((alt_stadium, team_city, 'Alternative', reason))
                else:
                    available_stadiums.append((alt_stadium, team_city, 'Alternative', True))
            else:
                # Get unavailability reason for alternative
                if alt_stadium in STADIUM_UNAVAILABILITY:
                    unavailable_start, unavailable_end = STADIUM_UNAVAILABILITY[alt_stadium]['unavailable']
                    reason = f"Unavailable from {unavailable_start.strftime('%Y-%m-%d')} to {unavailable_end.strftime('%Y-%m-%d')}"
                    unavailable_stadiums.append((alt_stadium, team_city, 'Alternative', reason))
    
    # 3. Add other stadiums in the same city
    if team_city in CITY_STADIUMS:
        for city_stadium in CITY_STADIUMS[team_city]:
            if city_stadium not in processed_stadiums:
                processed_stadiums.add(city_stadium)
                
                if is_stadium_available(city_stadium, match_date):
                    is_booked, booking_info = is_stadium_booked_full_day(city_stadium, match_date_str)
                    if is_booked:
                        reason = f"Booked for entire day on {match_date_str} ({booking_info['home_team']} vs {booking_info['away_team']} at {booking_info['time']})"
                        unavailable_stadiums.append((city_stadium, team_city, 'Other City Stadium', reason))
                    else:
                        available_stadiums.append((city_stadium, team_city, 'Other City Stadium', True))
                else:
                    # Check if this stadium has unavailability info
                    if city_stadium in STADIUM_UNAVAILABILITY:
                        unavailable_start, unavailable_end = STADIUM_UNAVAILABILITY[city_stadium]['unavailable']
                        reason = f"Unavailable from {unavailable_start.strftime('%Y-%m-%d')} to {unavailable_end.strftime('%Y-%m-%d')}"
                        unavailable_stadiums.append((city_stadium, team_city, 'Other City Stadium', reason))
    
    return available_stadiums, unavailable_stadiums


def update_scenario_stadium(scenario, new_stadium, new_city):
    """Update a scenario's stadium and city, and recalculate if needed."""
    scenario.stadium = new_stadium
    scenario.city = new_city
    # You may want to recalculate suitability_score, attendance, profit here
    # based on the new stadium's capacity and other factors
    return scenario





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
    Map 'Unknown' city to 'Riyadh' and handle invalid dates with fallbacks.
    """
    if city == 'Unknown':
        city = 'Riyadh'
        st.warning(f"City 'Unknown' detected. Defaulting to 'Riyadh' for prayer times.")

    if date is None:
        date = datetime.date.today()
        st.warning(f"No date provided for prayer times. Using today's date: {date}")

    city_mapping = {
        'Riyadh': 'Riyadh', 'Jeddah': 'Jeddah', 'Dammam': 'Dammam', 'Buraydah': 'Buraydah',
        'Al-Mubarraz': 'Al Mubarraz', 'Khamis Mushait': 'Khamis Mushait', 'Abha': 'Abha',
        'Al Khobar': 'Al Khobar', 'Saihat': 'Saihat', 'Al-Majmaah': 'Al-Majmaah',
        'Ar Rass': 'Ar Rass', 'Unaizah': 'Unaizah', 'NEOM': 'Tabuk'
    }

    # Fallback times only for when API completely fails
    jeddah_fallback_times = {
        'fajr': '04:45', 'dhuhr': '12:00', 'asr': '15:30', 'maghrib': '17:45', 'isha': '19:15'
    }
    
    riyadh_fallback_times = {
        'fajr': '05:35', 'dhuhr': '12:15', 'asr': '15:25', 'maghrib': '17:35', 'isha': '19:05'
    }

    api_city = city_mapping.get(city, city)
    date_str = date.strftime('%d-%m-%Y') if isinstance(date, (datetime.date, datetime.datetime)) else str(date)

    try:
        # Try the API first, regardless of how far in the future the date is
        url = f"http://api.aladhan.com/v1/timingsByCity/{date_str}?city={api_city}&country=Saudi%20Arabia&method=4"
        # st.write(f"Trying API call: {url}")  # Debug info
        response = requests.get(url, timeout=10)
        data = response.json()

        if response.status_code == 200 and data.get('code') == 200:
            # API call successful
            timings = data['data']['timings']
            prayer_times = {
                'timings': {
                    'fajr': timings['Fajr'], 'dhuhr': timings['Dhuhr'], 'asr': timings['Asr'],
                    'maghrib': timings['Maghrib'], 'isha': timings['Isha']
                },
                'minutes': {
                    'fajr_minutes': time_string_to_minutes(timings['Fajr']),
                    'dhuhr_minutes': time_string_to_minutes(timings['Dhuhr']),
                    'asr_minutes': time_string_to_minutes(timings['Asr']),
                    'maghrib_minutes': time_string_to_minutes(timings['Maghrib']),
                    'isha_minutes': time_string_to_minutes(timings['Isha'])
                }
            }
            # st.write(f"API success for {city} on {date_str}: Maghrib={timings['Maghrib']}, Isha={timings['Isha']}")
            return prayer_times
        else:
            # API returned an error response
            st.warning(f"API returned error for {city} on {date_str}: Status {response.status_code}, Code {data.get('code')}")
            raise Exception(f"API error: {data.get('status', 'Unknown error')}")

    except Exception as e:
        # API call failed completely
        st.error(f"API call failed for {city} on {date_str}: {e}")
        
        # Use fallback times only as last resort
        if city == 'Jeddah':
            st.warning(f"Using fallback prayer times for Jeddah on {date_str}.")
            return {
                'timings': jeddah_fallback_times,
                'minutes': {f"{prayer}_minutes": time_string_to_minutes(time) for prayer, time in jeddah_fallback_times.items()}
            }
        elif city == 'Riyadh':
            st.warning(f"Using fallback prayer times for Riyadh on {date_str}.")
            return {
                'timings': riyadh_fallback_times,
                'minutes': {f"{prayer}_minutes": time_string_to_minutes(time) for prayer, time in riyadh_fallback_times.items()}
            }
        else:
            # For other cities, return error
            return {'error': f'No fallback times available for {city} on {date_str}'}

def time_string_to_minutes(time_str):
    """
    Convert time string (HH:MM) to minutes since midnight
    """
    try:
        if not time_str or time_str == 'N/A':
            return 0
        
        # Handle both HH:MM and H:MM formats
        time_str = time_str.strip()
        parts = time_str.split(':')
        
        if len(parts) != 2:
            return 0
            
        hours = int(parts[0])
        minutes = int(parts[1])
        
        return hours * 60 + minutes
    except (ValueError, AttributeError):
        return 0

def minutes_to_time_string(total_minutes):
    """
    Convert minutes since midnight to time string (HH:MM)
    Handle negative values and values >= 1440 (24 hours)
    """
    try:
        # Handle negative values (previous day)
        while total_minutes < 0:
            total_minutes += 1440  # Add 24 hours
        
        # Handle values >= 24 hours (next day)
        total_minutes = total_minutes % 1440
        
        hours = total_minutes // 60
        minutes = total_minutes % 60
        
        return f"{hours:02d}:{minutes:02d}"
    except:
        return "00:00"
def round_time_smart(time_minutes, asr_minutes, maghrib_minutes, isha_minutes):
    """
    Smart rounding of match time to nearest 5-minute interval based on prayer conflicts.
    Rounds to: :00, :05, :10, :15, :20, :25, :30, :35, :40, :45, :50, :55
    ALWAYS tries rounding DOWN first, then UP if there's a conflict.
    
    Args:
        time_minutes: Match start time in minutes since midnight
        asr_minutes: Asr prayer time in minutes
        maghrib_minutes: Maghrib prayer time in minutes
        isha_minutes: Isha prayer time in minutes
    
    Returns:
        Rounded time in minutes
    """
    # Extract the minute component
    minute_part = time_minutes % 60
    hour_part = time_minutes - minute_part
    
    # Check if already at a 5-minute interval
    if minute_part % 5 == 0:
        st.write(f"DEBUG: Time already at 5-min interval :{minute_part:02d}")
        return time_minutes
    
    # Calculate nearest 5-minute intervals
    lower_interval = (minute_part // 5) * 5  # Round down
    upper_interval = lower_interval + 5        # Round up
    
    # Handle edge case: if upper_interval is 60, it becomes next hour
    if upper_interval == 60:
        upper_interval = 0
        upper_hour_part = hour_part + 60
    else:
        upper_hour_part = hour_part
    
    # ALWAYS try rounding DOWN first, then UP
    options = [
        (hour_part + lower_interval, f":{lower_interval:02d}", "DOWN"),
        (upper_hour_part + upper_interval, f":{upper_interval:02d}", "UP")
    ]
    
    st.write(f"DEBUG: Minute :{minute_part:02d} → trying DOWN to :{lower_interval:02d} first, then UP to :{upper_interval:02d}")
    
    # Check each option for prayer conflicts
    for rounded_time, label, direction in options:
        match_end = rounded_time + 120  # 2-hour match duration
        
        # Check if any prayer falls during the match
        has_conflict = False
        conflict_prayer = None
        for prayer_name, prayer_time in [('Asr', asr_minutes), ('Maghrib', maghrib_minutes), ('Isha', isha_minutes)]:
            if rounded_time <= prayer_time <= match_end:
                # Prayer falls during match - check if it's in halftime
                halftime_start = rounded_time + 45  # End of first half
                halftime_end = rounded_time + 75    # Start of second half
                
                if not (halftime_start <= prayer_time <= halftime_end):
                    # Prayer is NOT during halftime - this is a conflict
                    has_conflict = True
                    conflict_prayer = prayer_name
                    break
        
        if not has_conflict:
            st.write(f"DEBUG: ✅ Rounded {direction} to {label} - no conflicts")
            return rounded_time
        else:
            st.write(f"DEBUG: ❌ Rounding {direction} to {label} causes conflict with {conflict_prayer}")
    
    # If both options conflict, keep original time
    st.write(f"DEBUG: ⚠️ Both DOWN and UP rounding options conflict - keeping original :{minute_part:02d}")
    return time_minutes


def calculate_match_times_for_city_and_date(city, match_date, teams_data=None):
    """
    Enhanced version with smart time rounding to nearest 5-minute interval for ALL times.
    Calculates FOUR match start times per day: Maghrib - 51 min, Isha - 51 min, 20:30 (mandatory), and 21:00 (mandatory).
    Ensures matches avoid prayer times or place prayers in halftime.
    """
    result = {
        "asr_time": None,
        "maghrib_time": None,
        "isha_time": None,
        "match_slots": []
    }

    prayer_data = get_prayer_times_unified(city, match_date)
    if 'error' in prayer_data:
        st.error(f"Error fetching prayer times for {city} on {match_date}: {prayer_data['error']}")
        result.update({
            "asr_time": "15:30" if city == 'Jeddah' else "15:33",
            "maghrib_time": "17:45" if city == 'Jeddah' else "17:48",
            "isha_time": "19:15" if city == 'Jeddah' else "19:18"
        })
    else:
        result.update({
            "asr_time": prayer_data['timings']['asr'],
            "maghrib_time": prayer_data['timings']['maghrib'],
            "isha_time": prayer_data['timings']['isha']
        })

    asr_minutes = time_string_to_minutes(result["asr_time"])
    maghrib_minutes = time_string_to_minutes(result["maghrib_time"])
    isha_minutes = time_string_to_minutes(result["isha_time"])

    st.write(f"DEBUG: Prayer times for {city} on {match_date}:")
    st.write(f"  Maghrib: {result['maghrib_time']} = {maghrib_minutes} minutes")
    st.write(f"  Isha: {result['isha_time']} = {isha_minutes} minutes")

    # Generate initial slots: Maghrib - 51 min, Isha - 51 min, 20:30 (mandatory), 21:00 (mandatory)
    maghrib_slot_minutes = maghrib_minutes - 51
    isha_slot_minutes = isha_minutes - 51
    mandatory_slot_2030_minutes = time_string_to_minutes("20:30")  # NEW: 20:30 mandatory
    mandatory_slot_2100_minutes = time_string_to_minutes("21:00")  # Existing 21:00 mandatory
    
    # Apply smart rounding to calculated slots (NOT to mandatory slots)
    st.write(f"DEBUG: Before rounding - Maghrib slot: {minutes_to_time_string(maghrib_slot_minutes)}")
    maghrib_slot_minutes = round_time_smart(maghrib_slot_minutes, asr_minutes, maghrib_minutes, isha_minutes)
    st.write(f"DEBUG: After rounding - Maghrib slot: {minutes_to_time_string(maghrib_slot_minutes)}")
    
    st.write(f"DEBUG: Before rounding - Isha slot: {minutes_to_time_string(isha_slot_minutes)}")
    isha_slot_minutes = round_time_smart(isha_slot_minutes, asr_minutes, maghrib_minutes, isha_minutes)
    st.write(f"DEBUG: After rounding - Isha slot: {minutes_to_time_string(isha_slot_minutes)}")
    
    # Mandatory slots are NOT rounded
    st.write(f"DEBUG: Mandatory slot 20:30 - NOT ROUNDED (mandatory)")
    st.write(f"DEBUG: Mandatory slot 21:00 - NOT ROUNDED (mandatory)")
    
    maghrib_slot = minutes_to_time_string(maghrib_slot_minutes)
    isha_slot = minutes_to_time_string(isha_slot_minutes)
    mandatory_slot_2030 = minutes_to_time_string(mandatory_slot_2030_minutes)
    mandatory_slot_2100 = minutes_to_time_string(mandatory_slot_2100_minutes)

    st.write(f"DEBUG: All match slots:")
    st.write(f"  Maghrib slot: {maghrib_slot} (rounded)")
    st.write(f"  Isha slot: {isha_slot} (rounded)")
    st.write(f"  Mandatory slot: {mandatory_slot_2030} (NOT rounded)")
    st.write(f"  Mandatory slot: {mandatory_slot_2100} (NOT rounded)")

    candidate_slots = [maghrib_slot, isha_slot, mandatory_slot_2030, mandatory_slot_2100]

    # Check for prayer conflicts in each slot
    valid_slots = []
    for start_time in candidate_slots:
        start_minutes = time_string_to_minutes(start_time)
        end_minutes = start_minutes + 120  # 2-hour match
        prayer_conflict = False
        conflict_prayer = None
        
        for prayer_name, prayer_minutes in [('Asr', asr_minutes), ('Maghrib', maghrib_minutes), ('Isha', isha_minutes)]:
            if start_minutes <= prayer_minutes <= end_minutes:
                halftime_start = start_minutes + 45
                halftime_end = start_minutes + 75
                
                if not (halftime_start <= prayer_minutes <= halftime_end):
                    prayer_conflict = True
                    conflict_prayer = prayer_name
                    st.write(f"DEBUG: {start_time} conflicts with {prayer_name}")
                    break
        
        if not prayer_conflict:
            valid_slots.append(start_time)
            st.write(f"DEBUG: ✅ {start_time} is VALID")
        else:
            # For mandatory slots, still add them even if they conflict (just note the conflict)
            if start_time in [mandatory_slot_2030, mandatory_slot_2100]:
                valid_slots.append(start_time)
                st.write(f"DEBUG: ⚠️ {start_time} is MANDATORY (added despite {conflict_prayer} conflict)")

    # Fill to exactly 4 slots if needed
    if len(valid_slots) < 4:
        gap_available = maghrib_minutes - asr_minutes
        if gap_available >= 150:
            gap_start = asr_minutes + 30
            
            # Apply smart rounding to gap slot too
            st.write(f"DEBUG: Before rounding - Gap slot: {minutes_to_time_string(gap_start)}")
            gap_start = round_time_smart(gap_start, asr_minutes, maghrib_minutes, isha_minutes)
            st.write(f"DEBUG: After rounding - Gap slot: {minutes_to_time_string(gap_start)}")
            
            gap_time = minutes_to_time_string(gap_start)
            
            # Verify no conflict with this gap slot
            gap_end = gap_start + 120
            gap_conflict = False
            for prayer_minutes in [asr_minutes, maghrib_minutes, isha_minutes]:
                if gap_start <= prayer_minutes <= gap_end:
                    halftime_start = gap_start + 45
                    halftime_end = gap_start + 75
                    if not (halftime_start <= prayer_minutes <= halftime_end):
                        gap_conflict = True
                        break
            
            if not gap_conflict and gap_time not in valid_slots:
                valid_slots.append(gap_time)
                st.write(f"DEBUG: Added gap slot {gap_time}")
    
    # If we still need more slots, try alternative times with rounding
    if len(valid_slots) < 4:
        alternative_times = [
            isha_minutes - 60,  # Isha - 60 min
            maghrib_minutes - 30,  # Maghrib - 30 min
            asr_minutes + 60  # Asr + 60 min
        ]
        
        for alt_time in alternative_times:
            if len(valid_slots) >= 4:
                break
            
            # Apply smart rounding to alternative times
            st.write(f"DEBUG: Before rounding - Alternative slot: {minutes_to_time_string(alt_time)}")
            alt_time_rounded = round_time_smart(alt_time, asr_minutes, maghrib_minutes, isha_minutes)
            st.write(f"DEBUG: After rounding - Alternative slot: {minutes_to_time_string(alt_time_rounded)}")
            
            alt_time_str = minutes_to_time_string(alt_time_rounded)
            
            if alt_time_str not in valid_slots:
                # Check for conflicts
                alt_end = alt_time_rounded + 120
                alt_conflict = False
                for prayer_minutes in [asr_minutes, maghrib_minutes, isha_minutes]:
                    if alt_time_rounded <= prayer_minutes <= alt_end:
                        halftime_start = alt_time_rounded + 45
                        halftime_end = alt_time_rounded + 75
                        if not (halftime_start <= prayer_minutes <= halftime_end):
                            alt_conflict = True
                            break
                
                if not alt_conflict:
                    valid_slots.append(alt_time_str)
                    st.write(f"DEBUG: Added alternative slot {alt_time_str}")
    
    # Sort and limit to 4 slots
    valid_slots_sorted = sorted(set(valid_slots), key=time_string_to_minutes)[:4]
    result["match_slots"] = valid_slots_sorted
    
    st.write(f"Final match slots for {city} on {match_date}: {result['match_slots']}")
    return result


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
        'Al-Khaleej': {'city': 'Dammam', 'stadium': 'Prince Mohammed Bin Fahd Stadium', 'stadium_capacity': 20000},
        'Al-Ettifaq': {'city': 'Dammam', 'stadium': 'EGO Stadium', 'stadium_capacity': 15000},
        'Al-Taawoun': {'city': 'Buraydah', 'stadium': 'Al-Taawoun Club Stadium', 'stadium_capacity': 25000},
        'Al-Fateh': {'city': 'Al-Mubarraz', 'stadium': 'Al-Fateh Club Stadium', 'stadium_capacity': 20000},
        'Al-Hilal': {'city': 'Riyadh', 'stadium': 'Kingdom Arena', 'stadium_capacity': 30000},
        'Al-Ahli': {'city': 'Jeddah', 'stadium': 'Alinma Stadium', 'stadium_capacity': 30000},
        'Al-Ittihad': {'city': 'Jeddah', 'stadium': 'Alinma Stadium', 'stadium_capacity': 60000},
        'Damac': {'city': 'Khamis Mushait', 'stadium': 'Damac Club Stadium (Khamis Mushait)', 'stadium_capacity': 20000},
        'Al-Okhdood': {'city': 'Abha', 'stadium': 'Prince Hathloul bin Abdulaziz Sport Staduim', 'stadium_capacity': 20000},
        'Al-Hazem': {'city': 'Abha', 'stadium': 'Al-Hazem Club Stadium', 'stadium_capacity': 20000},
        'Al-Qadisiyah': {'city': 'Al Khobar', 'stadium': 'Mohammed Bin Fahd Stadiu', 'stadium_capacity': 20000},
        'Al-Shabab': {'city': 'Riyadh', 'stadium': 'Al-Shabab Club Stadium', 'stadium_capacity': 20000},
        'Al-Nassr': {'city': 'Riyadh', 'stadium': 'King Saud University Stadium (Al-Oul Park)', 'stadium_capacity': 25000},
        'Al-Fayha': {'city': 'Al-Majmaah', 'stadium': 'Al-Majmaah Sports City', 'stadium_capacity': 20000},
        'Al-Kholood': {'city': 'Ar Rass', 'stadium': 'Al-Hazem Club Stadium', 'stadium_capacity': 20000},
        'Al-riyadh': {'city': 'Riyadh', 'stadium': 'Prince Faisal bin Fahd Stadium', 'stadium_capacity': 15000},
        'Al-Najma': {'city': 'Buraydah', 'stadium': 'King Abdullah Sport City', 'stadium_capacity': 20000},
        'NEOM': {'city': 'NEOM', 'stadium': 'King Khalid Sports City Stadium', 'stadium_capacity': 20000}
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

    # Updated data dictionary with all 18 teams - corrected to match CITY_STADIUMS
    data = {
        'team': [
            'Al-Taawoun', 'Al-Hilal', 'Al-Nassr', 'Al-Ittihad', 'Al-Ahli', 'Al-Shabab',
            'Al-Ettifaq', 'Al-Fateh', 'Al-Fayha', 'Al-Khaleej', 'Al-Okhdood', 'Al-Hazem',
            'Al-Qadisiyah', 'Al-riyadh', 'Al-Najma', 'Al-Kholood', 'Damac', 'NEOM'
        ],
        'home_city': [
            'Buraydah', 'Riyadh', 'Riyadh', 'Jeddah', 'Jeddah', 'Riyadh',
            'Dammam', 'Al-Mubarraz', 'Al-Majmaah', 'Dammam', 'Najran', 'Ar Rass',
            'Al Khobar', 'Riyadh', 'Unaizah', 'Ar Rass', 'Khamis Mushait', 'NEOM'
        ],
        'home_stadium': [
            'Al-Taawoun Club Stadium (Buraydah)', 
            'Kingdom Arena', 
            'King Saud University Stadium (Al-Oul Park)',
            'Alinma Stadium', 
            'Alinma Stadium',
            'Al-Shabab Club Stadium', 
            'EGO Stadium',  # Changed from 'Al-Ettifaq Club Stadium'
            'Al-Fateh Club Stadium', 
            'Al-Majmaah Sports City', 
            'Prince Mohammed Bin Fahd Stadium',
            'Prince Hathloul Sport City',  # Changed from 'Prince Hathloul bin Abdulaziz Sport Staduim'
            'Al-Hazem Club Stadium', 
            'Mohammed Bin Fahd Stadiu',
            'Prince Faisal bin Fahd Stadium', 
            'King Abdullah Sport City',  # Al-Najma's stadium
            'Al-Hazem Club Stadium',
            'Damac Club Stadium (Khamis Mushait)', 
            'King Khalid Sports City Stadium'
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
        'city': ['Riyadh', 'Jeddah', 'Dammam', 'Buraydah', 'Al-Mubarraz', 'Khamis Mushait', 'Abha', 'Al Khobar', 'Saihat', 'Al-Majmaah', 'Ar Rass', 'Unaizah', 'NEOM', 'Najran'],
        'month': [9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9],
        'temperature': [35, 32, 33, 34, 33, 28, 27, 33, 34, 34, 34, 34, 30, 28],
        'humidity': [30, 60, 55, 35, 50, 40, 45, 55, 50, 35, 35, 35, 25, 40]
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
# Define team name mappings with normalized keys
    CLEAN_TEAM_NAMES = {
        'AL ITTIHAD': 'Al-Ittihad',
        'AL ETTIFAQ': 'Al-Ettifaq',
        'AL TAAWOUN': 'Al-Taawoun',
        'Al Taawoun': 'Al-Taawoun',
        'AL HILAL': 'Al-Hilal',
        'AL NASSR': 'Al-Nassr',
        'AL AHLI': 'Al-Ahli',
        'AL SHABAB': 'Al-Shabab',
        'AL FATEH': 'Al-Fateh',
        'AL FAYHA': 'Al-Fayha',
        'AL KHALEEJ': 'Al-Khaleej',
        'AL OKHDOOD': 'Al-Okhdood',
        'AL HAZEM': 'Al-Hazem',
        'Al Hazem': 'Al-Hazem',
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
        'AL-TAAWOUN': 'Al-Taawoun',
        'AL TAAWOUN ': 'Al-Taawoun',
        'AL-HAZEM': 'Al-Hazem',
        'AL HAZEM ': 'Al-Hazem',
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


def get_last_match_info(team, current_week, current_date):
    """
    Get the last match played by a team before the current date.
    Returns: (date, opponent, stadium, rest_days) or None if no previous match
    """
    if 'schedule_df' not in st.session_state:
        return None
    
    schedule_df = st.session_state.schedule_df
    if schedule_df.empty:
        return None
    
    # Filter for selected matches only
    selected_matches = schedule_df[schedule_df['is_selected'] == True].copy()
    
    if selected_matches.empty:
        return None
    
    # Convert date to datetime for comparison
    selected_matches['date_dt'] = pd.to_datetime(selected_matches['date'])
    current_date_dt = pd.to_datetime(current_date)
    
    # Find matches where the team played (as home or away) before current date
    team_matches = selected_matches[
        ((selected_matches['home_team'] == team) | (selected_matches['away_team'] == team)) &
        (selected_matches['date_dt'] < current_date_dt)
    ].sort_values('date_dt', ascending=False)
    
    if team_matches.empty:
        return None
    
    # Get the most recent match
    last_match = team_matches.iloc[0]
    opponent = last_match['away_team'] if last_match['home_team'] == team else last_match['home_team']
    
    # Calculate rest days
    rest_days = (current_date_dt.date() - last_match['date_dt'].date()).days
    
    return {
        'date': last_match['date'],
        'opponent': opponent,
        'stadium': last_match['stadium'],
        'was_home': last_match['home_team'] == team,
        'rest_days': rest_days
    }


def get_team_ranking():
    """
    Calculate team rankings based on last 4 years' performance (2021-2024).
    Teams without historical data are ranked last.
    Returns dictionary with team rankings and average positions.
    """
    # Historical rankings data (complete standings)
    historical_rankings = {
        2021: {
            'Al-Hilal': 1, 'Al-Ittihad': 2, 'Al-Nassr': 3, 'Al-Shabab': 4,
            'Damac': 5, 'Al-Tai': 6, 'Al-Raed': 7, 'Al-Fateh': 8,
            'Al-Fayha': 9, 'Abha': 10, 'Al-Taawoun': 11, 'Al-Ettifaq': 12,
            'Al-Faisaly': 13, 'Al-Batin': 14, 'Al-Ahli': 15, 'Al-Hazem': 16
        },
        2022: {
            'Al-Ittihad': 1, 'Al-Nassr': 2, 'Al-Hilal': 3, 'Al-Shabab': 4,
            'Al-Taawoun': 5, 'Al-Fateh': 6, 'Al-Ettifaq': 7, 'Damac': 8,
            'Al-Raed': 9, 'Al-Tai': 10, 'Al-Fayha': 11, 'Abha': 12,
            'Al-Wehda': 13, 'Al-Khaleej': 14, 'Al-Adalah': 15, 'Al-Batin': 16
        },
        2023: {
            'Al-Hilal': 1, 'Al-Nassr': 2, 'Al-Ahli': 3, 'Al-Taawoun': 4,
            'Al-Ittihad': 5, 'Al-Ettifaq': 6, 'Al-Fateh': 7, 'Al-Shabab': 8,
            'Al-Fayha': 9, 'Damac': 10, 'Al-Raed': 11, 'Al-Khaleej': 12,
            'Al-Wehda': 13, 'Al-riyadh': 14, 'Al-Okhdood': 15, 'Abha': 16,
            'Al-Tai': 17, 'Al-Hazem': 18
        },
        2024: {
            'Al-Ittihad': 1, 'Al-Hilal': 2, 'Al-Nassr': 3, 'Al-Qadisiyah': 4,
            'Al-Ahli': 5, 'Al-Shabab': 6, 'Al-Ettifaq': 7, 'Al-Taawoun': 8,
            'Al-Kholood': 9, 'Al-Fateh': 10, 'Al-riyadh': 11, 'Al-Khaleej': 12,
            'Al-Fayha': 13, 'Damac': 14, 'Al-Okhdood': 15, 'Al-Wehda': 16,
            'Al-Orobah': 17, 'Al-Raed': 18
        }
    }
    
    # Calculate average rankings for teams with historical data
    team_totals = {}
    team_counts = {}
    
    for year, rankings in historical_rankings.items():
        for team, rank in rankings.items():
            if team not in team_totals:
                team_totals[team] = 0
                team_counts[team] = 0
            team_totals[team] += rank
            team_counts[team] += 1
    
    # Calculate averages
    team_averages = {
        team: team_totals[team] / team_counts[team] 
        for team in team_totals
    }
    
    # Sort teams with historical data by average (lower is better)
    sorted_teams = sorted(team_averages.items(), key=lambda x: x[1])
    
    # Assign current rankings to teams with historical data
    current_rankings = {}
    for i, (team, avg) in enumerate(sorted_teams, 1):
        current_rankings[team] = {
            'rank': i,
            'average': round(avg, 2),
            'appearances': team_counts[team],
            'has_history': True
        }
    
    return current_rankings


def get_all_teams_with_ranks():
    """
    Get a sorted list of all teams with their rankings.
    Useful for debugging and verification.
    """
    rankings = get_team_ranking()
    sorted_teams = sorted(rankings.items(), key=lambda x: x[1]['rank'])
    
    print("=== ALL TEAM RANKINGS (Historical Data) ===")
    for team, info in sorted_teams:
        history_indicator = "✓" if info.get('has_history', False) else "✗"
        print(f"{history_indicator} #{info['rank']:2d} - {team:20s} (Avg: {info['average']:.2f}, Appearances: {info['appearances']})")
    print(f"\nTotal teams with historical data: {len(rankings)}")
    print("\nNote: Teams without historical data (2021-2024) will show as 'NEW TEAM' in badges")
    return sorted_teams



def check_team_in_rankings(team_name):
    """
    Check if a specific team exists in rankings and show its details.
    Helps identify spelling differences or missing teams.
    """
    rankings = get_team_ranking()
    
    if team_name in rankings:
        info = rankings[team_name]
        print(f"✓ {team_name} found!")
        print(f"  Rank: #{info['rank']}")
        print(f"  Average: {info['average']}")
        print(f"  Appearances: {info['appearances']}")
        return True
    else:
        print(f"✗ {team_name} NOT found in rankings")
        print(f"\nDid you mean one of these?")
        # Find similar team names
        all_teams = sorted(rankings.keys())
        for team in all_teams:
            if team_name.lower() in team.lower() or team.lower() in team_name.lower():
                print(f"  - {team}")
        return False



def get_ordinal_suffix(rank):
    """
    Convert a number to its ordinal form (1st, 2nd, 3rd, etc.)
    """
    if 10 <= rank % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(rank % 10, 'th')
    return f"{rank}{suffix}"


def get_team_rank_badge(team):
    """
    Get a visual badge for team ranking with ordinal numbers.
    Returns HTML string with badge or empty string.
    Teams without historical data get a "NEW TEAM" badge.
    """
    rankings = get_team_ranking()
    
    # Check if team has historical ranking
    if team not in rankings:
        # Team has no historical data - assign "NEW TEAM" badge
        style = {'icon': '🆕', 'color': '#FF6B6B', 'bg': '#FFE5E5', 'border': '#FF6B6B', 'text': 'NEW TEAM'}
        
        badge_parts = []
        badge_parts.append('<div style="display: inline-block; background: ')
        badge_parts.append(style['bg'])
        badge_parts.append('; border: 2px solid ')
        badge_parts.append(style['border'])
        badge_parts.append('; border-radius: 8px; padding: 4px 10px; margin: 5px 0; font-size: 0.85em;">')
        badge_parts.append('<span style="font-size: 1.2em;">')
        badge_parts.append(style['icon'])
        badge_parts.append('</span>')
        badge_parts.append('<span style="color: ')
        badge_parts.append(style['color'])
        badge_parts.append('; font-weight: bold; margin-left: 4px;">')
        badge_parts.append(style['text'])
        badge_parts.append('</span>')
        badge_parts.append('<span style="color: #666; font-size: 0.9em; margin-left: 6px;">(No History)</span>')
        badge_parts.append('</div>')
        
        return ''.join(badge_parts)
    
    rank_info = rankings[team]
    rank = rank_info['rank']
    avg = rank_info['average']
    
    # Get ordinal form of rank
    ordinal_rank = get_ordinal_suffix(rank)
    
    # Define badge styles based on ranking tiers
    if rank == 1:
        style = {'icon': '', 'color': '#FFD700', 'bg': '#FFF9E6', 'border': '#FFD700', 'text': ''}
    elif rank == 2:
        style = {'icon': '', 'color': '#C0C0C0', 'bg': '#F5F5F5', 'border': '#C0C0C0', 'text': ''}
    elif rank == 3:
        style = {'icon': '', 'color': '#CD7F32', 'bg': '#FFF5EE', 'border': '#CD7F32', 'text': ''}
    elif rank <= 5:
        style = {'icon': '', 'color': '#4A90E2', 'bg': '#E8F4FD', 'border': '#4A90E2', 'text': ''}
    elif rank <= 10:
        style = {'icon': '', 'color': '#5C6BC0', 'bg': '#E8EAF6', 'border': '#5C6BC0', 'text': ''}
    elif rank <= 14:
        style = {'icon': '', 'color': '#78909C', 'bg': '#ECEFF1', 'border': '#78909C', 'text': ''}
    else:
        style = {'icon': '', 'color': '#9E9E9E', 'bg': '#FAFAFA', 'border': '#BDBDBD', 'text': ''}
    
    # Build badge HTML using consistent double quotes
    badge_parts = []
    badge_parts.append('<div style="display: inline-block; background: ')
    badge_parts.append(style['bg'])
    badge_parts.append('; border: 2px solid ')
    badge_parts.append(style['border'])
    badge_parts.append('; border-radius: 8px; padding: 4px 10px; margin: 5px 0; font-size: 0.85em;">')
    badge_parts.append('<span style="font-size: 1.2em;">')
    badge_parts.append(style['icon'])
    badge_parts.append('</span>')
    badge_parts.append('<span style="color: ')
    badge_parts.append(style['color'])
    badge_parts.append('; font-weight: bold; margin-left: 4px;">')
    badge_parts.append(ordinal_rank)  # Use ordinal form instead of just rank
    
    # Add text label if it exists
    if style['text']:
        badge_parts.append(' - ')
        badge_parts.append(style['text'])
    
    badge_parts.append('</span>')
    badge_parts.append('</div>')
    
    return ''.join(badge_parts)


def get_match_prestige_level(home_team, away_team):
    """
    Determine the prestige level of a match based on team rankings.
    Returns tuple: (prestige_level, description, icon)
    Handles teams without historical data.
    """
    rankings = get_team_ranking()
    
    # Get ranks, treating teams without history as unranked (999)
    home_rank = rankings.get(home_team, {}).get('rank', 999)
    away_rank = rankings.get(away_team, {}).get('rank', 999)
    
    # If either team is new/unranked, lower the prestige
    if home_rank == 999 or away_rank == 999:
        # If one team is ranked in top 5 and other is new
        if (home_rank <= 5 and away_rank == 999) or (away_rank <= 5 and home_rank == 999):
            return ('medium', 'FEATURED MATCH', '🎯')
        else:
            return ('regular', 'STANDARD MATCH', '⚽')
    
    # Both teams exist in rankings
    if home_rank < 999 and away_rank < 999:
        # Top 3 derby (both in top 3)
        if home_rank <= 3 and away_rank <= 3:
            return ('elite', 'ELITE CLASH', '👑')
        # One top 3 team involved
        elif home_rank <= 3 or away_rank <= 3:
            return ('high', 'TOP TIER MATCH', '🏆')
        # Both in top 10
        elif home_rank <= 10 and away_rank <= 10:
            return ('medium-high', 'PREMIUM MATCH', '💎')
        # At least one in top 10
        elif home_rank <= 10 or away_rank <= 10:
            return ('medium', 'FEATURED MATCH', '🎯')
        # Mid-table clash
        else:
            return ('regular', 'STANDARD MATCH', '⚽')
    else:
        return ('regular', '', '')


def get_team_rest_days(team, match_date):
    """
    Calculate rest days for a team considering both selected matches and TEAM_UNAVAILABILITY.
    
    Args:
        team (str): Team name
        match_date (str or datetime.date): Date of the current match
    
    Returns:
        tuple: (rest_days, last_match_date, match_type)
               match_type can be 'league' or 'external'
    """
    import datetime
    
    TEAM_UNAVAILABILITY = {
    'Al-Ittihad': [
        datetime.date(2025, 9, 15),
        datetime.date(2025, 9, 30),
        datetime.date(2025, 10, 20),
        datetime.date(2025, 10, 28),
        datetime.date(2025, 11, 4),
        datetime.date(2025, 11, 24),
        datetime.date(2025, 12, 23),
        datetime.date(2026, 2, 10),
        datetime.date(2026, 2, 17)
    ],
    'Al-Ahli': [
        datetime.date(2025, 9, 15),
        datetime.date(2025, 9, 29),
        datetime.date(2025, 10, 20),
        datetime.date(2025, 10, 27),
        datetime.date(2025, 11, 4),
        datetime.date(2025, 11, 24),
        datetime.date(2025, 12, 22),
        datetime.date(2026, 2, 9),
        datetime.date(2026, 2, 16)
    ],
    'Al-Hilal': [
        datetime.date(2025, 9, 16),
        datetime.date(2025, 9, 29),
        datetime.date(2025, 10, 21),
        datetime.date(2025, 10, 28),
        datetime.date(2025, 11, 3),
        datetime.date(2025, 11, 25),
        datetime.date(2025, 12, 22),
        datetime.date(2026, 2, 9),
        datetime.date(2026, 2, 16)
    ],
    'Al-Nassr': [
        datetime.date(2025, 9, 17),
        datetime.date(2025, 10, 1),
        datetime.date(2025, 10, 22),
        datetime.date(2025, 10, 28),
        datetime.date(2025, 11, 5),
        datetime.date(2025, 11, 26),
        datetime.date(2025, 12, 24)
    ],
    'Al-Shabab': [
        datetime.date(2025, 10, 1),
        datetime.date(2025, 10, 21),
        datetime.date(2025, 10, 28),
        datetime.date(2025, 11, 5),
        datetime.date(2025, 12, 24),
        datetime.date(2026, 2, 1),
        datetime.date(2026, 2, 17)
    ],
 'Al-Ettifaq': [datetime.date(2025, 10, 24)],
    'Al-Fayha' : [
        datetime.date(2025, 10, 24)
    ],  
     'NEOM' : [
        datetime.date(2025, 10, 24)
    ],  
    'Al-Khaleej': [
        datetime.date(2025, 10, 27)
    ],
    'Al-Fateh': [
        datetime.date(2025, 10, 27)
    ],
    'Al-Okhdood': [
        datetime.date(2025, 10, 27)
    ],
    'Al-Batin': [
        datetime.date(2025, 10, 27)
    ],
    'Al-Qadisiyah': [
        datetime.date(2025, 10, 28)
    ],
    'Al-Kholood': [
        datetime.date(2025, 10, 28)
    ],
    'Al-Taawoun': [
        datetime.date(2025, 10, 27)
    ],
    'Al-riyadh': [
        datetime.date(2025, 10, 27)
    ],
    'Al-Najma': [
        datetime.date(2025, 10, 27)
    ],
    'Al-Hazem': [
        datetime.date(2025, 10, 28)
    ],
    'Al-Raed': [
        datetime.date(2025, 10, 28)
    ],
     'Damac': [
        datetime.date(2025, 10, 25)
    ]
    }
    
    # Convert match_date to datetime.date if it's a string
    if isinstance(match_date, str):
        match_date = datetime.datetime.strptime(match_date, '%Y-%m-%d').date()
    
    # Get external matches for this team
    external_matches = TEAM_UNAVAILABILITY.get(team, [])
    
    # Get league matches from schedule_df
    league_matches = []
    if 'schedule_df' in st.session_state and not st.session_state.schedule_df.empty:
        schedule_df = st.session_state.schedule_df
        selected_matches = schedule_df[schedule_df['is_selected'] == True].copy()
        
        if not selected_matches.empty:
            selected_matches['date_dt'] = pd.to_datetime(selected_matches['date']).dt.date
            team_matches = selected_matches[
                ((selected_matches['home_team'] == team) | (selected_matches['away_team'] == team)) &
                (selected_matches['date_dt'] < match_date)
            ]
            league_matches = team_matches['date_dt'].tolist()
    
    # Combine all matches and filter only those before match_date
    all_matches = []
    for ext_date in external_matches:
        if ext_date < match_date:
            all_matches.append((ext_date, 'external'))
    
    for league_date in league_matches:
        all_matches.append((league_date, 'league'))
    
    # Sort by date and get the most recent one
    if not all_matches:
        return None, None, None
    
    all_matches.sort(key=lambda x: x[0], reverse=True)
    last_match_date, match_type = all_matches[0]
    
    # Calculate rest days
    rest_days = (match_date - last_match_date).days
    
    return rest_days, last_match_date, match_type

def get_scenario_time_context(scenario, available_scenarios):
    """
    Get the context/reason why a scenario time was selected.
    Returns a string describing the time calculation method based on scenario position per day.
    
    Args:
        scenario: The current scenario object
        available_scenarios: List of all available scenarios for this match
    """
    try:
        import datetime
        
        # Get the date of the current scenario
        current_date = datetime.datetime.strptime(scenario.date, '%Y-%m-%d').date()
        
        # Group scenarios by date and find position within the same day
        scenarios_same_day = [s for s in available_scenarios 
                             if datetime.datetime.strptime(s.date, '%Y-%m-%d').date() == current_date]
        
        # Sort scenarios of the same day by time
        scenarios_same_day.sort(key=lambda s: datetime.datetime.strptime(s.time, '%H:%M').time())
        
        # Find the index of this scenario within its day
        scenario_index_in_day = scenarios_same_day.index(scenario)
        
        if scenario_index_in_day == 0:
            return "🌙 Calculated from Maghrib Prayer Time"
        elif scenario_index_in_day == 1:
            return "🕌 Calculated from Isha Prayer Time"
        else:
            return "⏰ Fixed Time"
    except (ValueError, AttributeError, IndexError):
        return "⏰ Fixed Time"  # Fallback if scenario not found





def display_week_scenarios(week_number, matches_from_excel):
    """
    Display matches for a week with stadium dropdown selection.
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
        7: datetime.date(2025, 10, 30), 8: datetime.date(2025, 11, 6),
        9: datetime.date(2025, 11, 21), 10: datetime.date(2025, 12, 19),
        11: datetime.date(2025, 12, 25), 12: datetime.date(2025, 12, 29),
        13: datetime.date(2026, 1, 2), 14: datetime.date(2026, 1, 8),
        15: datetime.date(2026, 1, 12), 16: datetime.date(2026, 1, 16),
        17: datetime.date(2026, 1, 20), 18: datetime.date(2026, 1, 24),
        19: datetime.date(2026, 1, 28), 20: datetime.date(2026, 2, 1),
        21: datetime.date(2026, 2, 5), 22: datetime.date(2026, 2, 12),
        23: datetime.date(2026, 2, 19), 24: datetime.date(2026, 2, 26),
        25: datetime.date(2026, 3, 5), 26: datetime.date(2026, 3, 12),
        27: datetime.date(2026, 4, 3), 28: datetime.date(2026, 4, 9),
        29: datetime.date(2026, 4, 23), 30: datetime.date(2026, 4, 28),
        31: datetime.date(2026, 5, 2), 32: datetime.date(2026, 5, 7),
        33: datetime.date(2026, 5, 13), 34: datetime.date(2026, 5, 21),
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

        # Check if match is already selected
        if match_id in st.session_state.scenario_manager.selected_scenarios:
            selected_count += 1
            scenario_id = st.session_state.scenario_manager.selected_scenarios[match_id]
            scenarios = st.session_state.scenario_manager.get_scenarios_for_match(match_id)
            selected_scenario = None
            for scenario in scenarios:
                if scenario.scenario_id == scenario_id:
                    selected_scenario = scenario
                    break
                        
            # For SELECTED matches
            if selected_scenario:
                day_name = datetime.datetime.strptime(selected_scenario.date, '%Y-%m-%d').strftime('%A')
                time_context = get_scenario_time_context(selected_scenario, scenarios)
                                
                # Get team rankings for the card
                home_badge = get_team_rank_badge(home)
                away_badge = get_team_rank_badge(away)
                prestige_level, prestige_desc, prestige_icon = get_match_prestige_level(home, away)
                
                # Create prestige badge if applicable
                prestige_html = ""
                if prestige_level != 'regular':
                    prestige_colors = {
                        'elite': {'bg': '#FFD700', 'text': '#000'},
                        'high': {'bg': '#4CAF50', 'text': '#FFF'},
                        'medium-high': {'bg': '#00BCD4', 'text': '#FFF'},  # Added medium-high
                        'medium': {'bg': '#2196F3', 'text': '#FFF'}
                    }
                    color = prestige_colors.get(prestige_level, {'bg': '#6c757d', 'text': '#FFF'})
                    prestige_html = f"""<div style='background: {color['bg']}; color: {color['text']}; display: inline-block; padding: 5px 12px; border-radius: 20px; font-weight: bold; font-size: 0.9em; margin: 5px 0;'>{prestige_icon} {prestige_desc}</div>"""
                
                # Get rest days
                last_match_html = ""
                if week_number > 1:
                    home_rest = get_team_rest_days(home, selected_scenario.date)
                    away_rest = get_team_rest_days(away, selected_scenario.date)
                    
                    if home_rest[0] is not None or away_rest[0] is not None:
                        last_match_parts = []
                        last_match_parts.append("<div style='margin-top: 8px; padding: 8px; background-color: #f0f8ff; border-radius: 5px;'>")
                        last_match_parts.append("<div style='font-weight: bold; color: #155724; margin-bottom: 5px;'>📋 Last Match & Rest Days:</div>")
                        
                        if home_rest[0] is not None:
                            rest_days, last_date, match_type = home_rest
                            match_icon = "🏆" if match_type == 'league' else "✈️"
                            match_label = "League" if match_type == 'league' else "External"
                            rest_color = "#28a745" if rest_days >= 3 else "#ffc107" if rest_days >= 2 else "#dc3545"
                            last_match_parts.append(f"<div style='font-size: 0.9em; color: #155724;'><b>{home}</b>: {match_icon} {match_label} match on {last_date.strftime('%Y-%m-%d')} | <span style='color: {rest_color}; font-weight: bold;'>⏱️ {rest_days} days rest</span></div>")
                        else:
                            last_match_parts.append(f"<div style='font-size: 0.9em; color: #155724;'><b>{home}</b>: No previous match</div>")
                        
                        if away_rest[0] is not None:
                            rest_days, last_date, match_type = away_rest
                            match_icon = "🏆" if match_type == 'league' else "✈️"
                            match_label = "League" if match_type == 'league' else "External"
                            rest_color = "#28a745" if rest_days >= 3 else "#ffc107" if rest_days >= 2 else "#dc3545"
                            last_match_parts.append(f"<div style='font-size: 0.9em; color: #155724;'><b>{away}</b>: {match_icon} {match_label} match on {last_date.strftime('%Y-%m-%d')} | <span style='color: {rest_color}; font-weight: bold;'>⏱️ {rest_days} days rest</span></div>")
                        else:
                            last_match_parts.append(f"<div style='font-size: 0.9em; color: #155724;'><b>{away}</b>: No previous match</div>")
                        
                        last_match_parts.append("</div>")
                        last_match_html = ''.join(last_match_parts)
                
                # Build selected card HTML properly with team ranks in squares side by side
                selected_card_parts = []
                selected_card_parts.append('<div style="background-color:#d4edda; border:2px solid #28a745; border-radius:10px; padding:15px; margin:10px 0;">')
                # Add team ranks in squares beside each other
                home_rank_badge = get_team_rank_badge(home) if home_badge else ""
                away_rank_badge = get_team_rank_badge(away) if away_badge else ""
                # Extract just the number from badges
                home_rank_num = home_rank_badge.replace("th", "").replace("st", "").replace("nd", "").replace("rd", "")
                away_rank_num = away_rank_badge.replace("th", "").replace("st", "").replace("nd", "").replace("rd", "")
                selected_card_parts.append(f'<div style="display: flex; gap: 15px; margin-bottom: 10px; flex-wrap: wrap;">')
                selected_card_parts.append(f'<div style="background: #155724; color: white; padding: 10px 20px; border-radius: 8px; font-weight: bold; font-size: 14px; white-space: nowrap;">{home} <span style="font-size: 16px; margin-left: 8px;">{home_rank_num}</span></div>')
                selected_card_parts.append(f'<div style="background: #155724; color: white; padding: 10px 20px; border-radius: 8px; font-weight: bold; font-size: 14px; white-space: nowrap;">{away} <span style="font-size: 16px; margin-left: 8px;">{away_rank_num}</span></div>')
                selected_card_parts.append(f'</div>')
                selected_card_parts.append(f'<div style="font-weight:bold; color:#28a745; font-size:14px;">✅ (SELECTED)</div>')
                
                if prestige_html:
                    selected_card_parts.append(prestige_html)
                
                selected_card_parts.append(f'<div style="color:#155724; margin-top:5px; line-height:1.5;">')
                selected_card_parts.append(f'📅 {selected_scenario.date} ({day_name}) 🕐 {selected_scenario.time}<br>')
                selected_card_parts.append(f'🏟️ {selected_scenario.stadium} ({selected_scenario.city})<br>')
                selected_card_parts.append(f'{time_context}<br>')
                selected_card_parts.append(f'👥 Attendance: {selected_scenario.attendance_percentage}%')
                selected_card_parts.append('</div>')
                
                if last_match_html:
                    selected_card_parts.append(last_match_html)
                
                selected_card_parts.append('</div>')
                
                # Display the selected match card
                st.markdown(''.join(selected_card_parts), unsafe_allow_html=True)
                
                if st.button(f"Deselect Match", key=f"deselect_{match_id}_{week_number}"):
                    # Remove from selected scenarios
                    del st.session_state.scenario_manager.selected_scenarios[match_id]
                    current_date = datetime.datetime.strptime(selected_scenario.date, '%Y-%m-%d').date()
                    
                    # Decrement day count
                    if st.session_state.day_counts.get(current_date, 0) > 0:
                        st.session_state.day_counts[current_date] -= 1
                    
                    # Remove the deselected match from schedule_df if it exists
                    if 'schedule_df' in st.session_state and 'match_id' in st.session_state.schedule_df.columns:
                        st.session_state.schedule_df = st.session_state.schedule_df[
                            st.session_state.schedule_df['match_id'] != match_id
                        ]
                    
                    st.success(f"Deselected {home} vs {away}. Day {current_date} is now available for other matches.")
                    st.rerun()
                    
            continue

        scenarios = st.session_state.scenario_manager.get_scenarios_for_match(match_id)
        
        if not scenarios:
            st.warning(f"No scenarios generated for {home} vs {away}.")
            continue

        available_scenarios = []
        filtered_out_count = 0
        for s in scenarios:
            scenario_date = datetime.datetime.strptime(s.date, '%Y-%m-%d').date()
            if scenario_date not in days:
                filtered_out_count += 1
                continue
            
            # Check team availability
            home_result = is_team_available(home, scenario_date)
            away_result = is_team_available(away, scenario_date)
            
            home_available = home_result
            home_conflict_reason = "Team conflict"
            away_available = away_result
            away_conflict_reason = "Team conflict"
            
            if isinstance(home_result, tuple) and len(home_result) == 2:
                home_available, home_conflict_reason = home_result
            if isinstance(away_result, tuple) and len(away_result) == 2:
                away_available, away_conflict_reason = away_result
            
            is_available = home_available and away_available
            
            conflict_parts = []
            if not home_available:
                conflict_parts.append(f"{home}: {home_conflict_reason}")
            if not away_available:
                conflict_parts.append(f"{away}: {away_conflict_reason}")
            
            conflict_reason = "; ".join(conflict_parts) if conflict_parts else ""
            
            s.is_available = is_available
            s.conflict_reason = conflict_reason
            
            available_scenarios.append(s)

        # Sort scenarios by date and time
        available_scenarios.sort(key=lambda s: (
            datetime.datetime.strptime(s.date, '%Y-%m-%d').date(),
            datetime.datetime.strptime(s.time, '%H:%M').time()
        ))

        st.subheader(f"{home} vs {away}")
        if not available_scenarios:
            st.info("No available scenarios.")
            continue

        day_counts_str = ", ".join([f"{day_names[i]} ({st.session_state.day_counts.get(day, 0)}/3)" for i, day in enumerate(days)])
        st.markdown(f"<div style='font-size: 0.8rem; color: #888;'>Current day assignments: {day_counts_str}</div>", unsafe_allow_html=True)

        cols = st.columns(3)
        for i, scenario in enumerate(available_scenarios):
            with cols[i % 3]:
                scenario_date = datetime.datetime.strptime(scenario.date, '%Y-%m-%d').date()
                
                # Get available and unavailable stadiums for the home team on this date and time
                available_stadiums, unavailable_stadiums = get_available_stadiums_for_team(
                    home, 
                    scenario_date, 
                    scenario.time,
                    current_match_id=match_id,
                    scenario_manager=st.session_state.scenario_manager
                )
                
                if not scenario.is_available:
                    card_color = "#ffebee"
                    border_color = "#f44336"
                else:
                    card_color = "#e8f5e9" if scenario.suitability_score > 80 else "#fff3e0" if scenario.suitability_score > 60 else "#ffebee"
                    border_color = "#4caf50" if scenario.suitability_score > 80 else "#ff9800" if scenario.suitability_score > 60 else "#f44336"
                
                day_name = datetime.datetime.strptime(scenario.date, '%Y-%m-%d').strftime('%A')
                time_context = get_scenario_time_context(scenario, available_scenarios)
                
                # Get team rankings
                home_badge = get_team_rank_badge(home)
                away_badge = get_team_rank_badge(away)
                prestige_level, prestige_desc, prestige_icon = get_match_prestige_level(home, away)
                
                # Create prestige badge if applicable
                prestige_html = ""
                if prestige_level != 'regular':
                    prestige_colors = {
                        'elite': {'bg': '#FFD700', 'text': '#000'},
                        'high': {'bg': '#4CAF50', 'text': '#FFF'},
                        'medium-high': {'bg': '#00BCD4', 'text': '#FFF'},  # Add this
                        'medium': {'bg': '#2196F3', 'text': '#FFF'},
                        'regular': {'bg': '#6c757d', 'text': '#FFF'}  # Add this
                    }
                    color = prestige_colors.get(prestige_level, {'bg': '#6c757d', 'text': '#FFF'})  # Change to .get()
                    prestige_html = f"""<div style='background: {color['bg']}; color: {color['text']}; display: inline-block; padding: 4px 10px; border-radius: 15px; font-weight: bold; font-size: 0.8em; margin: 4px 0;'>{prestige_icon} {prestige_desc}</div>"""
                
                # Get rest days for both teams
                last_match_html = ""
                if week_number > 1:
                    home_rest = get_team_rest_days(home, scenario.date)
                    away_rest = get_team_rest_days(away, scenario.date)
                    
                    if home_rest[0] is not None or away_rest[0] is not None:
                        last_match_parts = []
                        last_match_parts.append("<div style='margin-top: 8px; padding: 6px; background-color: rgba(255,255,255,0.6); border-radius: 5px; font-size: 0.85em;'>")
                        last_match_parts.append("<div style='font-weight: bold; margin-bottom: 3px;'>📋 Rest Days:</div>")
                        
                        if home_rest[0] is not None:
                            rest_days, last_date, match_type = home_rest
                            match_icon = "🏆" if match_type == 'league' else "✈️"
                            rest_color = "#28a745" if rest_days >= 3 else "#ffc107" if rest_days >= 2 else "#dc3545"
                            last_match_parts.append(f"<div><b>{home}</b>: {match_icon} {last_date.strftime('%Y-%m-%d')} | <span style='color: {rest_color}; font-weight: bold;'>⏱️ {rest_days}d</span></div>")
                        else:
                            last_match_parts.append(f"<div><b>{home}</b>: No previous match</div>")
                        
                        if away_rest[0] is not None:
                            rest_days, last_date, match_type = away_rest
                            match_icon = "🏆" if match_type == 'league' else "✈️"
                            rest_color = "#28a745" if rest_days >= 3 else "#ffc107" if rest_days >= 2 else "#dc3545"
                            last_match_parts.append(f"<div><b>{away}</b>: {match_icon} {last_date.strftime('%Y-%m-%d')} | <span style='color: {rest_color}; font-weight: bold;'>⏱️ {rest_days}d</span></div>")
                        else:
                            last_match_parts.append(f"<div><b>{away}</b>: No previous match</div>")
                        
                        last_match_parts.append("</div>")
                        last_match_html = ''.join(last_match_parts)
                
                # Build the availability section HTML
                availability_section = ""
                if not scenario.is_available:
                    # Escape any HTML characters in conflict_reason
                    import html
                    escaped_reason = html.escape(scenario.conflict_reason)
                    availability_section = f'<div style="color: #d32f2f; font-weight: bold; margin-top: 8px;">⚠️ Unavailable: {escaped_reason}</div>'
        
                
                # Display scenario card with team ranks in squares side by side
                card_parts = []
                card_parts.append(f'<div style="background-color: {card_color}; border-radius: 10px; padding: 15px; margin: 10px 0; border: 2px solid {border_color};">')
                
                # Add team ranks in squares beside each other
                home_rank_inline = get_team_rank_badge(home) if home_badge else ""
                away_rank_inline = get_team_rank_badge(away) if away_badge else ""
                # Extract just the number from badges
                home_rank_num = home_rank_inline.replace("th", "").replace("st", "").replace("nd", "").replace("rd", "")
                away_rank_num = away_rank_inline.replace("th", "").replace("st", "").replace("nd", "").replace("rd", "")
                card_parts.append(f'<div style="display: flex; gap: 15px; margin-bottom: 10px; flex-wrap: wrap;">')
                card_parts.append(f'<div style="background: #2196F3; color: white; padding: 10px 20px; border-radius: 8px; font-weight: bold; font-size: 14px; white-space: nowrap;">{home} <span style="font-size: 16px; margin-left: 8px;">{home_rank_num}</span></div>')
                card_parts.append(f'<div style="background: #2196F3; color: white; padding: 10px 20px; border-radius: 8px; font-weight: bold; font-size: 14px; white-space: nowrap;">{away} <span style="font-size: 16px; margin-left: 8px;">{away_rank_num}</span></div>')
                card_parts.append(f'</div>')
                
                card_parts.append(f'<div style="font-weight: bold;">📅 {scenario.date} ({day_name}) 🕐 {scenario.time}</div>')
                
                if prestige_html:
                    card_parts.append(prestige_html)
                
                card_parts.append(f'<div>🏟️ {scenario.stadium} ({scenario.city})</div>')
                card_parts.append(f'<div style="margin-top: 5px;">{time_context}</div>')
                card_parts.append(f'<div>👥 Attendance: {scenario.attendance_percentage}%</div>')
                
                if last_match_html:
                    card_parts.append(last_match_html)
                
                if availability_section:
                    card_parts.append(availability_section)
                
                card_parts.append('</div>')
                
                card_html = ''.join(card_parts)
                st.markdown(card_html, unsafe_allow_html=True)
                
                # Display unavailable stadiums with reasons
                if unavailable_stadiums:
                    st.markdown("<div style='margin-top: 5px; margin-bottom: 10px;'>", unsafe_allow_html=True)
                    for stad, city, stadium_type, reason in unavailable_stadiums:
                        st.markdown(
                            f"""
                            <div style='background-color: #ffebee; border-left: 4px solid #d32f2f; padding: 8px; margin: 5px 0; font-size: 0.85rem;'>
                                <div style='color: #d32f2f; font-weight: bold;'>🚫 {stad} ({stadium_type})</div>
                                <div style='color: #c62828; margin-top: 2px;'>{reason}</div>
                            </div>
                            """, unsafe_allow_html=True
                        )
                    st.markdown("</div>", unsafe_allow_html=True)
                
                # Stadium dropdown menu (only show if there are multiple options)
                if available_stadiums and len(available_stadiums) >= 1:
                    # Create options list with all stadiums (selectable and booked)
                    stadium_options = []
                    stadium_data = []  # Store (stadium, city, is_selectable) for validation
                    
                    for stad, city, stadium_type, is_selectable in available_stadiums:
                        if is_selectable:
                            stadium_options.append(f"{stad} ({stadium_type})")
                        else:
                            stadium_options.append(f"🔒 {stad} ({stadium_type}) - Already Booked")
                        stadium_data.append((stad, city, is_selectable))
                    
                    if len(stadium_options) > 1:
                        # Find current stadium index
                        current_index = 0
                        for idx, (stad, city, is_selectable) in enumerate(stadium_data):
                            if stad == scenario.stadium:
                                current_index = idx
                                break
                        
                        # Count booked stadiums
                        booked_count = sum(1 for _, _, sel in stadium_data if not sel)
                        if booked_count > 0:
                            st.markdown(
                                f"<div style='background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 8px; margin: 5px 0; font-size: 0.85rem;'>"
                                f"<span style='color: #856404;'>⚠️ {booked_count} stadium(s) already booked at {scenario.time}</span>"
                                f"</div>",
                                unsafe_allow_html=True
                            )
                        
                        # Create a unique key for storing the selected stadium in session state
                        stadium_session_key = f"selected_stadium_{scenario.scenario_id}_{week_number}_{match_id}"
                        
                        selected_stadium_option = st.selectbox(
                            "Select Stadium:",
                            options=stadium_options,
                            index=current_index,
                            key=f"stadium_select_{scenario.scenario_id}_{week_number}_{match_id}",
                            help="Stadiums with 🔒 are already booked for another match at this time."
                        )
                        
                        # Validate and update stadium selection
                        selected_index = stadium_options.index(selected_stadium_option)
                        new_stadium, new_city, is_selectable = stadium_data[selected_index]
                        
                        # Store the selected stadium and its selectability in session state
                        if stadium_session_key not in st.session_state:
                            st.session_state[stadium_session_key] = {}
                        st.session_state[stadium_session_key]['stadium'] = new_stadium
                        st.session_state[stadium_session_key]['city'] = new_city
                        st.session_state[stadium_session_key]['is_selectable'] = is_selectable
                        
                        # Check if user tried to select a booked stadium
                        if not is_selectable and new_stadium != scenario.stadium:
                            st.error(f"❌ Cannot select {new_stadium} - it's already booked at {scenario.time}")
                            # Keep the current stadium unchanged
                        elif new_stadium != scenario.stadium and is_selectable:
                            # Valid selection, update the scenario
                            scenario.stadium = new_stadium
                            scenario.city = new_city
                
                # Select button
                if scenario.is_available:
                    if st.button(f"Select", key=f"select_{scenario.scenario_id}_{week_number}_{match_id}"):
                        current_date = datetime.datetime.strptime(scenario.date, '%Y-%m-%d').date()
                        if st.session_state.day_counts.get(current_date, 0) >= 3:
                            st.error(f"Cannot select: {current_date} is full (3 matches).")
                        else:
                            st.session_state.day_counts[current_date] = st.session_state.day_counts.get(current_date, 0) + 1
                            st.session_state.scenario_manager.select_scenario(match_id, scenario.scenario_id)
                            
                            # Store match details
                            st.session_state.selected_match_id = match_id
                            st.session_state.match_teams = [home, away]
                            st.session_state.match_date = scenario.date
                            st.session_state.match_time = scenario.time
                            st.session_state.match_stadium = scenario.stadium
                            st.session_state.match_city = scenario.city
                            
                            # Update schedule_df
                            if 'schedule_df' in st.session_state:
                                new_match = pd.DataFrame([{
                                    'match_id': match_id, 'home_team': home, 'away_team': away,
                                    'date': scenario.date, 'time': scenario.time,
                                    'city': scenario.city, 'stadium': scenario.stadium,
                                    'suitability_score': scenario.suitability_score,
                                    'attendance_percentage': scenario.attendance_percentage,
                                    'profit': scenario.profit, 'week': week_number,
                                    'is_selected': True
                                }])
                                
                                if 'match_id' in st.session_state.schedule_df.columns:
                                    st.session_state.schedule_df = st.session_state.schedule_df[
                                        st.session_state.schedule_df['match_id'] != match_id
                                    ]
                                st.session_state.schedule_df = pd.concat([st.session_state.schedule_df, new_match], ignore_index=True)
                            
                            st.success(f"Selected {scenario.date} {scenario.time} for {home} vs {away}.")
                            
                            # DO NOT permanently remove scenarios from scenario_manager
                            # The display logic will filter them based on availability
                            
                            st.rerun()
                else:
                    st.button(f"Select", key=f"select_{scenario.scenario_id}_{week_number}_{match_id}", disabled=True)

    if selected_count == len(pairings):
        st.success(f"All {len(pairings)} matches selected for week {week_number}!")
        
def get_teams_for_match(match_id):
    """
    Helper function to get team names for a given match_id.
    You'll need to implement this based on your data structure.
    
    Args:
        match_id: The match identifier
    
    Returns:
        tuple: (home_team, away_team) or None if not found
    """
    # Implementation depends on how you store match information
    # This is just an example structure
    if hasattr(st.session_state, 'week_match_ids'):
        for week, matches in st.session_state.week_match_ids.items():
            for (home, away), m_id in matches.items():
                if m_id == match_id:
                    return (home, away)
    return None


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
    """
    Generates up to 9 match scenarios per match for weeks 7 to 34, using three time slots per day (16:00, Maghrib - 51 min, Isha - 44 min, with 21:00 mandatory),
    incorporating Asr, Maghrib, and Isha prayer times, ensuring matches avoid prayer times or place prayers during halftime.
    """
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
        7: datetime.date(2025, 10, 30), 8: datetime.date(2025, 11, 6), 9: datetime.date(2025, 11, 21),
        10: datetime.date(2025, 12, 19), 11: datetime.date(2025, 12, 25), 12: datetime.date(2025, 12, 29),
        13: datetime.date(2026, 1, 2), 14: datetime.date(2026, 1, 8), 15: datetime.date(2026, 1, 12),
        16: datetime.date(2026, 1, 16), 17: datetime.date(2026, 1, 20), 18: datetime.date(2026, 1, 24),
        19: datetime.date(2026, 1, 28), 20: datetime.date(2026, 2, 1), 21: datetime.date(2026, 2, 5),
        22: datetime.date(2026, 2, 12), 23: datetime.date(2026, 2, 19), 24: datetime.date(2026, 2, 26),
        25: datetime.date(2026, 3, 5), 26: datetime.date(2026, 3, 12), 27: datetime.date(2026, 4, 3),
        28: datetime.date(2026, 4, 9), 29: datetime.date(2026, 4, 23), 30: datetime.date(2026, 4, 28),
        31: datetime.date(2026, 5, 2), 32: datetime.date(2026, 5, 7), 33: datetime.date(2026, 5, 13),
        34: datetime.date(2026, 5, 21)
    }

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

                calculated = calculate_match_times_for_city_and_date(actual_city, day, teams_data_normalized)
                match_slots = calculated.get('match_slots', ['16:00', '17:18','20:30', '21:00'])
                asr_time_str = calculated.get('asr_time', '15:30' if actual_city == 'Jeddah' else '15:33')
                maghrib_time_str = calculated.get('maghrib_time', '17:45' if actual_city == 'Jeddah' else '17:48')
                isha_time_str = calculated.get('isha_time', '19:15' if actual_city == 'Jeddah' else '19:18')

                # Check team availability for this specific day
                home_availability = is_team_available(home_team, day)
                away_availability = is_team_available(away_team, day)
                
                # Handle tuple returns from is_team_available
                home_available = home_availability
                home_conflict_reason = "Team conflict"
                away_available = away_availability  
                away_conflict_reason = "Team conflict"
                
                if isinstance(home_availability, tuple) and len(home_availability) == 2:
                    home_available, home_conflict_reason = home_availability
                if isinstance(away_availability, tuple) and len(away_availability) == 2:
                    away_available, away_conflict_reason = away_availability
                
                is_available = home_available and away_available
                
                # Create conflict reason string
                conflict_parts = []
                if not home_available:
                    conflict_parts.append(f"{home_team}: {home_conflict_reason}")
                if not away_available:
                    conflict_parts.append(f"{away_team}: {away_conflict_reason}")
                conflict_reason = "; ".join(conflict_parts) if conflict_parts else ""

                slots_for_day = [s for s in match_slots if s not in used_slots_per_day[day]]

                for slot_time in slots_for_day:
                    if match_scenarios_total >= 12:
                        break
                    try:
                        slot_hour, slot_minute = map(int, slot_time.split(":"))
                        slot_datetime = datetime.datetime(day.year, day.month, day.day, slot_hour, slot_minute)
                    except ValueError:
                        st.error(f"Invalid time format for slot {slot_time}. Skipping.")
                        continue

                    prayer_key = 'None'
                    prayer_time_str = 'N/A'
                    slot_minutes = time_string_to_minutes(slot_time)
                    maghrib_slot = time_string_to_minutes(maghrib_time_str) - 51
                    isha_slot = time_string_to_minutes(isha_time_str) - 44
                    if slot_time == '21:00' or abs(slot_minutes - isha_slot) < 5:
                        prayer_key = 'Isha'
                        prayer_time_str = isha_time_str
                    elif abs(slot_minutes - maghrib_slot) < 5:
                        prayer_key = 'Maghrib'
                        prayer_time_str = maghrib_time_str
                    elif slot_time == '16:00':
                        prayer_key = 'None'
                        prayer_time_str = 'N/A'

                    scenario = MatchScenario(
                        scenario_id=scenario_id_counter,
                        match_id=match_id,
                        home_team=home_team,
                        away_team=away_team,
                        date=day.strftime('%Y-%m-%d'),
                        time=slot_time,
                        city=actual_city,
                        stadium=actual_stadium,
                        suitability_score=100 if is_available else 0,
                        attendance_percentage=random.randint(40, 95) if is_available else 0,
                        profit=random.randint(3000, 10000) if is_available else 0,
                        is_available=is_available
                    )
                    
                    # Add conflict reason to scenario object
                    scenario.conflict_reason = conflict_reason
                    
                    scenarios_for_match.append(scenario)
                    scenario_id_counter += 1
                    match_scenarios_total += 1
                    used_slots_per_day[day].add(slot_time)
                    
                    # Only count available scenarios toward day limits
                    if is_available:
                        day_name = day.strftime('%A')
                        st.session_state.day_counts[day_name][day] += 1
                    
                    st.write(f"Scenario {match_scenarios_total} for {home_team} vs {away_team}: {day} {slot_time} ({prayer_key} at {prayer_time_str}, {'Available' if is_available else 'Unavailable'})")

                # Generate additional scenarios for extra days if needed
                if match_scenarios_total < 9:
                    extra_days = [d for d in available_days if d != day and st.session_state.day_counts.get(d.strftime('%A'), {}).get(d, 0) < 3]
                    for extra_day in extra_days:
                        if match_scenarios_total >= 12:
                            break
                        extra_day_of_week = extra_day.strftime('%A')
                        extra_calculated = calculate_match_times_for_city_and_date(actual_city, extra_day, teams_data_normalized)
                        extra_slots = extra_calculated.get('match_slots', ['16:00', '17:18','20:30', '21:00'])
                        extra_asr_time = extra_calculated.get('asr_time', '15:30' if actual_city == 'Jeddah' else '15:33')
                        extra_maghrib_time = extra_calculated.get('maghrib_time', '17:45' if actual_city == 'Jeddah' else '17:48')
                        extra_isha_time = extra_calculated.get('isha_time', '19:15' if actual_city == 'Jeddah' else '19:18')

                        # Check team availability for extra day
                        extra_home_availability = is_team_available(home_team, extra_day)
                        extra_away_availability = is_team_available(away_team, extra_day)
                        
                        # Handle tuple returns
                        extra_home_available = extra_home_availability
                        extra_home_conflict_reason = "Team conflict"
                        extra_away_available = extra_away_availability
                        extra_away_conflict_reason = "Team conflict"
                        
                        if isinstance(extra_home_availability, tuple) and len(extra_home_availability) == 2:
                            extra_home_available, extra_home_conflict_reason = extra_home_availability
                        if isinstance(extra_away_availability, tuple) and len(extra_away_availability) == 2:
                            extra_away_available, extra_away_conflict_reason = extra_away_availability
                        
                        is_available_extra = extra_home_available and extra_away_available
                        
                        # Create conflict reason for extra day
                        extra_conflict_parts = []
                        if not extra_home_available:
                            extra_conflict_parts.append(f"{home_team}: {extra_home_conflict_reason}")
                        if not extra_away_available:
                            extra_conflict_parts.append(f"{away_team}: {extra_away_conflict_reason}")
                        extra_conflict_reason = "; ".join(extra_conflict_parts) if extra_conflict_parts else ""

                        for extra_slot in [s for s in extra_slots if s not in used_slots_per_day.get(extra_day, set())]:
                            if match_scenarios_total >= 12:
                                break
                            try:
                                slot_hour, slot_minute = map(int, extra_slot.split(":"))
                                slot_datetime = datetime.datetime(extra_day.year, extra_day.month, extra_day.day, slot_hour, slot_minute)
                            except ValueError:
                                st.error(f"Invalid time format for slot {extra_slot}. Skipping.")
                                continue

                            prayer_key = 'None'
                            prayer_time_str = 'N/A'
                            slot_minutes = time_string_to_minutes(extra_slot)
                            extra_maghrib_slot = time_string_to_minutes(extra_maghrib_time) - 51
                            extra_isha_slot = time_string_to_minutes(extra_isha_time) - 44
                            if extra_slot == '21:00' or abs(slot_minutes - extra_isha_slot) < 5:
                                prayer_key = 'Isha'
                                prayer_time_str = extra_isha_time
                            elif abs(slot_minutes - extra_maghrib_slot) < 5:
                                prayer_key = 'Maghrib'
                                prayer_time_str = extra_maghrib_time
                            elif extra_slot == '16:00':
                                prayer_key = 'None'
                                prayer_time_str = 'N/A'

                            scenario = MatchScenario(
                                scenario_id=scenario_id_counter,
                                match_id=match_id,
                                home_team=home_team,
                                away_team=away_team,
                                date=extra_day.strftime('%Y-%m-%d'),
                                time=extra_slot,
                                city=actual_city,
                                stadium=actual_stadium,
                                suitability_score=100 if is_available_extra else 0,
                                attendance_percentage=random.randint(40, 95) if is_available_extra else 0,
                                profit=random.randint(3000, 10000) if is_available_extra else 0,
                                is_available=is_available_extra
                            )
                            
                            # Add conflict reason to extra scenario
                            scenario.conflict_reason = extra_conflict_reason
                            
                            scenarios_for_match.append(scenario)
                            scenario_id_counter += 1
                            match_scenarios_total += 1
                            used_slots_per_day.setdefault(extra_day, set()).add(extra_slot)
                            
                            # Only count available scenarios toward day limits
                            if is_available_extra:
                                day_name = extra_day.strftime('%A')
                                st.session_state.day_counts[day_name][extra_day] += 1
                                
                            st.write(f"Extra scenario {match_scenarios_total} for {home_team} vs {away_team}: {extra_day} {extra_slot} ({prayer_key} at {prayer_time_str}, {'Available' if is_available_extra else 'Unavailable'})")

            scenarios_for_match = scenarios_for_match[:12]
            
            # Sort scenarios by date and time before storing
            scenarios_for_match.sort(key=lambda s: (
                datetime.datetime.strptime(s.date, '%Y-%m-%d').date(),
                datetime.datetime.strptime(s.time, '%H:%M').time()
            ))
            
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
    {"event": "FIFA Int'l Window (Men's)", "start_date": "2025-06-02", "end_date": "2025-06-10", "category": "FIFA International Window"},
    {"event": "AQ 9", "start_date": "2025-06-09", "end_date": "2025-06-09", "category": "Asian Cup Qualifiers"},
    {"event": "AQ 10", "start_date": "2025-06-10", "end_date": "2025-06-10", "category": "Asian Cup Qualifiers"},
    {"event": "ACQ FR2", "start_date": "2025-06-12", "end_date": "2025-06-12", "category": "Asian Cup Qualifiers"},
    {"event": "FIFA Club World Cup 2025", "start_date": "2025-06-15", "end_date": "2025-07-13", "category": "FIFA Event"},
    {"event": "FIFA Int'l Window (Women's)", "start_date": "2025-06-16", "end_date": "2025-06-24", "category": "FIFA International Window"},
    {"event": "Women's Asian Cup 2026 Qualifiers", "start_date": "2025-06-23", "end_date": "2025-07-01", "category": "Qualifiers"},
    {"event": "PS1", "start_date": "2025-07-29", "end_date": "2025-07-29", "category": "ACL Two"},
    {"event": "PS1", "start_date": "2025-07-30", "end_date": "2025-07-30", "category": "ACL Two"},
    {"event": "PS2", "start_date": "2025-08-05", "end_date": "2025-08-05", "category": "ACL Two"},
    {"event": "PS2", "start_date": "2025-08-06", "end_date": "2025-08-06", "category": "ACL Two"},
    {"event": "PS3", "start_date": "2025-08-12", "end_date": "2025-08-12", "category": "ACL Two"},
    {"event": "PS3", "start_date": "2025-08-13", "end_date": "2025-08-13", "category": "ACL Two"},
    {"event": "U23 Asian Cup 2026 Qualifiers", "start_date": "2025-08-18", "end_date": "2025-08-26", "category": "Qualifiers"},
    {"event": "AWCL - Prelim Stage", "start_date": "2025-08-25", "end_date": "2025-08-31", "category": "AWCL"},
    {"event": "FIFA Int'l Window (Men's)", "start_date": "2025-09-01", "end_date": "2025-09-09", "category": "FIFA International Window"},
    {"event": "Futsal Asian Cup 2026 Qualifiers", "start_date": "2025-09-15", "end_date": "2025-09-26", "category": "Qualifiers"},
    {"event": "MD1 (W)", "start_date": "2025-09-16", "end_date": "2025-09-16", "category": "ACL Elite"},
    {"event": "MD1", "start_date": "2025-09-16", "end_date": "2025-09-17", "category": "ACGL"},
    {"event": "MD1 (E)", "start_date": "2025-09-17", "end_date": "2025-09-17", "category": "ACL Elite"},
    {"event": "MD1", "start_date": "2025-09-17", "end_date": "2025-09-18", "category": "ACL Two"},
    {"event": "MD2 (W)", "start_date": "2025-09-30", "end_date": "2025-09-30", "category": "ACL Elite"},
    {"event": "MD2", "start_date": "2025-09-30", "end_date": "2025-10-01", "category": "ACGL"},
    {"event": "MD2 (E)", "start_date": "2025-10-01", "end_date": "2025-10-01", "category": "ACL Elite"},
    {"event": "MD2", "start_date": "2025-10-01", "end_date": "2025-10-02", "category": "ACL Two"},
    {"event": "AWCL - Group Stage", "start_date": "2025-10-06", "end_date": "2025-10-12", "category": "AWCL"},
    {"event": "FIFA Int'l Window (Men's)", "start_date": "2025-10-06", "end_date": "2025-10-14", "category": "FIFA International Window"},
    {"event": "FIFA Int'l Window (Women's)", "start_date": "2025-10-20", "end_date": "2025-10-28", "category": "FIFA International Window"},
    {"event": "MD3 (W)", "start_date": "2025-10-21", "end_date": "2025-10-21", "category": "ACL Elite"},
    {"event": "MD3", "start_date": "2025-10-21", "end_date": "2025-10-22", "category": "ACGL"},
    {"event": "MD3 (E)", "start_date": "2025-10-22", "end_date": "2025-10-22", "category": "ACL Elite"},
    {"event": "MD3", "start_date": "2025-10-22", "end_date": "2025-10-23", "category": "ACL Two"},
    {"event": "MD4 (W)", "start_date": "2025-11-04", "end_date": "2025-11-04", "category": "ACL Elite"},
    {"event": "MD4", "start_date": "2025-11-04", "end_date": "2025-11-05", "category": "ACGL"},
    {"event": "MD4 (E)", "start_date": "2025-11-05", "end_date": "2025-11-05", "category": "ACL Elite"},
    {"event": "MD4", "start_date": "2025-11-05", "end_date": "2025-11-06", "category": "ACL Two"},
    {"event": "FIFA Int'l Window (Men's)", "start_date": "2025-11-10", "end_date": "2025-11-18", "category": "FIFA International Window"},
    {"event": "U17 Women's Asian Cup 2026 Qualifiers R1", "start_date": "2025-11-17", "end_date": "2025-11-25", "category": "Qualifiers"},
    {"event": "FIFA Int'l Window (Women's)", "start_date": "2025-11-24", "end_date": "2025-12-02", "category": "FIFA International Window"},
    {"event": "U20 Women's Asian Cup 2026 Qualifiers R1", "start_date": "2025-12-01", "end_date": "2025-12-09", "category": "Qualifiers"},
    {"event": "MD5", "start_date": "2025-12-02", "end_date": "2025-12-03", "category": "ACGL"},
    {"event": "MD5", "start_date": "2025-12-03", "end_date": "2025-12-04", "category": "ACL Two"},
    {"event": "AFC U20 Asian Cup 2026", "start_date": "2026-01-31", "end_date": "2026-02-18", "category": "AFC Competition"},
    {"event": "FIFA Int'l Window (Women's)", "start_date": "2026-02-16", "end_date": "2026-02-24", "category": "FIFA International Window"},
    {"event": "MD5 (W)", "start_date": "2026-02-17", "end_date": "2026-02-17", "category": "ACL Elite"},
    {"event": "MD6", "start_date": "2026-02-17", "end_date": "2026-02-18", "category": "ACGL"},
    {"event": "MD5 (E)", "start_date": "2026-02-18", "end_date": "2026-02-18", "category": "ACL Elite"},
    {"event": "MD6", "start_date": "2026-02-18", "end_date": "2026-02-19", "category": "ACL Two"},
    {"event": "AWCL - QF (1st Leg)", "start_date": "2026-02-21", "end_date": "2026-02-22", "category": "AWCL"},
    {"event": "R16 (1st Leg) (W)", "start_date": "2026-02-24", "end_date": "2026-02-24", "category": "ACL Elite"},
    {"event": "R16 (1st Leg) (E)", "start_date": "2026-02-25", "end_date": "2026-02-25", "category": "ACL Elite"},
    {"event": "R16 (2nd Leg) (W)", "start_date": "2026-03-03", "end_date": "2026-03-03", "category": "ACL Elite"},
    {"event": "ZSF (1st Leg)", "start_date": "2026-03-03", "end_date": "2026-03-04", "category": "ACGL"},
    {"event": "R16 (2nd Leg) (E)", "start_date": "2026-03-04", "end_date": "2026-03-04", "category": "ACL Elite"},
    {"event": "R16 (1st Leg)", "start_date": "2026-03-04", "end_date": "2026-03-05", "category": "ACL Two"},
    {"event": "AWCL - QF (2nd Leg)", "start_date": "2026-03-07", "end_date": "2026-03-08", "category": "AWCL"},
    {"event": "ZSF (2nd Leg)", "start_date": "2026-03-10", "end_date": "2026-03-11", "category": "ACGL"},
    {"event": "R16 (2nd Leg)", "start_date": "2026-03-11", "end_date": "2026-03-12", "category": "ACL Two"},
    {"event": "FIFA Int'l Window (Men's)", "start_date": "2026-03-23", "end_date": "2026-03-31", "category": "FIFA International Window"},
    {"event": "AQ 11", "start_date": "2026-03-26", "end_date": "2026-03-26", "category": "Asian Cup Qualifiers"},
    {"event": "AQ 12", "start_date": "2026-03-31", "end_date": "2026-03-31", "category": "Asian Cup Qualifiers"},
    {"event": "AFC Futsal Asian Cup 2026", "start_date": "2026-04-01", "end_date": "2026-04-12", "category": "AFC Competition"},
    {"event": "QF (1st Leg)", "start_date": "2026-04-01", "end_date": "2026-04-02", "category": "ACL Two"},
    {"event": "FIFA Int'l Window (Women's)", "start_date": "2026-04-06", "end_date": "2026-04-14", "category": "FIFA International Window"},
    {"event": "QF (2nd Leg)", "start_date": "2026-04-08", "end_date": "2026-04-09", "category": "ACL Two"},
    {"event": "AWCL - SF (1st Leg)", "start_date": "2026-04-11", "end_date": "2026-04-12", "category": "AWCL"},
    {"event": "AFC U17 Asian Cup 2026", "start_date": "2026-04-16", "end_date": "2026-05-03", "category": "AFC Competition"},
    {"event": "AWCL - SF (2nd Leg)", "start_date": "2026-04-18", "end_date": "2026-04-19", "category": "AWCL"},
    {"event": "U17 Women's Asian Cup 2026 Qualifiers R2", "start_date": "2026-04-20", "end_date": "2026-04-28", "category": "Qualifiers"},
    {"event": "Finals (1st Leg)", "start_date": "2026-04-26", "end_date": "2026-04-26", "category": "ACL Elite"},
    {"event": "Final", "start_date": "2026-04-27", "end_date": "2026-04-27", "category": "ACGL"},
    {"event": "SF (1st Leg)", "start_date": "2026-04-29", "end_date": "2026-04-30", "category": "ACL Two"},
    {"event": "Finals (2nd Leg)", "start_date": "2026-05-03", "end_date": "2026-05-03", "category": "ACL Elite"},
    {"event": "SF (2nd Leg)", "start_date": "2026-05-06", "end_date": "2026-05-07", "category": "ACL Two"},
    {"event": "AWCL - Final", "start_date": "2026-05-10", "end_date": "2026-05-10", "category": "AWCL"},
    {"event": "Final", "start_date": "2026-05-17", "end_date": "2026-05-17", "category": "ACL Two"},
    {"event": "FIFA Int'l Window (Women's)", "start_date": "2026-05-25", "end_date": "2026-06-02", "category": "FIFA International Window"},
    {"event": "AQ 13", "start_date": "2026-06-04", "end_date": "2026-06-04", "category": "Asian Cup Qualifiers"},
    {"event": "AQ 14", "start_date": "2026-06-09", "end_date": "2026-06-09", "category": "Asian Cup Qualifiers"},
    {"event": "FIFA World Cup 2026", "start_date": "2026-06-11", "end_date": "2026-07-19", "category": "FIFA Event"},
    {"event": "U20 Women's Asian Cup 2026 Qualifiers R2", "start_date": "2026-06-15", "end_date": "2026-06-23", "category": "Qualifiers"}
]
    
    if 'afc_events' not in st.session_state:
        st.session_state.afc_events = afc_events_from_image
    
    afc_df = pd.DataFrame(afc_events_from_image)
    afc_df['start_date'] = pd.to_datetime(afc_df['start_date'])
    afc_df['end_date'] = pd.to_datetime(afc_df['end_date'])

    # Initialize all_events with AFC events - EXPAND MULTI-DAY EVENTS
    all_events = []
    
    for _, row in afc_df.iterrows():
        start_date = row['start_date'].date()
        end_date = row['end_date'].date()
        
        # Create an event for each day in the range
        current_date = start_date
        while current_date <= end_date:
            # Add day indicator for multi-day events
            if start_date == end_date:
                # Single day event
                event_name = row['event']
            else:
                # Multi-day event - add day indicator
                total_days = (end_date - start_date).days + 1
                current_day = (current_date - start_date).days + 1
                event_name = f"{row['event']} (Day {current_day}/{total_days})"
            
            all_events.append({
                'event': event_name,
                'start_date': pd.Timestamp(current_date),
                'end_date': pd.Timestamp(current_date),
                'category': row['category'],
                'original_event': row['event'],  # Keep original name for reference
                'is_multi_day': start_date != end_date,
                'day_number': (current_date - start_date).days + 1 if start_date != end_date else None
            })
            
            current_date += datetime.timedelta(days=1)

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
                'week': week_number,  # Store the actual week number
                'is_multi_day': False
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
    
    # Show multi-day events info
    multi_day_events = events_df[events_df.get('is_multi_day', False) == True]
    if len(multi_day_events) > 0:
        unique_multi_day = multi_day_events['original_event'].nunique() if 'original_event' in multi_day_events.columns else 0
        st.write(f"Multi-day events expanded: {unique_multi_day} events across {len(multi_day_events)} days")

    # CSS for calendar
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

    # JavaScript for navigation
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

    # Generate the main calendar
    calendar_html = '<div class="afc-calendar-wrapper">'

    start_date = datetime.date(2025, 6, 1)  # Start from June to show all AFC events
    end_date = datetime.date(2026, 6, 30)
    current_year = start_date.year
    
    while current_year <= end_date.year:
        calendar_html += f'<div class="year-section">'
        calendar_html += f'<div class="year-header">{current_year}</div>'
        
        start_month = 6 if current_year == 2025 else 1
        end_month = 6 if current_year == 2026 else 12
        
        for month_num in range(start_month, end_month + 1):
            month_name = calendar.month_name[month_num]
            days_in_month = calendar.monthrange(current_year, month_num)[1]
            
            # Filter events for this month
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
                
                # Get events for this specific day
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
                        # AFC events - now includes multi-day events properly
                        color = event_color_map.get(event['category'], '#6c757d')
                        event_name = event['event']
                        original_name = event.get('original_event', event_name)
                        
                        # Truncate event name for display
                        display_name = event_name[:35] + '...' if len(event_name) > 35 else event_name
                        
                        calendar_html += f'''<div class="event-indicator afc-event" 
                                        style="background-color: {color}; max-height: 30px; overflow: hidden; display: flex; align-items: center;"
                                        title="📅 {original_name} ({event['category']})">
                                        <span style="font-size: 10px; white-space: nowrap;">
                                        {display_name}
                                        </span>
                                        </div>'''
                
                calendar_html += '</div>'
            
            calendar_html += '</div></div>'
        
        calendar_html += '</div>'
        current_year += 1

    calendar_html += '</div>'
    st.markdown(calendar_html, unsafe_allow_html=True)

    # Navigation handling
    if st.session_state.get('navigate_to_tab1', False):
        st.session_state.selected_week = st.session_state.get('selected_week', 1)
        match_teams = st.session_state.get('match_teams', [])
        st.success(f"Navigating to Tab 1 for week {st.session_state.selected_week}")
        if match_teams:
            st.info(f"🏆 Teams: {' vs '.join(match_teams)}")
        st.session_state.navigate_to_tab1 = False
        st.rerun()

    # Show selected matches summary
    if len(selected_matches) > 0:
        st.subheader("Selected Matches Summary")
        for _, match in selected_matches.iterrows():
            match_date = pd.to_datetime(match['start_date']).date()
            week_num = match.get('week', 'Unknown')
            st.write(f"✅ {match['event']} on {match_date} at {match.get('time', 'TBD')} (Week {week_num})")

    # Analytics
    if not events_df.empty:
        # For analytics, use original events to avoid counting multi-day events multiple times
        analytics_events = []
        for _, event in events_df.iterrows():
            if event.get('is_multi_day', False) and event.get('day_number', 1) > 1:
                continue  # Skip duplicate days for multi-day events in analytics
            analytics_events.append({
                'Month': event['start_date'].strftime('%B'),
                'Category': event['category'],
                'Event': event.get('original_event', event['event'])
            })
        
        if analytics_events:
            analytics_df = pd.DataFrame(analytics_events)
            
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

def export_week_schedule(week_number, scenario_manager, week_match_ids):
    """Export schedule for a specific week with prayer times"""
    selected_scenarios = scenario_manager.selected_scenarios
    
    if not selected_scenarios:
        return None
    
    # Get match IDs for the specified week
    week_matches = week_match_ids.get(week_number, {})
    
    # Collect match data for this week
    matches_data = []
    for match_id, scenario_id in selected_scenarios.items():
        if match_id in week_matches.values():
            scenarios = scenario_manager.get_scenarios_for_match(match_id)
            for scenario in scenarios:
                if scenario.scenario_id == scenario_id:
                    # Get prayer times for this match's city and date
                    match_date = datetime.datetime.strptime(scenario.date, '%Y-%m-%d').date()
                    prayer_times = get_prayer_times_unified(scenario.city, match_date, prayer='all')
                    
                    # Extract Maghrib and Isha times
                    maghrib_time = prayer_times.get('timings', {}).get('maghrib', 'N/A')
                    isha_time = prayer_times.get('timings', {}).get('isha', 'N/A')
                    
                    matches_data.append({
                        'Week': week_number,
                        'Home Team': scenario.home_team,
                        'Away Team': scenario.away_team,
                        'Maghrib Prayer': maghrib_time,
                        'Isha Prayer': isha_time,
                        'Date': scenario.date,
                        'Day': datetime.datetime.strptime(scenario.date, '%Y-%m-%d').strftime('%A'),
                        'Time': scenario.time,
                        'Stadium': scenario.stadium,
                        'City': scenario.city,

                    })
                    break
    
    if not matches_data:
        return None
    
    # Create DataFrame and sort by date and time
    df = pd.DataFrame(matches_data)
    df = df.sort_values(['Date', 'Time'])
    
    return df


def export_all_scheduled_weeks(scenario_manager, week_match_ids):
    """Export schedule for all weeks with prayer times"""
    selected_scenarios = scenario_manager.selected_scenarios
    
    if not selected_scenarios:
        return None
    
    # Collect match data for all weeks
    matches_data = []
    
    for match_id, scenario_id in selected_scenarios.items():
        # Find which week this match belongs to
        week_number = None
        for week, match_ids in week_match_ids.items():
            if match_id in match_ids.values():
                week_number = week
                break
        
        if week_number is not None:
            scenarios = scenario_manager.get_scenarios_for_match(match_id)
            for scenario in scenarios:
                if scenario.scenario_id == scenario_id:
                    # Get prayer times for this match's city and date
                    match_date = datetime.datetime.strptime(scenario.date, '%Y-%m-%d').date()
                    prayer_times = get_prayer_times_unified(scenario.city, match_date, prayer='all')
                    
                    # Extract Maghrib and Isha times
                    maghrib_time = prayer_times.get('timings', {}).get('maghrib', 'N/A')
                    isha_time = prayer_times.get('timings', {}).get('isha', 'N/A')
                    
                    matches_data.append({
                        'Week': week_number,
                        'Home Team': scenario.home_team,
                        'Away Team': scenario.away_team,
                        'Maghrib Prayer': maghrib_time,
                        'Isha Prayer': isha_time,
                        'Date': scenario.date,
                        'Day': datetime.datetime.strptime(scenario.date, '%Y-%m-%d').strftime('%A'),
                        'Time': scenario.time,
                        'Stadium': scenario.stadium,
                        'City': scenario.city,

                    })
                    break
    
    if not matches_data:
        return None
    
    # Create DataFrame and sort by week, date, and time
    df = pd.DataFrame(matches_data)
    df = df.sort_values(['Week', 'Date', 'Time'])
    
    return df




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
        st.session_state.scenario_manager = ScenarioManager()
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
                            CONFIRMED
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
                    <div style="font-weight: bold; color: #155724; font-size: 16px;">Week {selected_week} Summary</div>
                    <div style="color: #155724; margin-top: 5px;">
                        Total confirmed matches for Week {selected_week}: {len(week_selected_matches)}<br>
                        All matches have been scheduled and confirmed<br>
                        Ready for matchday execution
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
        
        # ==================== EXPORT BUTTONS SECTION ====================
        # Add export buttons at the bottom of the page
        st.markdown("---")
        st.markdown("### Export Schedule")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Button 1: Export current week only
            if st.button(f"Download Week {st.session_state.selected_week} Schedule", key=f"export_week_{st.session_state.selected_week}_fixture", use_container_width=True):
                df_week = export_week_schedule(
                    st.session_state.selected_week,
                    st.session_state.scenario_manager,
                    st.session_state.week_match_ids
                )
                
                if df_week is not None and not df_week.empty:
                    # Create Excel file in memory
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df_week.to_excel(writer, index=False, sheet_name=f'Week {st.session_state.selected_week}')
                        
                        # Auto-adjust column widths
                        worksheet = writer.sheets[f'Week {st.session_state.selected_week}']
                        for idx, col in enumerate(df_week.columns):
                            max_length = max(
                                df_week[col].astype(str).apply(len).max(),
                                len(col)
                            ) + 2
                            worksheet.column_dimensions[chr(65 + idx)].width = max_length
                    
                    output.seek(0)
                    
                    st.download_button(
                        label=f"Download Week_{st.session_state.selected_week}_Schedule.xlsx",
                        data=output,
                        file_name=f"Week_{st.session_state.selected_week}_Schedule_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"download_week_{st.session_state.selected_week}_fixture",
                        use_container_width=True
                    )
                    st.success(f"Week {st.session_state.selected_week} schedule ready for download!")
                else:
                    st.warning(f"No matches selected for week {st.session_state.selected_week} yet.")
        
        with col2:
            # Button 2: Export all scheduled weeks
            if st.button("Download All Scheduled Weeks", key=f"export_all_from_fixture", use_container_width=True):
                df_all = export_all_scheduled_weeks(
                    st.session_state.scenario_manager,
                    st.session_state.week_match_ids
                )
                
                if df_all is not None and not df_all.empty:
                    # Create Excel file in memory
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df_all.to_excel(writer, index=False, sheet_name='All Weeks')
                        
                        # Auto-adjust column widths
                        worksheet = writer.sheets['All Weeks']
                        for idx, col in enumerate(df_all.columns):
                            max_length = max(
                                df_all[col].astype(str).apply(len).max(),
                                len(col)
                            ) + 2
                            worksheet.column_dimensions[chr(65 + idx)].width = max_length
                    
                    output.seek(0)
                    
                    total_weeks = df_all['Week'].nunique()
                    total_matches = len(df_all)
                    
                    st.download_button(
                        label=f"Download All_Weeks_Schedule.xlsx",
                        data=output,
                        file_name=f"All_Weeks_Schedule_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"download_all_fixture",
                        use_container_width=True
                    )
                    st.success(f"All schedule ready! ({total_weeks} weeks, {total_matches} matches)")
                else:
                    st.warning("No matches have been scheduled yet.")

if __name__ == "__main__":
    main()



























