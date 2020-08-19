# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Base definitions for MicroTVM"""

from __future__ import absolute_import

import os
import sys
from enum import Enum

import tvm
from tvm.contrib import util as _util
from tvm.contrib import cc as _cc
from .._ffi.function import _init_api

class LibType(Enum):
    """Enumeration of library types that can be compiled and loaded onto a device"""
    # library to be used as a MicroTVM runtime
    RUNTIME = 0
    # library to be used as an operator
    OPERATOR = 1


class Session:
    """MicroTVM Device Session

    Parameters
    ----------
    config : dict
        configuration for this session (as generated by
        `tvm.micro.device.host.default_config()`, for example)

    Example
    --------
    .. code-block:: python

      c_mod = ...  # some module generated with "c" as the target
      dev_config = micro.device.arm.stm32f746xx.default_config("127.0.0.1", 6666)
      with tvm.micro.Session(dev_config) as sess:
          micro_mod = create_micro_mod(c_mod, dev_config)
    """

    def __init__(self, config):
        self._check_system()
        # TODO(weberlo): add config validation

        # grab a binutil instance from the ID in the config
        dev_funcs = tvm.micro.device.get_device_funcs(config["device_id"])
        self.create_micro_lib = dev_funcs["create_micro_lib"]
        self.toolchain_prefix = config["toolchain_prefix"]
        self.mem_layout = config["mem_layout"]
        self.word_size = config["word_size"]
        self.thumb_mode = config["thumb_mode"]
        self.comms_method = config["comms_method"]

        # First, find and compile runtime library.
        runtime_src_path = os.path.join(get_micro_host_driven_dir(), "utvm_runtime.c")
        tmp_dir = _util.tempdir()
        runtime_obj_path = tmp_dir.relpath("utvm_runtime.obj")
        self.create_micro_lib(runtime_obj_path, runtime_src_path, LibType.RUNTIME)
        #input(f"check {runtime_obj_path}: ")

        comms_method = config["comms_method"]
        if comms_method == "openocd":
            server_addr = config["server_addr"]
            server_port = config["server_port"]
        elif comms_method == "host":
            server_addr = ""
            server_port = 0
        else:
            raise RuntimeError(f"unknown communication method: f{self.comms_method}")

        self.module = _CreateSession(
            comms_method,
            runtime_obj_path,
            self.toolchain_prefix,
            self.mem_layout["text"].get("start", 0),
            self.mem_layout["text"]["size"],
            self.mem_layout["rodata"].get("start", 0),
            self.mem_layout["rodata"]["size"],
            self.mem_layout["data"].get("start", 0),
            self.mem_layout["data"]["size"],
            self.mem_layout["bss"].get("start", 0),
            self.mem_layout["bss"]["size"],
            self.mem_layout["args"].get("start", 0),
            self.mem_layout["args"]["size"],
            self.mem_layout["heap"].get("start", 0),
            self.mem_layout["heap"]["size"],
            self.mem_layout["workspace"].get("start", 0),
            self.mem_layout["workspace"]["size"],
            self.mem_layout["stack"].get("start", 0),
            self.mem_layout["stack"]["size"],
            self.word_size,
            self.thumb_mode,
            server_addr,
            server_port)
        self._enter = self.module["enter"]
        self._exit = self.module["exit"]

    def _check_system(self):
        """Check if the user's system is supported by MicroTVM.

        Raises error if not supported.
        """
        if not sys.platform.startswith("linux"):
            raise RuntimeError("MicroTVM is currently only supported on Linux hosts")
        # TODO(weberlo): Add 32-bit support.
        # It's primarily the compilation pipeline that isn't compatible.
        if sys.maxsize <= 2**32:
            raise RuntimeError("MicroTVM is currently only supported on 64-bit host platforms")

    def __enter__(self):
        self._enter()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self._exit()


def create_micro_mod(c_mod, dev_config):
    """Produces a micro module from a given module.

    Parameters
    ----------
    c_mod : tvm.module.Module
        module with "c" as its target backend

    dev_config : Dict[str, Any]
        MicroTVM config dict for the target device

    Return
    ------
    micro_mod : tvm.module.Module
        micro module for the target device
    """
    temp_dir = _util.tempdir()
    lib_obj_path = temp_dir.relpath("dev_lib.obj")
    c_mod.export_library(
        lib_obj_path,
        fcompile=cross_compiler(dev_config, LibType.OPERATOR))
    micro_mod = tvm.module.load(lib_obj_path)
    return micro_mod


def cross_compiler(dev_config, lib_type):
    """Create a cross-compile function that wraps `create_lib` for a `Binutil` instance.

    For use in `tvm.module.Module.export_library`.

    Parameters
    ----------
    dev_config : Dict[str, Any]
        MicroTVM config dict for the target device

    lib_type : micro.LibType
        whether to compile a MicroTVM runtime or operator library

    Return
    ------
    func : Callable[[str, str, Optional[str]], None]
        cross compile function taking a destination path for the object file
        and a path for the input source file.

    Example
    --------
    .. code-block:: python

      c_mod = ...  # some module generated with "c" as the target
      fcompile = tvm.micro.cross_compiler(dev_config, LibType.OPERATOR)
      c_mod.export_library("dev_lib.obj", fcompile=fcompile)
    """
    dev_funcs = tvm.micro.device.get_device_funcs(dev_config['device_id'])
    create_micro_lib = dev_funcs['create_micro_lib']
    def compile_func(obj_path, src_path, **kwargs):
        if isinstance(obj_path, list):
            obj_path = obj_path[0]
        if isinstance(src_path, list):
            src_path = src_path[0]
        create_micro_lib(obj_path, src_path, lib_type, kwargs.get("options", None))
    return _cc.cross_compiler(compile_func, output_format="obj")


def get_micro_host_driven_dir():
    """Get directory path for uTVM host-driven runtime source files.

    Return
    ------
    micro_device_dir : str
        directory path
    """
    micro_dir = os.path.dirname(os.path.realpath(os.path.expanduser(__file__)))
    micro_host_driven_dir = os.path.join(micro_dir, "..", "..", "..",
                                         "src", "runtime", "micro", "host_driven")
    return micro_host_driven_dir


def get_micro_device_dir():
    """Get directory path for parent directory of device-specific source files

    Return
    ------
    micro_device_dir : str
        directory path
    """
    micro_dir = os.path.dirname(os.path.realpath(os.path.expanduser(__file__)))
    micro_device_dir = os.path.join(micro_dir, "..", "..", "..",
                                    "src", "runtime", "micro", "device")
    return micro_device_dir


_init_api("tvm.micro", "tvm.micro.base")