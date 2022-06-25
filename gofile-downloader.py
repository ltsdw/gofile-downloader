from urllib.request import Request, urlopen
from urllib.error import URLError
from bs4 import BeautifulSoup, ResultSet, Tag, NavigableString
from os import path, mkdir, getcwd, chdir
from sys import exit, stdout
from typing import Any, List, Dict, Generator
from requests import get
from urllib.request import Request, urlopen


class Main:
    def __init__(self, url: str) -> None:

        url = url.replace("https://", "").replace("http://", "")

        self.id: str = url[len("gofile.io/d/"):]
        self.token: str = self._getToken()
        self.url: str = f"https://api.gofile.io/getContent?contentId={self.id}&token={self.token}&websiteToken=12345&cache=true"

        self._createDir(self.id)

        [self._downloadContent(link, self.token) for link in self._getLinks(self.url)]


    @staticmethod
    def _createDir(id: str) -> None:
        """
        creates a directory where the files will be saved if doesn't exist and change to it.

        :param id: content of the id.
        :return:
        """

        current_dir: str = getcwd()

        filepath: str = path.join(current_dir, id)

        try:
            mkdir(path.join(filepath))
        # if the directory already exist is safe to do nothing
        except FileExistsError:
            pass

        chdir(filepath)


    @staticmethod
    def _getToken() -> str:
        """
        :return: The access token of an account. Or exit if account creating fail.
        """


        create_account_response: Dict = get("https://api.gofile.io/createAccount").json()
        api_token = create_account_response["data"]["token"]
        
        account_response: Dict = get("https://api.gofile.io/getAccountDetails?token=" + api_token).json()

        if account_response["status"] != 'ok':
            print("Account creating failed!")
            exit(-1)    

        return api_token


    @staticmethod
    def _downloadContent(url: str, token: str, chunk_size: int = 4096) -> None:
        """
        Download the content of the url.

        :param url: url to the content.
        :param token: the access token of the account.
        :param chunk_size: the number of bytes it should read into memory.
        :return:
        """

        filename = url.split('/')[-1]
        filename = filename.replace("%20", ' ')

        if path.exists(filename):
            print(f"{filename} already exist, skipping.")

            return

        print(f"Downloading {filename}")

        headers: Dict = {
            "Cookie": "accountToken=" + token,
            "Accept-Encoding": "gzip, deflate, br",
            "User-Agent": "Mozilla/5.0",
            "Accept": "*/*",
            "Referer": url + ("/" if not url.endswith("/") else ""),
            "Origin": url,
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache"
        }

        with get(url, headers=headers, stream=True) as response_handler:
            if response_handler.status_code in (403, 404, 405, 500):
                print(f"Couldn't download the file from {url}.\nStatus code: {response_handler.status_code}")
                return
            with open(filename, 'wb+') as handler:
                has_size: str | None = response_handler.headers.get('Content-Length')

                total_size: float

                if has_size:
                    total_size = float(has_size)
                else:
                    print(f"{filename} has no content.")
                    return

                for i, chunk in enumerate(response_handler.iter_content(chunk_size=chunk_size)):
                    progress: float = i * chunk_size / total_size * 100

                    handler.write(chunk)

                    stdout.write(f"\r{round(progress, 1)}%")
                    stdout.flush()

                stdout.write("\n")
                stdout.flush()


    @staticmethod
    def _getLinks(url: str) -> Generator[str, None, None]:
        """
        Yields each and every link of an url.

        :param url: url to the content.
        :return: an generator of type string, the file link. 
        """


        response: Dict = get(url).json()

        data: Dict = response["data"]
        if "contents" in data.keys():
            contents: Dict = data["contents"]

            for content in contents.values():
                yield content["link"]

        else:
            print(data)
            print(f"Failed to get a link as response from the {url}")
            exit(-1)


if __name__ == '__main__':
    print('Starting, please wait...')

    try:
        from sys import argv


        url: str


        try:
            url = argv[1]
        except IndexError:
            print("specify an url, like: ./gofile-downloader.py https://gofile.io/d/contentid")
            exit(-1)


        Main(url=url)


    except KeyboardInterrupt:
        exit(1)

