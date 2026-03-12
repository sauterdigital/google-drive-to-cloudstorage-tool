# Drive to Cloud Storage

A command-line tool to transfer files from **Google Drive** to **Google Cloud Storage (GCS)**, with colored terminal output and a Drive-logo ASCII banner.

---

## Requirements

- Python 3.10+
- [Google Cloud SDK (`gcloud`)](https://cloud.google.com/sdk/docs/install) — needed for authentication

---

## Installation

```bash
# Clone or navigate to the project directory
cd google-drive-to-cloudstorage-tool

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\Activate.ps1       # Windows (PowerShell)

# Install the package
pip install -e .
```

---

## Authentication

Before transferring files, authenticate once with your Google account:

```bash
gdrive-to-gcs auth login --project YOUR_GCP_PROJECT_ID
```

This runs `gcloud auth application-default login`, opens a browser for you to sign in, and stores credentials locally. You only need to do this once per machine.

> **Note:** The `--project` flag sets the GCP billing/quota project. If your `gcloud` CLI already has a default project configured, it can be omitted.

---

## Usage

### Transfer by Drive folder path

```bash
gdrive-to-gcs transfer --drive-folder "My Drive/Reports" --bucket my-gcs-bucket
```

### Transfer by Drive folder ID

```bash
gdrive-to-gcs transfer --folder-id 1A2B3C4D5E --bucket my-gcs-bucket
```

### With all options

```bash
gdrive-to-gcs transfer \
  --drive-folder "My Drive/Reports/2025" \
  --bucket my-gcs-bucket \
  --prefix backups/reports/ \
  --project my-gcp-project
```

---

## Options

| Flag | Alias | Description |
|------|-------|-------------|
| `--drive-folder PATH` | `-d` | Google Drive folder path (e.g. `My Drive/Data`) |
| `--folder-id ID` | `-f` | Google Drive folder ID (found in the Drive URL) |
| `--bucket NAME` | `-b` | Destination GCS bucket name **(required)** |
| `--prefix PREFIX` | `-x` | Path prefix inside the bucket (optional) |
| `--project PROJECT_ID` | `-p` | GCP project ID (auto-detected if omitted) |

> Either `--drive-folder` or `--folder-id` must be provided.

---

## How it works

1. **Authentication** — loads existing Application Default Credentials (no interactive prompt after the first `auth login`).
2. **Folder resolution** — if `--drive-folder` is used, the path is resolved segment by segment via the Drive API.
3. **Recursive scan** — all files under the folder (including subfolders) are listed.
4. **Transfer** — each file is streamed from Drive and uploaded to GCS in 50 MB chunks. Already-existing blobs are skipped automatically.
5. **Summary** — transferred, skipped, and failed counts are printed at the end.

### Google Workspace files

Files created natively in Google Drive (Docs, Sheets, Slides, Drawings) cannot be downloaded directly. They are automatically exported:

| Drive type | Exported as |
|------------|-------------|
| Google Docs | PDF |
| Google Sheets | CSV |
| Google Slides | PDF |
| Google Drawings | PNG |

---

## Example output

```
                 **########=-                    ____       _           __
                ****#####*=---                  / __ \_____(_)   _____ / /____ 
               *******##*------                / / / / ___/ / | / / _ \  __/ _ \
              **********--------              / /_/ / /  / /| |/ /  __/ /_/  __/
             **********----------            /_____/_/  /_/ |___/\___/\__/\___/
            **********  ----------
          ***********    -----------              ___  __                __
          **********      ----------             / __\/ /___  __ _____/ /
        ***********        -----------          / /  / / _ \/ // / _  /
         #######*************++++++++          / /__/ / ___/\_,_/\_,_/
          #####***************++++++           \____/_/\___/
           ###*****************++++
            #*******************++

  › Loading credentials...
  ✓ Credentials loaded  (project: my-gcp-project)
  › Source  Reports  (1A2B3C4D5E)
  › Dest    gs://my-gcs-bucket/backups/reports/
  › Found 24 file(s)

  [1/24] OK    Q1-summary.pdf  (1.2 MB)
  [2/24] OK    data.csv  (340.0 KB)
  [3/24] SKIP  archive.zip
  ...

Transfer complete!
  Transferred : 23
  Skipped     : 1
  Total bytes : 45.3 MB
  Elapsed     : 12.4s
```

---

## Finding a folder ID

Open the folder in Google Drive in your browser. The URL will look like:

```
https://drive.google.com/drive/folders/1A2B3C4D5E6F7G8H9
```

The last segment (`1A2B3C4D5E6F7G8H9`) is the folder ID.

---

## License

MIT
