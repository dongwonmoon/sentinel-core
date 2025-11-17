from typing import List, Tuple

from langchain_core.documents import Document

from ...core.config import Settings
from ..embeddings.base import BaseEmbeddingModel
from .base import BaseVectorStore
from ...core.logger import get_logger

logger = get_logger(__name__)


class MilvusVectorStore(BaseVectorStore):
    """
    오픈 소스 벡터 데이터베이스인 Milvus를 사용하는 벡터 스토어 구현체입니다. (현재는 플레이스홀더)
    `BaseVectorStore` 추상 클래스를 상속받아, Milvus와의 통신을 위한
    구체적인 로직을 구현해야 합니다.
    """

    def __init__(self, settings: Settings, embedding_model: BaseEmbeddingModel):
        """
        MilvusVectorStore 클래스의 인스턴스를 초기화합니다.
        향후 Milvus 클라이언트 연결 및 컬렉션(Collection) 준비 로직이 여기에 구현되어야 합니다.

        Args:
            settings: Milvus 연결 정보(호스트, 포트 등)를 포함한 애플리케이션 설정 객체.
            embedding_model: 텍스트를 벡터로 변환하는 데 사용할 임베딩 모델 객체.
        """
        self._provider = "milvus"
        self.settings = settings
        self.embedding_model = embedding_model
        logger.warning(
            "MilvusVectorStore가 `create_vector_store` 팩토리에서 호출되었지만, 아직 구현되지 않았습니다."
        )
        # 향후 구현 예시:
        # from pymilvus import MilvusClient
        # self.client = MilvusClient(uri=settings.MILVUS_URI, token=settings.MILVUS_TOKEN)
        raise NotImplementedError(
            "MilvusVectorStore는 아직 구현되지 않았습니다. "
            "구현하려면 이 파일을 수정하고, 필요한 Milvus 연결 정보를 설정해야 합니다."
        )

    async def upsert_documents(
        self, documents_data: List[Dict[str, Any]]
    ) -> None:
        """
        문서와 그 벡터를 Milvus 컬렉션에 비동기적으로 추가하거나 업데이트합니다.
        """
        raise NotImplementedError(
            "MilvusVectorStore의 upsert_documents 메서드는 아직 구현되지 않았습니다."
        )

    async def search(
        self,
        query_embedding: List[float],
        allowed_groups: List[str],
        k: int = 4,
        doc_ids_filter: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Milvus에서 주어진 쿼리 임베딩과 유사한 문서를 비동기적으로 검색합니다.
        `allowed_groups`를 사용하여 접근 제어를 구현해야 합니다.
        """
        raise NotImplementedError(
            "MilvusVectorStore의 search 메서드는 아직 구현되지 않았습니다."
        )

    async def delete_documents(self, doc_ids: List[str]) -> int:
        """
        Milvus에서 주어진 문서 ID와 일치하는 모든 벡터를 삭제합니다.
        """
        raise NotImplementedError(
            "MilvusVectorStore의 delete_documents 메서드는 아직 구현되지 않았습니다."
        )
