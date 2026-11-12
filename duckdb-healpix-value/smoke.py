import sitecustomize
from bench import *
for case,arms in [(1,['sql','shim']),(2,['sql','shim']),(3,['ranges','shim']),(4,['sql','python','shim','geography']),(7,['python','shim']),(8,['sql','shim']),(9,['sql','shim']),(10,['sql','shim'])]:
 for arm in arms:
  start=time.perf_counter()
  try:
   a=execute(case,1000000,arm); print(case,arm,len(a),time.perf_counter()-start,flush=True)
  except Exception as e:print(case,arm,repr(e),flush=True)
