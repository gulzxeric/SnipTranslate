from pathlib import Path
import sys
from time import perf_counter
import gc
import numpy as np
from PIL import Image
from rapidocr import RapidOCR

pixels = np.asarray(Image.open(sys.argv[1]).convert('RGB'))[:, :, ::-1].copy()
for size, threads, batch in [(None, 2, 6), (1280, 4, 1), (960, 4, 1), (1280, 4, 2)]:
    params = {'Global.use_cls': False, 'Global.log_level': 'warning',
              'EngineConfig.onnxruntime.intra_op_num_threads': threads,
              'EngineConfig.onnxruntime.inter_op_num_threads': 1, 'Rec.rec_batch_num': batch}
    if size:
        params.update({'Det.limit_type': 'max', 'Det.limit_side_len': size})
    engine = RapidOCR(params=params)
    for index in range(2):
        started = perf_counter()
        result = engine(pixels, use_cls=False)
        print((size, threads, batch), index, round(perf_counter()-started, 3), result.txts, flush=True)
    del engine
    gc.collect()
