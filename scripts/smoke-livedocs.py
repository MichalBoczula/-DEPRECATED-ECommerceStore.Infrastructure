"""Verify HTTPS probes, portal/assets and the deployed source commit."""
import json
import sys
import time
from urllib.request import urlopen
from urllib.parse import urlsplit

def check(portal, commit):
    url=urlsplit(portal)
    if (url.scheme != "https" or url.path != "/livedoc/" or not url.hostname
            or not url.hostname.endswith(".azurecontainerapps.io") or url.username or url.password
            or url.port not in (None,443) or url.query or url.fragment):
        raise ValueError("Invalid public LiveDocs URL.")
    base=f"https://{url.hostname}"
    for route in ("/health/live","/health/ready","/livedoc/","/livedoc/styles.css"):
        with urlopen(base+route,timeout=10) as response:
            if response.status != 200: raise ValueError("LiveDocs route is not ready.")
    with urlopen(base+"/build-info.json",timeout=10) as response:
        if json.load(response)["commitSha"] != commit:
            raise ValueError("The deployed LiveDocs source does not match the release.")
if __name__ == "__main__":
    deadline=time.monotonic()+300
    while True:
        try:
            check(sys.argv[1],sys.argv[2])
            print("LiveDocs HTTPS probes, portal/assets and source identity passed.")
            break
        except Exception:
            if time.monotonic() >= deadline: raise SystemExit("LiveDocs public verification failed; inspect the deployed release securely.")
            time.sleep(5)
