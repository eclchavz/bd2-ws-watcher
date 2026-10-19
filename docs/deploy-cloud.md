# Running it in the cloud

The same container runs on a small cloud server, so checks keep going when your PC is off. The dashboard stays private: only your own devices on [Tailscale](https://tailscale.com) (free) can open it (ADR 0001).

**Run it in one place only.** If the PC and the cloud server both run it, every alert arrives twice. Stop the PC copy (`docker compose down`) before starting the cloud one.

Measured memory use: about 50 MB, so the free 1 GB server is plenty.

## Option A: Google Cloud e2-micro (free)

Google's free tier includes one e2-micro server per month in `us-west1`, `us-central1` or `us-east1`, with 30 GB of *standard* disk and 1 GB of outbound traffic a month from North America (to anywhere except China and Australia). This app uses only a small fraction of that. Prices and limits change, so check https://cloud.google.com/free/docs/free-cloud-features#compute before you start.

### 1. Create the server

1. Sign in at https://console.cloud.google.com, create a project (e.g. `bd2-watcher`) and enable billing. The free tier still needs a card on file.
2. Go to **Compute Engine → VM instances → Create instance**:
   - **Region:** `us-west1` (Oregon, the closest free region to Arizona)
   - **Machine type:** `e2-micro`
   - **Boot disk:** Debian 12, **Standard persistent disk**, 30 GB. "Balanced" and "SSD" disks are *not* free.
   - **Firewall:** leave "Allow HTTP" and "Allow HTTPS" **unchecked**
3. Create it, then click **SSH** to open a terminal in the browser.

### 2. Prepare it (in the SSH terminal)

```sh
# 1 GB of swap as headroom for the 1 GB of RAM (safe to run again)
[ -f /swapfile ] || { sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile; }
sudo swapon /swapfile 2>/dev/null; grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Docker (starts on boot) and permission to use it without sudo
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER

# Tailscale: sign in with the same account as your phone and PC
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Then **close the SSH window and open a new one**, so the docker permission takes effect. Check with `docker compose version`: it must be **2.24.4 or newer**, which the get.docker.com install gives you. Older versions would misread `compose.cloud.yaml`.

In the [Tailscale admin console](https://login.tailscale.com/admin/dns), turn on **MagicDNS** and **HTTPS Certificates**. Step 4 needs both.

### 3. Bring the app and your data

```sh
git clone https://github.com/eclchavz/bd2-ws-watcher.git && cd bd2-ws-watcher
nano .env    # paste the contents of your PC's .env (Discord webhook, Gmail, TZ=America/Phoenix)
echo 'COMPOSE_FILE=compose.yaml:compose.cloud.yaml' >> .env
```

That last line makes every plain `docker compose ...` command on this server use the private-only settings, so you can't publish the dashboard by accident. Don't add it to your PC's `.env`.

To keep your history (price charts, alert log, what's already been seen), copy the database. On the PC, stop the app first with `docker compose down` and wait for it to finish. Then upload **every** file in `data/` whose name starts with `bd2watcher.db` (`bd2watcher.db`, plus `bd2watcher.db-wal` and `bd2watcher.db-shm` if they exist) with the SSH window's **Upload file** button, and move them into place:

```sh
mkdir -p data && mv ~/bd2watcher.db* data/
```

Without the database, the first check of each source is a fresh silent baseline, so no flood of alerts. You only lose history.

### 4. Start it and publish the dashboard to your tailnet

```sh
docker compose up -d --build
sudo tailscale serve --bg 8080
tailscale serve status    # shows the private address, e.g. https://bd2-watcher.<your-tailnet>.ts.net
```

Open that address on your phone or PC with Tailscale on. `tailscale serve --bg` and the container's `restart: unless-stopped` both survive reboots. Run `sudo reboot`, wait a minute, and check the dashboard again.

### 5. Check that it's private

- On the server, run `sudo ss -tlnp | grep 8080`. Every line must show `127.0.0.1:8080`, never `0.0.0.0:8080` or `*:8080`. This is the check that matters: Google's firewall would hide a mistake from an outside test.
- From a device **not** on Tailscale (e.g. your phone with Tailscale switched off), try `http://<the server's external IP>:8080`. It must time out.
- With Tailscale on, the `ts.net` address loads the dashboard.
- `docker compose logs -f` shows the checks. Send a test alert with `docker compose run --rm bd2watcher bd2watcher send-test-alert discord`.

### Updating later

```sh
cd bd2-ws-watcher && git pull && docker compose up -d --build
```

## Option B: Hetzner (about €5–6 a month)

If Google's free tier doesn't work out, a Hetzner Cloud server is the cheapest reliable option. Prices changed during 2026, so check https://www.hetzner.com/cloud.

1. Create a server in **Hillsboro, OR (us-west)** or Ashburn, VA, with the smallest shared-CPU type and Debian 12, and add your SSH key.
2. Under **Firewalls**, create one that allows only inbound SSH (TCP 22) and Tailscale (UDP 41641), and attach it. Without the UDP rule, Tailscale still works but routes through its relays, which is slower.
3. SSH in and follow steps 2 to 5 above (the swap step is optional, since Hetzner's smallest server has more memory).
