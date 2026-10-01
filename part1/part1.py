#!/usr/bin/env python3

import argparse
import os
import pathlib
import sys
import time
import urllib.request

import google.auth
from google.api_core.exceptions import Forbidden, NotFound
from google.cloud import compute_v1

HERE = pathlib.Path(__file__).resolve().parent
SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]

APP_PORT = 5000
FIREWALL_RULE = "allow-5000"
NETWORK_TAG = "allow-5000"
DEFAULT_ZONE = "us-west1-b"
DEFAULT_MACHINE_TYPE = "f1-micro"   # required for the final version; --machine-type e2-medium is faster for testing

IMAGE_PROJECT = "ubuntu-os-cloud"
IMAGE_FAMILY = "ubuntu-2204-lts"

# The class's public Flask tutorial repo; flaskr is at the repo root.
DEFAULT_REPO = os.environ.get("REPO_URL", "https://github.com/cu-csci-4253-datacenter/flask-tutorial")
DEFAULT_APP_SUBDIR = os.environ.get("APP_SUBDIR", "")


# ---------------------------------------------------------------- helpers (reused by Parts 2 and 3)

class Clients:
    """One typed client per Compute Engine resource, all sharing the same credentials."""

    def __init__(self, credentials):
        self.instances = compute_v1.InstancesClient(credentials=credentials)
        self.firewalls = compute_v1.FirewallsClient(credentials=credentials)
        self.images = compute_v1.ImagesClient(credentials=credentials)
        self.disks = compute_v1.DisksClient(credentials=credentials)
        self.snapshots = compute_v1.SnapshotsClient(credentials=credentials)


def get_credentials_and_project(project_arg=None):
    creds, detected_project = google.auth.default(scopes=SCOPES)
    project = project_arg or os.environ.get("GOOGLE_CLOUD_PROJECT") or detected_project
    if not project:
        sys.exit("Could not determine the project. Pass --project or set GOOGLE_CLOUD_PROJECT.")
    return creds, project


def wait_for(operation, label, timeout=900):
    """Block until an ExtendedOperation finishes; raise if it failed."""
    result = operation.result(timeout=timeout)
    if operation.error_code:
        raise RuntimeError(f"{label} failed: [{operation.error_code}] {operation.error_message}")
    return result


def exists(get_call):
    """True if the zero-argument get_call succeeds, False if it raises NotFound."""
    try:
        get_call()
        return True
    except NotFound:
        return False


def firewall_rule_exists(clients, project):
    """firewalls.list filtered by name, as the assignment asks."""
    request = compute_v1.ListFirewallsRequest(project=project, filter=f'name = "{FIREWALL_RULE}"')
    return any(rule.name == FIREWALL_RULE for rule in clients.firewalls.list(request=request))


def ensure_firewall_rule(clients, project):
    try:
        if firewall_rule_exists(clients, project):
            print(f"Firewall rule '{FIREWALL_RULE}' already exists.")
            return
    except Forbidden:
        print(f"Warning: no permission to list firewall rules; assuming '{FIREWALL_RULE}' exists.")
        return

    rule = compute_v1.Firewall(
        name=FIREWALL_RULE,
        network="global/networks/default",
        direction="INGRESS",
        allowed=[compute_v1.Allowed(I_p_protocol="tcp", ports=[str(APP_PORT)])],
        source_ranges=["0.0.0.0/0"],
        target_tags=[NETWORK_TAG],
        description=f"Allow inbound tcp:{APP_PORT} to VMs tagged {NETWORK_TAG}",
    )
    print(f"Creating firewall rule '{FIREWALL_RULE}' ...")
    wait_for(clients.firewalls.insert(project=project, firewall_resource=rule), "firewall insert")


def latest_ubuntu_image(clients):
    """Use the image family, not a hard-coded image name."""
    return clients.images.get_from_family(project=IMAGE_PROJECT, family=IMAGE_FAMILY).self_link


def set_network_tags(clients, project, zone, name, tags):
    """instances.setTags needs the instance's current tags fingerprint."""
    inst = clients.instances.get(project=project, zone=zone, instance=name)
    op = clients.instances.set_tags(
        project=project, zone=zone, instance=name,
        tags_resource=compute_v1.Tags(items=list(tags), fingerprint=inst.tags.fingerprint))
    wait_for(op, f"set tags on {name}")


def create_instance(clients, project, zone, name, source_image=None, startup_script=None,
                    extra_metadata=None, machine_type=DEFAULT_MACHINE_TYPE, tags=(NETWORK_TAG,),
                    source_snapshot=None):
    """Create a VM booting from source_image or source_snapshot, then apply network
    tags with setTags. No service_accounts entry, so the VM gets no default service account."""
    items = []
    if startup_script:
        items.append(compute_v1.Items(key="startup-script", value=startup_script))
    for key, value in (extra_metadata or {}).items():
        if value not in (None, ""):
            items.append(compute_v1.Items(key=key, value=str(value)))

    init = compute_v1.AttachedDiskInitializeParams(disk_size_gb=10)
    if source_snapshot:
        init.source_snapshot = source_snapshot
    else:
        init.source_image = source_image

    instance = compute_v1.Instance(
        name=name,
        machine_type=f"zones/{zone}/machineTypes/{machine_type}",
        disks=[compute_v1.AttachedDisk(boot=True, auto_delete=True, initialize_params=init)],
        network_interfaces=[compute_v1.NetworkInterface(
            network="global/networks/default",
            access_configs=[compute_v1.AccessConfig(type_="ONE_TO_ONE_NAT", name="External NAT")],
        )],
        metadata=compute_v1.Metadata(items=items),
    )
    op = clients.instances.insert(project=project, zone=zone, instance_resource=instance)
    wait_for(op, f"create instance {name}")
    if tags:
        set_network_tags(clients, project, zone, name, tags)


def get_external_ip(clients, project, zone, name):
    inst = clients.instances.get(project=project, zone=zone, instance=name)
    return inst.network_interfaces[0].access_configs[0].nat_i_p


def wait_for_http(url, timeout=900, interval=5):
    """Poll url until it answers. Returns seconds waited, or None on timeout."""
    start = time.perf_counter()
    while time.perf_counter() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if resp.status < 500:
                    return time.perf_counter() - start
        except Exception:
            pass
        time.sleep(interval)
    return None


# ---------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(description="Part 1: create a VM running a web app from git.")
    parser.add_argument("--project")
    parser.add_argument("--zone", default=DEFAULT_ZONE)
    parser.add_argument("--name", default="blog")
    parser.add_argument("--repo", default=DEFAULT_REPO,
                        help="git URL; for a private repo use https://<user>:<PAT>@github.com/... at run time")
    parser.add_argument("--app-subdir", default=DEFAULT_APP_SUBDIR,
                        help="subdirectory of the repo containing the app ('' for repo root)")
    parser.add_argument("--machine-type", default=DEFAULT_MACHINE_TYPE)
    parser.add_argument("--startup-script", default=str(HERE / "startup-script.sh"))
    parser.add_argument("--wait", action="store_true", help="wait until the app answers over HTTP")
    args = parser.parse_args()

    creds, project = get_credentials_and_project(args.project)
    clients = Clients(creds)
    print(f"Project: {project}  Zone: {args.zone}")

    ensure_firewall_rule(clients, project)

    if exists(lambda: clients.instances.get(project=project, zone=args.zone, instance=args.name)):
        sys.exit(f"Instance '{args.name}' already exists. Delete it or pass --name.")

    startup_script = pathlib.Path(args.startup_script).read_text()
    print(f"Creating instance '{args.name}' ...")
    t0 = time.perf_counter()
    create_instance(
        clients, project, args.zone, args.name,
        source_image=latest_ubuntu_image(clients),
        startup_script=startup_script,
        extra_metadata={"repo-url": args.repo, "app-subdir": args.app_subdir},
        machine_type=args.machine_type,
    )
    print(f"Instance created in {time.perf_counter() - t0:.1f}s.")

    ip = get_external_ip(clients, project, args.zone, args.name)
    url = f"http://{ip}:{APP_PORT}"

    if args.wait:
        print("Waiting for the app to finish installing and respond ...")
        if wait_for_http(url) is None:
            print("App did not respond in time; check the serial console output.")
        else:
            print(f"App is up {time.perf_counter() - t0:.1f}s after the create request.")

    print()
    print("The Flask application is available at:")
    print()
    print(f"    {url}")
    if not args.wait:
        print("The startup script needs a few minutes to install the app before that page loads.")


if __name__ == "__main__":
    main()
