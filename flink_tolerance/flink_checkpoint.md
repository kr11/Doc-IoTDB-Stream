# 1、Flink 容错机制
## 1.1 Flink exactly once模式
flink实现exactly once策略，是flink会持续的对整个系统做snapshot，然后把全局状态(snaphot)根据设定好的路径保存到master node 或者是HDFS中，当系统出现failure时，flink停止处理数据，把系统恢复到最近的一次checkpoint
### 1.1.1 什么是global state(全局状态)
分布式系统由空间上分离的process和连接这些process的channel组成。空间上分立的含义就是process不共享memory，而是通过communication channel 上进行的message pass来异步通信交流。
分布式系统的global state 就是所有process，channel的集合。
process的local state取决于the state of local memory and the history of its activity。
channel的local state是从上游发送进channel的message集合减去下游process从channel接受的message的差集
分布式系统没有共享内存和全局时钟，如果分布式系统有共享内存，那么可以从共享内存中直接获取整个分布式系统的snapshot，不用分别获得各个process、channel的local state再组合成为一个global state。
未来获得一致性global state，采用chandy-Lamport算法
(该算法就是在数据中插入marker也就是barrier)

如图所示：A是JobManager，B、C是source streaming，D是普通的算子
JobManager首先发起snapshot，所有source发送barrier

每个barrier先后到达各自的source。Source在收到barrier后记录自身的state，然后向下游发送barrier。