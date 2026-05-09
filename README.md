# gofile-downloader

Download files from https://gofile.io

---

#### Requirements

- Python version 3.10 or newer.
- **[uv](https://docs.astral.sh/uv/getting-started/installation/)**: A blazing-fast Python package and project manager. (If you have pip installed, you can use it to install uv: `pip install uv`)

---

#### Dependencies

With `uv`, you don't need to manually install dependencies or manage virtual environments. The `uv run` command handles everything automatically on the fly.

_(Optional: If you just want to install the dependencies without running the script, use `uv sync`)_

---

#### Usage

```
uv run gofile-downloader.py https://gofile.io/d/contentid
```

If it has password:

```
uv run gofile-downloader.py https://gofile.io/d/contentid password
```

If you have a text file with multiple urls:

```
https://gofile.io/d/contentid1
https://gofile.io/d/contentid2
https://gofile.io/d/contentid3
https://gofile.io/d/contentid4
```

```
uv run gofile-downloader.py my-urls.txt
```

If you specify a password, this password will be used for ALL urls provided in the text file:

```
uv run gofile-downloader.py my-urls.txt password
```

It's possible to provide per link password, just don't pass the password altogether, provide the password in the text file separated by a space.

```
https://gofile.io/d/contentid1 password1
https://gofile.io/d/contentid2
https://gofile.io/d/contentid3
https://gofile.io/d/contentid4 password4
```

---

#### Environment Variables

The script behavior can be customized using environment variables. Instead of passing them via your terminal (which changes depending on your OS), you can simply create a `.env` file in the root directory of this project. `uv` will load them automatically.

Create a `.env` file and set your desired configurations:

```env
# Specify where to download to (the path must exist already)
GF_DOWNLOAD_DIR="./downloads"

# Toggle manual file selection to download (1 for True)
GF_INTERACTIVE="1"

# Specify a specific account token
GF_TOKEN="your_account_token_here"

# Configure the maximum number of concurrent downloads
GF_MAX_CONCURRENT_DOWNLOADS="5"

# Configure the number of retries on timeout
GF_MAX_RETRIES="5"

# Configure a timeout for connections (in seconds)
GF_TIMEOUT="15.0"

# Configure the number of bytes read per chunk
GF_CHUNK_SIZE="2097152"

# Specify browser user agent (defaults Mozilla/5.0)
GF_USERAGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64)..."
```
