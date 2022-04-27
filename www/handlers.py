#!/usr/bin/env python3
# -*- coding: utf-8 -*-
__author__ = 'YoungerKayn'
# MVC，或url处理模块

from models import User
from coroweb import get
import asyncio

#'__template__'指定的模板文件是test.html，其他参数是传递给模板的数据
@get('/')
async def index(request):
    users = await User.findAll()
    return {
        '__template__': 'test.html',
        'users': users
    }