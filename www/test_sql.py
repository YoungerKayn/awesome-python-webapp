import asyncio

import orm

from models import User

async def test(loop):

    await orm.create_pool(loop=loop,user='root', password='password', db='awesome')

    u = User(name='Test', email='test@example.com', passwd='password', image='about:blank')

    await u.save()

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
loop.run_until_complete(test(loop))