from typing import List, Tuple

from langchain_core.documents import Document

from ..config import Settings
from ..embeddings.base import BaseEmbeddingModel
from .base import BaseVectorStore
from ..logger import get_logger

logger = get_logger(__name__)


class MilvusVectorStore(BaseVectorStore):
    """
    Milvus를 사용하는 벡터 스토어 구현체입니다. (플레이스홀더)
    BaseVectorStore 추상 클래스를 상속받습니다.
    """

    def __init__(self, settings: Settings, embedding_model: BaseEmbeddingModel):
        """
        MilvusVectorStore 클래스의 인스턴스를 초기화합니다.
        (향후 Milvus 연결 로직이 여기에 구현될 것입니다.)

        Args:
            settings: 애플리케이션의 설정을 담고 있는 Settings 객체입니다.
            embedding_model: 텍스트를 벡터로 변환하는 데 사용할 임베딩 모델 객체입니다.
        """
        self.settings = settings
        self.embedding_model = embedding_model
        logger.warning(
            "MilvusVectorStore가 초기화되었지만, 아직 구현되지 않았습니다."
        )
        # 예: self.client = MilvusClient(host=settings.MILVUS_HOST, port=settings.MILVUS_PORT)
        raise NotImplementedError(
            "MilvusVectorStore는 아직 구현되지 않았습니다."
        )

    async def upsert_documents(
        self,
        documents: List[Document],
        permission_groups: List[str],
    ) -> None:
        """
        문서를 Milvus 벡터 스토어에 비동기적으로 추가하거나 업데이트합니다.
        """
        raise NotImplementedError(
            "MilvusVectorStore의 upsert_documents가 구현되지 않았습니다."
        )

    async def search(
        self,
        query: str,
        allowed_groups: List[str],
        k: int = 4,
    ) -> List[Tuple[Document, float]]:
        """
        Milvus에서 주어진 쿼리와 유사한 문서를 비동기적으로 검색합니다.
        """
        raise NotImplementedError(
            "MilvusVectorStore의 search가 구현되지 않았습니다."
        )
