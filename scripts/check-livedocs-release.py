"""Validate reviewed LiveDocs metadata; live runs also verify its publication run."""
import argparse
import json
import re
from urllib.request import urlopen

def check(value):
    if (set(value) != {"schemaVersion", "image", "commitSha", "publicationRun", "contractCommit"}
            or type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1
            or not re.fullmatch(r"mb0101/ecommerce-store-livedocs@sha256:[a-f0-9]{64}",value["image"])
            or not all(re.fullmatch(r"[a-f0-9]{40}", value[name]) for name in ("commitSha", "contractCommit"))
            or type(value["publicationRun"]) is not int or value["publicationRun"] <= 0):
        raise ValueError("Invalid reviewed LiveDocs release metadata.")
    return value

def verify(value):
    url = "https://api.github.com/repos/MichalBoczula/ECommerceStore.LiveDocs/actions/runs/"+str(value["publicationRun"])
    with urlopen(url,timeout=30) as response:
        run = json.load(response)
    if (run["conclusion"] != "success" or run["head_sha"] != value["commitSha"]
            or run["head_branch"] != "main" or run["event"] not in ("push","workflow_dispatch")
            or run["repository"]["full_name"] != "MichalBoczula/ECommerceStore.LiveDocs"):
        raise ValueError("LiveDocs publication provenance does not match the selected release.")

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file")
    parser.add_argument("--verify-publication",action="store_true")
    args=parser.parse_args()
    try:
        with open(args.file) as source: value=check(json.load(source))
        if args.verify_publication: verify(value)
        print("Reviewed immutable LiveDocs image/source metadata verified.")
    except Exception:
        raise SystemExit("LiveDocs release validation failed; verify its immutable digest and publication provenance.")
