---
This custom integration reads downstream DOCSIS measurements from a cable FRITZ!Box and exposes numeric channel values as Home Assistant sensors.

# Configuration

Install the `fritzbox_docsis` integration with HACS or place its folder in `custom_components`, then restart Home Assistant. Add it from **Settings > Devices & services > Add integration** and search for **FRITZ!Box DOCSIS**.

Enter the router URL (for example, `http://192.168.178.1`), a FRITZ!Box username, and its password. The account must be allowed to access cable information. HTTPS is supported when Home Assistant trusts the router's certificate; certificate checks are not disabled.
