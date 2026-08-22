"""通用递归/标题层级切分（T3）。

参考：rag_qa/edu_text_spliter/edu_chinese_recursive_text_splitter.py
元数据：team、system、version、last_updated、security_level 必填。
"""


class RecursiveSplitter:
    # TODO(T3 算法组): RecursiveCharacterTextSplitter + 标题层级切分。
    def split(self, documents):
        raise NotImplementedError
