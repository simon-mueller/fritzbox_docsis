"""
Sensors displaying the DOCSIS channels and their properties

For more details about this platform, please refer to the documentation at
https://github.com/simon-mueller/fritzbox_docsis
"""

import requests
import hashlib
import xml.etree.ElementTree as ET
import json

import logging

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorStateClass, SensorEntity, SensorDeviceClass
from homeassistant.helpers.entity import Entity
from homeassistant.core import CoreState
from homeassistant.const import UnitOfEnergy
from homeassistant.util.dt import utc_from_timestamp

_LOGGER = logging.getLogger(__name__)

REQUIREMENTS = ["requests==2.31.2"]

CONF_FB_HOST = 'FB_HOST'
CONF_FB_USER = 'FB_USER'
CONF_FB_PASS = 'FB_PASS'

ICON = 'mdi:router-wireless'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
  vol.Required(CONF_FB_HOST): cv.string,
  vol.Required(CONF_FB_USER): cv.string,
  vol.Required(CONF_FB_PASS): cv.string,
})

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
  """ Setup the sensors."""
  Sensor_mappings = [
    [
      'channel_id',      None
    ],
    [
      'frequency',      'MHz'
    ],
    [
      'power_level',      'dBm'
    ],
    [
      'mse',      'dB'
    ],
    [
      'latency',      'ms'
    ],
    [
      'correctable_errors',      None
    ],
    [
      'non_correctable_errors',      None
    ]
  ]

  # make array with all the values it will output
  devices = [FritzBoxDocsisSensor(name, unit_of_measurement) for name, unit_of_measurement in Sensor_mappings]

  #adding all the devices
  async_add_entities(devices)

  #getting parameters from config file
  FB_HOST = config[CONF_FB_HOST]
  FB_USER = config[CONF_FB_USER]
  FB_PASS = config[CONF_FB_PASS]

  def update_entities(data):
    """Update entities with the latest data and trigger an update."""
    #Make all devices aware of new data
    for device in devices:
      if(device._name == 'channel_id'):
        device._state = data['channelID']
      elif(device._name == 'frequency'):
        device._state = data['frequency']
      elif(device._name == 'power_level'):
        device._state = data['powerLevel']
      elif(device._name == 'mse'):
        device._state = data['mse']
      elif(device._name == 'latency'):
        device._state = data['latency']
      elif(device._name == 'correctable_errors'):
        device._state = data['corrErrors']
      elif(device._name == 'non_correctable_errors'):
        device._state = data['nonCorrErrors']


    hass.async_create_task(device.async_update_ha_state(force_refresh=True))

  async def update():
    FRITZBOX_URL = f"https://{FB_HOST}"
    USERNAME = FB_USER
    PASSWORD = FB_PASS

    # Session-Handling
    session = requests.Session()
    
    def get_challenge():
        """Get Login-Challenge from Fritz!Box."""
        url = f"{FRITZBOX_URL}/login_sid.lua"
        response = session.get(url)
        xml_data = ET.fromstring(response.text)
        sid = xml_data.find("SID").text
        challenge = xml_data.find("Challenge").text
        return sid, challenge
    
    def create_response(challenge, password):
        """Create Response-Hash for Fritz!Box Challenge."""
        if challenge and challenge != "0000000000000000":
            challenge_response = f"{challenge}-{password}".encode("utf-16le")
            hash_value = hashlib.md5(challenge_response).hexdigest()
            return f"{challenge}-{hash_value}"
        return None
    
    def login():
        """Log into Fritz!Box and return Session ID."""
        sid, challenge = get_challenge()
        response_hash = create_response(challenge, PASSWORD)
        
        if response_hash:
            login_data = {
                "username": USERNAME,
                "response": response_hash
            }
            login_response = session.get(f"{FRITZBOX_URL}/login_sid.lua", params=login_data, verify=False)
            xml_data = ET.fromstring(login_response.text)
            sid = xml_data.find("SID").text
            return sid
        return None

    def get_cable_channels():
      """Get DOCSIS channel info from Fritz!Box."""
      sid = login()
      if not sid or sid == "0000000000000000":
          print("Login failed!")
          return

      # API-Endpoint where we can find the cable information
      url = f"{FRITZBOX_URL}/data.lua"
      params = {"xhr": 1, "sid": sid, "lang": "de", "page": "docInfo", "xhrId": "all", "no_sidrenew": "", "headers": { "Content-Type": "application/x-www-form-urlencoded" } }
      
      response = session.post(url, data=params, verify=False)
      if response.status_code == 200:
          data = response.json()
          return data
      else:
          print("Error retrieving cable channel info.", response)
        
    def extract_errors(chan_data):
      # Extract DOCSIS channels
      docsis31_ds = chan_data['data']['channelDs']['docsis31']
      docsis30_ds = chan_data['data']['channelDs']['docsis30']
      
      # ignore upstream for now
      #docsis31_us = chan_data['data']['channelUs']['docsis31']
      #docsis30_us = chan_data['data']['channelUs']['docsis30']
  
         
      #headers = channels[0].keys()  # Extract column names from first channel entry
      #rows = [channel.values() for channel in channels]  # Extract values
      #data = {}
      #for channel in docsis30_ds:
      #  for key, value in channel.items():
      #    data[key] = value

      return docsis30_ds
  
    cable_data = get_cable_channels()
    data = extract_errors(cable_data)

    update_entities(data)
  hass.loop.create_task(update())

class FritzBoxDocsisSensor(Entity):
  """Representation of a FritzBox DOCSIS Sensor"""

  def __init__(self, name, unit_of_measurement):
    """Initialize the sensor."""
    self._name = name
    self._unit_of_measurement = unit_of_measurement
    self._state = None
    _LOGGER.info("FritzBoxDocsis integration initialized")

  @property
  def name(self):
    """Return the name of the sensor."""
    return self._name

  @property
  def state(self):
    """Return the state of the sensor."""
    return self._state

  @property
  def unit_of_measurement(self):
    """Return the uom of the sensor."""
    return self._unit_of_measurement

  @property
  def icon(self):
    """Return the icon to use in the frontend, if given."""
    return ICON

