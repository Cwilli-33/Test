"""Database models for tracking processed images and extractions."""
from sqlalchemy import Column, String, Float, DateTime, Integer, Text, Boolean, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class ProcessedImage(Base):
    """Track processed images to prevent duplicate processing."""
    
    __tablename__ = "processed_images"
    
    fingerprint = Column(String(255), primary_key=True, index=True)
    file_id = Column(String(255), nullable=False)
    message_id = Column(Integer, nullable=False)
    chat_id = Column(String(255), nullable=False)
    contact_id = Column(String(255), nullable=True, index=True)
    action = Column(String(50), nullable=True)
    processed_at = Column(DateTime, default=func.now(), nullable=False)
    confidence = Column(Float, nullable=True)
    document_type = Column(String(50), nullable=True)
    
    __table_args__ = (
        Index('idx_processed_at', 'processed_at'),
        Index('idx_contact_action', 'contact_id', 'action'),
    )


class LeadExtraction(Base):
    """Store extraction results for audit trail and analytics."""
    
    __tablename__ = "lead_extractions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    fingerprint = Column(String(255), nullable=False, index=True)
    contact_id = Column(String(255), nullable=False, index=True)
    action = Column(String(50), nullable=False)
    
    # Identifiers used for matching
    ein = Column(String(50), nullable=True, index=True)
    business_name = Column(String(255), nullable=True)
    owner_phone = Column(String(50), nullable=True, index=True)
    owner_email = Column(String(255), nullable=True, index=True)
    
    # Matching metadata
    match_method = Column(String(50), nullable=True)
    match_confidence = Column(Integer, nullable=True)
    
    # Extraction quality
    extraction_confidence = Column(Float, nullable=False)
    document_type = Column(String(50), nullable=True)
    extraction_notes = Column(Text, nullable=True)
    
    # Raw data (for debugging)
    raw_extracted_data = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    __table_args__ = (
        Index('idx_created_at', 'created_at'),
        Index('idx_ein_business', 'ein', 'business_name'),
    )
