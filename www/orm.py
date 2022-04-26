#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# 编写ORM

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
        port=kw.get('port', 3306),
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
        # 'aiomysql.DictCursor' = 要求返回字典格式
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

# 到这里sql的基本函数就创建完了，下面是ORM部分：

# 这个函数只在下面的 Model元类中被调用，作用好像是加数量为 num 的'?'
def create_args_string(num):
    L = []
    for i in range(num):
        L.append('?')
    return ', '.join(L)

# ModelMetaclass是Model的元类
class ModelMetaclass(type):
    def __new__(cls, name, bases, attrs):
        # 排除Model类本身:
        if name=='Model':
            return type.__new__(cls, name, bases, attrs)
        # 获取table名称:
        tableName = attrs.get('__table__', None) or name
        logging.info('found model: %s (table: %s)' % (name, tableName))
        # 获取所有的Field和主键名:
        mappings = dict()
        fields = [] # fields 中是非主键属性名
        primaryKey = None
        for k, v in attrs.items():
            if isinstance(v, Field):
                logging.info('found mapping: %s ==> %s' % (k, v))
                # 将输入的属性和内容以dict格式传进 mappings
                mappings[k] = v
                if v.primary_key:
                    # 主键重复则报错
                    if primaryKey:
                        raise RuntimeError('Duplicate primary key for field: %s' % k)
                    primaryKey = k
                else:
                    fields.append(k)
        # 未找到主键则报错
        if not primaryKey:
            raise RuntimeError('Primary key not found.')
        # 将先前从 attrs 传入 mappings 中的属性和内容剔除主键后再次传回 attrs
        # 即这一段的作用是分离主键和非主键
        for k in mappings.keys():
            attrs.pop(k)
        # 对表名添加标识，防止SQL注入。` ` 中内容为数据库名、表名等
        escaped_fields = list(map(lambda f: '`%s`' % f, fields))
        attrs['__mappings__'] = mappings # 保存属性和列的映射关系
        attrs['__table__'] = tableName
        attrs['__primary_key__'] = primaryKey # 主键属性名
        attrs['__fields__'] = fields # 除主键外的属性名
        # 构造默认的SELECT, INSERT, UPDATE和DELETE语句:
        attrs['__select__'] = 'select `%s`, %s from `%s`' % (primaryKey, ', '.join(escaped_fields), tableName)
        attrs['__insert__'] = 'insert into `%s` (%s, `%s`) values (%s)' % (tableName, ', '.join(escaped_fields), primaryKey, create_args_string(len(escaped_fields) + 1))
        attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (tableName, ', '.join(map(lambda f: '`%s`=?' % (mappings.get(f).name or f), fields)), primaryKey)
        attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (tableName, primaryKey)
        return type.__new__(cls, name, bases, attrs)
        
# 创建完ModelMetaclass后，所有它的子类会自动通过ModelMetaclass扫描映射关系，
# 并存储到自身的类属性如__table__、__mappings__中，以便构造SQL语句


# Model是所有ORM映射的基类
class Model(dict, metaclass=ModelMetaclass):

    def __init__(self, **kw):
        super(Model, self).__init__(**kw)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

    def getValue(self, key):
        return getattr(self, key, None)

    def getValueOrDefault(self, key):
        value = getattr(self, key, None)
        if value is None:
            field = self.__mappings__[key]
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s: %s' % (key, str(value)))
                setattr(self, key, value)
        return value

    # 以上都是在将属性和内容映射
    # 以下为向基类 Model 添加class方法和实例方法，让子类调用：

    # *** 往 Model 类添加 class 方法 ***

    @classmethod
    async def findAll(cls, where=None, args=None, **kw):
        # 即SQL语句 'SELECT `column_name` FROM `table_name` WHERE `limit`'
        sql = [cls.__select__]
        # where 默认值为 None，即不设过滤条件
        # 如果 where 有值就在 sql 加上字符串 'where' 和 变量 where
        if where:
            sql.append('where')
            sql.append(where)
        if args is None:
            # args 默认值为 None 
            # 如果 findAll 函数未传入有效的 where 参数，则将 '[]' 传入 args 
            args = []
        orderBy = kw.get('orderBy', None)
        # ORDERBY 指将结果集按升序进行排序后输出
        if orderBy:
            sql.append('order by')
            sql.append(orderBy)
        # limit 是过滤条件
        limit = kw.get('limit', None)
        if limit is not None:
            sql.append('limit')
            if isinstance(limit, int):
                sql.append('?')
                args.append(limit)
            elif isinstance(limit, tuple) and len(limit) == 2:
                sql.append('?, ?')
                args.extend(limit)
            else:
                # 将过滤条件最大值设为2，为了防止SQL注入？
                raise ValueError('Invalid limit value: %s' % str(limit))
        rs = await select(' '.join(sql), args)
        # 返回选择的列表里的所有值，完成 findAll 函数
        return [cls(**r) for r in rs]

    @classmethod
    async def findNumber(cls, selectField, where=None, args=None):
        # 返回 selectField 下数据的数量
        sql = ['select count(%s) _num_ from `%s`' % (selectField, cls.__table__)]
        if where:
            sql.append('where')
            sql.append(where)
        rs = await select(' '.join(sql), args, 1) # 
        if len(rs) == 0:
            return None
        return rs[0]['_num_']

    @classmethod
    async def find(cls, pk):
        # 通过主键找对象
        rs = await select('%s where `%s`=?' % (cls.__select__, cls.__primary_key__), [pk], 1)
        if len(rs) == 0:
            return None
        return cls(**rs[0])


    # *** 往 Model 类添加实例方法，就可以让所有子类调用实例方法

    async def save(self):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = await execute(self.__insert__, args)
        if rows != 1:
            logging.warning('failed to insert record: affected rows: %s' % rows)

    async def update(self):
        args = list(map(self.getValue, self.__fields__))
        args.append(self.getValue(self.__primary_key__))
        rows = await execute(self.__update__, args)
        if rows != 1:
            logging.warning('failed to update by primary key: affected rows: %s' % rows)

    async def remove(self):
        args = [self.getValue(self.__primary_key__)]
        rows = await execute(self.__delete__, args)
        if rows != 1:
            logging.warning('failed to remove by primary key: affected rows: %s' % rows)


# Field 元类 和各种 Field 子类：

class Field(object):
    def __init__(self, name, column_type, primary_key, default):
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.default = default
    def __str__(self):
        return '<%s:%s>' % (self.__class__.__name__, self.name)

# 映射varchar的StringField
class StringField(Field):
    def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100)'):
        super().__init__(name, ddl, primary_key, default)

# 映射整数型的IntegerField
class IntegerField(Field):
    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'bigint', primary_key, default)

# 映射浮点数型的FloatField
class FloatField(Field):
    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'real', primary_key,default)

# 映射布尔值的BooleanField
class BooleanField(Field):
    def __init__(self, name=None, default=False):
        super().__init__(name, 'boolean', False, default)

# 不是很清楚映射了什么，类型同varchar一样是字符串，应该是储存类型不同
class TextField(Field):
    def __init__(self, name=None, default=None):
        super().__init__(name, 'text', False, default)




# 以下例子示范如何定义一个User对象，将它与数据库表users关联起来，以及它的调用方式
'''
class User(Model):
    # 注意到以下三个属性是类的属性，描述User对象和表的映射关系，而非实例的属性
    # 实例的属性必须通过 __init__() 方法初始化，故两者互不干扰
    __table__ = 'users'
    id = IntegerField(primary_key=True)
    name = StringField()
# 创建实例:
user = User(id=123, name='Michael')
# 存入数据库:
user.insert()
# 查询所有User对象:
users = User.findAll()
'''