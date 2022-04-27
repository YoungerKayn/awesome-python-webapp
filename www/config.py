#!/usr/bin/env python3
# -*- coding: utf-8 -*-
__author__ = 'YoungerKayn'
# 读取配置文件

import config_default

class Dict(dict):
    # 创建支持通过 x.y 格式调用的字典
    def __init__(self, names=(), values=(), **kw):
        super(Dict, self).__init__(**kw)
        for k, v in zip(names, values):
            self[k] = v

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Dict' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value


# 用于导入配置的主要部分

configs = config_default.configs

# 覆写
def merge(defaults, override):
    r = {}
    for k, v in defaults.items():
        if k in override:
            if isinstance(v, dict):
                r[k] = merge(v, override[k])
            else:
                r[k] = override[k]
        else:
            r[k] = v
    return r

# 通过Dict类实现 x.y 形式取值
def toDict(d):
    D = Dict()
    for k, v in d.items(): # d.items()的作用是以列表的形式返回可遍历的元组数组
        D[k] = toDict(v) if isinstance(v, dict) else v
    return D

try:
    import config_override
    configs = merge(configs, config_override.configs)
except ImportError:
    pass

configs = toDict(configs)