import os
import time

influx = "http://localhost:8086/write?db=test"

i1 = [1, 1, 1, 1, 0, 1, 1, 1, 1, 0]
t = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
# t =  [0, 1, 2, 6, 5, 4, 3, 7, 8, 9]

one_day_nano = 86400 * 1e9
data_interval = 1

current_10 = int(time.time())
#秒数为0，方便查看
current_10 -= current_10%10
base_time = current_10*1e9 + 20*one_day_nano
for i, code_match in enumerate(i1):
    os.system('curl -i -XPOST %s --data-binary "ka,app=cmdb code_match=%d %d"'
              % (influx, code_match, base_time + data_interval * t[i] * 1e9))
    # os.system('curl -i -XPOST %s --data-binary "ka,app=cmdb code_match=%d"'
    #           % (influx, id))
    # print("time=%d" % (base_time + 5 * t[i] * 1e9))
    # time.sleep(1)

