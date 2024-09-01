# gofile-downloader
Download files from https://gofile.io

# Requirements

Python version 3.10 or newer.

Modules:

```
pip3 install -r requirements.txt
```

# Usage
```
python gofile-downloader.py https://gofile.io/d/contentid
```

If it has password:
```
python gofile-downloader.py https://gofile.io/d/contentid password
```

If you have a text file with multiple urls:
```
https://gofile.io/d/contentid1
https://gofile.io/d/contentid2
https://gofile.io/d/contentid3
https://gofile.io/d/contentid4
```
```
python gofile-downloader.py my-urls.txt
```

If you specify a password, this password will be used for ALL urls provided in the text file:
```
python gofile-downloader.py my-urls.txt password
```

It's possible to provide per link password, just don't pass the password altogether, provide the password in the text file separated by a space.

**my-url.txt**:
```
https://gofile.io/d/contentid1 password1
https://gofile.io/d/contentid2
https://gofile.io/d/contentid3
https://gofile.io/d/contentid4 password4
```

Use the environment variable **`GF_DOWNLOADDIR`** to specify where to download to (the
path must exist already):
```
GF_DOWNLOADDIR="/path/to/the/directory" python gofile-downloader.py https://gofile.io/d/contentid

```

Use the environment variable **`GF_USERAGENT`** to specify browser user agent (default Mozilla/5.0):
```
GF_USERAGENT="user agent string" python gofile-downloader.py https://gofile.io/d/contentid

```

Use the environment variable **`GF_TOKEN`** to specify a specific account token:
```
GF_TOKEN="account_token string" python gofile-downloader.py https://gofile.io/d/contentid

```

Use the environment variable **`GF_INTERACTIVE`** to toggle manual file selection to download:
```
GF_INTERACTIVE="1" python gofile-downloader.py https://gofile.io/d/contentid

```
