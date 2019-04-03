# Kapacitor如何处理乱序数据

[TOC]

Kapacitor作为流数据处理框架，结合TICKScript脚本语言，形成了比较丰富的监控功能。虽然Kapacitor对于顺序到达的数据功能强大，但实际场景中，乱序数据是很常见的，包括以下两种情况：

1. 时间戳不按顺序到达：如在真实时间0s,1s,2s分别来了三个点，它们的数据时间是2s,0s,1s
2. 流数据的数据时间和真实时间不符合：在真实时间30s,31s,32s分别来了三个点，它们的数据时间是10s,15s,20s。

通过一些黑盒实验，验证一下Kapacitor对于乱序数据的处理能力。



## 实验场景

参考 [博客](https://www.annhe.net/article-3580.html#joinNode) 的设置，但是根据最新版本的Kapacitor进行一些改造。首先启动Kapacitor和influxdb。influxdb和Kapacitor的安装参见 [博客](https://blog.csdn.net/SoftPoeter/article/details/88698405) 。

| 软件      | 版本  |
| --------- | ----- |
| influxdb  | 1.4.2 |
| Kapacitor | 1.5.2 |
|           |       |

首先在influxdb中创建数据库test：

```shell
# 启动客户端
influx
# 客户端命令
create database test
```

采用http请求产生数据：

```shell
import os
import time

influx = "http://localhost:8086/write?db=test"

# 检测code_match，为0则异常，报警
code_matches = [1, 1, 1, 1, 0, 1, 1, 1, 1, 0]
# 顺序时间
t = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
# 乱序时间
# t = [0, 1, 2, 6, 5, 4, 3, 7, 8, 9]

base_time = 1554575034104007000
for i, code_match in enumerate(code_matches):
    os.system('curl -i -XPOST %s --data-binary "ka,app=cmdb code_match=%d %d"'
              % (influx, id, base_time + 1 * t[i] * 1e9))
    # 下面两行不指定时间戳，采用机器时间
    # os.system('curl -i -XPOST %s --data-binary "ka,app=cmdb code_match=%d"'
    #           % (influx, id))
    print("time=%d" % (base_time + 5 * t[i] * 1e9))
    # 采用机器时间的话则取消注释，指定了数据时间则sleep没有意义
    # time.sleep(1)
```

无window的tick脚本：

```json
dbrp "test"."autogen"

stream
    |from()
        .measurement('ka')
    |alert()
        .crit(lambda: int("code_match") == 0)
        .log('/Users/XXX/test_alerts.log')
```

有window的tick脚本，window跨度为3s，每1s检测和处理一次：

```json
dbrp "test"."autogen"

stream
    |from()
        .measurement('ka')
    |window()
        .period(3s)
        .every(1s)   
    |alert()
        .crit(lambda: int("code_match") == 0)
        .log('/Users/XXX/test_alert_window.log')
```

启动任务：

```shell
# 清除环境，没有指定过任务则不必须
kapacitor disable test_alert
kapacitor delete tasks test_alert
kapacitor disable test_alert_window
kapacitor delete tasks test_alert_window


kapacitor define test_alert -tick test_alert.tick
kapacitor enable test_alert

kapacitor define test_alert_window -tick test_alert_window.tick
kapacitor enable test_alert_window
```

## S1：Window.tick+真实时间+顺序

最简单的场景，先熟悉一下alert的工作方式。在本场景下，只要window中有异常点，alert就会报警，如果上一个window是异常的，alert也会报警。(如果要全部点异常才报警，可以加`.all()`语句)。

脚本如下(仅列出关键部分)：

```python
import os
import time

influx = "http://localhost:8086/write?db=test"

i1 = [1, 1, 1, 1, 0, 1, 1, 1, 1, 0]
t = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
# t = [0, 1, 2, 6, 5, 4, 3, 7, 8, 9]

# base_time = 1554575034104007000
for i, id in enumerate(i1):
    # os.system('curl -i -XPOST %s --data-binary "ka,app=cmdb code_match=%d %d"'
    #           % (influx, id, base_time + 1 * t[i] * 1e9))
    os.system('curl -i -XPOST %s --data-binary "ka,app=cmdb code_match=%d"'
              % (influx, id))
    # print("time=%d" % (base_time + 5 * t[i] * 1e9))
    time.sleep(1)

```

输出日志关键部分如下。为了清晰明了，所有时间戳均写为 `Scene+0s`, 如`S1+5s`。

```shell
{"previousLevel":"OK","value":[
		[S1+3,code_match=1],
		[S1+4,code_match=0],
]},
{"previousLevel":"CRITICAL","value":[
		[S1+4,code_match=0],
		[S1+5,code_match=1],
]},
{"previousLevel":"CRITICAL","value":[
		[S1+4,code_match=1],
		[S1+5,code_match=1],
]},
# 本来应该输出下面的记录，但是并没有！
#{"previousLevel":"OK","value":[
#		[S1+8,code_match=1],
#		[S1+9,code_match=0],
#]},
```

### 小结

1. 在本场景下，数据时间和机器时间吻合，`S1+4`，`S1+9`是异常点。窗口长度为3s内，因此是2个点。
2. S1+8和S1+9是异常的，但是没有输出，因为kapacitor是lazy模式，必须由下一个点到来，才能触发上一个异常状态。



## S2：Window.tick+虚构时间+顺序

S2比S1，数据中手动指定了时间。数据时间比真实时间要迟很多(例如1天)，以保证这些点是上一个场景之后到来的。

脚本如下：

1. 数据时间由人为指定；
2. 数据时间间隔为5，长于window的`every`参数。
3. 数据时间为顺序。
4. 没有time.sleep(1)，意味着这些记录在真实时间的0.1s内发送到Kapacitor

```python
import os
import time

influx = "http://localhost:8086/write?db=test"

i1 = [1, 1, 1, 1, 0, 1, 1, 1, 1, 0]
t = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
# t = [0, 1, 2, 6, 5, 4, 3, 7, 8, 9]

one_day_nano = 86400 * 1e9
data_interval = 5
# base_time比真实时间要晚
base_time = 1554575034104007000
for i, id in enumerate(i1):
    os.system('curl -i -XPOST %s --data-binary "ka,app=cmdb code_match=%d %d"'
              % (influx, id, base_time + data_interval * t[i] * 1e9))
    # os.system('curl -i -XPOST %s --data-binary "ka,app=cmdb code_match=%d"'
    #           % (influx, id))
    # print("time=%d" % (base_time + 5 * t[i] * 1e9))
    # time.sleep(1)

```

相比于S1，增加了4条日志：

```shell
# S1的最后测试例现在才触发
{"previousLevel":"OK","value":[
		[S1+8,code_match=1],
		[S1+9,code_match=0],
]},
# 因为上一个window是异常，因此输出。又因为数据时间之间超出了3s，因此只有一个点。
{"previousLevel":"CRITICAL","value":[
		[S2+0,code_match=1],
]},
# 数据时间间隔为5s>3s，因此只记录1个点，与真实时间无关
{"previousLevel":"OK","value":[
		[S2+4,code_match=0],
]},
{"previousLevel":"CRITICAL","value":[
		[S2+5,code_match=1],
]},

```

### 小结

1. Kapacitor以数据时间为准，与真实时间无关。尽管这十条数据在0.1s内到达Kapacitor，Kapacitor并没有把他们当做一个window中的点；
2. 同理，因为数据时间写成了5s，因此Kapacitor的每个window中只记录了1个点。



## S3：Window.tick+虚构时间+乱序

S3相比S2，数据时间继续推迟1天，异常点的顺序变了。

脚本如下：

1. 时间虚构并增加1天
2. 数据间隔变为1s，保证1个window中有多个点
3. 数据乱序：到来顺序是6s，5s，4s，3s，其中第5s是异常点。

```python
import os
import time

influx = "http://localhost:8086/write?db=test"

i1 = [1, 1, 1, 1, 0, 1, 1, 1, 1, 0]
# t = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
t =  [0, 1, 2, 6, 5, 4, 3, 7, 8, 9]

one_day_nano = 86400 * 1e9
data_interval = 1
# base_time比真实时间要晚
base_time = 1554575034104007000+one_day_nano
for i, id in enumerate(i1):
    os.system('curl -i -XPOST %s --data-binary "ka,app=cmdb code_match=%d %d"'
              % (influx, id, base_time + data_interval * t[i] * 1e9))
    # os.system('curl -i -XPOST %s --data-binary "ka,app=cmdb code_match=%d"'
    #           % (influx, id))
    # print("time=%d" % (base_time + 5 * t[i] * 1e9))
    # time.sleep(1)

```

相比于S1，增加了5条日志，为了便于解释，我们给每一个报警编号：

```shell
# S2结尾时候的异常引发两条alert，不赘述
# alert 0
{"previousLevel":"OK","value":[
		[S2+9,code_match=0],
]},
# alert 1
{"previousLevel":"CRITICAL","value":[
		[S3+0,code_match=1],
]},

# 关键
# alert 2
{"previousLevel":"OK","value":[
		[S3+6,code_match=1],
    [S3+5,code_match=0],
    [S3+4,code_match=1],
    [S3+3,code_match=1],
]},
# alert 3
{"previousLevel":"CRITICAL","value":[
		[S3+6,code_match=1],
    [S3+5,code_match=0],
    [S3+4,code_match=1],
    [S3+3,code_match=1],
    [S3+7,code_match=1],
]},
# alert 4
{"previousLevel":"CRITICAL","value":[
		[S3+6,code_match=1],
    [S3+5,code_match=0],
    [S3+4,code_match=1],
    [S3+3,code_match=1],
    [S3+7,code_match=1],
    [S3+8,code_match=1],
]},

```

数据时间间隔是1s，正常情况是写入2个点。但是为什么出现了这种情况呢？参考S1和S2可知：

1. 本次的输出是由于下一个点到来引起的；
2. 当异常点全部退出后，第一次由critical转为OK，也会输出一次。

这样就得到了一个不太圆满的解释：

### 小结

1. S3+6先来，在window中。
2. 异常点S3+5到来，并不立即触发；
3. S3+4到来，但是S3+5不在(S3+4-W, S3+4]范围内，S3+5也一样；
4. S7到来，S3+5不在(S3+7-W, S3+7]范围内，但是S3+5小于S3+7，触发第一次(alert 2)；
5. S8到来，S3+5小于S3+8，触发第二次(alert 3)；
6. S9到来，触发第三次（alert 4）；
7. 和S1相同的是，数据频率1s，window=5s，一个异常点会触发三次报警。但是上述解释的逻辑并不畅通。
8. 总之，Kapacitor并不能处理乱序情况。



## 结论

1. S1：Kapacitor对于窗口的维护是lazy模式，虽然第$t$时刻出现了异常，但如果没有下一个数据出现，$t$时刻的异常不会输出到日志；

   1. 不会出现"没有后续来点，异常点逐渐移出窗口"的情况。逐渐消失是指：[110], [10], [0]，[]。

2. S2结论：Kapacitor对于流数据时间戳的处理与真实时间无关，完全按照数据时间戳；

3. Kapacitor对于乱序数据并不特别处理。

4. 想要理解这种bug情况，可以去看源码，但是似乎并不必要。

   



