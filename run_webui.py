#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Hommey 商旅助手 - 新 Web 界面启动入口
"""
import os
import sys
import logging

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

import uvicorn

if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════╗
    ║     Hommey 商旅助手 - Web 界面             ║
    ║     http://localhost:8000                  ║
    ╚═══════════════════════════════════════════╝
    """)
    uvicorn.run(
        "webui_new.server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
