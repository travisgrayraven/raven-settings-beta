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
        st.error("FATAL: API credentials are not configured. Please follow the setup instructions to add your credentials to the app's Settings.")
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
        # Find the index of the currently selected UUID to preserve selection across reruns
        device_names = list(device_map.keys())
        current_selection_index = 0
        if st.session_state.selected_uuid:
            # Find the name corresponding to the stored UUID
            for name, uuid in device_map.items():
                if uuid == st.session_state.selected_uuid:
                    current_selection_index = device_names.index(name)
                    break
        
        selected_name = st.selectbox(
            "Select a Raven from the list:",
            options=device_names,
            index=current_selection_index
        )
        # Update the selected UUID if the selection changes
        if st.session_state.selected_uuid != device_map[selected_name]:
            st.session_state.selected_uuid = device_map[selected_name]
            st.session_state.current_settings = None # Clear old settings on new device selection
            st.rerun()
        
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
        
        # Use tabs for a cleaner layout
        tab_msg, tab_audio, tab_cam, tab_events, tab_obd, tab_wifi, tab_did, tab_sys, tab_eld = st.tabs([
            "Driver Messaging", "Audio", "Camera", "Events", "OBD", "WiFi Hotspot", "Driver ID", "System", "ELD"
        ])

        with tab_msg:
            st.subheader("Send a one-time message")
            msg_text = st.text_input("Message (15 char max)", placeholder="e.g., Call the office", max_chars=15)
            msg_duration = st.number_input("Duration (seconds)", min_value=1, value=300)
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
            audio_data = s.get('audio', {})
            update_payload["audio"] = {
                "audio_notifications_enabled": st.checkbox("General Audio Notifications", audio_data.get('audio_notifications_enabled')),
                "streaming_audio_enabled": st.checkbox("Enable Audio in Live Stream", audio_data.get('streaming_audio_enabled')),
                "message_notification_audio_enabled": st.checkbox("Message Notification Sound", audio_data.get('message_notification_audio_enabled'))
            }

        with tab_cam:
            st.subheader("Camera Settings")
            cam_data = s.get('camera', {})
            road_cam_data = cam_data.get('road_camera', {})
            cabin_cam_data = cam_data.get('cabin_camera', {})
            
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("<b>Road Camera:</b>", unsafe_allow_html=True)
                road_cam_enabled = st.checkbox("Enabled", road_cam_data.get('camera_enabled'), key='rc_en')
                road_cam_audio = st.checkbox("Audio Recording", road_cam_data.get('audio_recording'), key='rc_aud')
            with c2:
                st.markdown("<b>Cabin Camera:</b>", unsafe_allow_html=True)
                cabin_cam_enabled = st.checkbox("Enabled", cabin_cam_data.get('camera_enabled'), key='cc_en')
                cabin_cam_audio = st.checkbox("Audio Recording", cabin_cam_data.get('audio_recording'), key='cc_aud')
            
            st.divider()
            vid_profile_options = ['standard', 'legacy', 'balanced', 'extended']
            vid_profile = st.selectbox("Video Profile", vid_profile_options, index=vid_profile_options.index(cam_data.get('video_recording_profile', 'standard')))
            
            update_payload["camera"] = {
                "road_camera": {"camera_enabled": road_cam_enabled, "audio_recording": road_cam_audio},
                "cabin_camera": {"camera_enabled": cabin_cam_enabled, "audio_recording": cabin_cam_audio},
                "video_recording_profile": vid_profile
            }
            
        with tab_events:
            st.subheader("Event Settings")
            events_payload = {}
            events_data = s.get('events', {})

            with st.expander("G-Force Events", expanded=True):
                c1, c2 = st.columns(2)
                events_payload['harsh_braking_event_enabled'] = c1.checkbox("Harsh Braking", events_data.get('harsh_braking_event_enabled'))
                events_payload['harsh_braking_accel_threshold'] = c2.number_input("Threshold (Braking)", value=events_data.get('harsh_braking_accel_threshold', 0), key='hb_thresh')
                events_payload['aggressive_accel_event_enabled'] = c1.checkbox("Aggressive Accel", events_data.get('aggressive_accel_event_enabled'))
                events_payload['aggressive_accel_threshold'] = c2.number_input("Threshold (Accel)", value=events_data.get('aggressive_accel_threshold', 0), key='aa_thresh')
                events_payload['harsh_cornering_event_enabled'] = c1.checkbox("Harsh Cornering", events_data.get('harsh_cornering_event_enabled'))
                events_payload['harsh_cornering_accel_threshold'] = c2.number_input("Threshold (Cornering)", value=events_data.get('harsh_cornering_accel_threshold', 0), key='hc_thresh')
                events_payload['possible_impact_event_enabled'] = c1.checkbox("Possible Impact", events_data.get('possible_impact_event_enabled'))
                events_payload['possible_impact_accel_threshold'] = c2.number_input("Threshold (Impact)", value=events_data.get('possible_impact_accel_threshold', 0), key='pi_thresh')
                events_payload['car_bumped_event_enabled'] = c1.checkbox("Car Bumped (when parked)", events_data.get('car_bumped_event_enabled'))
                events_payload['car_bumped_accel_threshold'] = c2.number_input("Threshold (Bumped)", value=events_data.get('car_bumped_accel_threshold', 0), key='cb_thresh')

            with st.expander("Standard & Miscellaneous Events"):
                c1, c2, c3 = st.columns(3)
                events_payload['idling_event_enabled'] = c1.checkbox("Idling", events_data.get('idling_event_enabled'))
                events_payload['idling_event_grace_period'] = c2.number_input("Idling Grace Period (ms)", value=events_data.get('idling_event_grace_period', 0))
                events_payload['idling_event_speed_floor'] = c3.number_input("Idling Speed Floor (km/h)", value=events_data.get('idling_event_speed_floor', 0))
                
                st.divider()
                st.markdown("<b>Speeding</b>", unsafe_allow_html=True)
                c1, c2, c3 = st.columns(3)
                events_payload['speeding_event_enabled'] = c1.checkbox("Speeding Event Enabled", events_data.get('speeding_event_enabled'))
                events_payload['speeding_event_threshold'] = c2.number_input("Speeding Threshold", value=events_data.get('speeding_event_threshold', 0))
                events_payload['speeding_event_threshold_type'] = c3.selectbox("Speeding Type", ['CONSTANT', 'PERCENT'], index=['CONSTANT', 'PERCENT'].index(events_data.get('speeding_event_threshold_type', 'CONSTANT')), key='se_type')

                st.markdown("<b>Speeding Visual Warning</b>", unsafe_allow_html=True)
                c1, c2, c3 = st.columns(3)
                c1.empty() # Placeholder for alignment
                events_payload['speeding_visual_warning_threshold'] = c2.number_input("Visual Warning Threshold", value=events_data.get('speeding_visual_warning_threshold', 0))
                events_payload['speeding_visual_warning_threshold_type'] = c3.selectbox("Visual Warning Type", ['CONSTANT', 'PERCENT'], index=['CONSTANT', 'PERCENT'].index(events_data.get('speeding_visual_warning_threshold_type', 'CONSTANT')), key='svw_type')
                
                st.divider()
                st.markdown("<b>Miscellaneous</b>", unsafe_allow_html=True)
                events_payload['auto_video_upload_enabled'] = st.checkbox("Auto Upload Event Video", events_data.get('auto_video_upload_enabled'))
                events_payload['bad_install_event_enabled'] = st.checkbox("Bad Install Detection", events_data.get('bad_install_event_enabled'))

            with st.expander("Driver Monitoring (DMS)"):
                def dms_row(label, base_key, data):
                    st.markdown(f"<b>{label}:</b>", unsafe_allow_html=True)
                    c1, c2, c3, c4 = st.columns(4)
                    payload = {}
                    payload[f'{base_key}_event_enabled'] = c1.checkbox("Enabled", data.get(f'{base_key}_event_enabled'), key=f'{base_key}_en')
                    payload[f'{base_key}_visual_alert_enabled'] = c2.checkbox("Visual Alert", data.get(f'{base_key}_visual_alert_enabled'), key=f'{base_key}_vis')
                    payload[f'{base_key}_grace_period'] = c3.number_input("Grace Period (ms)", value=data.get(f'{base_key}_grace_period',0), key=f'{base_key}_grace')
                    payload[f'{base_key}_speed_threshold'] = c4.number_input("Speed Threshold", value=data.get(f'{base_key}_speed_threshold',0), key=f'{base_key}_speed')
                    st.divider()
                    return payload

                events_payload.update(dms_row("Cellphone Detection", "cellphone_detection", events_data))
                events_payload.update(dms_row("Camera Obscured", "camera_obscured", events_data))
                events_payload.update(dms_row("Distracted Detection", "distracted_detection", events_data))
                events_payload.update(dms_row("Drinking Detection", "drinking_detection", events_data))
                events_payload.update(dms_row("Eating Detection", "eating_detection", events_data))
                events_payload.update(dms_row("Smoking Detection", "smoking_detection", events_data))
                events_payload.update(dms_row("Fatigue (Tired) Detection", "tired_detection", events_data))
            
            with st.expander("Assistance (ADAS)"):
                st.markdown("<b>Tailgating Detection:</b>", unsafe_allow_html=True)
                c1, c2, c3 = st.columns(3)
                events_payload['tailgating_detection_event_enabled'] = c1.checkbox("Enabled", events_data.get('tailgating_detection_event_enabled'), key='tg_en')
                events_payload['tailgating_detection_visual_alert_enabled'] = c2.checkbox("Visual Alert", events_data.get('tailgating_detection_visual_alert_enabled'), key='tg_vis')
                st.markdown("---")
                c1, c2, c3 = st.columns(3)
                events_payload['tailgating_detection_speed_threshold'] = c1.number_input("Speed Threshold (km/h)", value=events_data.get('tailgating_detection_speed_threshold', 0))
                events_payload['tailgating_detection_grace_period'] = c2.number_input("Grace Period (s)", value=events_data.get('tailgating_detection_grace_period', 0))
                events_payload['tailgating_detection_follow_time'] = c3.number_input("Follow Time (s)", value=float(events_data.get('tailgating_detection_follow_time', 0.0)))
                c1, c2, c3 = st.columns(3)
                events_payload['tailgating_detection_critical_reaction_time'] = c1.number_input("Critical Reaction Time (s)", value=float(events_data.get('tailgating_detection_critical_reaction_time', 0.0)))
                events_payload['tailgating_detection_alert_reaction_time'] = c2.number_input("Alert Reaction Time (s)", value=float(events_data.get('tailgating_detection_alert_reaction_time', 0.0)))
                events_payload['tailgating_detection_safe_reaction_time'] = c3.number_input("Safe Reaction Time (s)", value=float(events_data.get('tailgating_detection_safe_reaction_time', 0.0)))

                st.divider()
                st.markdown("<b>Vanishing Point Calibration:</b>", unsafe_allow_html=True)
                c1, c2 = st.columns(2)
                events_payload['vanishing_point_calibration_enabled'] = c1.checkbox("Enabled", events_data.get('vanishing_point_calibration_enabled'), key='vp_en')
                events_payload['vanishing_point_calibration_force'] = c2.checkbox("Force Calibration", events_data.get('vanishing_point_calibration_force'), key='vp_force')

            with st.expander("Security"):
                sec_data = events_data
                c1,c2,c3 = st.columns(3)
                events_payload['security_event_preview_count'] = c1.number_input("Preview Image Count", value=sec_data.get('security_event_preview_count', 0))
                events_payload['security_event_preview_duration'] = c2.number_input("Preview Duration (s)", value=sec_data.get('security_event_preview_duration', 0))
                events_payload['security_event_video_duration'] = c3.number_input("Video Duration (s)", value=sec_data.get('security_event_video_duration', 0))

            # Assign the fully built dictionary to the main payload
            update_payload["events"] = events_payload

        with tab_obd:
            st.subheader("OBD Settings")
            obd_data = s.get('obd', {})
            update_payload["obd"] = {
                "canbus_enabled": st.checkbox("CANbus Enabled", obd_data.get('canbus_enabled')),
                "low_battery_cutoff_millivolts": st.number_input("Low Battery Cutoff (mV)", value=obd_data.get('low_battery_cutoff_millivolts', 0))
            }

        with tab_wifi:
            st.subheader("WiFi Hotspot")
            wifi_data = s.get('wifi_hotspot', {})
            update_payload["wifi_hotspot"] = {
                "hotspot_enabled": st.checkbox("Hotspot Enabled", wifi_data.get("hotspot_enabled")),
                "auto_disable_on_engine_off": st.checkbox("Auto-Disable on Engine Off", wifi_data.get("auto_disable_on_engine_off")),
                "ssid": st.text_input("SSID", wifi_data.get("ssid")),
                "password": st.text_input("Password", wifi_data.get("password"), type="password")
            }

        with tab_did:
            st.subheader("Driver ID")
            did_data = s.get('driver_id', {})
            update_payload["driver_id"] = {
                "barcode_driver_id_enabled": st.checkbox("Barcode ID Enabled", did_data.get('barcode_driver_id_enabled')),
                "barcode_driver_id_request_period": st.selectbox("Request Period", ["PER_TRIP", "ALWAYS"], index=["PER_TRIP", "ALWAYS"].index(did_data.get('barcode_driver_id_request_period', 'PER_TRIP'))),
                "barcode_driver_id_audio_delay": st.number_input("Audio Delay (s)", value=did_data.get('barcode_driver_id_audio_delay', 0))
            }
            
        with tab_sys:
            st.subheader("System Settings")
            sys_data = s.get('system', {})
            update_payload["system"] = {
                "gesture_enabled": st.checkbox("Gesture Enabled", sys_data.get('gesture_enabled')),
                "video_recording_after_parked_duration": st.number_input("Video Rec After Parked (s)", value=sys_data.get('video_recording_after_parked_duration', 0)),
                "vehicle_speed_adjustment_percent": st.number_input("Speed Adjustment (%)", value=sys_data.get('vehicle_speed_adjustment_percent', 0))
            }

        with tab_eld:
            st.subheader("ELD Settings")
            eld_data = s.get('eld', {})
            update_payload["eld"] = {
                "eld_enabled": st.checkbox("ELD Enabled", eld_data.get('eld_enabled')),
                "eld_visual_ud_alert_enabled": st.checkbox("Visual Unidentified Driving Alert", eld_data.get('eld_visual_ud_alert_enabled')),
                "eld_visual_ud_alert_period": st.number_input("Alert Period (ms)", value=eld_data.get('eld_visual_ud_alert_period', 0))
            }

        # --- UPDATE BUTTON ---
        st.header(" ") # Spacer
        if st.button("SAVE AND UPDATE ALL SETTINGS TO RAVEN", type="primary", use_container_width=True):
            with st.spinner("Updating settings..."):
                success, error = update_settings(API_DOMAIN, st.session_state.access_token, st.session_state.selected_uuid, update_payload)
                if success:
                    st.success(success)
                    # Also refresh the settings in the session state to reflect changes
                    st.session_state.current_settings, _ = get_settings(API_DOMAIN, st.session_state.access_token, st.session_state.selected_uuid)
                    st.rerun() # Rerun to show the refreshed settings in the UI
                if error:
                    st.error(error)
