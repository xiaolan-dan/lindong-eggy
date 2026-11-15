# -*- coding: utf-8 -*-
"""把 素材/轮换原图/ 里的原图裁成胶囊贴图，输出到 轮换图/。

胶囊宽高比是 556:44（约 12.6:1），所以每张图都按这个比例「居中裁一条」，
再缩到 1200px 宽存成 PNG（Tk 原生只认 PNG/GIF，JPG 放进去是读不出来的）。

用法：
    python 素材\make_photos.py
"""
import os
import shutil
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.environ.get("PHOTO_SRC") or os.path.join(BASE, "素材", "轮换原图")
OUT = os.environ.get("PHOTO_OUT") or os.path.join(BASE, "轮换图")
ASPECT_W, ASPECT_H = 556.0, 44.0     # 和 dynamic_island.py 里的胶囊比例一致
TARGET_W = 1200                      # 输出宽度，够 2x DPI 用

# 交给 System.Drawing 做高质量缩放（纯标准库的 Python 解不了 JPEG）
PS = r"""
param($src, $dst, $aspect, $tw)
Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap($src)
$w = $bmp.Width; $h = $bmp.Height
$ch = [int][Math]::Round($w / $aspect)
if ($ch -gt $h) { $ch = $h; $w2 = [int][Math]::Round($h * $aspect) } else { $w2 = $w }
if ($w2 -gt $w) { $w2 = $w }
if ($w2 -lt 2) { $w2 = 2 }
if ($ch -lt 2) { $ch = 2 }
$x0 = [int](($w - $w2) / 2)
$y0 = [int](($h - $ch) / 2)
$th = [int][Math]::Round($tw / $aspect)
$out = New-Object System.Drawing.Bitmap($tw, $th, [System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
$g = [System.Drawing.Graphics]::FromImage($out)
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
$g.DrawImage($bmp, (New-Object System.Drawing.Rectangle(0, 0, $tw, $th)), (New-Object System.Drawing.Rectangle($x0, $y0, $w2, $ch)), [System.Drawing.GraphicsUnit]::Pixel)
$out.Save($dst, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $out.Dispose(); $bmp.Dispose()
"{0} -> {1}x{2} (crop {3}x{4} @ {5},{6})" -f (Split-Path $src -Leaf), $tw, $th, $w2, $ch, $x0, $y0
"""


def main():
    if not os.path.isdir(SRC):
        print("没有原图目录：", SRC)
        return 1
    os.makedirs(OUT, exist_ok=True)
    names = sorted(n for n in os.listdir(SRC)
                   if n.lower().endswith((".jpg", ".jpeg", ".png")))
    if not names:
        print("原图目录是空的：", SRC)
        return 1

    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        print("找不到 pwsh / powershell，无法调用 System.Drawing")
        return 1
    script_path = os.path.join(SRC, "_crop.ps1")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(PS)

    aspect = ASPECT_W / ASPECT_H
    failed = 0
    for i, name in enumerate(names, 1):
        src = os.path.join(SRC, name)
        dst = os.path.join(OUT, "%02d.png" % i)
        r = subprocess.run([shell, "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-File", script_path, "-src", src, "-dst", dst,
                            "-aspect", "%.6f" % aspect, "-tw", str(TARGET_W)],
                           capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            failed += 1
            print("FAIL", name, (r.stdout or "").strip(), (r.stderr or "").strip()[:300])
        else:
            print((r.stdout or "").strip())
    try:
        os.remove(script_path)
    except OSError:
        pass
    print("完成 %d 张，失败 %d 张，输出目录：%s" % (len(names) - failed, failed, OUT))
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
