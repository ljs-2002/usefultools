# usefultools
收集一些常用的工具函数和工具装饰器。

***目录***
- [usefultools](#usefultools)
  - [函数](#函数)
    - [LOAD\_ENV() \& GET\_ENV()](#load_env--get_env)
  - [装饰器](#装饰器)
    - [detail\_exception](#detail_exception)
    - [multi\_dispatch](#multi_dispatch)

***安装依赖***
```shell
python -m pip install -r requirements.txt
```

## 函数

### LOAD_ENV() & GET_ENV()
将密码、APIKEY等敏感信息存放在环境变量中，通过`LOAD_ENV()`函数加载环境变量，通过`GET_ENV()`函数获取环境变量。

***使用方法：***
1. 在项目根目录下新建`.env`文件，将敏感信息存放在其中，格式为`KEY=VALUE`。
2. 在需要使用敏感信息的文件中，导入`LOAD_ENV`和`GET_ENV`函数。
3. 在文件的开头调用`LOAD_ENV()`函数，加载环境变量。
   ```python
   from usefultools.func import LOAD_ENV, GET_ENV
   ```
4. 在需要使用敏感信息的地方，调用`GET_ENV('KEY')`函数获取环境变量。
注意：通过`GET_ENV('KEY')`获取的是字符串类型，需要根据实际情况进行转换。

## 装饰器

### detail_exception
让函数在发生异常时抛出的错误信息带有函数的名字。

***使用方法：***
1. 导入`detail_exception`装饰器。
   ```python
   from usefultools.wrap import detail_exception
   ```
2. 在需要使用的函数上方加上`@detail_exception`装饰器。
   ```python
    @detail_exception
    def test():
        raise Exception('test')
   ```

### multi_dispatch
根据所有参数的类型进行函数重载。
整体设计参考functools.singledispatch。

***使用方法：***
1. 导入`multi_dispatch`装饰器。
   ```python
   from usefultools.wrap import multi_dispatch
   ```
2. 在需要使用的函数func上方加上`@multi_dispatch`装饰器。该函数会作为未匹配到任何重载函数时的默认情况。之后使用func.register注册关于func的重载函数。
   ```python
    @multi_dispatch
    def test(*args, **kwargs):
        print('default',*args,**kwargs)
   ```
3. 在作为重载函数的上方加上`@test.register`装饰器。
   ```python
    @test.register
    def _(a:int,b:str):
        print('int, str',a,b)
    @test.register
    def _(a:str):
        print('str',a)
   ```
4. 重复注册相同参数类型的函数会报TypeError，使用force=True选项可以覆盖原有的重载函数。
    ```python
   @test.register
    def _(a:str):
        print('str',a)
    @test.register
    def _(a:str): # 报错TypeError
        print('new str2',a)
   ```
   ```python
   @test.register
    def _(a:str):
        print('str',a)
    @test.register(force=True)
    def _(a:str): # 成功注册
        print('new str2',a)
   ```