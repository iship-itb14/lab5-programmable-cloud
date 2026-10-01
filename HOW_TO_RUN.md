# GCP VM lab (Cloud Client Libraries version): how to run

All three parts use the **Cloud Client Library** for Compute Engine, [`google-cloud-compute`](https://cloud.google.com/python/docs/reference/compute/latest) (`from google.cloud import compute_v1`), instead of the discovery-based API Client Library (`googleapiclient`).

## What changed from the API Client version

| | API Client Library (`googleapiclient`) | Cloud Client Library (`google-cloud-compute`) |
| --- | --- | --- |
| Clients | one `discovery.build("compute", "v1")` object | one typed client per resource: `InstancesClient`, `FirewallsClient`, `ImagesClient`, `DisksClient`, `SnapshotsClient` |
| Request bodies | plain dicts in REST JSON camelCase (`machineType`, `accessConfigs`) | typed objects with snake_case fields (`compute_v1.Instance(machine_type=...)`, `AccessConfig(type_=...)`, `Allowed(I_p_protocol=...)`) |
| Calls | `compute.instances().insert(...).execute()` | `clients.instances.insert(project=..., zone=..., instance_resource=...)` |
| Waiting | poll `zoneOperations().wait()` / `globalOperations().wait()` | `ExtendedOperation.result()` blocks until done |
| Errors | `HttpError`, check `e.resp.status == 404` | `google.api_core.exceptions.NotFound` / `Forbidden` |
| Responses | dicts (`inst["networkInterfaces"][0]["accessConfigs"][0]["natIP"]`) | typed objects (`inst.network_interfaces[0].access_configs[0].nat_i_p`) |

The startup scripts are unchanged. VM1 in Part 3 now installs `google-cloud-compute` instead of `google-api-python-client`. Commands below work in Cloud Shell or anywhere the Cloud SDK is installed.

## One-time setup

```bash
gcloud config set project <YOUR_PROJECT_ID>
gcloud services enable compute.googleapis.com iam.googleapis.com
gcloud auth application-default login      # not needed in Cloud Shell
pip install -r requirements.txt
```

The default zone is `us-west1-b`; pass `--zone` to change it.

## Choosing the app repo

By default the VM installs the public Flask tutorial app (`pallets/flask`, subdirectory `examples/tutorial`), which is good for testing. To use your class repo instead:

```bash
python part1/part1.py --repo https://github.com/<org>/<repo>.git --app-subdir ""
```

For a private repo, put a read-only fine-grained GitHub PAT in the URL at run time, from an environment variable so it never lands in your code:

```bash
python part1/part1.py --repo "https://<github-user>:${GITHUB_PAT}@github.com/<org>/<repo>.git"
```

The token is stored in the VM's metadata (visible to anyone with access to your project), so revoke it when you finish. The startup script removes it from the cloned repo's config so it isn't baked into the Part 2 image.

If your app isn't the Flask tutorial, edit the three lines marked `ADJUST` in `part1/startup-script.sh` (install command, one-time setup, start command).

## Part 1

```bash
python part1/part1.py --wait
```

This creates the `allow-5000` firewall rule (if missing) and the VM `blog`, then prints the URL to visit. Without `--wait` it returns as soon as the VM is running, and the app needs a few more minutes to install.

## Part 2

Run after Part 1 has finished installing the app.

```bash
python part2/part2.py
```

This creates snapshot `base-snapshot-blog` (the README's `base-snapshot-<instance>` naming), image `blog-image`, and VMs `blog-clone-1..3`, then writes `part2/TIMING.md`. Add `--from-snapshot` to boot the clones straight from the snapshot, as the Part 2 README describes, instead of through an image. Commit `TIMING.md`. Clones start the app from the disk, so compare their "until app answers" times with Part 1's.

## Part 3: service account

Create the service account with the two roles from the Part 3 README (Service Account User and Compute Admin), and save the key as `service-credentials.json`. You can use the console screenshots in the README, or run:

```bash
PROJECT=$(gcloud config get-value project)
SA=vm-launcher@${PROJECT}.iam.gserviceaccount.com

gcloud iam service-accounts create vm-launcher --display-name "VM launcher (lab)"
gcloud projects add-iam-policy-binding $PROJECT \
  --member serviceAccount:$SA --role roles/compute.admin
gcloud projects add-iam-policy-binding $PROJECT \
  --member serviceAccount:$SA --role roles/iam.serviceAccountUser
gcloud iam service-accounts keys create part3/service-credentials.json --iam-account $SA
```

For tighter least privilege, `roles/compute.instanceAdmin.v1` plus `roles/compute.securityAdmin` is enough for this code. Service Account User is only needed if a VM gets a service account attached, and these VMs don't get one.

Then run:

```bash
cd part3 && python part3.py --wait
```

The project comes from `GOOGLE_CLOUD_PROJECT` if set, otherwise from the key file, so you don't need the stub's `'FILL IN YOUR PROJECT'`.

The program creates `vm1-launcher` using the key. VM1 creates `vm2-blog` with Part 1's code. Neither VM has a default service account attached, so VM1 can only act through the key you gave it.

If key creation fails with an organization-policy error (`iam.disableServiceAccountKeyCreation`), your project blocks key downloads; ask your instructor, or use a personal project.

Watch VM1 work:

```bash
gcloud compute instances get-serial-port-output vm1-launcher --zone us-west1-b
```

## Cleanup (VMs, disks, and images cost money)

```bash
gcloud compute instances delete blog blog-clone-1 blog-clone-2 blog-clone-3 vm1-launcher vm2-blog --zone us-west1-b --quiet
gcloud compute images delete blog-image --quiet
gcloud compute snapshots delete base-snapshot-blog --quiet
gcloud compute firewall-rules delete allow-5000 --quiet
gcloud iam service-accounts keys list --iam-account $SA   # then delete the key, or the whole account:
gcloud iam service-accounts delete $SA --quiet
```
