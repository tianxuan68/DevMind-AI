"""通用日志模块（基线）。

T14 的审计日志接口请实现到 internal_kb_qa/core/audit_logger.py；
本模块仅保留基础结构化日志能力。
参考基线：E:/study_project/Itcast_qa_system/base/logger.py
"""
import logging
import sys

logger = logging.getLogger("devmind-ai")
logger.setLevel(logging.INFO)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
logger.addHandler(handler)
