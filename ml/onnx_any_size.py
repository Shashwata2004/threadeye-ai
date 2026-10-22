"""Free the height and width of an exported ThreadEye ONNX model, so a line-scan strip runs in one pass.

    uv run --no-project --with onnx python ml/onnx_any_size.py data/model/threadeye_s.onnx

YOLOX is fully convolutional and the export leaves decoding out of the graph, so only the declared shapes
pin the input to 640 x 640: this rewrites them (weights untouched) and drops the stored intermediate shapes.
Models exported by ml/kaggle/train.py after 2026-10-22 are already free. Writes the file in place.
"""

import sys

import onnx

path = sys.argv[1]
m = onnx.load(path)
dims = m.graph.input[0].type.tensor_type.shape.dim
for i, name in ((0, "batch"), (2, "height"), (3, "width")):
    dims[i].dim_param = name
out = m.graph.output[0].type.tensor_type.shape.dim
out[0].dim_param, out[1].dim_param = "batch", "anchors"
del m.graph.value_info[:]
onnx.checker.check_model(m)
onnx.save(m, path)
print(f"{path}: input {[d.dim_param or d.dim_value for d in dims]}")
