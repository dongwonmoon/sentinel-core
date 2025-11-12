"""create initial tables for documents and chunks

Revision ID: 711d0b8478e2
Revises: 
Create Date: 2025-11-12 12:17:44.354443

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql



# revision identifiers, used by Alembic.
revision: str = '711d0b8478e2'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'documents',
        sa.Column('doc_id', sa.TEXT(), nullable=False),
        sa.Column('source_type', sa.VARCHAR(length=100), nullable=True),
        sa.Column('permission_groups', postgresql.ARRAY(sa.TEXT()), server_default=sa.text("ARRAY['all_users']"), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'"), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('doc_id')
    )
    op.create_index('idx_documents_permission_groups', 'documents', ['permission_groups'], unique=False, postgresql_using='gin')

    # 1. pgvector 확장이 활성화되었는지 확인 (DB에서 미리 실행)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. 'document_chunks' 테이블 생성
    op.create_table(
        'document_chunks',
        sa.Column('chunk_id', sa.BIGINT(), nullable=False),
        sa.Column('doc_id', sa.TEXT(), nullable=False),
        sa.Column('chunk_text', sa.TEXT(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'"), nullable=True),
        sa.ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('chunk_id')
    )
    
    # 3. 'vector' 컬럼 추가
    op.execute("ALTER TABLE document_chunks ADD COLUMN embedding vector(768)")
    
    # 4. 인덱스 생성
    op.create_index('idx_document_chunks_doc_id', 'document_chunks', ['doc_id'], unique=False)
    
    # 5. 벡터 인덱스 생성 (HNSW)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw 
        ON document_chunks 
        USING hnsw (embedding vector_l2_ops);
    """)


def downgrade() -> None:
    # ### 'upgrade'의 반대 순서로 테이블 삭제 ###
    op.execute("DROP INDEX IF EXISTS idx_chunks_embedding_hnsw;")
    op.drop_table('document_chunks')
    op.drop_table('documents')
    op.execute("DROP EXTENSION IF EXISTS vector;")
