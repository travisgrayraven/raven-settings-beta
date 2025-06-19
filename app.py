import streamlit as st
import requests
import json
import time

# --- Page Configuration ---
st.set_page_config(page_title="Raven Device Manager", layout="wide")

# --- Helper Functions for API Calls ---
# These functions now take parameters and return data, making them easier to manage.

def request_token(domain, key, secret):
    """Requests a new bearer token from the API."""
    url = f"{domain}/auth/token"
    payload = {'api_key': {'key': key, 'secret': secret}}
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json', 'User-Agent': 'Python/StreamlitClient'}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get('token'), None  # token, error
    except Exception as e:
        return None, f"Token Error: {e}"

def list_devices(domain, token):
    """Lists Raven devices and looks up vehicle details via NHTSA API."""
    list_url = f"{domain}/ravens"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json', 'User-Agent': 'Python/StreamlitClient'}
    NHTSA_API_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVin"
    
    try:
        response = requests.get(list_url, headers=headers, timeout=10)
        response.raise_for_status()
        devices_data = response.json().get('results', [])
        
        if not isinstance(devices_data, list):
            return None, "API response did not return a list of devices."

        device_options = []
        status_messages = []
        for device in devices_data:
            uuid = device.get('uuid', 'N/A')
            sn = device.get('enclosure_serial_no', 'N/A')
            vin = device.get('vin', '')
            vehicle_make, vehicle_model, vehicle_year = 'N/A', 'N/A', 'N/A'
            
            if vin:
                try:
                    nhtsa_url = f"{NHTSA_API_URL}/{vin}?format=json"
                    nhtsa_response = requests.get(nhtsa_url, timeout=5)
                    nhtsa_response.raise_for_status()
                    nhtsa_results = nhtsa_response.json().get('Results', [])
                    for result in nhtsa_results:
                        if result.get('Variable') == 'Make': vehicle_make = result.get('Value', 'N/A')
                        elif result.get('Variable') == 'Model': vehicle_model = result.get('Value', 'N/A')
                        elif result.get('Variable') == 'Model Year': vehicle_year = result.get('Value', 'N/A')
                except Exception as nhtsa_err:
                    status_messages.append(f"⚠️ Could not look up VIN {vin}: {nhtsa_err}")
            
            vehicle_name = f"{vehicle_year} {vehicle_make} {vehicle_model}".strip().replace("N/A", "").strip()
            if not vehicle_name:
                vehicle_name = f"Vehicle SN: {sn}"

            device_options.append({"name": vehicle_name, "uuid": uuid})
            status_messages.append(f"Found: {vehicle_name} (UUID: {uuid})")
        
        return device_options, "\n".join(status_messages)

    except Exception as e:
        return None, f"An error occurred while listing devices: {e}"

def get_settings(domain, token, uuid):
    """Gets current settings for a specific Raven."""
    url = f"{domain}/ravens/{uuid}/settings"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json(), None
    except Exception as e:
        return None, f"Get Settings Error: {e}"

def update_settings(domain, token, uuid, payload):
    """Updates settings for a specific Raven."""
    url = f"{domain}/ravens/{uuid}/settings"
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    try:
        response = requests.patch(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        return "Settings updated successfully!", None
    except Exception as e:
        error_body = ""
        if 'response' in locals() and hasattr(response, 'text'):
            error_body = response.text
        return None, f"Update Error: {e}\nResponse Body: {error_body}"
        
def send_message(domain, token, uuid, message, duration):
    """Sends a message to the driver."""
    url = f"{domain}/ravens/{uuid}/driver-message"
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    payload = {"message": message, "duration": duration}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        return "Message sent successfully!", None
    except Exception as e:
        return None, f"Send Message Error: {e}"

def clear_message(domain, token, uuid):
    """Clears the message from the driver's screen."""
    url = f"{domain}/ravens/{uuid}/driver-message"
    headers = {'Authorization': f'Bearer {token}'}
    try:
        response = requests.delete(url, headers=headers, timeout=10)
        response.raise_for_status()
        return "Clear message request sent successfully!", None
    except Exception as e:
        return None, f"Clear Message Error: {e}"


# --- Streamlit UI & State Management ---

st.title("Raven Device Settings Manager")

# Initialize session state
if 'access_token' not in st.session_state:
    st.session_state.access_token = None
if 'devices' not in st.session_state:
    st.session_state.devices = []
if 'selected_uuid' not in st.session_state:
    st.session_state.selected_uuid = None
if 'current_settings' not in st.session_state:
    st.session_state.current_settings = None
if 'status_message' not in st.session_state:
    st.session_state.status_message = ""
    

# --- SECTION 1: API Configuration and Authentication ---
with st.expander("1. API Configuration & Authentication", expanded=True):
    # Load credentials from st.secrets
    try:
        API_DOMAIN = st.secrets["api_credentials"]["domain"]
        API_KEY = st.secrets["api_credentials"]["key"]
        API_SECRET = st.secrets["api_credentials"]["secret"]
        st.info(f"Credentials loaded for domain: `{API_DOMAIN}`")
    except (KeyError, FileNotFoundError):
        st.error("FATAL: API credentials are not configured. Please follow the setup instructions to add your credentials to secrets.toml.")
        st.stop() # Halt the app if secrets are not found

    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("Request New Access Token", type="primary"):
            with st.spinner("Requesting token..."):
                token, error = request_token(API_DOMAIN, API_KEY, API_SECRET)
                if token:
                    st.session_state.access_token = token
                    st.success("Access Token received!")
                if error:
                    st.session_state.access_token = None
                    st.error(error)

    with col2:
        if st.session_state.access_token:
            st.success(f"Token is active: `{st.session_state.access_token[:15]}...`")
        else:
            st.warning("No active access token. Please request a token.")


# --- SECTION 2: Device Selection ---
st.header("2. Select Device")

if not st.session_state.access_token:
    st.warning("You must request an access token before you can select a device.")
else:
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("List Available Ravens"):
            with st.spinner("Fetching device list..."):
                devices, status = list_devices(API_DOMAIN, st.session_state.access_token)
                st.session_state.status_message = status
                if devices:
                    st.session_state.devices = devices
                else:
                    st.session_state.devices = []

    # Display status messages from the listing process
    if st.session_state.status_message:
        st.info(st.session_state.status_message)
        
    if st.session_state.devices:
        device_map = {d['name']: d['uuid'] for d in st.session_state.devices}
        selected_name = st.selectbox(
            "Select a Raven from the list:",
            options=device_map.keys(),
            index=0
        )
        st.session_state.selected_uuid = device_map[selected_name]
        st.write(f"Selected UUID: `{st.session_state.selected_uuid}`")


# --- SECTION 3: Device Settings ---
st.header("3. Manage Settings")

if not st.session_state.selected_uuid:
    st.warning("You must select a device above to manage its settings.")
else:
    # Button to fetch the latest settings for the selected device
    if st.button("Get Current Settings for Selected Raven"):
        with st.spinner("Fetching settings..."):
            settings, error = get_settings(API_DOMAIN, st.session_state.access_token, st.session_state.selected_uuid)
            if settings:
                st.session_state.current_settings = settings
                st.success("Successfully loaded current settings.")
            if error:
                st.session_state.current_settings = None
                st.error(error)
                
    # If settings have been loaded, display the UI
    if st.session_state.current_settings:
        s = st.session_state.current_settings
        
        # This is where we will build the payload for the update
        update_payload = {}
        
        # Use tabs for a cleaner layout than nested accordions
        tab_msg, tab_audio, tab_cam, tab_events, tab_obd, tab_wifi, tab_did, tab_sys, tab_eld = st.tabs([
            "Driver Messaging", "Audio", "Camera", "Events", "OBD", "WiFi Hotspot", "Driver ID", "System", "ELD"
        ])

        with tab_msg:
            st.subheader("Send a one-time message")
            msg_text = st.text_input("Message (15 char max)", key="msg_text", max_chars=15)
            msg_duration = st.number_input("Duration (seconds)", min_value=1, value=300, key="msg_duration")
            c1, c2, c3 = st.columns(3)
            if c1.button("Send Message", type="primary"):
                success, error = send_message(API_DOMAIN, st.session_state.access_token, st.session_state.selected_uuid, msg_text, msg_duration)
                if success: st.success(success)
                if error: st.error(error)
            if c2.button("Clear Last Message", type="secondary"):
                success, error = clear_message(API_DOMAIN, st.session_state.access_token, st.session_state.selected_uuid)
                if success: st.success(success)
                if error: st.error(error)

        with tab_audio:
            st.subheader("Audio Settings")
            update_payload["audio"] = {
                "audio_notifications_enabled": st.checkbox("General Audio Notifications", s.get('audio', {}).get('audio_notifications_enabled')),
                "streaming_audio_enabled": st.checkbox("Enable Audio in Live Stream", s.get('audio', {}).get('streaming_audio_enabled')),
                "message_notification_audio_enabled": st.checkbox("Message Notification Sound", s.get('audio', {}).get('message_notification_audio_enabled'))
            }

        with tab_cam:
            st.subheader("Camera Settings")
            c1, c2 = st.columns(2)
            road_cam_enabled = c1.checkbox("Road Camera Enabled", s.get('camera', {}).get('road_camera', {}).get('camera_enabled'))
            road_cam_audio = c1.checkbox("Road Camera Audio Recording", s.get('camera', {}).get('road_camera', {}).get('audio_recording'))
            cabin_cam_enabled = c2.checkbox("Cabin Camera Enabled", s.get('camera', {}).get('cabin_camera', {}).get('camera_enabled'))
            cabin_cam_audio = c2.checkbox("Cabin Camera Audio Recording", s.get('camera', {}).get('cabin_camera', {}).get('audio_recording'))
            vid_profile = st.selectbox("Video Profile", ['standard', 'legacy', 'balanced', 'extended'], index=['standard', 'legacy', 'balanced', 'extended'].index(s.get('camera', {}).get('video_recording_profile', 'standard')))
            
            update_payload["camera"] = {
                "road_camera": {"camera_enabled": road_cam_enabled, "audio_recording": road_cam_audio},
                "cabin_camera": {"camera_enabled": cabin_cam_enabled, "audio_recording": cabin_cam_audio},
                "video_recording_profile": vid_profile
            }
            
        with tab_events:
            # Recreate the nested accordion from the original using st.expander
            st.subheader("Event Settings")
            
            # This is a large dict, so we'll build it piece by piece
            events_payload = {}
            events_data = s.get('events', {})

            with st.expander("G-Force Events"):
                c1, c2 = st.columns(2)
                events_payload['harsh_braking_event_enabled'] = c1.checkbox("Harsh Braking", events_data.get('harsh_braking_event_enabled'))
                events_payload['harsh_braking_accel_threshold'] = c2.number_input("Braking Threshold", value=events_data.get('harsh_braking_accel_threshold', 0), key='hb_thresh')
                events_payload['aggressive_accel_event_enabled'] = c1.checkbox("Aggressive Accel", events_data.get('aggressive_accel_event_enabled'))
                events_payload['aggressive_accel_threshold'] = c2.number_input("Accel Threshold", value=events_data.get('aggressive_accel_threshold', 0), key='aa_thresh')
                # ... Add all other G-Force settings here in the same pattern ...
            
            with st.expander("Standard & Misc Events"):
                events_payload['idling_event_enabled'] = st.checkbox("Idling Event", events_data.get('idling_event_enabled'))
                # ... Add all other Standard settings here ...

            with st.expander("Driver Monitoring (DMS)"):
                st.write("Cellphone Detection")
                events_payload['cellphone_detection_event_enabled'] = st.checkbox("Enabled", events_data.get('cellphone_detection_event_enabled'), key='dms_cell_en')
                # ... Add all other DMS settings here ...
            
            # NOTE: For brevity, not all 200+ settings are individually mapped.
            # The pattern is established above. For a full migration, each checkbox/input
            # would need to be created like the examples.
            # A simpler, though less user-friendly way, is to show the JSON and allow editing.
            st.warning("Note: Not all 200+ event settings have been individually mapped in this demo. The key ones are shown as an example.")
            st.json(s.get('events', {}))
            
            # For the demo, we will pass the original event data back if unchanged
            # A full implementation would build this dict from dozens of widgets
            update_payload["events"] = events_data 

        with tab_obd:
            st.subheader("OBD Settings")
            obd_data = s.get('obd', {})
            update_payload["obd"] = {
                "canbus_enabled": st.checkbox("CANbus Enabled", obd_data.get('canbus_enabled')),
                "low_battery_cutoff_millivolts": st.number_input("Low Battery Cutoff (mV)", value=obd_data.get('low_battery_cutoff_millivolts', 0))
            }
        
        # ... Other tabs (WiFi, Driver ID, etc.) would follow the same pattern ...
        # For example:
        with tab_wifi:
            st.subheader("WiFi Hotspot")
            wifi_data = s.get('wifi_hotspot', {})
            update_payload["wifi_hotspot"] = {
                "hotspot_enabled": st.checkbox("Hotspot Enabled", wifi_data.get("hotspot_enabled")),
                "auto_disable_on_engine_off": st.checkbox("Auto-Disable on Engine Off", wifi_data.get("auto_disable_on_engine_off")),
                "ssid": st.text_input("SSID", wifi_data.get("ssid")),
                "password": st.text_input("Password", wifi_data.get("password"), type="password")
            }


        # --- UPDATE BUTTON ---
        st.header(" ") # Spacer
        if st.button("SAVE AND UPDATE ALL SETTINGS TO RAVEN", type="primary", use_container_width=True):
            # Because not all settings are mapped, we display a warning.
            # In a full app, you would remove this check and build the full payload.
            st.warning("Sending update payload. Note: only settings on visible tabs are included in this demo.")
            
            with st.spinner("Updating settings..."):
                # In a real scenario, the update_payload would be fully constructed from all widgets
                success, error = update_settings(API_DOMAIN, st.session_state.access_token, st.session_state.selected_uuid, update_payload)
                if success:
                    st.success(success)
                    # Also refresh the settings in the session state
                    st.session_state.current_settings, _ = get_settings(API_DOMAIN, st.session_state.access_token, st.session_state.selected_uuid)
                if error:
                    st.error(error)
