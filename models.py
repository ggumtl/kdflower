from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from database import Base

class Category(Base):
    __tablename__ = "category"

    idx = Column(Integer, primary_key=True, autoincrement=True, index=True)
    name = Column(String, nullable=False)
    order_no = Column(Integer, default=0, index=True)  # 순서 정렬용 컬럼

    flowers = relationship("FlowerList", back_populates="category_rel")

class FlowerList(Base):
    __tablename__ = "flower_list"

    idx = Column(Integer, primary_key=True, autoincrement=True, index=True)
    update_date = Column(DateTime, server_default=func.now(), onupdate=func.now())
    category = Column(Integer, ForeignKey("category.idx", ondelete="SET NULL"), nullable=True)
    name = Column(String, nullable=False)
    name2 = Column(String, nullable=True)
    color = Column(String, nullable=True)
    price = Column(Integer, default=0)
    img_path = Column(String, nullable=True)
    view = Column(Integer, default=1)

    category_rel = relationship("Category", back_populates="flowers")