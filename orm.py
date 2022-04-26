import aiomysql,asyncio,logging

# 输出日志
def log(sql, args=()):
    logging.info('SQL: %s' % sql)

# 创建连接池
async def create_pool(loop, **kw):
    logging.info('create database connection pool...')
    global __pool
    __pool = await aiomysql.create_pool(
        host=kw.get('host', 'localhost'),
        port=kw.get('port', 7777),
        user=kw['user'],
        password=kw['password'],
        db=kw['db'],
        charset=kw.get('charset', 'utf8'),
        autocommit=kw.get('autocommit', True),
        maxsize=kw.get('maxsize', 10),
        minsize=kw.get('minsize', 1),
        loop=loop
    )

# 下面两个函数是sql的基本函数

# select语句
async def select(sql, args, size=None):
    log(sql, args)
    global __pool
    with (await __pool) as conn:
        # 'aiomysql.DictCursor'看似复杂，但它仅仅是要求返回字典格式
        cur = await conn.cursor(aiomysql.DictCursor)
        # SQL语句的占位符是?，而MySQL的占位符是%s，select()函数在内部自动替换
        # 注意要始终坚持使用带参数的SQL，而不是自己拼接SQL字符串，这样可以防止SQL注入攻击
        await cur.execute(sql.replace('?', '%s'), args or ())
        # if 语句里就是在执行sql语句
        if size:
            rs = await cur.fetchmany(size)
        else:
            rs = await cur.fetchall()
        # 执行完成后关闭游标，打印日志，返回结果后关闭数据库连接
        await cur.close()
        logging.info('rows returned: %s' % len(rs))
        return rs

# insert、update、delete语句都需要三个参数，可以定义一个通用函数
async def execute(sql, args):
    log(sql)
    with (await __pool) as conn:
        # 类似上面的select()，不过execute()函数和select()函数所不同的是，cursor对象不返回结果集，而是通过rowcount返回结果数
        try:
            cur = await conn.cursor()
            await cur.execute(sql.replace('?', '%s'), args)
            # affectd = 影响的行数
            affected = cur.rowcount
            await cur.close()
        except BaseException as e:
            raise
        return affected

# 到这里sql的基本函数就创建完了，下面是ORM部分

