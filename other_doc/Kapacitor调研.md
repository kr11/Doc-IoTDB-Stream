# Kapacitor 设计

## 总体设计

Kapacitor采用基于流（flow）的程序模型，将用户自定义的部分抽象为节点(node)，而将节点之间的传输(edge)隐藏起来。整体构成一个**DAG**图。



### Tasks

用户通过定义一个个**task**并在kapacitor上运行。task的定义方式是`TICKscript`。

### Models

数据传输方式包括`Stream`和`Batch`。其中批处理每次传输一组数据，stream则每次传输单点(single entities)。

* batch传输中，一个batch包括一个`timestamp`，一组`field`，一组`tag`。
* stream传输中，每个点不完全包括batch中的信息，但是也要包括所属`database`、`retention policy`和`measurement`。

**最新**：kapacitor试图为`batch`和`stream`引入`group`的概念，如果转入node的序列被按照某个维度分组(group by dimension)。

### Edges

两个`node`之间即为一个edge。与storm等相似，由于kapacitor是有向图，因此edge两端的node分为父子节点，信息的输入与输出定义为`collect`和`emit`：

- Collect — collect from parent data
- Emit — emit to a child

在目前的IoTDB-流框架中，不考虑如此复杂的信息流模型。

>  实现：edge通过Go Channels实现，见`edge.go`。每个edge有三个channel，但只有一个非零。channel目前是unbuffered。

batch数据的传输通常有两种：

1. 常用。将整个batch数据包装到一个对象中(a single object)。
2. 在stream中插入marker用于标记。marker标记了batch的起止点，其他部分则是stream。

第一种简单易行，但是缺点是必须维持整个batch在内存中。比如简单的计数操作，第二种情况是O(1)，只需要维持一个计数器即可，但是第一个必须是 $O(\|batch\|)$ 的。

### Source Mapping

kapacitor接收多种输入，包括influxdb的query结果等。task的管理在`task_master.go`中。

在stream模式下，所有sources将数据写入`taskmaster`，`taskmaster`交给一个global edge(类似于bus)。启动一个task之后，从global edge中fork一份给他(get a fork)。fork需要经过database限制、retention policies等等的过滤(类似于权限？)。

对于batch任务下，`taskmaster`负责管理查询InfluxDB进程的启动。查询的结果将直接传递到任务的根节点。(不接受filter？为何如此特别？)

### Windows

window包括两个参数：

1. period：每个window的时间跨度。
2. every：window被处理的频率。这里的处理是指edge数据被emit到child。

```javascript
stream
    .window()
        .period(10s)
        .every(5s)
// 每个window固定保持有10s的数据，每隔5s处理一次。这意味着相邻两个window之间有5s的overlap
```



### 作者认为的挑战

* 对于流任务：如果单个节点停止处理数据，则整个DAG都会受到影响，最终导致所有节点都停止处理任务。
* Fragile：node有多个parent，有多个child，由于处理数据的顺序，系统运行方式发生变化，则总是导致死锁。(也许是成环了？)

* 如果数据流停止，那么时间也会停止。在某些情况下，用户仍然希望传输中的数据被刷出。(难道是说没有input，flow中的数据就停下来了，而不是继续流动最终流过全部节点？)



## 代码结构分析

1. tick解析：在tick包下，包括了详细的词法解析和语法解析，看起来是kapacitor自己实现的，代码行数16185
2. 任务define： services/task_store/service.go:680, handleCreateTask。(通过http请求发送到kapacitord)
3. 任务enable, disable： services/task_store/service.go:860, handleUpdateTask。(通过http请求发送到kapacitord)
4. 任务delete： services/task_store/service.go:1399, handleDeleteTask。(通过http请求发送到kapacitord)
5. 当kapacitor强制终止，再恢复后，kapacitor会重启运行时的任务.
6. 当任务启动时，会通过edge、window等定义node；由TaskMaster启动任务，并fork相应的流。监控线程会启动，并在条件满足时触发。以alert任务为例：
   1. 所有任务的node流动开始于`node.go:163`: start函数
   2. alertNode创建在`alert.go:83` : newAlertNode函数
   3. alert处理在`alert.go:702`: 

### 断点：

```shell
alert.go:84
alert.go:702
alert.go:535
consumer.go:66
service.go:869
service.go:863
service.go:860
service.go:430
service.go:1930
service.go:1735
service.go:1656
service.go:1545
service.go:675
service.go:681
service.go:581
service.go:520
edge.go:57
edge.go:38
main.go:143
window.go:54
window.go:39
window.go:32
main.go:182
window.go:20
service.go:2020
service.go:2017
task_master.go:492
main.go:156
task.go:126
task.go:198
```



