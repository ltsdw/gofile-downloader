#! /usr/bin/env python3


from os import path, mkdir, getcwd, chdir, getenv
from sys import exit, stdout, stderr
from typing import Dict, List
from requests import get
from concurrent.futures import ThreadPoolExecutor
from platform import system
from hashlib import sha256
from uuid import uuid4
from shutil import move, rmtree


NEW_LINE: str = "\n" if system() != "Windows" else "\r\n"


def die(_str: str) -> None:
    """
    Display a message of error and exit.

    :param _str: a string to be printed.
    :return:
    """


    stderr.write(_str + NEW_LINE)
    stderr.flush()

    exit(-1)


def _print(_str: str) -> None:
    """
    Print a message.

    :param _str: a string to be printed.
    :return:
    """


    stdout.write(_str)
    stdout.flush()


# increase max_workers for parallel downloads
# defaults to 5 download at time
class Main:
    def __init__(self, url: str, password: str | None = None, max_workers: int = 5) -> None:


        try:
            if not url.split("/")[-2] == "d":
                die(f"The url probably doesn't have an id in it: {url}")

            self._id: str = url.split("/")[-1]
        except IndexError:
            die(f"Something is wrong with the url: {url}.")


        self._downloaddir: str | None = getenv("GF_DOWNLOADDIR")

        if self._downloaddir and path.exists(self._downloaddir):
            chdir(self._downloaddir)

        self._root_dir: str = path.join(getcwd(), self._id)
        self._token: str = self._getToken()
        self._url: str = f"https://api.gofile.io/getContent?contentId={self._id}&token={self._token}&websiteToken=12345&cache=true"
        self._password: str | None = sha256(password.encode()).hexdigest() if password else None
        self._max_workers: int = max_workers

        # list of files and its respective path, uuid, filename and link
        self._files_link_list: List[Dict] = []

        self._createDir(self._id)

        self._parseLinks(self._id, self._token, self._password)

        self._threadedDownloads()


    def _threadedDownloads(self) -> None:
        """
        Parallelize the downloads.

        :return:
        """

        chdir(self._root_dir)

        self._createDir("tmp-dir")

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            for item in self._files_link_list:
                executor.submit(self._downloadContent, item, self._token)

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            for item in self._files_link_list:
                if path.exists(item["uuid"]):
                    move(item["uuid"], item["path"])

        chdir(self._root_dir)

        rmtree("tmp-dir")


    def _createDir(self, dirname: str) -> None:
        """
        creates a directory where the files will be saved if doesn't exist and change to it.

        :param dirname: name of the directory to be created.
        :return:
        """

        current_dir: str = getcwd()

        filepath: str = path.join(current_dir, dirname)

        try:
            mkdir(path.join(filepath))
        # if the directory already exist is safe to do nothing
        except FileExistsError:
            pass

        chdir(filepath)


    @staticmethod
    def _getToken() -> str:
        """
        Gets the access token of account created.

        :return: The access token of an account. Or exit if account creation fail.
        """


        create_account_response: Dict = get("https://api.gofile.io/createAccount").json()
        api_token = create_account_response["data"]["token"]
        
        account_response: Dict = get("https://api.gofile.io/getAccountDetails?token=" + api_token).json()

        if account_response["status"] != 'ok':
            die("Account creation failed!")

        return api_token


    @staticmethod
    def _downloadContent(file_info: Dict, token: str, chunk_size: int = 4096) -> None:
        """
        Download a file.

        :param file_info: a dictionary with information about a file to be downloaded.
        :param token: the access token of the account.
        :param chunk_size: the number of bytes it should read into memory.
        :return:
        """


        uuid: str = file_info["uuid"]
        filename: str = file_info["filename"]
        url: str = file_info["link"]

        if path.exists(file_info["path"]):
            if path.getsize(file_info["path"]) > 0:
                _print(f"{filename} already exist, skipping." + NEW_LINE)

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
                _print(
                    f"Couldn't download the file from {url}."
                    + NEW_LINE
                    + "Status code: {response_handler.status_code}"
                    + NEW_LINE
                )

                return

            with open(uuid, 'wb+') as handler:
                has_size: str | None = response_handler.headers.get('Content-Length')

                total_size: float

                if has_size:
                    total_size = float(has_size)
                else:
                    return

                for i, chunk in enumerate(response_handler.iter_content(chunk_size=chunk_size)):
                    progress: float = i * chunk_size / total_size * 100

                    handler.write(chunk)

                    _print(f"\rDownloading {filename}: {round(progress, 1)}%")

                _print(f"\rDownloaded {filename}: 100.0%!" + NEW_LINE)


    def _parseLinks(self, _id: str, token: str, password: str | None = None) -> None:
        """
        Parses for possible links recursively and populate a list with file's info.

        :param _id: url to the content.
        :param token: access token.
        :param password: content's password.
        :return:
        """


        url: str = f"https://api.gofile.io/getContent?contentId={_id}&token={token}&websiteToken=12345&cache=true"

        if password:
            url = url + f"&password={password}"

        response: Dict = get(url).json()

        data: Dict = response["data"]

        if "contents" in data.keys():
            contents: Dict = data["contents"]

            for content in contents.values():
                if content["type"] == "folder":
                    self._createDir(content["name"])

                    self._parseLinks(content["id"], token, password)

                    chdir(path.pardir)

                else:
                    self._files_link_list.append(
                        {
                            "path": path.join(getcwd(), content["name"]),
                            "uuid": str(uuid4()),
                            "filename": content["name"],
                            "link": content["link"]
                        }
                    )

        else:
            die(f"Failed to get a link as response from the {url}")


if __name__ == '__main__':
    try:
        from sys import argv


        url: str | None = None
        password: str | None = None

        argc: int = len(argv)

        if argc > 1:
            url = argv[1]

            if argc > 2:
                password = argv[2]


            # Run
            _print('Starting, please wait...' + NEW_LINE)
            Main(url=url, password=password)
        else:
            die("Usage:"
                + NEW_LINE
                + "python gofile-downloader.py https://gofile.io/d/contentid"
                + NEW_LINE
                + "python gofile-downloader.py https://gofile.io/d/contentid password"
            )
    except KeyboardInterrupt:
        exit(1)

