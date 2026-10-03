"""测试分层（**开发者工具**，见 `DEVELOPING.md` §七）。

三层，各只回答一个问题：

* ``unit/``     —— 一个纯函数在四层配置下的取值与**优先级**；
* ``contract/`` —— 客户端与文档之间冻结的那张表（8 个错误码）有没有走样；
* 验收层不在这里 —— 它需要真 IDE 实例，命令是 ``python -m ctl verify --case read.ping``。

**只用标准库**（R12′.1）。跑法：``python -m unittest discover -s tests -t . -v``
"""
