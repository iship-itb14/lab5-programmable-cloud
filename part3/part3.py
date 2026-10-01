#!/usr/bin/env python3
"""
Part 3 (Cloud Client Libraries version) - Use a service account to create VM1; VM1 then runs Part 1 to create VM2.

This program authenticates explicitly with the service-account key file (not your
own user credentials) and creates VM1. VM1's metadata carries:
  part1-py             Part 1's program
  vm2-startup-script   Part 1's startup script (for VM2)
  service-credentials  the service-account key, so VM1's code can call the API
  project / zone / vm2-name / repo-url / app-subdir
VM1's startup script (vm1-startup.sh) installs the Python client libraries, writes
those files to disk, and runs part1.py with GOOGLE_APPLICATION_CREDENTIALS set to
the key. VM1 has NO default service account attached, so the only way it can create
VM2 is with the credentials we handed it.

Create the service account and key first (see HOW_TO_RUN.md). Never commit the key.
"""
import argparse
import os
import pathlib
import sys
import time

from google.oauth2 import service_account

HERE = pathlib.Path(__file__).resolve().parent
PART1_DIR = HERE.parent / "part1"
sys.path.insert(0, str(PART1_DIR))
import part1 as p1  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Part 3: service account -> VM1 -> VM2.")
    parser.add_argument("--key-file", default="service-credentials.json",
                        help="service-account key (looked up in the current dir, then next to this file)")
    parser.add_argument("--project", help="defaults to $GOOGLE_CLOUD_PROJECT, then the key's project")
    parser.add_argument("--zone", default=p1.DEFAULT_ZONE)
    parser.add_argument("--vm1", default="vm1-launcher")
    parser.add_argument("--vm2", default="vm2-blog")
    parser.add_argument("--repo", default=p1.DEFAULT_REPO)
    parser.add_argument("--app-subdir", default=p1.DEFAULT_APP_SUBDIR)
    parser.add_argument("--machine-type", default=p1.DEFAULT_MACHINE_TYPE,
                        help="used for both VM1 and VM2")
    parser.add_argument("--wait", action="store_true",
                        help="wait for VM1 to create VM2 and for VM2's app to answer")
    args = parser.parse_args()

    key_path = pathlib.Path(args.key_file)
    if not key_path.exists() and not key_path.is_absolute():
        key_path = HERE / args.key_file
    if not key_path.exists():
        sys.exit(f"Key file {key_path} not found. Create it with the gcloud commands in HOW_TO_RUN.md.")

    creds = service_account.Credentials.from_service_account_file(str(key_path), scopes=p1.SCOPES)
    project = args.project or os.getenv("GOOGLE_CLOUD_PROJECT") or creds.project_id
    clients = p1.Clients(creds)  # every compute_v1 client authenticates as the service account
    print(f"Acting as service account {creds.service_account_email} in project {project}")

    for name in (args.vm1, args.vm2):
        if p1.exists(lambda: clients.instances.get(project=project, zone=args.zone, instance=name)):
            sys.exit(f"Instance '{name}' already exists. Delete it first.")

    metadata = {
        "part1-py": (PART1_DIR / "part1.py").read_text(),
        "vm2-startup-script": (PART1_DIR / "startup-script.sh").read_text(),
        "service-credentials": key_path.read_text(),
        "project": project,
        "zone": args.zone,
        "vm2-name": args.vm2,
        "repo-url": args.repo,
        "app-subdir": args.app_subdir,
        "machine-type": args.machine_type,
    }

    print(f"Creating VM1 '{args.vm1}' with the service account's credentials ...")
    t0 = time.perf_counter()
    p1.create_instance(
        clients, project, args.zone, args.vm1,
        source_image=p1.latest_ubuntu_image(clients),
        startup_script=(HERE / "vm1-startup.sh").read_text(),
        extra_metadata=metadata,
        tags=(),  # VM1 serves nothing; it only needs outbound access to the API
        machine_type=args.machine_type,
    )
    print(f"VM1 created in {time.perf_counter() - t0:.1f}s. It will now create VM2 '{args.vm2}'.")

    if not args.wait:
        print(f"\nWatch progress:  gcloud compute instances get-serial-port-output {args.vm1} --zone {args.zone}")
        print(f"Then find VM2's IP with:  gcloud compute instances list")
        print(f"and visit http://<VM2 external IP>:{p1.APP_PORT}")
        return

    print("Waiting for VM2 to appear ...")
    deadline = time.perf_counter() + 900
    while not p1.exists(lambda: clients.instances.get(project=project, zone=args.zone, instance=args.vm2)):
        if time.perf_counter() > deadline:
            sys.exit("VM2 did not appear within 15 minutes; check VM1's serial console output.")
        time.sleep(10)
    ip = p1.get_external_ip(clients, project, args.zone, args.vm2)
    url = f"http://{ip}:{p1.APP_PORT}"
    print(f"VM2 exists after {time.perf_counter() - t0:.1f}s. Waiting for its app ...")
    if p1.wait_for_http(url) is None:
        print("VM2's app did not respond in time; check its serial console output.")
    print(f"\nVisit {url} to use the application running on VM2.")


if __name__ == "__main__":
    main()
