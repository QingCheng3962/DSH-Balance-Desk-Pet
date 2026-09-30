# -*- coding: utf-8 -*-
"""双击即启动（.pyw 走 pythonw，无控制台窗口）。

和 dsh_whale_pet.py 等价，只是省得处理命令行。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dsh_whale_pet import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
