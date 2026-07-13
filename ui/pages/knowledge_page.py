from PySide6.QtWidgets import QLabel, QListWidget, QVBoxLayout, QWidget


class KnowledgePage(QWidget):
    namespaces = ("shared", "moisture", "boiling", "after_sales")
    message = "模拟知识库：真实检索将在公共服务阶段接入"

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("page-knowledge")
        self.setAccessibleName("知识库")

        layout = QVBoxLayout(self)
        title = QLabel("知识库")
        title.setProperty("heading", True)
        self.message_label = QLabel(self.message)
        self.message_label.setAccessibleName("知识库接入状态")
        self.namespace_list = QListWidget()
        self.namespace_list.setAccessibleName("知识库命名空间")
        self.namespace_list.addItems(self.namespaces)
        layout.addWidget(title)
        layout.addWidget(self.message_label)
        layout.addWidget(self.namespace_list)
        layout.addStretch()

    def lookup(self, namespace: str, _query: str) -> list[object]:
        if namespace not in self.namespaces:
            raise ValueError(f"unknown knowledge namespace: {namespace}")
        return []
