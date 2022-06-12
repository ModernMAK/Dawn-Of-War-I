from __future__ import annotations

import zlib
from abc import ABC
from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath
from typing import List, Optional, Tuple, BinaryIO, Type, Generic, TypeVar

from relic.sga import protocols as p
from relic.sga._core import StorageType, Version
from relic.sga.protocols import IONode, IOWalk, IOContainer


def _build_io_path(name: str, parent: Optional[p.IONode]) -> PurePath:
    if parent is not None and isinstance(parent, p.IOPathable):
        return parent.path / name
    else:
        return PurePath(name)


TFile = TypeVar("TFile", bound=p.File)
TFolder = TypeVar("TFolder", bound=p.Folder)
TDrive = TypeVar("TDrive", bound=p.Drive)
TArchive = TypeVar("TArchive", bound=p.Archive)
TMetadata = TypeVar("TMetadata")
TFileMetadata = TypeVar("TFileMetadata")


@dataclass
class _FileLazyInfo:
    jump_to: int
    packed_size: int
    unpacked_size: int
    stream: BinaryIO
    decompress: bool

    def read(self, decompress: Optional[bool] = None) -> bytes:
        decompress = self.decompress if decompress is None else decompress
        jump_back = self.stream.tell()
        self.stream.seek(self.jump_to)
        buffer = self.stream.read(self.packed_size)
        if decompress and self.packed_size != self.unpacked_size:
            buffer = zlib.decompress(buffer)
            assert len(buffer) == self.unpacked_size  # TODO Raise Exception instead
        self.stream.seek(jump_back)
        return buffer


@dataclass
class DriveDef:
    alias: str
    name: str
    root_folder: int
    folder_range: Tuple[int, int]
    file_range: Tuple[int, int]


@dataclass
class FolderDef:
    name_pos: int
    folder_range: Tuple[int, int]
    file_range: Tuple[int, int]


@dataclass
class FileDefABC:
    name_pos: int
    data_pos: int
    length_on_disk: int
    length_in_archive: int
    storage_type: StorageType


@dataclass
class File(Generic[TFileMetadata], p.File[TFileMetadata]):
    name: str
    _data: Optional[bytes]
    storage_type: StorageType
    _is_compressed: bool
    metadata: TFileMetadata
    parent: Optional[IOContainer] = None
    _lazy_info: Optional[_FileLazyInfo] = None

    @property
    def data(self) -> bytes:
        if self._data is None:
            if self._lazy_info is None:
                raise TypeError("Data was not loaded!")
            else:
                self._data = self._lazy_info.read()
                self._lazy_info = None
        return self._data

    @data.setter
    def data(self, value: bytes) -> None:
        self._data = value

    @contextmanager
    def open(self, read_only: bool = True):
        data = self.data
        with BytesIO(data) as stream:
            yield stream
            if not read_only:
                stream.seek(0)
                self.data = stream.read()

    @property
    def is_compressed(self) -> bool:
        return self._is_compressed

    def compress(self) -> None:
        if self.data is None:
            raise TypeError("Data was not loaded!")
        if not self._is_compressed:
            self.data = zlib.compress(self.data)
            self._is_compressed = True

    def decompress(self) -> None:
        if self._is_compressed:
            self.data = zlib.decompress(self.data)
            self._is_compressed = False

    @property
    def path(self) -> PurePath:
        return _build_io_path(self.name, self.parent)


@dataclass
class Folder(p.Folder):
    name: str
    sub_folders: List[Folder]
    files: List[File]
    parent: Optional[IONode] = None

    @property
    def path(self) -> PurePath:
        return _build_io_path(self.name, self.parent)

    def walk(self) -> IOWalk:
        yield self, self.sub_folders, self.files
        for folder in self.sub_folders:
            for inner_walk in folder.walk():
                yield inner_walk


@dataclass
class Drive(p.Drive):
    alias: str
    name: str
    sub_folders: List[Folder]
    files: List[File]
    parent: None = None
    __ignore__ = ["parent"]

    @property
    def path(self) -> PurePath:
        return _build_io_path(f"{self.alias}:", None)

    def walk(self) -> IOWalk:
        yield self, self.sub_folders, self.files
        for folder in self.sub_folders:
            for inner_walk in folder.walk():
                yield inner_walk


@dataclass
class Archive(Generic[TMetadata], p.Archive[TMetadata]):
    name: str
    metadata: TMetadata
    drives: List[Drive]

    def walk(self) -> IOWalk:
        for drive in self.drives:
            for inner_walk in drive.walk():
                yield inner_walk


# for good typing; manually define dataclass attributes in construct
# it sucks, but good typing is better than no typing
class API(Generic[TArchive, TDrive, TFolder, TFile], p.API[TArchive, TDrive, TFolder, TFile], ABC):
    def __init__(self, version: Version, archive: Type[TArchive], drive: Type[TDrive], folder: Type[TFolder], file: Type[TFile], serializer: APISerializer):
        self.version = version
        self.Archive = archive
        self.Drive = drive
        self.Folder = folder
        self.File = file
        self._serializer = serializer

    def read(self, stream: BinaryIO, lazy: bool = False, decompress: bool = True) -> TArchive:
        return self._serializer.read(stream, lazy, decompress)

    def write(self, stream: BinaryIO, archive: TArchive) -> int:
        return self._serializer.write(stream, archive)


class APISerializer(Generic[TArchive]):
    def read(self, stream: BinaryIO, lazy: bool = False, decompress: bool = True) -> TArchive:
        raise NotImplementedError

    def write(self, stream: BinaryIO, archive: TArchive) -> int:
        raise NotImplementedError
