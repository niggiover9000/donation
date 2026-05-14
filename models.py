from sqlalchemy import Column, Integer, String, Float, Boolean
from database import Base

class Bid(Base):
    __tablename__ = "bids"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    amount = Column(Float)
    token = Column(String, unique=True, index=True)
    organization = Column(String, default="")

class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    min_bid = Column(Float, default=10.0)
    org1 = Column(String, default="")
    org2 = Column(String, default="")
    org3 = Column(String, default="")
    deadline = Column(String, default="")
    feature_ticker = Column(Boolean, default=False)
    feature_leaderboard = Column(Boolean, default=False)
    feature_goal = Column(Boolean, default=False)
    goal_amount = Column(Float, default=1000.0)
    paypal_link = Column(String, default="https://paypal.me/")
