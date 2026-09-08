yum 安装 pip
- https://www.jianshu.com/p/df3bb8e2b1c3
遇到无法安装的情况
- https://blog.csdn.net/StriverChuiYing/article/details/82318798
Centos + selenium + headless Chrome
- https://www.cnblogs.com/xiaomifeng0510/p/12072081.html
utf8
- https://blog.csdn.net/u011537073/article/details/86498982
get innerHtml
- https://www.browserstack.com/guide/get-html-source-of-web-element-in-selenium-webdriver#:~:text=There%20are%20two%20ways%20to,opening%20tag%20and%20ending%20tag.
关闭所有 chrome 和 python3 的进程（网络出错时，进程会阻塞而无法自动回收）
- sudo ps -ef | grep chrome | grep -v grep | awk '{print $2}' | xargs kill -9
- sudo ps -ef | grep python3 | grep -v grep | awk '{print $2}' | xargs kill -9
unicode 编码问题
- 不要用 python2
csv 显示 tab 不分列问题
- 数据-分裂-选分割符号-下一步-选逗号-完成