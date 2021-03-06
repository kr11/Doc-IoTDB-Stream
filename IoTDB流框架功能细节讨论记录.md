# IoTDB流框架功能点

2019年04月04日 星期四讨论记录

## 数据时间与真实时间

区分概念：

* 数据时间：数据中给出的时间戳；所有时序数据都需要有时间戳；
* 真实时间：设备流逝的时间，或者说真实世界的时间。

流框架只考虑数据时间，无视真实时间。以下所有时间均指的是数据时间。

## 窗口滑动与处理逻辑

以基于时间的窗口为例。用户指定两个参数：

* window_length-T：窗口时间范围为$T$
* window_every-s：每隔$s​$ 秒触发一次操作。

暂不考虑乱序，所有点顺序到来。当"新点加入"时，触发逻辑如下：

1. 新点 $p_{t}$ 到来：时间戳为$t$，加入当前活跃窗口`window array`；
2. 排序：包括$p_{T+1}$在内排序(考虑乱序点)，时间范围为$[t_{min}, t_{max}]$
3. 移除过时点：移除 $[t_{min}, t_{max}-T]$范围内的点，剩余窗口跨度为T：$( t_{max}-T, t_{max}]$
4. 执行用户定义的逻辑

## 批量定义任务[TODO]

对于10000台设备，每台设备下都有统一的s1, s2, s3传感器。为这些设备批量定义任务，可以通过例如正则匹配完成。这样的功能应该有实际应用场景。

### 多序列输入与对齐 [TODO]

用户的UDF包含多个序列，需要两两对齐才能执行（例如通过经度、纬度计算平均速度）。但序列频率不一致，如何**补齐**？序列时间戳有偏差，如何**对齐**？

## 流框架通知UDF机制

注意，由于流数据流速较高，因此存在两种处理策略：

* stream：每个点到来都触发窗口处理，延迟低
* batch：到达n个点之后才触发窗口处理，延迟高

另外，流框架封装了中间层逻辑，流框架上面是用户的UDF，下面是memory table、磁盘数据甚至其他节点数据。流框架和UDF之间采取`发布-订阅模式`。

## 乱序点逻辑

对于乱序数据，流框架定义如下逻辑：

1. 乱序点到来后，仍按照`窗口滑动与处理逻辑`小节逻辑进行
2. 如果乱序点排序后存在于活跃窗口中，则正常处理
3. 如果乱序点直接超时，在第3步被移除，允许用户指定"如何处理乱序点"。
   1. 最简单的是输出到日志、另一条错误输出流或http。也允许用户指定其他操作，如强行重写回正常输出流、强制与当前窗口中数据进行计算等。类似于java的`Exception`处理机制。

## Memory Table无法覆盖活跃窗口

memory table是活跃的、内存中整理好的离散数据，非常适合流框架高速计算。但：

1. 用户可能指定非常大的窗口，超过了memory table。
2. 用户可能指定了多条序列输入，属于不同的storage group，这些storage group被LRU轮换出去而不得不读取磁盘，甚至要从不同节点获取

schedule：

1. 第一步：
   1. 要求UDF的输入序列只能属于相同storage group，避免问题2；
   2. 触发逻辑操作后，仅处理memory table中的数据**[存疑]**
2. 第二步：
   1. 可以通过查询，获取不再当前memory table的数据，完成计算



## 复杂查询

用户可指定的操作的复杂程度schedule：

1. 单条序列，无写操作，仅条件判断报警
   1. 多条输入序列，无写操作报警
2. 基于单条/多条序列的当前输入，生成新序列写出
3. 需要对额外序列进行**历史数据查询** (如同比环比数据)。



### 用户script输入方式

以上UDF的复杂程度也直接影响到script脚本语言的复杂程度。

script通过SQL，以字符串的形式输入。

## LRU轮换策略

schedule：

1. 通过用户合理的配置，减少UDF涉及到的filenode的LRU轮换
2. 流框架是否要影响到FileNodeManager？

## window实现

schedule：

1. 基于时间的window
2. 基于数量的window以及其他window

## barrier是否需要?

`窗口滑动与处理逻辑`，`多序列输入和对齐`，`流框架通知UDF机制`三部分共同完成barrier的功能。

## 快照

当流框架的某个UDF隶属的fileNode被轮换，或者整个系统关机时，应该将当前窗口的相关数据进行快照并落盘。重启或FileNode载入后，UDF可以恢复上一时刻的状态。



## 日志与恢复

当系统意外崩溃，流框架应该可以根据系统的WAL和恢复策略恢复到上一时刻状态。

注意，仅在FileNode轮换出去的时候进行`快照`无法保证完全恢复，流框架还需要一些额外机制保证安全。