# Instance creation timing (Part 2)

Source: image `blog-image` (from snapshot `base-snapshot-blog` of `blog`), zone `us-west1-c`, machine type `e2-micro`. Created with google-cloud-compute.

| Instance | insert until RUNNING (s) | Until app answers on port 5000 (s) |
| --- | --- | --- |
| blog-clone-1 | 16.5 | 37.2 |
| blog-clone-2 | 23.4 | 44.0 |
| blog-clone-3 | 21.8 | 43.4 |

Compare with Part 1 (`python part1.py --wait`), where the VM has to install
packages and the app at boot before it can serve requests.

## Comparison with Part 1

| Instance | insert until RUNNING (s) | Until app answers on port 5000 (s) |
| --- | --- | --- |
| blog (Part 1, installs at boot) | 17.2 | 474.5 |

Clones created from the custom image serve the app roughly 10x sooner, because the software is already installed on the disk.

## Note on zone and machine type

`us-west1-b` returned `ZONE_RESOURCE_POOL_EXHAUSTED` for `f1-micro` and `e2-medium`, and `us-west1-a` was also exhausted, so all instances were created in `us-west1-c` on `e2-micro`. The code defaults to `us-west1-b` / `f1-micro`; these were overridden at run time with `--zone` and `--machine-type`.
