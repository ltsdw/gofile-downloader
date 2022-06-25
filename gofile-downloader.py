from os import path, mkdir, getcwd, chdir
from sys import exit, stdout, stderr
from typing import Dict, Generator
from requests import get
from concurrent.futures import ThreadPoolExecutor
from platform import system


NEW_LINE: str = "\n"


if system() == "Windows":
    NEW_LINE = "\r\n"


def die(message: str) -> None:
    """
    Display a message of error and exit.

    :param message: message to be displayed.
    :return:
    """


    stderr.write(message + NEW_LINE)
    stderr.flush()

    exit(-1)


# increase _max_workers for multiple parallel downloads
# defaults to one download at time
class Main:
    def __init__(self, url: str, _max_workers: int = 1) -> None:

        url = url.replace("https://", "").replace("http://", "")

        self.id: str = url[len("gofile.io/d/"):]
        self.token: str = self._getToken()
        self.url: str = f"https://api.gofile.io/getContent?contentId={self.id}&token={self.token}&websiteToken=12345&cache=true"

        self._createDir(self.id)

        self._threadedDownloads(_max_workers)


    def _threadedDownloads(self, max_workers: int) -> None:
        """
        Parallelize the downloads.
        :param max_workers: the max thread number.
        :return:
        """

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for link in self._getLinks(self.url):
                executor.submit(self._downloadContent, link, self.token)


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
        :return: The access token of an account. Or exit if account creation fail.
        """


        create_account_response: Dict = get("https://api.gofile.io/createAccount").json()
        api_token = create_account_response["data"]["token"]
        
        account_response: Dict = get("https://api.gofile.io/getAccountDetails?token=" + api_token).json()

        if account_response["status"] != 'ok':
            die("Account creating failed!")

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
                print(f"Couldn't download the file from {url}." + NEW_LINE + "Status code: {response_handler.status_code}")
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

                    stdout.write(f"\rDownloading {filename}: {round(progress, 1)}%")
                    stdout.flush()

                stdout.write(f"\rDownloaded {filename}: 100.0%!" + NEW_LINE)
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
            die(f"Failed to get a link as response from the {url}")


if __name__ == '__main__':
    print('Starting, please wait...')

    try:
        from sys import argv


        url: str


        try:
            url = argv[1]
            Main(url=url)
        except IndexError:
            die("specify an url, like: ./gofile-downloader.py https://gofile.io/d/contentid")

    except KeyboardInterrupt:
        exit(1)

