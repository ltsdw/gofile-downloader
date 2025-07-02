#! /usr/bin/env python3


from os import chdir, getcwd, getenv, listdir, mkdir, path, rmdir
from sys import exit, stdout, stderr
from typing import Any, Iterator, NoReturn, TextIO
from requests import Session, Timeout
from requests.structures import CaseInsensitiveDict
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from platform import system
from hashlib import sha256
from shutil import move
from time import perf_counter


NEW_LINE: str = "\n" if system() != "Windows" else "\r\n"


def _print(msg: str, error: bool = False) -> None:
    """
    _print

    Print a message.

    :param msg: a string to be printed.
    :param error: if the error stream output should be used instead of the standard output.
    :return:
    """

    output: TextIO = stderr if error else stdout
    output.write(msg)
    output.flush()


def die(msg: str) -> NoReturn:
    """
    die

    Display a message of error and exit.

    :param msg: a string to be printed.
    :return:
    """

    _print(f"{msg}{NEW_LINE}", True)
    exit(-1)


class Main:
    def __init__(self, url: str, password: str | None = None) -> None:
        root_dir: str | None = getenv("GF_DOWNLOADDIR")
        token: str | None = getenv("GF_TOKEN")
        # Defaults to 5 concurrent downloads
        self._max_workers: int = int(getenv("GF_MAX_CONCURRENT_DOWNLOADS", 5))
        # Defaults to 5 retries
        self._number_retries: int = int(getenv("GF_MAX_RETRIES", 5))
        # Connection and read timeout, defaults to 15 seconds
        self._timeout: float = float(getenv("GF_TIMEOUT", 15.0))
        self._user_agent: str | None = getenv("GF_USERAGENT")
        self._interactive: bool = getenv("GF_INTERACTIVE") == "1"
        # The number of bytes it should read into memory
        self._chunk_size: int = int(getenv("GF_CHUNK_SIZE", 2097152))

        if root_dir and path.exists(root_dir):
            chdir(root_dir)

        self._session: Session = Session()
        self._lock: Lock = Lock()
        self._message: str = " "
        self._content_dir: str | None = None
        self._root_dir: str = root_dir if root_dir else getcwd()
        self._headers: dict[str, str] = {
            "Accept-Encoding": "gzip",
            "User-Agent": self._user_agent if self._user_agent else "Mozilla/5.0",
            "Connection": "keep-alive",
            "Accept": "*/*",
        }

        # Dictionary to hold information about file and its directories structure
        # {"index": {"path": "", "filename": "", "link": ""}}
        # where the largest index is the top most file
        self._files_info: dict[str, dict[str, str]] = {}

        self._set_account_access_token(token)
        self._parse_url_or_file(url, password)


    def _threaded_downloads(self) -> None:
        """
        _threaded_downloads

        Parallelize the downloads.

        :return:
        """

        if not self._content_dir:
            _print(f"Content directory wasn't created, nothing done.{NEW_LINE}")
            return

        chdir(self._content_dir)

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            for item in self._files_info.values():
                executor.submit(self._download_content, item)

        chdir(self._root_dir)


    def _create_dir(self, dirname: str) -> None:
        """
        _create_dir

        creates a directory where the files will be saved if doesn't exist and change to it.

        :param dirname: name of the directory to be created.
        :return:
        """

        try:
            mkdir(dirname)
        # if the directory already exist is safe to do nothing
        except FileExistsError:
            pass


    def _set_account_access_token(self, token: str | None = None) -> None:
        """
        _set_account_access_token

        Get a new access token for the account created or use the token provided for an already existent account.

        :param token: token to be used accross connections if available.
        :return:
        """

        if token:
            self._headers["Cookie"] = f"accountToken={token}"
            self._headers["Authorization"] = f"Bearer {token}"
            return

        response: dict[Any, Any] = {}

        for _ in range(self._number_retries):
            try:
                response = self._session.post(
                    "https://api.gofile.io/accounts",
                    headers=self._headers,
                    timeout=self._timeout
                ).json()
            except Timeout:
                continue
            else:
                break

        if not response and response["status"] != "ok":
            die("Account creation failed!")

        self._headers["Cookie"] = f"accountToken={response["data"]["token"]}"
        self._headers["Authorization"] = f"Bearer {response["data"]["token"]}"


    def _download_content(self, file_info: dict[str, str]) -> None:
        """
        _download_content

        Requests the contents of the file and writes it.

        :param file_info: a dictionary with information about a file to be downloaded.
        :return:
        """

        filepath: str = path.join(file_info["path"], file_info["filename"])

        if self._should_skip_download(filepath):
            return

        tmp_file: str =  f"{filepath}.part"
        url: str = file_info["link"]

        # check for partial download and resume from last byte
        headers: dict[str, str] = self._headers.copy()
        if path.isfile(tmp_file):
            part_size = int(path.getsize(tmp_file))
            headers["Range"] = f"bytes={part_size}-"

        for _ in range(self._number_retries):
            try:
                part_size: int = 0
                if path.isfile(tmp_file):
                    part_size = int(path.getsize(tmp_file))
                    headers["Range"] = f"bytes={part_size}-"

                has_size: str | None = self._perform_download(
                    file_info,
                    url,
                    tmp_file,
                    headers,
                    part_size
                )
            except Timeout:
                continue
            else:
                if has_size:
                    self._finalize_download(file_info, tmp_file, has_size)
                break


    @staticmethod
    def _should_skip_download(filepath: str) -> bool:
        """
        _should_skip_download

        Checks if a file already exists and has non-zero size.

        :param filepath: filepath.
        :return: True if download should be skipped, False otherwise.
        """

        if path.exists(filepath) and path.getsize(filepath) > 0:
            _print(f"{filepath} already exist, skipping.{NEW_LINE}")
            return True
        return False


    def _perform_download(
        self,
        file_info: dict[str, str],
        url: str,
        tmp_file: str,
        headers: dict[str, str],
        part_size: int,
    ) -> str | None:
        """
        _perform_download

        Executes the HTTP GET request, processes file chunks, and tracks progress.

        :param file_info: a dictionary containing file details.
        :param url: the file download URL.
        :param tmp_file: temporary file path for partial downloads.
        :param headers: request headers.
        :param part_size: the current partial file size.
        :return: the total file size (if available).
        """

        with self._session.get(url, headers=headers, stream=True, timeout=self._timeout) as response:
            status_code: int = response.status_code

            if not self._is_valid_response(response.status_code, part_size):
                _print(
                    f"Couldn't download the file from {url}.{NEW_LINE}"
                    f"Status code: {status_code}{NEW_LINE}"
                )
                return None

            has_size: str | None = self._extract_file_size(response.headers, part_size, url, status_code)

            if not has_size:
                return None

            self._write_chunks(
                response.iter_content(chunk_size=self._chunk_size),
                tmp_file,
                part_size,
                float(has_size),
                file_info["filename"]
            )

            return has_size


    #@staticmethod
    def _is_valid_response(self, status_code: int, part_size: int) -> bool:
        """
        _is_valid_response

        Validates HTTP status code based on partial download state.

        :param status_code: the HTTP status code.
        :param part_size: the current partial file size.
        :return: True if status code is acceptable, False otherwise.
        """

        if status_code in (403, 404, 405, 500):
            return False
        if part_size == 0 and status_code != 200:
            return False
        if part_size > 0 and status_code != 206:
            return False
        return True


    @staticmethod
    def _extract_file_size(
        headers: CaseInsensitiveDict[str], part_size: int, url: str, status_code: int
    ) -> str | None:
        """
        _extract_file_size

        Retrieves the file size from HTTP headers.

        :param headers: the HTTP response headers.
        :param part_size: the current partial file size.
        :param url: the request URL.
        :param status_code: the HTTP status code.
        :return: the total file size as a string, or None if unavailable.
        """

        content_length: str | None = headers.get("Content-Length")
        content_range: str | None = headers.get("Content-Range")
        has_size: str | None = (
            content_length if part_size == 0
            else content_range.split("/")[-1] if content_range
            else None
        )

        if not has_size:
            _print(
                f"Couldn't find the file size from {url}.{NEW_LINE}"
                f"Status code: {status_code}{NEW_LINE}"
            )

        return has_size


    def _write_chunks(
        self,
        chunks: Iterator[Any],
        tmp_file: str,
        part_size: int,
        total_size: float,
        filename: str
    ) -> None:
        """
        _write_chunks

        Iterates over download chunks and writes them to disk, updating progress.

        :param chunks: a generator of byte chunks.
        :param tmp_file: temporary file path.
        :param part_size: number of bytes already downloaded.
        :param total_size: total file size in bytes.
        :param filename: the file's name.
        :return:
        """

        start_time: float = perf_counter()

        with open(tmp_file, "ab") as f:
            for i, chunk in enumerate(chunks):
                f.write(chunk)
                self._update_progress(filename, part_size, i, chunk, total_size, start_time)


    def _update_progress(
        self,
        filename: str,
        part_size: int,
        i: int,
        chunk: bytes,
        total_size: float,
        start_time: float
    ) -> None:
        """
        _update_progress

        Calculates and displays download progress and transfer rate.

        :param filename: the name of the file being downloaded.
        :param part_size: initial file size in bytes.
        :param i: current iteration number.
        :param chunk: the downloaded byte chunk.
        :param total_size: total file size.
        :param start_time: download start time.
        :return:
        """

        progress: float = (part_size + (i * len(chunk))) / total_size * 100
        rate: float = (i * len(chunk)) / (perf_counter() - start_time)

        unit: str = "B/s"
        if rate < 1024:
            unit = "B/s"
        elif rate < (1024 ** 2):
            rate /= 1024
            unit = "KB/s"
        elif rate < (1024 ** 3):
            rate /= (1024 ** 2)
            unit = "MB/s"
        else:
            rate /= (1024 ** 3)
            unit = "GB/s"

        with self._lock:
            _print(f"\r{' ' * len(self._message)}")
            self._message = (
                f"\rDownloading {filename}: {part_size + i * len(chunk)} "
                f"of {int(total_size)} {round(progress, 1)}% {round(rate, 1)}{unit}"
            )
            _print(self._message)


    def _finalize_download(self, file_info: dict[str, str], tmp_file: str, has_size: str) -> None:
        """
        _finalize_download

        Verifies the final file size and moves the temporary file to its destination.

        :param file_info: a dictionary containing file details.
        :param tmp_file: temporary file path.
        :param has_size: expected file size.
        :return:
        """

        with self._lock:
            if path.getsize(tmp_file) == int(has_size):
                _print(f"\r{' ' * len(self._message)}")
                _print(
                    f"\rDownloading {file_info['filename']}: {path.getsize(tmp_file)} "
                    f"of {has_size} Done!{NEW_LINE}"
                )
                move(tmp_file, path.join(file_info["path"], file_info["filename"]))


    def _parse_links_recursively(
        self,
        content_id: str,
        password: str | None = None,
        pathing_count: dict[str, int] = {},
        recursive_files_index: dict[str, int] = {"index": 0}
    ) -> None:
        """
        _parse_links_recursively

        Parses for possible links recursively and populate a list with file's info
        while also creating directories and subdirectories.

        :param content_id: url to the content.
        :param password: content's password.
        :param pathing_count: pointer-like object for keeping track of naming collision of pathing (filepaths and
                              directories) should only be internally used by this function to keep object state track.
        :param recursive_files_index: pointer-like object for keeping track of files indeces,
                                      should only be internally used by this function toakeep object state track.
        :return:
        """

        response: dict[Any, Any] = {}
        url: str = f"https://api.gofile.io/contents/{content_id}?wt=4fd6sg89d7s6&cache=true&sortField=createTime&sortDirection=1"

        if password:
            url = f"{url}&password={password}"

        for _ in range(self._number_retries):
            try:
                response = self._session.get(url, headers=self._headers, timeout=self._timeout).json()
            except Timeout:
                continue
            else:
                break

        if not response or response["status"] != "ok":
            _print(f"Failed to get a link as response from the {url}.{NEW_LINE}")
            return

        data: dict[Any, Any] = response["data"]

        if "password" in data and "passwordStatus" in data and data["passwordStatus"] != "passwordOk":
            _print(f"Password protected link. Please provide the password.{NEW_LINE}")
            return

        if data["type"] != "folder":
            current_dir: str = getcwd()
            filename: str = data["name"]
            recursive_files_index["index"] += 1
            filepath: str = path.join(current_dir, filename)

            if filepath in pathing_count:
                pathing_count[filepath] += 1
            else:
                pathing_count[filepath] = 0

            if pathing_count and pathing_count[filepath] > 0:
                extension: str
                filename, extension = path.splitext(filename)
                filename = f"{filename}({pathing_count[filepath]}){extension}"

            self._files_info[str(recursive_files_index["index"])] = {
                "path": current_dir,
                "filename": filename,
                "link": data["link"]
            }

            return

        # Do not use the default root directory named "root" created by gofile,
        # the naming may clash if another url link uses the same "root" name.
        # And if the root directory isn't named as the content id
        # create such a directory before proceeding
        folder_name: str = data["name"]

        if not self._content_dir and folder_name != content_id:
            self._content_dir = path.join(self._root_dir, content_id)

            self._create_dir(self._content_dir)
            chdir(self._content_dir)
        elif not self._content_dir and folder_name == content_id:
            self._content_dir = path.join(self._root_dir, content_id)
            self._create_dir(self._content_dir)

        # Only create subdirectories after the content directory is already created
        absolute_path: str = path.join(getcwd(), folder_name)

        if absolute_path in pathing_count:
            pathing_count[absolute_path] += 1
        else:
            pathing_count[absolute_path] = 0

        if pathing_count and pathing_count[absolute_path] > 0:
            absolute_path = f"{absolute_path}({pathing_count[absolute_path]})"

        self._create_dir(absolute_path)
        chdir(absolute_path)

        for child_id in data["children"]:
            child: dict[Any, Any] = data["children"][child_id]

            if child["type"] == "folder":
                self._parse_links_recursively(child["id"], password, pathing_count, recursive_files_index)
            else:
                current_dir: str = getcwd()
                filename: str = child["name"]
                recursive_files_index["index"] += 1
                filepath: str = path.join(current_dir, filename)

                if filepath in pathing_count:
                    pathing_count[filepath] += 1
                else:
                    pathing_count[filepath] = 0

                if pathing_count and pathing_count[filepath] > 0:
                    extension: str
                    filename, extension = path.splitext(filename)
                    filename = f"{filename}({pathing_count[filepath]}){extension}"

                self._files_info[str(recursive_files_index["index"])] = {
                    "path": current_dir,
                    "filename": filename,
                    "link": child["link"]
                }

        chdir(path.pardir)


    def _print_list_files(self) -> None:
        """
        _print_list_files

        Helper function to display a list of all files for selection.

        :return:
        """

        MAX_FILENAME_CHARACTERS: int = 100
        width: int = max(len(f"[{v}] -> ") for v in self._files_info.keys())

        for (k, v) in self._files_info.items():
            # Trim the filepath if it's too long
            filepath: str = path.join(v["path"], v["filename"])
            filepath = f"...{filepath[-MAX_FILENAME_CHARACTERS:]}" \
                if len(filepath) > MAX_FILENAME_CHARACTERS \
                else filepath

            text: str =  f"{f'[{k}] -> '.ljust(width)}{filepath}"

            _print(f"{text}{NEW_LINE}"
                   f"{'-' * len(text)}"
                   f"{NEW_LINE}"
            )


    def _download(self, url: str, password: str | None = None) -> None:
        """
        _download

        Requests to start downloading files.

        :param url: url of the content.
        :param password: content's password.
        :return:
        """

        try:
            if not url.split("/")[-2] == "d":
                _print(f"The url probably doesn't have an id in it: {url}.{NEW_LINE}")
                return

            content_id: str = url.split("/")[-1]
        except IndexError:
            _print(f"{url} doesn't seem a valid url.{NEW_LINE}")
            return

        _password: str | None = sha256(password.encode()).hexdigest() if password else password

        self._parse_links_recursively(content_id, _password)

        # probably the link is broken so the content dir wasn't even created.
        if not self._content_dir:
            _print(f"No content directory created for url: {url}, nothing done.{NEW_LINE}")
            self._reset_class_properties()
            return

        # removes the root content directory if there's no file or subdirectory
        if not listdir(self._content_dir) and not self._files_info:
            _print(f"Empty directory for url: {url}, nothing done.{NEW_LINE}")
            rmdir(self._content_dir)
            self._reset_class_properties()
            return

        if self._interactive:
            self._print_list_files()

            input_list: list[str] = input(
                f"Files to download (Ex: 1 3 7 | or leave empty to download them all)"
                f"{NEW_LINE}"
                f":: "
            ).split()
            input_list = list(set(input_list) & set(self._files_info.keys())) # ensure only valid index strings are stored

            if not input_list:
                _print(f"Nothing done.{NEW_LINE}")
                rmdir(self._content_dir)
                self._reset_class_properties()
                return

            keys_to_delete: list[str] = list(set(self._files_info.keys()) - set(input_list))

            for key in keys_to_delete:
                del self._files_info[key]

        self._threaded_downloads()
        self._reset_class_properties()


    def _parse_url_or_file(self, url_or_file: str, _password: str | None = None) -> None:
        """
        _parse_url_or_file

        Parses a file or a url for possible links.

        :param url_or_file: a filename with urls to be downloaded or a single url.
        :param password: password to be used across all links, if not provided a per link password may be used.
        :return:
        """

        if not (path.exists(url_or_file) and path.isfile(url_or_file)):
            self._download(url_or_file, _password)
            return

        with open(url_or_file, "r") as f:
            lines: list[str] = f.readlines()

        for line in lines:
            line_splitted: list[str] = line.split(" ")
            url: str = line_splitted[0].strip()
            password: str | None = _password if _password else line_splitted[1].strip() \
                if len(line_splitted) > 1 else _password

            self._download(url, password)


    def _reset_class_properties(self) -> None:
        """
        _reset_class_properties

        Simply put the properties of the class to be used again for another link if necessary.
        This should be called after all jobs related to a link is done.

        :return:
        """

        self._message: str = " "
        self._content_dir: str | None = None
        self._files_info.clear()


if __name__ == "__main__":
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
            _print(f"Starting, please wait...{NEW_LINE}")
            Main(url=url, password=password)
        else:
            die(f"Usage:"
                f"{NEW_LINE}"
                f"python gofile-downloader.py https://gofile.io/d/contentid"
                f"{NEW_LINE}"
                f"python gofile-downloader.py https://gofile.io/d/contentid password"
            )
    except KeyboardInterrupt:
        exit(1)

