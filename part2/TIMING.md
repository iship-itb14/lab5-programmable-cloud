# Instance creation timing (Part 2)

Source: image `blog-image` (from snapshot `base-snapshot-blog` of `blog`), zone `us-west1-c`, machine type `e2-micro`. Created with google-cloud-compute.

| Instance | insert until RUNNING (s) | Until app answers on port 5000 (s) |
| --- | --- | --- |
| blog-clone-1 | 16.5 | 37.2 |
| blog-clone-2 | 23.4 | 44.0 |
| blog-clone-3 | 21.8 | 43.4 |

Compare with Part 1 (`python part1.py --wait`), where the VM has to install
packages and the app at boot before it can serve requests.
