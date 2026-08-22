"""PDF 解析器（T2）：pymupdf，保留代码块结构标记。"""


class PDFLoader:
    # TODO(T2 数据组): 输出 Document(page_content, metadata={source, page, doc_type})
    def load(self, file_path: str):
        raise NotImplementedError
