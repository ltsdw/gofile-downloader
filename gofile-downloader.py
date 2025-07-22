#! /usr/bin/env python3


from os import getcwd, getenv, listdir, makedirs, path, rmdir
from sys import exit, stdout, stderr
from typing import Any, Iterator, NoReturn, TextIO
from itertools import count
from requests import Session, Response, Timeout
from requests.structures import CaseInsensitiveDict
from concurrent.futures import ThreadPoolExecutor
from threading import Lock, Event
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


class Downloader:
    def __init__(self, url_or_file: str, password: str | None = None) -> None:
        root_dir: str | None = getenv("GF_DOWNLOAD_DIR")

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

        self._session: Session = Session()
        self._lock: Lock = Lock()
        self._stop_event: Event = Event()
        self._message: str = " "
        self._root_dir: str = root_dir if root_dir else getcwd()
        self._url_or_file: str = url_or_file
        self._password: str | None = password
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


    def _parse_url_or_file(self, url_or_file: str, _password: str | None = None) -> None:
        """
        _parse_url_or_file

        Parses a file or a url for possible links.

        :param url_or_file: a filename with urls to be downloaded or a single url.
        :param password: password to be used across all links, if not provided a per link password may be used.
        :return:
        """

        if not (path.exists(url_or_file) and path.isfile(url_or_file)):
            self._run(url_or_file, _password)
            return

        with open(url_or_file, "r") as f:
            lines: list[str] = f.readlines()

        for line in lines:
            line_splitted: list[str] = line.split(" ")
            url: str = line_splitted[0].strip()
            password: str | None = _password if _password else line_splitted[1].strip() \
                if len(line_splitted) > 1 else _password

            self._run(url, password)


    def _run(self, url: str, password: str | None = None) -> None:
        """
        _run

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

        content_dir: str = path.join(self._root_dir, content_id)
        self._build_content_tree_structure(content_dir, content_id, _password)

        # removes the root content directory if there's no file or subdirectory
        if not listdir(content_dir) and not self._files_info:
            _print(f"Empty directory for url: {url}, nothing done.{NEW_LINE}")
            self._remove_dir(content_dir)
            self._reset_class_properties()
            return

        if self._interactive:
            self._do_interactive(content_dir)

        self._threaded_downloads()
        self._reset_class_properties()


    def _get_response(self, **kwargs: Any) -> Response | None:
        """
        _get_response

        Auxiliary function for the requests.session.get.

        :param kwargs: arguments for the requests.session.get function.
        :return: requests.Response or None on requests.Timeout.
        """

        for _ in range(self._number_retries):
            try:
                return self._session.get(timeout=self._timeout, **kwargs)
            except Timeout:
                continue


    def _threaded_downloads(self) -> None:
        """
        _threaded_downloads

        Parallelize the downloads.

        :return:
        """

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            for item in self._files_info.values():
                if self._stop_event.is_set():
                    return

                executor.submit(self._download_content, item)


    def _create_dirs(self, dirname: str) -> None:
        """
        _create_dirs

        Creates a directory and its subdirectories recursively if they don't exist.

        :param dirname: name of the directory to be created.
        :return:
        """

        makedirs(dirname, exist_ok = True)


    def _remove_dir(self, dirname: str) -> None:
        """
        _remove_dir

        Removes a directory if it's empty ignoring any throw.

        :param dirname: name of the directory to be created.
        :return:
        """

        try:
            rmdir(dirname)
        except:
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

        self._headers["Cookie"] = f"accountToken={response['data']['token']}"
        self._headers["Authorization"] = f"Bearer {response['data']['token']}"


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

        if self._stop_event.is_set():
            return

        response: Response | None = self._get_response(url=url, headers=headers, stream=True)

        if not response:
            self._clear_message()
            _print(
                f"Couldn't download the file, failed to get a response from {url}.{NEW_LINE}"
            )
            return None

        with response:
            status_code: int = response.status_code

            if not self._is_valid_response(response.status_code, part_size):
                self._clear_message()
                _print(
                    f"Couldn't download the file from {url}.{NEW_LINE}"
                    f"Status code: {status_code}{NEW_LINE}"
                )
                return None

            has_size: str | None = self._extract_file_size(response.headers, part_size)

            if not has_size:
                self._clear_message()
                _print(
                    f"Couldn't find the file size from {url}.{NEW_LINE}"
                    f"Status code: {status_code}{NEW_LINE}"
                )
                return None

            self._write_chunks(
                response.iter_content(chunk_size=self._chunk_size),
                tmp_file,
                part_size,
                float(has_size),
                file_info["filename"]
            )

            return has_size


    @staticmethod
    def _is_valid_response(status_code: int, part_size: int) -> bool:
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
    def _extract_file_size(headers: CaseInsensitiveDict[str], part_size: int) -> str | None:
        """
        _extract_file_size

        Retrieves the file size from HTTP headers.

        :param headers: the HTTP response headers.
        :param part_size: the current partial file size.
        :return: the total file size as a string, or None if unavailable.
        """

        content_length: str | None = headers.get("Content-Length")
        content_range: str | None = headers.get("Content-Range")
        has_size: str | None = (
            content_length if part_size == 0
            else content_range.split("/")[-1] if content_range
            else None
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
                if self._stop_event.is_set():
                    return

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
            self._clear_message()
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


    def _register_file(self, file_index: count, filepath: str, file_url: str) -> None:
        """
        _register_file

        Registers file information into the internal files info dictionary
        (with sequential index, path, filename and download url).

        :param file_index: an itertools.count object used to sequentially index discovered files.
                           Acts as a mutable counter local to the parsing thread context.
                           Should not be modified outside this function.
        :param filepath: absolute or relative path to the file on the local filesystem.
        :param file_url: remote URL link for downloading the file.
        :return:
        """

        self._files_info[str(next(file_index))] = {
            "path": path.dirname(filepath),
            "filename": path.basename(filepath),
            "link": file_url
        }


    def _resolve_naming_collision(
        self,
        pathing_count: dict[str, int],
        absolute_parent_dir: str,
        child_name: str,
        is_dir: bool = False,
    ) -> str:
        """
        _resolve_naming_collision

        Ensures unique file or directory paths by checking and updating a naming collision
        tracker. If a collision is detected, appends a numeric suffix to the name to
        avoid overwriting existing paths.

        :param pathing_count: dictionary used to track the number of naming collisions
                              for each path encountered during traversal.
        :param absolute_parent_dir: absolute path to the parent directory where the child
                                    (file or directory) will be created.
        :param child_name: original name of the file or directory.
        :param is_dir: boolean flag indicating whether the child is a directory, defaults to False.
        :return: a unique filepath string with a numeric suffix appended if needed.
        """

        filepath: str = path.join(absolute_parent_dir, child_name)

        if filepath in pathing_count:
            pathing_count[filepath] += 1
        else:
            pathing_count[filepath] = 0

        if pathing_count and pathing_count[filepath] > 0 and is_dir:
            return f"{filepath}({pathing_count[filepath]})"

        if pathing_count and pathing_count[filepath] > 0:
            extension: str
            root, extension = path.splitext(filepath)

            return f"{root}({pathing_count[filepath]}){extension}"

        return filepath


    def _build_content_tree_structure(
        self,
        parent_dir: str,
        content_id: str,
        password: str | None = None,
        pathing_count: dict[str, int] | None = None,
        file_index: count = count(start=0, step=1)
    ) -> None:
        """
        _build_content_tree_structure

        Recursively traverses a remote content structure and builds a corresponding
        local directory tree (handling naming collisions), while registering files url.

        :param parent_dir: absolute path to the parent directory where the current content
                           directory or file should be created.
        :param content_id: content identifier.
        :param password: optional password to access protected content.
        :param pathing_count: pointer-like dictionary used internally to track naming collisions
                              for file and directory paths. Should not be modified outside this function.
        :param file_index: an itertools.count object used to sequentially index discovered files.
                           Acts as a mutable counter local to the parsing thread context.
                           Should not be modified outside this function.
        :return:
        """

        url: str = f"https://api.gofile.io/contents/{content_id}?wt=4fd6sg89d7s6&cache=true&sortField=createTime&sortDirection=1"

        if not pathing_count:
            pathing_count = {}

        if password:
            url = f"{url}&password={password}"

        response: Response | None = self._get_response(url=url, headers=self._headers)
        json_response: dict[str, Any] = {} if not response else response.json()

        if not json_response or json_response["status"] != "ok":
            _print(f"Failed to fetch data response from the {url}.{NEW_LINE}")
            return

        data: dict[str, Any] = json_response["data"]

        if "password" in data and "passwordStatus" in data and data["passwordStatus"] != "passwordOk":
            _print(f"Password protected link. Please provide the password.{NEW_LINE}")
            return

        if data["type"] != "folder":
            filepath: str = self._resolve_naming_collision(pathing_count, parent_dir, data["name"])

            self._register_file(file_index, filepath, data["link"])
            return

        folder_name: str = data["name"]
        absolute_path: str = self._resolve_naming_collision(pathing_count, parent_dir, folder_name)

        # If the content directory (the root directory) directory isn't named the same as the content_id,
        # use the content_id as a name for the content directory.
        #
        # Also do not use the default root directory named as "root" created by default.
        if path.basename(parent_dir) == content_id:
            absolute_path = parent_dir

        self._create_dirs(absolute_path)

        # Checks if there is any children (files and directories) and handle them
        for child in data["children"].values():
            if child["type"] == "folder":
                self._build_content_tree_structure(absolute_path, child["id"], password, pathing_count, file_index)
            else:
                filepath: str = self._resolve_naming_collision(pathing_count, absolute_path, child["name"])

                self._register_file(file_index, filepath, child["link"])


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


    def _do_interactive(self, content_dir: str) -> None:
        """
        _do_interactive

        Performs interactive file selection for download.

        :param content_dir: Content root directory.
        :return:
        """

        self._print_list_files()

        # Ensure only valid index strings are stored.
        input_list: set[str] = set(input(
            f"Files to download (Ex: 1 3 7) | or leave empty to download them all"
            f"{NEW_LINE}"
            f":: "
        ).split())
        input_list = set(self._files_info.keys()) if not input_list \
                     else input_list & set(self._files_info.keys())

        if not input_list:
            _print(f"Nothing done.{NEW_LINE}")
            self._remove_dir(content_dir)
            self._reset_class_properties()
            return

        keys_to_delete: list[str] = list(set(self._files_info.keys()) - set(input_list))

        for key in keys_to_delete:
            del self._files_info[key]


    def _reset_class_properties(self) -> None:
        """
        _reset_class_properties

        Simply put the properties of the class to be used again for another link if necessary.
        This should be called after all jobs related to a link is done.

        :return:
        """

        self._message: str = " "
        self._files_info.clear()

    def _clear_message(self) -> None:
        """
        _clear_message

        Empties the terminal if there's something already to the current line.

        :return:
        """

        _print(f"\r{' ' * len(self._message)}\r")


    def run(self) -> None:
        """
        run

        This method starts the download process after the creation of the Downloader object.

        :return:
        """

        token: str | None = getenv("GF_TOKEN")

        _print(f"Starting, please wait...{NEW_LINE}")
        self._set_account_access_token(token)
        self._parse_url_or_file(self._url_or_file, self._password)


    def stop(self) -> None:
        """
        stop

        Stops all work from continuing.

        :return:
        """

        with self._lock:
            self._clear_message()
            self._message = f"\rStopping, please wait...{NEW_LINE}"
            _print(self._message)
            self._stop_event.set()


if __name__ == "__main__":
    downloader: Downloader | None = None

    try:
        from sys import argv

        url_or_file: str | None = None
        password: str | None = None
        argc: int = len(argv)

        if argc > 1:
            url_or_file = argv[1]

            if argc > 2:
                password = argv[2]

            downloader = Downloader(url_or_file=url_or_file, password=password)

            # Run
            downloader.run()
        else:
            die(f"Usage:"
                f"{NEW_LINE}"
                f"python gofile-downloader.py https://gofile.io/d/contentid"
                f"{NEW_LINE}"
                f"python gofile-downloader.py https://gofile.io/d/contentid password"
            )
    except KeyboardInterrupt:
        if downloader:
            downloader.stop()

        exit(1)

