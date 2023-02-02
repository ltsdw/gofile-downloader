# gofile-downloader
Download files from https://gofile.io

# Requirements
```
pip install -r requirements.txt
```

# Usage
```
python gofile-downloader.py https://gofile.io/d/contentid
```

If it has password:
```
python gofile-downloader.py https://gofile.io/d/contentid password
```

Use the environment variable **`GF_DOWNLOADDIR`** to specify where to download to (the
path must exist already):
```
GF_DOWNLOADDIR="/path/to/the/directory" python gofile-downloader.py https://gofile.io/d/contentid

```
