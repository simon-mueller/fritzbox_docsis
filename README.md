---
This custom integration scrapes the DOCSIS information from your Cable Fritz!Box and creates a sensor for each used channel.

# Configuration

Enable the integration in your `configuration.yaml`:

```
sensor:
  - platform: FritzBoxDocsis
    FB_HOST: 192.168.178.1
    FB_USER: homeassistant
    FB_PASS: ****************
```

All fields are mandatory.

Be sure to restart HomeAssistant after adding/changing these.
