#!/usr/bin/env python3

import argparse
import pathlib
import sys
import time

from google.cloud import compute_v1

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "part1"))
import part1 as p1  # noqa: E402


def boot_disk_name(clients, project, zone, instance):
    inst = clients.instances.get(project=project, zone=zone, instance=instance)
    boot = next(d for d in inst.disks if d.boot)
    return boot.source.rsplit("/", 1)[-1]


def main():
    parser = argparse.ArgumentParser(description="Part 2: snapshot -> image -> 3 timed instances.")
    parser.add_argument("--project")
    parser.add_argument("--zone", default=p1.DEFAULT_ZONE)
    parser.add_argument("--source", default="blog", help="the Part 1 VM")
    parser.add_argument("--snapshot", help="defaults to base-snapshot-<source>")
    parser.add_argument("--image", default="blog-image")
    parser.add_argument("--prefix", default="blog-clone")
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--machine-type", default=p1.DEFAULT_MACHINE_TYPE)
    parser.add_argument("--from-snapshot", action="store_true",
                        help="boot the clones straight from the snapshot instead of via a custom image")
    parser.add_argument("--no-http", action="store_true",
                        help="skip timing how long each app takes to answer over HTTP")
    args = parser.parse_args()
    args.snapshot = args.snapshot or f"base-snapshot-{args.source}"

    creds, project = p1.get_credentials_and_project(args.project)
    clients = p1.Clients(creds)

    # 1. Snapshot the Part 1 VM's boot disk.
    if p1.exists(lambda: clients.snapshots.get(project=project, snapshot=args.snapshot)):
        print(f"Snapshot '{args.snapshot}' already exists; reusing it.")
    else:
        disk = boot_disk_name(clients, project, args.zone, args.source)
        print(f"Snapshotting disk '{disk}' of '{args.source}' -> '{args.snapshot}' ...")
        t0 = time.perf_counter()
        op = clients.disks.create_snapshot(
            project=project, zone=args.zone, disk=disk,
            snapshot_resource=compute_v1.Snapshot(name=args.snapshot))
        p1.wait_for(op, "create snapshot")
        print(f"Snapshot created in {time.perf_counter() - t0:.1f}s.")

    snapshot_url = f"projects/{project}/global/snapshots/{args.snapshot}"
    image_url = f"projects/{project}/global/images/{args.image}"

    # 2. Create a custom image from the snapshot (skipped with --from-snapshot).
    if args.from_snapshot:
        print("Clones will boot directly from the snapshot.")
    elif p1.exists(lambda: clients.images.get(project=project, image=args.image)):
        print(f"Image '{args.image}' already exists; reusing it.")
    else:
        print(f"Creating image '{args.image}' from snapshot ...")
        t0 = time.perf_counter()
        op = clients.images.insert(
            project=project,
            image_resource=compute_v1.Image(name=args.image, source_snapshot=snapshot_url))
        p1.wait_for(op, "create image")
        print(f"Image created in {time.perf_counter() - t0:.1f}s.")

    p1.ensure_firewall_rule(clients, project)

    # 3. Create and time the clones.
    results = []
    for i in range(1, args.count + 1):
        name = f"{args.prefix}-{i}"
        if p1.exists(lambda: clients.instances.get(project=project, zone=args.zone, instance=name)):
            sys.exit(f"Instance '{name}' already exists. Delete it or pass --prefix.")
        print(f"Creating '{name}' ...")
        t0 = time.perf_counter()
        if args.from_snapshot:
            p1.create_instance(clients, project, args.zone, name, source_snapshot=snapshot_url,
                               machine_type=args.machine_type)
        else:
            p1.create_instance(clients, project, args.zone, name, source_image=image_url,
                               machine_type=args.machine_type)
        api_secs = time.perf_counter() - t0
        url = f"http://{p1.get_external_ip(clients, project, args.zone, name)}:{p1.APP_PORT}"

        app_secs = None
        if not args.no_http and p1.wait_for_http(url, timeout=600) is not None:
            app_secs = time.perf_counter() - t0
        results.append((name, api_secs, app_secs, url))
        ready = "n/a" if app_secs is None else f"{app_secs:.1f}s"
        print(f"  {name}: RUNNING after {api_secs:.1f}s, app answering after {ready}  ({url})")

    # 4. Record timings.
    source = (f"snapshot `{args.snapshot}` of `{args.source}`" if args.from_snapshot
              else f"image `{args.image}` (from snapshot `{args.snapshot}` of `{args.source}`)")
    lines = [
        "# Instance creation timing (Part 2)",
        "",
        f"Source: {source}, zone `{args.zone}`, machine type `{args.machine_type}`. Created with google-cloud-compute.",
        "",
        "| Instance | insert until RUNNING (s) | Until app answers on port 5000 (s) |",
        "| --- | --- | --- |",
    ]
    for name, api_secs, app_secs, _ in results:
        app_col = "not measured" if app_secs is None else f"{app_secs:.1f}"
        lines.append(f"| {name} | {api_secs:.1f} | {app_col} |")
    lines += [
        "",
        "Compare with Part 1 (`python part1.py --wait`), where the VM has to install",
        "packages and the app at boot before it can serve requests.",
        "",
    ]
    (HERE / "TIMING.md").write_text("\n".join(lines))
    print(f"\nTimings written to {HERE / 'TIMING.md'}")
    for name, _, _, url in results:
        print(f"Visit {url} ({name})")


if __name__ == "__main__":
    main()
