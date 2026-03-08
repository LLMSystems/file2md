# doclayout_yolo labels
```bash
0 = 'title'
1 = 'plain text'
2 = 'abandon'
3 = 'figure'
4 = 'figure_caption'
5 = 'table'
6 = 'table_caption'
7 = 'table_footnote'
8 = 'isolate_formula'
9 = 'formula_caption'
```

## 將pdf轉成image
### 方法一
```python
from pdf2image import convert_from_path

pdf_path = "demo/pdfs/demo1.pdf"

images = convert_from_path(pdf_path, dpi=300)
folder = "output_images"
os.makedirs(folder, exist_ok=True)
for i, img in enumerate(images):
    img.save(f"{folder}/page_{i+1}.png", "PNG")
```

### 方法二
```python
# pip install pymupdf
import fitz

doc = fitz.open(pdf_path)
for i, page in enumerate(doc):
    pix = page.get_pixmap(dpi=300)
    os.makedirs("output_images2", exist_ok=True)
    pix.save(f"output_images2/page_{i+1}.png")
```

## 將MinerU數據轉成可訓練資料
```python
import os
from pathlib import Path

import cv2
from doclayout_yolo import YOLOv10

device = "cuda"

model = YOLOv10(
    "models/Layout/YOLO/doclayout_yolo_docstructbench_imgsz1280_2501.pt"
).to(device)

image_folder = Path("./output_images")
label_folder = Path("./labels")
label_folder.mkdir(parents=True, exist_ok=True)

images = sorted([str(p) for p in image_folder.glob("*.png")])

det_res = model.predict(
    images,
    imgsz=1280,
    conf=0.25,
    iou=0.45,
    verbose=False,
)

for image_path, result in zip(images, det_res):
    pred_boxes = result.boxes.cpu()
    image_name = Path(image_path).stem
    label_path = label_folder / f"{image_name}.txt"

    lines = []
    for d in pred_boxes:
        cls_id = int(d.cls)

        # d.xywhn shape usually = (1, 4)
        x_center, y_center, width, height = d.xywhn.squeeze().tolist()

        line = f"{cls_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"
        lines.append(line)

    with open(label_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

print("YOLO labels generated successfully.")
```

## 透過 labelImg 標註資料
在`./windows_v1.8.1/data/predefined_classes.txt`改成以下內容
```txt
title
plain text
abandon
figure
figure_caption
table
table_caption
table_footnote
isolate_formula
formula_caption
```