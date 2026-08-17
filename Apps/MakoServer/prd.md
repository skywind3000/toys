# MakoServer

使用 MakoServer + Flask 做一个类似 php 的系统。



## 模板服务

- 基于 Mako / Flask，提供一套类似 .php 的网页服务；
- 用户请求 http://localhost/web/demo.mako 的话，就会解析出相对目录，并到根目录下寻找 .mako 文件并渲染返回；
- 如果请求的是 .html / .jpg 等，就会读取并设置好对应的 content type 再返回内容；
- 如果请求的不包含文件名，就会依次尝试追加 `index.mako` 和 `index.html` 和 `index.htm` 几个文件；
- 在 Flask 端提供一系列 bridge 函数/对象，可以由 .mako 脚本使用并用来设置返回的 header，返回码，读取发送上来的 parameter，读取是 GET 还是 POST 等，读取 body 等，就像 PHP 的 `$_ARGS[xxx]` 字典一样，提供 cookie 设置；

## 运行方式

- 这个 MakoServer 可以单独运行，指定一个根目录和端口就能启动一个 HTTP Server 提供页面服务；
- 这个 MakoServer 也可以按 WSGI 的模式运行，它会寻找配置文件，从里面解析出根目录；
- 还可以单独传入一个 .mako 脚本，就像命令行运行 .php 那样渲染出来；

