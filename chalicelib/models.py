import enum
import logging
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, backref
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)

Base = declarative_base()


class StatusEnum(enum.Enum):
    pending = 1
    processing = 2
    signed = 3
    executed = 4


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(80), nullable=False)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text)
    expires = Column(DateTime)

    def __repr__(self):
        return "<User %r>" % self.username


class Lease(Base):
    __tablename__ = "leases"

    id = Column(Integer, primary_key=True)
    bluemoon_id = Column(Integer)
    unit_number = Column(String(15))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", backref=backref("leases", lazy=True))

    def __repr__(self):
        return "<Lease %r>" % self.unit_number


class LeaseEsignature(Base):
    __tablename__ = "lease_esignatures"

    id = Column(Integer, primary_key=True)
    bluemoon_id = Column(Integer)
    status = Column(Enum(StatusEnum), default=StatusEnum.pending)
    data = Column(JSON)
    lease_id = Column(Integer, ForeignKey("leases.id"), nullable=False)
    lease = relationship("Lease", backref=backref("esignatures", lazy=True))

    def __repr__(self):
        return "<LeaseEsignature %r>" % self.id

    def transition_status(self, signers_data):
        """Determine status of esignatures based on signers data."""
        # As this is Bluemoon logic and there are other possible
        # statuses such as expired. A ticket has been created to
        # include the status on the object
        signers = 0
        signed = 0
        owner = False
        for signer in signers_data:
            if signer["identifier"] == "owner":
                owner = signer["completed"]
                continue

            signers += 1
            if signer["completed"]:
                signed += 1

        if owner:
            self.status = StatusEnum.executed
        elif signers == signed:
            self.status = StatusEnum.signed
        elif signers:
            self.status = StatusEnum.processing
        else:
            self.status = StatusEnum.pending
