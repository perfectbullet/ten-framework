#
# Copyright © 2025 Agora
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0, with certain conditions.
# Refer to the "LICENSE" file in the root directory for more information.
#
from typing import TypeVar, cast

from libten_runtime_python import (
    _Cmd,  # pyright: ignore[reportPrivateUsage]
    _ten_py_cmd_register_type,  # pyright: ignore[reportPrivateUsage]
)

from .msg import Msg

T = TypeVar("T", bound="Cmd")


class Cmd(_Cmd, Msg):
    def __init__(self, name: str):  # pyright: ignore[reportMissingSuperCall]
        raise NotImplementedError("Use Cmd.create instead.")

    @classmethod
    def create(cls: type[T], name: str) -> T:
        return cast(T, cls.__new__(cls, name))

    def clone(self) -> "Cmd":  # pyright: ignore[reportImplicitOverride]
        return cast("Cmd", _Cmd.clone(self))


_ten_py_cmd_register_type(Cmd)

'''这段代码定义了一个 Python 的 Cmd 类，用于包装底层的 C/C++ 命令对象：

导入部分：


TypeVar, cast: 用于类型提示和类型转换
_Cmd: 从底层 C/C++ 扩展模块导入的私有命令类
_ten_py_cmd_register_type: 用于注册命令类型的函数
Msg: 消息基类
类型变量：


T = TypeVar("T", bound="Cmd"): 定义泛型类型变量，限定为 Cmd 或其子类
Cmd 类：


继承自 _Cmd（底层实现）和 Msg（消息接口）
__init__: 被禁用，抛出 NotImplementedError，强制使用 create 方法创建实例
create: 类方法，正确的实例化方式，通过 __new__ 直接创建对象，绕过 __init__，支持子类化
clone: 克隆方法，返回命令对象的副本
注册：


_ten_py_cmd_register_type(Cmd): 将 Cmd 类注册到底层运行时系统
这种设计模式确保对象创建通过特定的工厂方法，便于底层 C/C++ 扩展正确初始化对象。'''